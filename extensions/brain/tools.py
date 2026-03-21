"""J.A.R.V.I.S. - Herramientas invocables por el LLM."""

TOOLS = {
    "remember": {
        "desc": "Guardar un hecho sobre el usuario en memoria permanente",
        "params": "fact: texto del hecho",
    },
    "move": {
        "desc": "Mover el robot",
        "params": "direction: forward|backward|left|right|stop, duration: float, speed: 0-1",
    },
    "search_knowledge": {
        "desc": "Buscar en documentos subidos (RAG via Qdrant)",
        "params": "query: texto de busqueda",
    },
}


def tools_prompt() -> str:
    lines = [
        "\n## Herramientas disponibles",
        'Formato de tool-use: {"tool": "nombre", "params": {...}}',
        "",
        "Reglas obligatorias:",
        "- Usa remember cuando el usuario comparta datos personales (nombre, ciudad, gustos, etc.).",
        "- Usa move solo cuando el usuario ordene movimiento fisico del robot.",
        "- Si no corresponde una herramienta, responde solo texto y no incluyas JSON.",
        "",
    ]
    for name, tool in TOOLS.items():
        lines.append(f"- **{name}**: {tool['desc']} -> {{{tool['params']}}}")
    return "\n".join(lines)
