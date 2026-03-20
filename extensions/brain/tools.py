"""J.A.R.V.I.S. — Herramientas invocables por el LLM."""

TOOLS = {
    "move": {
        "desc": "Mover el robot",
        "params": "direction: forward|backward|left|right|stop, duration: float, speed: 0-1"
    },
    "remember": {
        "desc": "Guardar un hecho sobre el usuario en memoria permanente",
        "params": "fact: texto del hecho"
    },
    "search_knowledge": {
        "desc": "Buscar en documentos subidos (RAG vía Qdrant)",
        "params": "query: texto de búsqueda"
    },
}


def tools_prompt() -> str:
    lines = ["\n## Herramientas disponibles",
             'Incluye un JSON para invocar: {"tool": "nombre", "params": {...}}\n']
    for name, t in TOOLS.items():
        lines.append(f"- **{name}**: {t['desc']}  →  {{{t['params']}}}")
    return "\n".join(lines)
