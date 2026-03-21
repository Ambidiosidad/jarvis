"""
J.A.R.V.I.S. Tools v2
========================
Herramientas invocables por el LLM.
Incluye movimiento, memoria, emociones y aprendizaje.
"""

TOOLS = {
    "move": {
        "desc": "Mover el robot",
        "params": "direction: forward|backward|left|right|stop, duration: float, speed: 0-1"
    },
    "remember": {
        "desc": "Guardar un hecho sobre el usuario en memoria permanente",
        "params": "fact: texto del hecho"
    },
    "update_emotion": {
        "desc": "Actualizar tu estado emocional actual",
        "params": "mood: str, energy: 0-1, patience: 0-1, bond: 0-1, reason: str"
    },
    "learn_pattern": {
        "desc": "Registrar un patrón observado sobre el usuario",
        "params": "type: preference|habit|interest|communication_style, description: str"
    },
    "search_knowledge": {
        "desc": "Buscar en documentos subidos (RAG vía Qdrant)",
        "params": "query: texto de búsqueda"
    },
    "summarize_conversation": {
        "desc": "Generar un resumen de la conversación actual para memoria a largo plazo",
        "params": "summary: texto del resumen, topics: lista de temas"
    },
}


def tools_prompt() -> str:
    lines = ["\n## Herramientas disponibles",
             'Incluye un JSON para invocar: {"tool": "nombre", "params": {...}}\n']
    for name, t in TOOLS.items():
        lines.append(f"- **{name}**: {t['desc']}  →  {{{t['params']}}}")
    return "\n".join(lines)
