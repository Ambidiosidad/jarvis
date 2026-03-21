"""
J.A.R.V.I.S. Brain v2.1
==========================
Orquestador con:
- Chain-of-thought prompting
- Estado emocional AUTOMÁTICO (no depende del LLM)
- Aprendizaje de patrones
- Auto-resumen de conversaciones
- Detección automática de hechos personales
"""
import os, json, re, asyncio, unicodedata
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from personality import build_system_prompt
from tools import tools_prompt
from emotion_analyzer import analyze_conversation_sentiment

app = FastAPI(title="Jarvis Brain v2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

OLLAMA = os.getenv("OLLAMA_URL", "http://nomad_ollama:11434")
MEMORY = os.getenv("MEMORY_URL", "http://jarvis-memory:8401")
VOICE = os.getenv("VOICE_URL", "http://jarvis-voice:8402")
MOTORS = os.getenv("MOTORS_URL", "http://jarvis-motors:8404")
MODEL = os.getenv("MODEL_NAME", "gemma3:1b")
TOOLS_TEXT = tools_prompt()
ASCII_ONLY = os.getenv("JARVIS_ASCII_ONLY", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

_message_count = 0
_SUMMARIZE_EVERY = 10


# ═══════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════

async def _get_memory() -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/context")
            return r.json().get("context", "") if r.status_code == 200 else ""
    except Exception:
        return ""


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
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/emotions", json=state)
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


async def _call_llm(prompt: str, system: str,
                    max_tokens: int = 512) -> str:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_ctx": 4096,
                "num_predict": max_tokens,
            }
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
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


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
    (r"(?:me llamo|mi nombre es|soy)\s+(\w+)", "El usuario se llama {}"),
    (r"(?:vivo en|soy de)\s+(.+?)(?:\.|,|$)", "El usuario vive en {}"),
    (r"(?:trabajo en|trabajo como|soy)\s+(.+?)(?:\.|,|$)", "El usuario trabaja como/en {}"),
    (r"(?:tengo)\s+(\d+)\s+años", "El usuario tiene {} años"),
    (r"(?:me gusta|me encanta|me apasiona)\s+(.+?)(?:\.|,|$)", "Al usuario le gusta {}"),
]


async def _auto_extract_facts(user_msg: str):
    """Extract personal facts from user message automatically."""
    lower = user_msg.lower()
    for pattern, template in _FACT_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            fact = template.format(match.group(1).strip())
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
            f"{m['role']}: {m['content'][:200]}" for m in messages
        )

        result = await _call_llm(
            f"Resume esta conversación en 2-3 frases breves. "
            f"Incluye qué se discutió y qué es importante. "
            f"Al final pon TEMAS: seguido de los temas principales "
            f"separados por comas.\n\n{conversation}",
            "Genera resúmenes concisos. Solo el resumen, sin explicaciones.",
            max_tokens=150
        )

        lines = result.strip().split("\n")
        topics_line = ""
        summary_lines = []
        for line in lines:
            if line.upper().startswith("TEMAS:"):
                topics_line = line.split(":", 1)[1].strip()
            else:
                summary_lines.append(line)

        summary_text = " ".join(summary_lines).strip()
        topics = [t.strip() for t in topics_line.split(",") if t.strip()] \
            if topics_line else ["conversación"]

        if summary_text:
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

    # 2. Auto-extract facts from user message
    await _auto_extract_facts(user_msg)

    # 3. Get current emotional state
    current_emotion = await _get_current_emotion()

    # 4. Get memory context
    memory = await _get_memory()

    # 5. Build emotional context for prompt
    emotion_text = (
        f"## Tu estado emocional actual:\n"
        f"Humor: {current_emotion.get('mood', 'neutral')} | "
        f"Energía: {current_emotion.get('energy', 0.5):.1f} | "
        f"Paciencia: {current_emotion.get('patience', 0.8):.1f} | "
        f"Vínculo: {current_emotion.get('bond', 0.1):.2f}\n"
        f"Adapta tu tono: si curious→haz preguntas, "
        f"si happy→muestra entusiasmo, si empathetic→sé cálido, "
        f"si thoughtful→sé reflexivo."
    )

    # 6. Build system prompt
    system = build_system_prompt(TOOLS_TEXT, memory, emotion_text)

    # 7. Call LLM
    raw = await _call_llm(user_msg, system)

    # 8. Save response
    await _save_msg("assistant", raw)

    # 9. Execute any tool calls the LLM generated
    tool_calls = _extract_all_tools(raw)
    if tool_calls:
        await _exec_tools(tool_calls)

    # 10. AUTOMATIC emotion update (doesn't depend on LLM)
    new_emotion = analyze_conversation_sentiment(
        user_msg, raw, current_emotion
    )
    await _update_emotion(new_emotion)

    # 11. Auto-summarize periodically
    if _message_count >= _SUMMARIZE_EVERY:
        _message_count = 0
        asyncio.create_task(_auto_summarize())

    return {
        "text": _out(_clean(raw)),
        "tools": tool_calls,
        "emotion": _sanitize_emotion(new_emotion),
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
        "audio_url": f"{VOICE}/tts?text={response_text[:300]}",
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
    return {
        "service": "jarvis-brain", "version": "2.1",
        "model": MODEL, "emotion": emotion, "memory": stats,
        "messages_until_summary": max(0, _SUMMARIZE_EVERY - _message_count)
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL,
            "service": "jarvis-brain", "version": "2.1",
            "ascii_only": ASCII_ONLY}
