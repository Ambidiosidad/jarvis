"""
J.A.R.V.I.S. Brain — Orquestador central.
Recibe mensajes, consulta memoria, llama al LLM, ejecuta herramientas.
"""
import os, json
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File
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
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(f"{MEMORY}/facts", params={"fact": fact})
    except Exception:
        pass


async def _call_llm(user_msg: str) -> str:
    memory = await _get_memory()
    system = build_system_prompt(TOOLS_TEXT, memory)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OLLAMA}/api/generate", json={
            "model": MODEL, "prompt": user_msg, "system": system,
            "stream": False,
            "options": {"temperature": 0.7, "num_ctx": 4096, "num_predict": 512}
        })
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
            return (text[:start] + text[end:]).strip()
    except (ValueError, json.JSONDecodeError):
        pass
    return text


async def _exec_tool(tc: dict):
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
                    "speed": params.get("speed", 0.7)})
        except Exception:
            pass


async def _think(user_msg: str) -> dict:
    await _save_msg("user", user_msg)
    raw = await _call_llm(user_msg)
    await _save_msg("assistant", raw)
    tool_call = _extract_tool(raw)
    if tool_call:
        await _exec_tool(tool_call)
    return {"text": _clean(raw), "tool": tool_call}


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
    return {
        "transcription": user_text,
        "response": result["text"],
        "tool_executed": result["tool"],
        "audio_url": f"{VOICE}/tts?text={result['text'][:300]}"
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "service": "jarvis-brain"}
