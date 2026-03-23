"""
J.A.R.V.I.S. Brain v3.1
- Multi-turn context
- Intent routing + dual model selection
- Automatic fact extraction and emotion updates
- Optional live visual context via jarvis-vision
"""

import asyncio
import json
import os
import re
import unicodedata
from urllib.parse import quote

import httpx
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from emotion_analyzer import analyze_conversation_sentiment
from intent_classifier import classify_intent
from personality import build_system_prompt
from tools import tools_prompt

app = FastAPI(title="Jarvis Brain")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA = os.getenv("OLLAMA_URL", "http://jarvis_ollama:11434")
MEMORY = os.getenv("MEMORY_URL", "http://jarvis-memory:8401")
VOICE = os.getenv("VOICE_URL", "http://jarvis-voice:8402")
VISION = os.getenv("VISION_URL", "http://jarvis-vision:8405")
MOTORS = os.getenv("MOTORS_URL", "http://jarvis-motors:8404")

MODEL = os.getenv("MODEL_NAME", "gemma3:1b")
MODEL_REASONING = os.getenv("MODEL_REASONING", "qwen2.5:3b")

ASCII_ONLY = os.getenv("JARVIS_ASCII_ONLY", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CONTEXT_WINDOW = int(os.getenv("JARVIS_CONTEXT_MESSAGES", "6"))

_message_count = 0
_SUMMARIZE_EVERY = 10

_SESSION_DEFAULT = {
    "speaker_enabled": True,
    "mic_enabled": True,
    "auto_vision": False,
    "language": os.getenv("JARVIS_LANGUAGE", "es"),
}
_SESSION_STATE: dict[str, dict] = {}


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


def _get_session_state(session_id: str) -> dict:
    sid = session_id.strip() if session_id else "default"
    if sid not in _SESSION_STATE:
        _SESSION_STATE[sid] = dict(_SESSION_DEFAULT)
    return _SESSION_STATE[sid]


def _apply_semantic_controls(message: str, state: dict) -> dict:
    text = _to_ascii(message).lower()
    controls: dict[str, object] = {}

    if re.search(r"\b(no hables|modo silencio|mute|silencio|dont speak|be quiet)\b", text):
        state["speaker_enabled"] = False
        controls["speaker_enabled"] = False
    elif re.search(r"\b(habla|desmute|quita silencio|vuelve a hablar|speak|unmute)\b", text):
        state["speaker_enabled"] = True
        controls["speaker_enabled"] = True

    if re.search(r"\b(desactiva micro|no escuches|mute mic|disable mic|dont listen)\b", text):
        state["mic_enabled"] = False
        controls["mic_enabled"] = False
    elif re.search(r"\b(activa micro|escuchame|unmute mic|enable mic|listen to me)\b", text):
        state["mic_enabled"] = True
        controls["mic_enabled"] = True

    if re.search(
        r"\b(activa camara|modo vision|mira siempre|enable camera|camera mode|always look)\b",
        text,
    ):
        state["auto_vision"] = True
        controls["auto_vision"] = True
    elif re.search(
        r"\b(desactiva camara|sin vision|no mires|disable camera|no vision|dont look)\b",
        text,
    ):
        state["auto_vision"] = False
        controls["auto_vision"] = False

    return controls


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------


async def _get_memory_context() -> str:
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            res = await client.get(f"{MEMORY}/context")
            if res.status_code == 200:
                return res.json().get("context", "")
    except Exception:
        pass
    return ""


async def _get_recent_messages(limit: int | None = None) -> list[dict]:
    max_messages = limit if isinstance(limit, int) and limit > 0 else CONTEXT_WINDOW
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            res = await client.get(
                f"{MEMORY}/messages/recent",
                params={"limit": max_messages},
            )
            if res.status_code == 200:
                return res.json().get("messages", [])
    except Exception:
        pass
    return []


async def _get_current_emotion() -> dict:
    fallback = {
        "mood": "neutral",
        "energy": 0.5,
        "patience": 0.8,
        "bond": 0.1,
        "reason": "default",
    }
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            res = await client.get(f"{MEMORY}/emotions/current")
            if res.status_code == 200:
                return res.json()
    except Exception:
        pass
    return fallback


async def _save_msg(role: str, content: str) -> None:
    try:
        payload = _to_ascii(content) if ASCII_ONLY else content
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(
                f"{MEMORY}/messages",
                json={"role": role, "content": payload},
            )
    except Exception:
        pass


async def _save_fact(fact: str) -> None:
    try:
        payload = _to_ascii(fact) if ASCII_ONLY else fact
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(f"{MEMORY}/facts", params={"fact": payload})
    except Exception:
        pass


async def _update_emotion(state: dict) -> None:
    try:
        payload = _sanitize_emotion(state) if ASCII_ONLY else state
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(f"{MEMORY}/emotions", json=payload)
    except Exception:
        pass


async def _learn_pattern(pattern_type: str, description: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(
                f"{MEMORY}/patterns",
                params={"pattern_type": pattern_type, "description": description},
            )
    except Exception:
        pass


async def _save_summary(summary: str, topics: list[str]) -> None:
    try:
        summary_value = _to_ascii(summary) if ASCII_ONLY else summary
        topics_value = [_to_ascii(t) for t in topics] if ASCII_ONLY else topics
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                f"{MEMORY}/summaries",
                json={"summary": summary_value, "topics": topics_value},
            )
    except Exception:
        pass


async def _save_observation(observation: dict) -> None:
    try:
        summary = observation.get("summary", "")
        labels = observation.get("labels", [])
        confidence = float(observation.get("mood_confidence", 0.5))

        if ASCII_ONLY:
            summary = _to_ascii(summary)
            labels = [_to_ascii(label) for label in labels]

        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(
                f"{MEMORY}/observations",
                json={
                    "source": "vision",
                    "summary": summary,
                    "labels": labels,
                    "confidence": confidence,
                },
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Vision helpers
# ---------------------------------------------------------------------------


_VISION_HINTS = re.compile(
    r"\b("
    r"mira|mirar|ver|ves|veo|camara|camera|imagen|image|foto|photo|"
    r"gafas|glasses|cara|rostro|face|emocion|expresion|smile|"
    r"que\s+ves|what\s+do\s+you\s+see"
    r")\b",
    re.IGNORECASE,
)

_NAME_QUERY_HINTS = re.compile(
    r"\b("
    r"como me llamo|cual es mi nombre|mi nombre|te acuerdas de mi nombre|"
    r"recuerdas mi nombre|what is my name|do you remember my name"
    r")\b",
    re.IGNORECASE,
)


def _should_use_vision(message: str, force: bool = False) -> bool:
    if force:
        return True
    return bool(_VISION_HINTS.search(message or ""))


def _is_name_query(message: str) -> bool:
    return bool(_NAME_QUERY_HINTS.search(_to_ascii(message)))


def _normalize_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]", "", (name or "").strip())
    if not value:
        return ""
    return value[:1].upper() + value[1:]


def _extract_name_from_memory(memory_context: str) -> str | None:
    context = _to_ascii(memory_context or "")
    patterns = [
        r"(?:el usuario se llama|usuario se llama)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
        r"(?:the user is called|user is called)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
        r"(?:me llamo|mi nombre es)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
        r"(?:my name is)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            name = _normalize_name(match.group(1))
            if name:
                return name

    return None


def _extract_name_from_messages(messages: list[dict]) -> str | None:
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        text = _to_ascii(str(msg.get("content", "")))
        match = re.search(
            r"(?:me llamo|mi nombre es|my name is)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
            text,
            re.IGNORECASE,
        )
        if match:
            name = _normalize_name(match.group(1))
            if name:
                return name
    return None


def _name_response(name: str, message: str) -> str:
    text = _to_ascii(message).lower()
    if "what is my name" in text or "remember my name" in text:
        return f"Your name is {name}. I remember it."
    return f"Te llamas {name}. Lo recuerdo."


def _vision_unavailable_response(message: str, language: str = "es") -> str:
    text = _to_ascii(message).lower()
    if not str(language).lower().startswith("es"):
        return (
            "I cannot access your live webcam feed in this Docker-on-Windows setup. "
            "I can still analyze images if you upload one to /analyze-image."
        )
    if "camera" in text or "camara" in text or "verme" in text or "puedes" in text:
        return (
            "No puedo acceder al streaming en vivo de tu webcam en este entorno Docker de Windows. "
            "Si quieres, puedo analizar una imagen que subas al endpoint /analyze-image."
        )
    return "No tengo acceso en vivo a tu webcam ahora mismo. Puedo analizar una imagen subida en /analyze-image."


def _vision_unavailable(reason: str) -> dict:
    return {
        "available": False,
        "error": reason,
        "summary": "Live camera data is unavailable.",
        "labels": ["vision_unavailable"],
        "people_count": 0,
        "glasses_detected": False,
        "mood_estimate": "unknown",
        "mood_confidence": 0.0,
    }


async def _get_live_vision(message: str, force: bool = False) -> dict | None:
    wants_vision = _should_use_vision(message, force)
    if not wants_vision:
        return None

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            res = await client.post(f"{VISION}/analyze")
            if res.status_code != 200:
                return _vision_unavailable(f"vision_http_{res.status_code}")
            data = res.json()

        data["available"] = True
        await _save_observation(data)
        return data
    except Exception:
        return _vision_unavailable("vision_unreachable")


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


async def _call_llm_chat(
    user_msg: str,
    system: str,
    history: list[dict],
    max_tokens: int = 512,
    model: str | None = None,
) -> str:
    messages = [{"role": "system", "content": system}]

    for msg in history:
        messages.append(
            {
                "role": msg.get("role", "user"),
                "content": str(msg.get("content", ""))[:500],
            }
        )

    messages.append({"role": "user", "content": user_msg})

    payload = {
        "model": model or MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 4096,
            "num_predict": max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            res = await client.post(f"{OLLAMA}/api/chat", json=payload)
            res.raise_for_status()
            return res.json().get("message", {}).get("content", "").strip()
        except Exception:
            # Fallback to primary model if reasoning model is unavailable.
            selected = model or MODEL
            if selected != MODEL:
                payload["model"] = MODEL
                res_fallback = await client.post(f"{OLLAMA}/api/chat", json=payload)
                res_fallback.raise_for_status()
                return res_fallback.json().get("message", {}).get("content", "").strip()
            raise


async def _call_llm_simple(prompt: str, system: str, max_tokens: int = 150) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        res = await client.post(
            f"{OLLAMA}/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 2048,
                    "num_predict": max_tokens,
                },
            },
        )
        res.raise_for_status()

    return res.json().get("response", "").strip()


# ---------------------------------------------------------------------------
# Tooling and extraction
# ---------------------------------------------------------------------------


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
    cleaned = re.sub(r'\{[^{}]*"tool"[^{}]*\}', "", text)
    cleaned = re.sub(r"```json\s*```", "", cleaned)
    cleaned = re.sub(r"```\s*```", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def _exec_tools(tool_calls: list[dict]) -> None:
    for call in tool_calls:
        tool = call.get("tool")
        params = call.get("params", {})

        if tool == "remember":
            await _save_fact(params.get("fact", ""))

        elif tool == "move":
            try:
                direction = params.get("direction", "stop")
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        f"{MOTORS}/move/{direction}",
                        params={
                            "duration": params.get("duration", 1.0),
                            "speed": params.get("speed", 0.7),
                        },
                    )
            except Exception:
                pass

        elif tool == "learn_pattern":
            await _learn_pattern(
                params.get("type", "preference"),
                params.get("description", ""),
            )

        elif tool == "observe_scene":
            vision_data = await _get_live_vision("", force=True)
            if vision_data:
                summary = vision_data.get("summary", "Scene observed")
                await _save_fact(f"Visual observation: {summary}")


_FACT_PATTERNS = [
    (
        r"(?:me llamo|mi nombre es)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
        "El usuario se llama {}",
    ),
    (
        r"(?:vivo en|soy de)\s+([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z0-9_-]+)?)",
        "El usuario vive en {}",
    ),
    (
        r"(?:trabajo en|trabajo como)\s+(.+?)(?:\.|,|$)",
        "El usuario trabaja en/como {}",
    ),
    (r"(?:tengo)\s+(\d+)\s+anos", "El usuario tiene {} anos"),
    (
        r"(?:me gusta|me encanta|me apasiona)\s+(.+?)(?:\.|,|y\s|$)",
        "Al usuario le gusta {}",
    ),
    (
        r"(?:my name is)\s+([A-Za-z][A-Za-z0-9_-]{1,40})",
        "El usuario se llama {}",
    ),
    (
        r"(?:i live in)\s+([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z0-9_-]+)?)",
        "El usuario vive en {}",
    ),
]


async def _auto_extract_facts(user_msg: str) -> None:
    raw_message = _to_ascii(user_msg) if ASCII_ONLY else user_msg
    for pattern, template in _FACT_PATTERNS:
        match = re.search(pattern, raw_message, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip()
        if "se llama" in template:
            value = _normalize_name(value)
        if len(value) > 2:
            await _save_fact(template.format(value))


async def _auto_summarize() -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{MEMORY}/messages/recent", params={"limit": 20})
            if res.status_code != 200:
                return
            messages = res.json().get("messages", [])

        if len(messages) < 6:
            return

        conversation = "\n".join(
            f"{m['role']}: {m['content'][:150]}" for m in messages
        )

        result = await _call_llm_simple(
            (
                "Resume in 2 short sentences what was discussed. "
                "At the end write TOPICS: topic1, topic2\n\n"
                f"{conversation}"
            ),
            "Generate concise summaries only.",
        )

        lines = result.strip().split("\n")
        topics_line = ""
        summary_lines = []
        for line in lines:
            if "TOPICS:" in line.upper():
                topics_line = line.split(":", 1)[1].strip()
            else:
                summary_lines.append(line)

        summary_text = " ".join(summary_lines).strip()
        topics = [t.strip() for t in topics_line.split(",") if t.strip()] or ["conversation"]

        if len(summary_text) > 10:
            await _save_summary(summary_text, topics)

    except Exception as exc:
        print(f"[BRAIN] Auto-summarize error: {exc}")


# ---------------------------------------------------------------------------
# Main thinking pipeline
# ---------------------------------------------------------------------------


async def _think(
    user_msg: str,
    use_vision: bool = False,
    session_state: dict | None = None,
) -> dict:
    global _message_count

    await _save_msg("user", user_msg)
    _message_count += 1

    await _auto_extract_facts(user_msg)

    intent = classify_intent(user_msg)

    current_emotion = await _get_current_emotion()
    emotion_text = (
        f"Tu humor: {current_emotion.get('mood', 'neutral')}. "
        f"Vinculo con usuario: {current_emotion.get('bond', 0.1):.1f}/1.0."
    )

    memory_context = await _get_memory_context()

    force_vision = use_vision or bool((session_state or {}).get("auto_vision", False))
    wants_vision = _should_use_vision(user_msg, force=force_vision)
    vision_data = await _get_live_vision(user_msg, force=force_vision)
    vision_context = ""
    if vision_data:
        if vision_data.get("available", True):
            labels = ", ".join(vision_data.get("labels", []))
            summary = vision_data.get("summary", "")
            vision_context = (
                "\n\n## Live visual context\n"
                f"- {summary}\n"
                f"- labels: {labels}\n"
                f"- people_count: {vision_data.get('people_count', 0)}\n"
                f"- glasses_detected: {vision_data.get('glasses_detected', False)}\n"
                f"- mood_estimate: {vision_data.get('mood_estimate', 'unknown')}"
            )
        else:
            vision_context = (
                "\n\n## Live visual context\n"
                "- Live camera data is unavailable right now.\n"
                "- Do not claim that you can currently see the scene.\n"
                "- Ask the user to provide an image or enable camera access."
            )

    known_name = _extract_name_from_memory(memory_context)
    session_language = (session_state or {}).get("language", "es")
    history: list[dict] = []

    if _is_name_query(user_msg) and not known_name:
        history = await _get_recent_messages(limit=max(20, CONTEXT_WINDOW))
        known_name = _extract_name_from_messages(history)
        if known_name:
            await _save_fact(f"El usuario se llama {known_name}")

    active_model = MODEL_REASONING if intent in ("logic", "factual") else MODEL
    if _is_name_query(user_msg) and known_name:
        raw = _name_response(known_name, user_msg)
    elif wants_vision and vision_data and not vision_data.get("available", True):
        raw = _vision_unavailable_response(user_msg, session_language)
    else:
        system = build_system_prompt(
            intent,
            memory_context + vision_context,
            emotion_text,
        )
        if str(session_language).lower().startswith("es"):
            system += "\n\nINSTRUCCION: Responde en espanol salvo que el usuario pida otro idioma."
        system = f"{system}\n\n{tools_prompt()}"

        if not history:
            history = await _get_recent_messages()

        try:
            raw = await _call_llm_chat(user_msg, system, history, model=active_model)
        except Exception:
            raw = (
                "I could not reach the local language model right now. "
                "Please verify that Ollama is running and models are installed."
            )

    await _save_msg("assistant", raw)

    tool_calls = _extract_all_tools(raw)
    if tool_calls:
        await _exec_tools(tool_calls)

    new_emotion = analyze_conversation_sentiment(user_msg, raw, current_emotion)
    await _update_emotion(new_emotion)

    if _message_count >= _SUMMARIZE_EVERY:
        _message_count = 0
        asyncio.create_task(_auto_summarize())

    return {
        "text": _out(_clean(raw)),
        "tools": tool_calls,
        "emotion": _sanitize_emotion(new_emotion),
        "intent": intent,
        "model_used": active_model,
        "vision": vision_data,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _build_tts_url(text: str, language: str = "es") -> str:
    return f"{VOICE}/tts?text={quote(text[:300])}&language={quote(language)}"


def _build_response_payload(
    result: dict,
    session_id: str | None = None,
    session_state: dict | None = None,
    controls_applied: dict | None = None,
) -> dict:
    payload = {
        "response": _out(result["text"]),
        "tools_executed": result["tools"],
        "emotion": _sanitize_emotion(result["emotion"]),
        "intent": result["intent"],
        "model_used": result["model_used"],
        "vision": result["vision"],
    }
    if session_id is not None:
        payload["session_id"] = session_id
    if session_state is not None:
        payload["session_state"] = session_state
        if session_state.get("speaker_enabled", True):
            payload["audio_url"] = _build_tts_url(
                payload["response"],
                session_state.get("language", "es"),
            )
        else:
            payload["audio_url"] = None
    if controls_applied is not None:
        payload["controls_applied"] = controls_applied
    return payload


async def _converse_core(
    message: str,
    session_id: str = "default",
    use_vision: bool = False,
) -> dict:
    state = _get_session_state(session_id)
    controls_applied = _apply_semantic_controls(message, state)
    result = await _think(message, use_vision=use_vision, session_state=state)
    return _build_response_payload(
        result,
        session_id=session_id,
        session_state=state,
        controls_applied=controls_applied,
    )


@app.post("/chat")
async def chat(message: str, use_vision: bool = False) -> dict:
    result = await _think(message, use_vision=use_vision)
    return _build_response_payload(result)


@app.post("/converse")
async def converse(message: str, session_id: str = "default", use_vision: bool = False) -> dict:
    return await _converse_core(message, session_id=session_id, use_vision=use_vision)


@app.post("/vision-chat")
async def vision_chat(message: str) -> dict:
    result = await _think(message, use_vision=True)
    return _build_response_payload(result)


@app.post("/voice-chat")
async def voice_chat(audio: UploadFile = File(...), use_vision: bool = False) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"audio": (audio.filename, await audio.read(), audio.content_type)}
        stt_res = await client.post(f"{VOICE}/stt", files=files)
        user_text = stt_res.json().get("text", "")

    if not user_text:
        return {"transcription": "", "response": "I could not understand you."}

    result = await _think(user_text, use_vision=use_vision)
    payload = _build_response_payload(result)
    payload["transcription"] = _out(user_text)
    payload["audio_url"] = _build_tts_url(payload["response"])
    return payload


@app.post("/converse-audio")
async def converse_audio(
    audio: UploadFile = File(...),
    session_id: str = "default",
    use_vision: bool = False,
) -> dict:
    state = _get_session_state(session_id)
    if not state.get("mic_enabled", True):
        return {
            "session_id": session_id,
            "transcription": "",
            "response": "Microphone input is disabled for this session.",
            "session_state": state,
            "controls_applied": {},
            "audio_url": None,
        }

    async with httpx.AsyncClient(timeout=60) as client:
        files = {"audio": (audio.filename, await audio.read(), audio.content_type)}
        stt_res = await client.post(
            f"{VOICE}/stt",
            files=files,
            params={"language": state.get("language", "es")},
        )
        user_text = stt_res.json().get("text", "")

    if not user_text:
        return {
            "session_id": session_id,
            "transcription": "",
            "response": "I could not understand you.",
            "session_state": state,
            "controls_applied": {},
            "audio_url": None,
        }

    payload = await _converse_core(
        user_text,
        session_id=session_id,
        use_vision=use_vision,
    )
    payload["transcription"] = _out(user_text)
    return payload


@app.get("/status")
async def status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            emotion = (await client.get(f"{MEMORY}/emotions/current")).json()
            stats = (await client.get(f"{MEMORY}/stats")).json()
    except Exception:
        emotion = {"mood": "unknown"}
        stats = {}

    return {
        "service": "jarvis-brain",
        "version": "3.1",
        "model": MODEL,
        "reasoning_model": MODEL_REASONING,
        "emotion": _sanitize_emotion(emotion),
        "memory": stats,
        "context_window": CONTEXT_WINDOW,
        "messages_until_summary": max(0, _SUMMARIZE_EVERY - _message_count),
        "vision_url": VISION,
        "active_sessions": len(_SESSION_STATE),
    }


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "jarvis-brain",
        "version": "3.1",
        "model": MODEL,
        "reasoning_model": MODEL_REASONING,
        "ascii_only": ASCII_ONLY,
        "vision_url": VISION,
    }
