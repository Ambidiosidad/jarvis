"""
J.A.R.V.I.S. Brain v2
========================
Orquestador con:
- Chain-of-thought prompting
- Estado emocional persistente
- Aprendizaje de patrones
- Auto-resumen de conversaciones
"""
import os, json, re, unicodedata
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from personality import build_system_prompt
from tools import tools_prompt

app = FastAPI(title="Jarvis Brain v2")
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

# Counter for auto-summarization (every N messages)
_message_count = 0
_SUMMARIZE_EVERY = 10  # Summarize every 10 user messages


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


async def _get_emotion_text() -> str:
    """Get formatted emotional state for prompt injection."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/emotions/current")
            if r.status_code == 200:
                e = r.json()
                return (
                    f"## Tu estado emocional actual:\n"
                    f"Humor: {e['mood']} | Energía: {e['energy']:.1f} | "
                    f"Paciencia: {e['patience']:.1f} | "
                    f"Vínculo: {e['bond']:.1f}\n"
                    f"({e['reason']})\n"
                    f"Adapta tu tono a este estado."
                )
    except Exception:
        pass
    return ""


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
            await c.post(f"{MEMORY}/facts",
                         params={"fact": fact_to_store})
    except Exception:
        pass


async def _update_emotion(mood: str, energy: float, patience: float,
                          bond: float, reason: str):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/emotions", json={
                "mood": mood,
                "energy": min(1.0, max(0.0, energy)),
                "patience": min(1.0, max(0.0, patience)),
                "bond": min(1.0, max(0.0, bond)),
                "reason": reason
            })
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
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/summaries",
                         json={"summary": summary, "topics": topics})
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


def _extract_all_tools(text: str) -> list[dict]:
    """Extract ALL JSON tool calls from the response."""
    tools = []
    # Find all JSON-like blocks
    for match in re.finditer(r'\{[^{}]*"tool"[^{}]*\}', text):
        try:
            parsed = json.loads(match.group())
            if "tool" in parsed:
                tools.append(parsed)
        except json.JSONDecodeError:
            continue
    return tools


def _clean(text: str) -> str:
    """Remove all JSON tool blocks from visible text."""
    cleaned = re.sub(r'\{[^{}]*"tool"[^{}]*\}', '', text)
    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _to_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _out(text: str) -> str:
    return _to_ascii(text) if ASCII_ONLY else text


async def _exec_tools(tool_calls: list[dict]):
    """Execute all tool calls from the response."""
    for tc in tool_calls:
        tool = tc.get("tool")
        params = tc.get("params", {})

        if tool == "remember":
            await _save_fact(params.get("fact", ""))

        elif tool == "update_emotion":
            await _update_emotion(
                mood=params.get("mood", "neutral"),
                energy=params.get("energy", 0.5),
                patience=params.get("patience", 0.8),
                bond=params.get("bond", 0.1),
                reason=params.get("reason", "")
            )

        elif tool == "learn_pattern":
            await _learn_pattern(
                pattern_type=params.get("type", "preference"),
                description=params.get("description", "")
            )

        elif tool == "summarize_conversation":
            await _save_summary(
                summary=params.get("summary", ""),
                topics=params.get("topics", [])
            )

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


async def _auto_summarize():
    """Ask the LLM to summarize recent conversation for long-term memory."""
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
            f"{m['role']}: {m['content']}" for m in messages
        )

        summary_prompt = (
            f"Resume esta conversación en 2-3 frases. "
            f"Incluye: qué se discutió, qué aprendiste del usuario, "
            f"y qué fue importante.\n\n{conversation}"
        )

        summary_system = (
            "Eres un asistente que genera resúmenes concisos. "
            "Responde SOLO con el resumen, sin explicaciones. "
            "Incluye al final una línea con los temas principales "
            "separados por comas, precedidos por 'TEMAS:'"
        )

        result = await _call_llm(summary_prompt, summary_system,
                                 max_tokens=200)

        # Parse summary and topics
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
            if topics_line else ["conversación general"]

        if summary_text:
            await _save_summary(summary_text, topics)

    except Exception as e:
        print(f"[BRAIN] Auto-summarize error: {e}")


# ═══════════════════════════════════════
#  Main thinking pipeline
# ═══════════════════════════════════════

async def _think(user_msg: str) -> dict:
    """Full cognitive pipeline: memory → emotion → LLM → tools → response."""
    global _message_count

    # 1. Save user message
    await _save_msg("user", user_msg)
    _message_count += 1

    # 2. Get memory context + emotional state
    memory = await _get_memory()
    emotion_text = await _get_emotion_text()

    # 3. Build system prompt with everything
    system = build_system_prompt(TOOLS_TEXT, memory, emotion_text)

    # 4. Call LLM
    raw = await _call_llm(user_msg, system)

    # 5. Save assistant response
    await _save_msg("assistant", raw)

    # 6. Extract and execute ALL tool calls
    tool_calls = _extract_all_tools(raw)
    if tool_calls:
        await _exec_tools(tool_calls)

    # 7. Auto-summarize every N messages
    if _message_count >= _SUMMARIZE_EVERY:
        _message_count = 0
        # Run in background (don't block response)
        import asyncio
        asyncio.create_task(_auto_summarize())

    return {"text": _out(_clean(raw)), "tools": tool_calls}


# ═══════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════

@app.post("/chat")
async def chat(message: str):
    """Chat por texto — endpoint principal."""
    result = await _think(message)
    return {
        "response": _out(result["text"]),
        "tools_executed": result["tools"]
    }


@app.post("/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    """Chat por voz: audio → STT → LLM → respuesta."""
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
        "audio_url": f"{VOICE}/tts?text={response_text[:300]}"
    }


@app.get("/status")
async def status():
    """Full status with emotional state."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            emotion = (await c.get(f"{MEMORY}/emotions/current")).json()
            stats = (await c.get(f"{MEMORY}/stats")).json()
    except Exception:
        emotion = {"mood": "unknown"}
        stats = {}
    return {
        "service": "jarvis-brain",
        "version": "2.0",
        "model": MODEL,
        "emotion": emotion,
        "memory": stats,
        "messages_until_summary": _SUMMARIZE_EVERY - _message_count
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "service": "jarvis-brain",
            "version": "2.0", "ascii_only": ASCII_ONLY}
