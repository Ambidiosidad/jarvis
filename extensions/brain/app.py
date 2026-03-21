"""
J.A.R.V.I.S. Brain - Orquestador central.
Recibe mensajes, consulta memoria, llama al LLM y ejecuta herramientas.
"""

import json
import os
import re
import unicodedata
from typing import Optional

import httpx
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from personality import build_system_prompt
from tools import tools_prompt

app = FastAPI(title="Jarvis Brain")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OLLAMA = os.getenv("OLLAMA_URL", "http://nomad_ollama:11434")
MEMORY = os.getenv("MEMORY_URL", "http://jarvis-memory:8401")
VOICE = os.getenv("VOICE_URL", "http://jarvis-voice:8402")
MOTORS = os.getenv("MOTORS_URL", "http://jarvis-motors:8404")
MODEL = os.getenv("MODEL_NAME", "gemma3:1b")
TOOLS_TEXT = tools_prompt()
ASCII_ONLY = os.getenv("JARVIS_ASCII_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}

MOVE_DIRECTIONS = {"forward", "backward", "left", "right", "stop"}
MOVE_INTENT_RE = re.compile(
    r"\b(avanza|avanzar|mueve|mover|gira|retrocede|detente|para|parar|stop|forward|backward|left|right)\b",
    re.IGNORECASE,
)
ASCII_TRANSLATION_TABLE = str.maketrans(
    {
        "\u00BF": "?",
        "\u00A1": "!",
        "\u201C": '"',
        "\u201D": '"',
        "\u2018": "'",
        "\u2019": "'",
    }
)


async def _get_memory() -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MEMORY}/context")
            return r.json().get("context", "") if r.status_code == 200 else ""
    except Exception:
        return ""


async def _save_msg(role: str, content: str):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/messages", json={"role": role, "content": content})
    except Exception:
        pass


async def _save_fact(fact: str):
    if not fact:
        return

    fact_to_store = _to_ascii(fact) if ASCII_ONLY else fact
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/facts", params={"fact": fact_to_store})
    except Exception:
        pass


async def _call_llm(user_msg: str) -> str:
    memory = await _get_memory()
    system = build_system_prompt(TOOLS_TEXT, memory)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            f"{OLLAMA}/api/generate",
            json={
                "model": MODEL,
                "prompt": user_msg,
                "system": system,
                "stream": False,
                "options": {"temperature": 0.7, "num_ctx": 4096, "num_predict": 512},
            },
        )
        r.raise_for_status()
    return r.json().get("response", "").strip()


def _extract_tool(text: str) -> Optional[dict]:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
        return parsed if "tool" in parsed else None
    except (ValueError, json.JSONDecodeError):
        return None


def _clean(text: str) -> str:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
        if "tool" in parsed:
            cleaned = (text[:start] + text[end:]).strip()
            cleaned = re.sub(r"```(?:json)?\s*```", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
            return cleaned or "Entendido."
    except (ValueError, json.JSONDecodeError):
        pass
    return text


def _to_ascii(text: str) -> str:
    normalized = (text or "").translate(ASCII_TRANSLATION_TABLE)
    normalized = unicodedata.normalize("NFKD", normalized)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _output_text(text: str) -> str:
    return _to_ascii(text) if ASCII_ONLY else text


def _is_move_intent(user_msg: str) -> bool:
    return bool(MOVE_INTENT_RE.search(user_msg or ""))


def _normalize_fact_fragment(fragment: str) -> str:
    value = re.sub(r"\s+", " ", fragment).strip(" .,!?:;\"'")
    value = re.split(r"\b(?:y|and|pero|que)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return value.strip(" .,!?:;\"'")


def _extract_facts_from_user_message(user_msg: str) -> list[str]:
    text = re.sub(r"\s+", " ", user_msg).strip()
    if not text:
        return []

    patterns = [
        (r"\bme llamo\s+([^\.,;!?]+)", "El usuario se llama {}"),
        (r"\bmi nombre es\s+([^\.,;!?]+)", "El usuario se llama {}"),
        (r"\bvivo en\s+([^\.,;!?]+)", "El usuario vive en {}"),
    ]

    facts: list[str] = []
    for pattern, template in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = _normalize_fact_fragment(match.group(1))
        if value:
            facts.append(template.format(value))

    unique_facts: list[str] = []
    seen = set()
    for fact in facts:
        key = fact.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_facts.append(fact)
    return unique_facts


async def _exec_tool(tc: dict, user_msg: str) -> bool:
    tool = tc.get("tool")
    params = tc.get("params", {}) or {}

    if tool == "remember":
        fact = str(params.get("fact", "")).strip()
        if not fact:
            return False
        await _save_fact(fact)
        return True

    if tool == "move":
        direction = str(params.get("direction", "")).strip().lower()
        if direction not in MOVE_DIRECTIONS or not _is_move_intent(user_msg):
            return False

        try:
            duration = float(params.get("duration", 1.0))
            speed = float(params.get("speed", 0.7))
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(
                    f"{MOTORS}/move/{direction}",
                    params={"duration": duration, "speed": speed},
                )
            return True
        except Exception:
            return False

    return False


async def _think(user_msg: str) -> dict:
    await _save_msg("user", user_msg)
    raw = await _call_llm(user_msg)
    await _save_msg("assistant", raw)

    tool_call = _extract_tool(raw)
    tool_executed = None
    if tool_call:
        executed = await _exec_tool(tool_call, user_msg)
        if executed:
            tool_executed = tool_call

    remember_fact = ""
    if tool_call and str(tool_call.get("tool", "")).lower() == "remember":
        remember_fact = str((tool_call.get("params") or {}).get("fact", "")).strip()

    if not remember_fact:
        for fact in _extract_facts_from_user_message(user_msg):
            await _save_fact(fact)

    return {"text": _output_text(_clean(raw)), "tool": tool_executed}


@app.post("/chat")
async def chat(message: str):
    result = await _think(message)
    return {"response": result["text"], "tool_executed": result["tool"]}


@app.post("/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    async with httpx.AsyncClient(timeout=60) as c:
        files = {"audio": (audio.filename, await audio.read(), audio.content_type)}
        r = await c.post(f"{VOICE}/stt", files=files)
        user_text = r.json().get("text", "")

    if not user_text:
        return {"transcription": "", "response": "No te he entendido."}

    result = await _think(user_text)
    transcription = _output_text(user_text)
    return {
        "transcription": transcription,
        "response": result["text"],
        "tool_executed": result["tool"],
        "audio_url": f"{VOICE}/tts?text={result['text'][:300]}",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL,
        "service": "jarvis-brain",
        "ascii_only": ASCII_ONLY,
    }
