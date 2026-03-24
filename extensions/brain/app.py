"""
J.A.R.V.I.S. Brain v3.1
========================
Integración con Memory v3 (Supermemory offline):
- Extracción de hechos estáticos + contexto dinámico
- Perfil de usuario con resolución de contradicciones
- Contexto temporal que caduca (72h)
- Modelo dual + clasificador de intención + multi-turno
"""
import os, json, re, asyncio, unicodedata, io
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from personality import build_system_prompt
from tools import tools_prompt
from emotion_analyzer import analyze_conversation_sentiment
from intent_classifier import classify_intent
from fact_extractor import extract_facts
from inferencer import extract_facts_with_llm

app = FastAPI(title="Jarvis Brain v3.1")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

OLLAMA = os.getenv("OLLAMA_URL", "http://jarvis_ollama:11434")
MEMORY = os.getenv("MEMORY_URL", "http://jarvis-memory:8401")
VOICE = os.getenv("VOICE_URL", "http://jarvis-voice:8402")
MOTORS = os.getenv("MOTORS_URL", "http://jarvis-motors:8404")
MODEL = os.getenv("MODEL_NAME", "gemma3:1b")
MODEL_REASONING = os.getenv("MODEL_REASONING", "qwen2.5:3b")
ASCII_ONLY = os.getenv("JARVIS_ASCII_ONLY", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
CONTEXT_WINDOW = int(os.getenv("JARVIS_CONTEXT_MESSAGES", "6"))

_message_count = 0
_SUMMARIZE_EVERY = 10


# ═══════════════════════════════════════
#  Text helpers
# ═══════════════════════════════════════

def _to_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")

def _out(text: str) -> str:
    return _to_ascii(text) if ASCII_ONLY else text

def _sanitize_emotion(emotion: dict) -> dict:
    if not ASCII_ONLY:
        return emotion
    return {k: (_to_ascii(v) if isinstance(v, str) else v)
            for k, v in (emotion or {}).items()}


# ═══════════════════════════════════════
#  Memory helpers (Supermemory-style)
# ═══════════════════════════════════════

async def _get_memory_context() -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/context")
            return r.json().get("context", "") if r.status_code == 200 else ""
    except Exception:
        return ""


async def _get_recent_messages() -> list[dict]:
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
        c_store = _to_ascii(content) if ASCII_ONLY else content
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/messages",
                         json={"role": role, "content": c_store})
    except Exception:
        pass


async def _save_fact(fact: str, profile_type: str = "static",
                     category: str = "general"):
    """Save to memory store + profile with contradiction resolution."""
    try:
        f_store = _to_ascii(fact) if ASCII_ONLY else fact
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/memories", json={
                "content": f_store,
                "memory_type": "fact",
                "category": category,
                "source": "conversation",
            })
            await c.post(f"{MEMORY}/profile", params={
                "fact": f_store,
                "profile_type": profile_type,
                "category": category,
            })
    except Exception:
        pass


async def _save_dynamic_context(fact: str, category: str = "general"):
    """Save temporary context that expires after 72h."""
    try:
        f_store = _to_ascii(fact) if ASCII_ONLY else fact
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/memories", json={
                "content": f_store,
                "memory_type": "context",
                "category": category,
                "source": "conversation",
                "ttl_hours": 72.0,
            })
            await c.post(f"{MEMORY}/profile", params={
                "fact": f_store,
                "profile_type": "dynamic",
                "category": category,
            })
    except Exception:
        pass


async def _update_emotion(state: dict):
    try:
        s = _sanitize_emotion(state) if ASCII_ONLY else state
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/emotions", json=s)
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
        s_store = _to_ascii(summary) if ASCII_ONLY else summary
        t_store = [_to_ascii(t) for t in topics] if ASCII_ONLY else topics
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/summaries",
                         json={"summary": s_store, "topics": t_store})
    except Exception:
        pass


# ═══════════════════════════════════════
#  LLM calls
# ═══════════════════════════════════════

async def _call_llm_chat(user_msg: str, system: str,
                         history: list[dict],
                         max_tokens: int = 512,
                         model: str = None) -> str:
    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"][:500]
        })
    messages.append({"role": "user", "content": user_msg})

    payload = {
        "model": model or MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 4096,
            "num_predict": max_tokens,
        }
    }

    async with httpx.AsyncClient(timeout=120) as c:
        try:
            r = await c.post(f"{OLLAMA}/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "").strip()
        except Exception:
            selected = model or MODEL
            if selected != MODEL:
                payload["model"] = MODEL
                r2 = await c.post(f"{OLLAMA}/api/chat", json=payload)
                r2.raise_for_status()
                return r2.json().get("message", {}).get("content", "").strip()
            raise


async def _call_llm_simple(prompt: str, system: str,
                           max_tokens: int = 150) -> str:
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
            fact = params.get("fact", "")
            await _save_fact(fact, "static", "general")

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
#  Fact extraction (Supermemory-style)
# ═══════════════════════════════════════

async def _auto_extract_facts(user_msg: str):
    """
    Extract facts using fact_extractor module.
    Routes to static (permanent) or dynamic (temporal) profile.
    Memory v3 handles contradiction resolution automatically.
    """
    facts = extract_facts(user_msg)
    for f in facts:
        if f["profile_type"] == "static":
            await _save_fact(f["fact"], "static", f["category"])
        else:
            await _save_dynamic_context(f["fact"], f["category"])

    # LLM-powered extraction for complex messages
    if len(user_msg) > 50:
        try:
            llm_facts = await extract_facts_with_llm(user_msg)
            for f in llm_facts:
                if f["type"] == "static":
                    await _save_fact(f["fact"], "static", f["category"])
                else:
                    await _save_dynamic_context(f["fact"], f["category"])
        except Exception:
            pass


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

    # 2. Extract static facts + dynamic context (Supermemory-style)
    await _auto_extract_facts(user_msg)

    # 3. Save long messages as dynamic conversation topics
    if len(user_msg) > 80:
        topic = user_msg[:100].replace('\n', ' ').strip()
        await _save_dynamic_context(
            f"Tema reciente: {topic}", "conversation")

    # 4. Classify intent
    intent = classify_intent(user_msg)

    # 5. Get emotional state
    current_emotion = await _get_current_emotion()
    emotion_text = (
        f"Tu humor: {current_emotion.get('mood', 'neutral')}. "
        f"Vínculo: {current_emotion.get('bond', 0.1):.1f}/1.0."
    )

    # 6. Get memory context (static profile + dynamic + summaries)
    memory = await _get_memory_context()

    # 7. Build specialized system prompt
    system = build_system_prompt(intent, memory, emotion_text)

    # 8. Get recent conversation for multi-turn
    history = await _get_recent_messages()

    # 9. Select model and call LLM
    active_model = MODEL_REASONING if intent in ("logic", "factual") else MODEL
    raw = await _call_llm_chat(user_msg, system, history, model=active_model)

    # 10. Save response
    await _save_msg("assistant", raw)

    # 11. Execute tool calls
    tool_calls = _extract_all_tools(raw)
    if tool_calls:
        await _exec_tools(tool_calls)

    # 12. Update emotion
    new_emotion = analyze_conversation_sentiment(
        user_msg, raw, current_emotion)
    await _update_emotion(new_emotion)

    # 13. Auto-summarize periodically
    if _message_count >= _SUMMARIZE_EVERY:
        _message_count = 0
        asyncio.create_task(_auto_summarize())

    return {
        "text": _out(_clean(raw)),
        "tools": tool_calls,
        "emotion": _sanitize_emotion(new_emotion),
        "intent": intent,
        "model_used": active_model,
    }


# ═══════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════

@app.post("/chat")
async def chat(message: str):
    try:
        result = await _think(message)
        return {
            "response": result["text"],
            "tools_executed": result["tools"],
            "emotion": result["emotion"],
            "intent": result["intent"],
            "model_used": result["model_used"],
        }
    except Exception as e:
        return {
            "response": (
                "No he podido procesar el mensaje ahora mismo. "
                "Revisa que Ollama y los modelos esten cargados."
            ),
            "tools_executed": [],
            "emotion": {"mood": "neutral", "energy": 0.5, "patience": 0.8, "bond": 0.1, "reason": "error"},
            "intent": "general",
            "model_used": MODEL,
            "error": str(e),
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

    try:
        result = await _think(user_text)
        return {
            "transcription": _out(user_text),
            "response": result["text"],
            "tools_executed": result["tools"],
            "emotion": result["emotion"],
            "intent": result["intent"],
            "model_used": result["model_used"],
            "audio_url": f"{VOICE}/tts?text={result['text'][:300]}"
        }
    except Exception as e:
        return {
            "transcription": _out(user_text),
            "response": (
                "No he podido procesar el audio ahora mismo. "
                "Verifica Ollama y los modelos."
            ),
            "tools_executed": [],
            "emotion": {"mood": "neutral", "energy": 0.5, "patience": 0.8, "bond": 0.1, "reason": "error"},
            "intent": "general",
            "model_used": MODEL,
            "audio_url": None,
            "error": str(e),
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
        "service": "jarvis-brain", "version": "3.1",
        "model": MODEL, "model_reasoning": MODEL_REASONING,
        "emotion": _sanitize_emotion(emotion),
        "memory": stats,
        "context_window": CONTEXT_WINDOW,
        "messages_until_summary": max(0, _SUMMARIZE_EVERY - _message_count)
    }


@app.get("/")
async def serve_ui():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/voice-proxy/tts")
async def proxy_tts(text: str):
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{VOICE}/tts", params={"text": text[:300]})
            return StreamingResponse(io.BytesIO(r.content), media_type="audio/wav")
    except Exception:
        return {"error": "TTS not available"}


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL,
            "service": "jarvis-brain", "version": "3.1",
            "memory_engine": "supermemory-offline"}
