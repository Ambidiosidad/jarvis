"""
J.A.R.V.I.S. Memory Inferencer
=================================
Usa el LLM local para extraer hechos complejos que el regex
del fact_extractor no puede detectar.

Replica la inferencia de relaciones de Supermemory pero offline.
Se ejecuta periódicamente (no en cada mensaje, para ahorrar recursos).
"""
import os
import json
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://jarvis_ollama:11434")
MODEL = os.getenv("MODEL_NAME", "gemma3:1b")

_EXTRACT_PROMPT = """Eres un extractor de hechos. Del siguiente mensaje del usuario,
extrae SOLO los hechos importantes sobre el usuario.

Responde ÚNICAMENTE con un JSON array. Cada elemento tiene:
- "fact": el hecho en tercera persona ("El usuario...")
- "type": "static" (permanente) o "dynamic" (temporal/proyecto actual)
- "category": "identity", "location", "work", "interests", "project", "relationship", "general"

Si no hay hechos relevantes, responde: []

Ejemplos:
Mensaje: "Soy ingeniero en Google y estoy desarrollando una app de fitness"
Respuesta: [{"fact":"El usuario es ingeniero en Google","type":"static","category":"work"},{"fact":"Está desarrollando una app de fitness","type":"dynamic","category":"project"}]

Mensaje: "Hoy hace buen tiempo"
Respuesta: []

Mensaje del usuario:
"""


async def extract_facts_with_llm(user_msg: str) -> list[dict]:
    """
    Use the LLM to extract complex facts from a user message.
    Returns list of dicts: {fact, type, category}
    Only call this for messages that seem rich in personal info.
    """
    # Skip short messages or greetings
    if len(user_msg) < 30:
        return []

    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{OLLAMA_URL}/api/generate", json={
                "model": MODEL,
                "prompt": _EXTRACT_PROMPT + user_msg,
                "system": "Responde solo JSON. Sin texto adicional.",
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 2048,
                    "num_predict": 200,
                }
            })
            if r.status_code != 200:
                return []

            raw = r.json().get("response", "").strip()

            # Try to extract JSON from response
            # The LLM might wrap it in ```json ... ```
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            # Find array in response
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1:
                return []

            parsed = json.loads(raw[start:end+1])
            if not isinstance(parsed, list):
                return []

            # Validate structure
            valid = []
            for item in parsed:
                if isinstance(item, dict) and "fact" in item:
                    valid.append({
                        "fact": item.get("fact", ""),
                        "type": item.get("type", "static"),
                        "category": item.get("category", "general"),
                    })
            return valid

    except (json.JSONDecodeError, Exception):
        return []


_DERIVE_PROMPT = """Analiza estos dos hechos sobre un usuario y determina si puedes
inferir algo nuevo que NO esté explícitamente dicho.

Hecho 1: {fact1}
Hecho 2: {fact2}

Si puedes inferir algo nuevo, responde con JSON:
{{"derived": "El hecho inferido", "confidence": 0.0-1.0}}

Si no hay inferencia útil, responde: {{"derived": null}}
"""


async def derive_relationship(fact1: str, fact2: str) -> dict | None:
    """
    Try to derive a new fact from two existing facts.
    Like Supermemory's 'derives' relationship type.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{OLLAMA_URL}/api/generate", json={
                "model": MODEL,
                "prompt": _DERIVE_PROMPT.format(fact1=fact1, fact2=fact2),
                "system": "Responde solo JSON.",
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 1024,
                    "num_predict": 100,
                }
            })
            if r.status_code != 200:
                return None

            raw = r.json().get("response", "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None

            parsed = json.loads(raw[start:end+1])
            if parsed.get("derived"):
                return {
                    "fact": parsed["derived"],
                    "confidence": parsed.get("confidence", 0.5),
                }
    except Exception:
        pass
    return None
