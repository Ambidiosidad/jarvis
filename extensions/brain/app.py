"""
J.A.R.V.I.S. Brain v3
========================
Mejoras sobre v2.1:
- Multi-turno: inyecta últimos mensajes como contexto conversacional
- Clasificación de intención: prompt especializado por tipo de pregunta
- Prompts optimizados para modelos pequeños (1B-3B)
- Todo lo anterior: emociones automáticas, auto-resumen, extracción de hechos
"""
import os, json, re, asyncio, unicodedata
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from personality import build_system_prompt
from tools import tools_prompt
from emotion_analyzer import analyze_conversation_sentiment
from intent_classifier import classify_intent

app = FastAPI(title="Jarvis Brain v3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

OLLAMA = os.getenv("OLLAMA_URL", "http://nomad_ollama:11434")
MEMORY = os.getenv("MEMORY_URL", "http://jarvis-memory:8401")
VOICE = os.getenv("VOICE_URL", "http://jarvis-voice:8402")
MOTORS = os.getenv("MOTORS_URL", "http://jarvis-motors:8404")
MODEL = os.getenv("MODEL_NAME", "gemma3:1b")
ASCII_ONLY = os.getenv("JARVIS_ASCII_ONLY", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

# How many previous messages to include as conversation context
CONTEXT_WINDOW = int(os.getenv("JARVIS_CONTEXT_MESSAGES", "6"))

_message_count = 0
_SUMMARIZE_EVERY = 10


# ═══════════════════════════════════════
#  Memory & emotion helpers
# ═══════════════════════════════════════

async def _get_memory_context() -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/context")
            return r.json().get("context", "") if r.status_code == 200 else ""
    except Exception:
        return ""


async def _get_recent_messages() -> list[dict]:
    """Get recent conversation messages for multi-turn context."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/messages/recent",
                            params={"limit": CONTEXT_WINDOW})
            return r.json().get("messages", []) if r.status_code == 200 else []
    except Exception:
        return []


async def _get_current_emotion() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/emotions/current")
            return r.json() if r.status_code == 200 else {}
    except Exception:
        return {"mood": "neutral", "energy": 0.5, "patience": 0.8,
                "bond": 0.1, "reason": "default"}


async def _save_msg(role: str, content: str):
    try:
        content_to_store = _to_ascii(content) if ASCII_ONLY else content
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/messages",
                         json={"role": role, "content": content_to_store})
    except Exception:
        pass


async def _save_fact(fact: str):
    try:
        fact_to_store = _to_ascii(fact) if ASCII_ONLY else fact
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/facts", params={"fact": fact_to_store})
    except Exception:
        pass


async def _update_emotion(state: dict):
    try:
        state_to_store = _sanitize_emotion(state) if ASCII_ONLY else state
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/emotions", json=state_to_store)
    except Exception:
        pass


async def _learn_pattern(pattern_type: str, description: str):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/patterns",
                         params={"pattern_type": pattern_type,
                                 "description": description})
    except Exception:
        pass


async def _save_summary(summary: str, topics: list):
    try:
        summary_to_store = _to_ascii(summary) if ASCII_ONLY else summary
        topics_to_store = [_to_ascii(t) for t in topics] if ASCII_ONLY else topics
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/summaries",
                         json={"summary": summary_to_store, "topics": topics_to_store})
    except Exception:
        pass


# ═══════════════════════════════════════
#  LLM call with multi-turn context
# ═══════════════════════════════════════

def _to_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _out(text: str) -> str:
    return _to_ascii(text) if ASCII_ONLY else text


def _sanitize_emotion(emotion: dict) -> dict:
    if not ASCII_ONLY:
        return emotion
    safe = {}
    for key, value in (emotion or {}).items():
        safe[key] = _to_ascii(value) if isinstance(value, str) else value
    return safe


async def _call_llm_chat(user_msg: str, system: str,
                         history: list[dict],
                         max_tokens: int = 512) -> str:
    """
    Call Ollama with chat API (multi-turn) instead of generate API.
    This gives the LLM context of the recent conversation.
    """
    messages = [{"role": "system", "content": system}]

    # Add conversation history
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"][:500]  # Truncate to save context space
        })

    # Add current user message
    messages.append({"role": "user", "content": user_msg})

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OLLAMA}/api/chat", json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_ctx": 4096,
                "num_predict": max_tokens,
            }
        })
        r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()


async def _call_llm_simple(prompt: str, system: str,
                           max_tokens: int = 150) -> str:
    """Simple generate call for internal tasks (summarization)."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 2048,
                        "num_predict": max_tokens}
        })
        r.raise_for_status()
    return r.json().get("response", "").strip()


# ═══════════════════════════════════════
#  Tool parsing and execution
# ═══════════════════════════════════════

def _extract_all_tools(text: str) -> list[dict]:
    tools = []
    for match in re.finditer(r'\{[^{}]*"tool"[^{}]*\}', text):
        try:
            parsed = json.loads(match.group())
            if "tool" in parsed:
                tools.append(parsed)
        except json.JSONDecodeError:
            continue
    return tools


def _clean(text: str) -> str:
    cleaned = re.sub(r'\{[^{}]*"tool"[^{}]*\}', '', text)
    cleaned = re.sub(r'```json\s*```', '', cleaned)
    cleaned = re.sub(r'```\s*```', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


async def _exec_tools(tool_calls: list[dict]):
    for tc in tool_calls:
        tool = tc.get("tool")
        params = tc.get("params", {})

        if tool == "remember":
            await _save_fact(params.get("fact", ""))

        elif tool == "move":
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    d = params.get("direction", "stop")
                    await c.post(f"{MOTORS}/move/{d}", params={
                        "duration": params.get("duration", 1.0),
                        "speed": params.get("speed", 0.7)
                    })
            except Exception:
                pass

        elif tool == "learn_pattern":
            await _learn_pattern(
                params.get("type", "preference"),
                params.get("description", ""))


# ═══════════════════════════════════════
#  Automatic fact extraction
# ═══════════════════════════════════════

_FACT_PATTERNS = [
    (r"(?:me llamo|mi nombre es)\s+([A-Z]\w+)", "El usuario se llama {}"),
    (r"(?:vivo en|soy de)\s+([A-Z]\w+(?:\s+\w+)?)", "El usuario vive en {}"),
    (r"(?:trabajo en|trabajo como)\s+(.+?)(?:\.|,|$)", "El usuario trabaja en/como {}"),
    (r"(?:tengo)\s+(\d+)\s+años", "El usuario tiene {} años"),
    (r"(?:me gusta|me encanta|me apasiona)\s+(.+?)(?:\.|,|y\s|$)", "Al usuario le gusta {}"),
    (r"(?:my name is)\s+(\w+)", "El usuario se llama {}"),
    (r"(?:i live in)\s+(\w+(?:\s+\w+)?)", "El usuario vive en {}"),
]


async def _auto_extract_facts(user_msg: str):
    for pattern, template in _FACT_PATTERNS:
        match = re.search(pattern, user_msg, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if len(value) > 2:  # Avoid single-char matches
                fact = template.format(value)
                await _save_fact(fact)


# ═══════════════════════════════════════
#  Auto-summarization
# ═══════════════════════════════════════

async def _auto_summarize():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{MEMORY}/messages/recent",
                            params={"limit": 20})
            if r.status_code != 200:
                return
            messages = r.json().get("messages", [])

        if len(messages) < 6:
            return

        conversation = "\n".join(
            f"{m['role']}: {m['content'][:150]}" for m in messages
        )

        result = await _call_llm_simple(
            f"Resume en 2 frases qué se discutió. "
            f"Al final escribe TEMAS: tema1, tema2\n\n{conversation}",
            "Genera resúmenes breves. Solo el resumen."
        )

        lines = result.strip().split("\n")
        topics_line = ""
        summary_lines = []
        for line in lines:
            if "TEMAS:" in line.upper():
                topics_line = line.split(":", 1)[1].strip()
            else:
                summary_lines.append(line)

        summary_text = " ".join(summary_lines).strip()
        topics = [t.strip() for t in topics_line.split(",") if t.strip()] \
            if topics_line else ["conversación"]

        if summary_text and len(summary_text) > 10:
            await _save_summary(summary_text, topics)

    except Exception as e:
        print(f"[BRAIN] Auto-summarize error: {e}")


# ═══════════════════════════════════════
#  Main thinking pipeline
# ═══════════════════════════════════════

async def _think(user_msg: str) -> dict:
    global _message_count

    # 1. Save user message
    await _save_msg("user", user_msg)
    _message_count += 1

    # 2. Auto-extract facts
    await _auto_extract_facts(user_msg)

    # 3. Classify intent → select specialized prompt
    intent = classify_intent(user_msg)

    # 4. Get emotional state
    current_emotion = await _get_current_emotion()
    emotion_text = (
        f"Tu humor: {current_emotion.get('mood', 'neutral')}. "
        f"Vínculo con usuario: {current_emotion.get('bond', 0.1):.1f}/1.0."
    )

    # 5. Get memory context (facts + summaries)
    memory = await _get_memory_context()

    # 6. Build specialized system prompt
    system = build_system_prompt(intent, memory, emotion_text)

    # 7. Get recent conversation history for multi-turn
    history = await _get_recent_messages()

    # 8. Call LLM with full context
    raw = await _call_llm_chat(user_msg, system, history)

    # 9. Save response
    await _save_msg("assistant", raw)

    # 10. Execute tool calls
    tool_calls = _extract_all_tools(raw)
    if tool_calls:
        await _exec_tools(tool_calls)

    # 11. Update emotion automatically
    new_emotion = analyze_conversation_sentiment(
        user_msg, raw, current_emotion
    )
    await _update_emotion(new_emotion)

    # 12. Auto-summarize periodically
    if _message_count >= _SUMMARIZE_EVERY:
        _message_count = 0
        asyncio.create_task(_auto_summarize())

    return {
        "text": _out(_clean(raw)),
        "tools": tool_calls,
        "emotion": _sanitize_emotion(new_emotion),
        "intent": intent,
    }


# ═══════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════

@app.post("/chat")
async def chat(message: str):
    result = await _think(message)
    return {
        "response": _out(result["text"]),
        "tools_executed": result["tools"],
        "emotion": _sanitize_emotion(result["emotion"]),
        "intent": result["intent"],
    }


@app.post("/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    async with httpx.AsyncClient(timeout=60) as c:
        files = {"audio": (audio.filename, await audio.read(),
                           audio.content_type)}
        r = await c.post(f"{VOICE}/stt", files=files)
        user_text = r.json().get("text", "")

    if not user_text:
        return {"transcription": "", "response": "No te he entendido."}

    result = await _think(user_text)
    response_text = _out(result["text"])

    return {
        "transcription": _out(user_text),
        "response": response_text,
        "tools_executed": result["tools"],
        "emotion": _sanitize_emotion(result["emotion"]),
        "intent": result["intent"],
        "audio_url": f"{VOICE}/tts?text={response_text[:300]}"
    }


@app.get("/status")
async def status():
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            emotion = (await c.get(f"{MEMORY}/emotions/current")).json()
            stats = (await c.get(f"{MEMORY}/stats")).json()
    except Exception:
        emotion = {"mood": "unknown"}
        stats = {}
    emotion = _sanitize_emotion(emotion)
    return {
        "service": "jarvis-brain", "version": "3.0",
        "model": MODEL, "emotion": emotion, "memory": stats,
        "context_window": CONTEXT_WINDOW,
        "messages_until_summary": max(0, _SUMMARIZE_EVERY - _message_count)
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL,
            "service": "jarvis-brain", "version": "3.0",
            "ascii_only": ASCII_ONLY}
