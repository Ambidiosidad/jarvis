"""
J.A.R.V.I.S. Fact Extractor v3
=================================
Extracción automática de hechos y contexto dinámico.
Alimenta el sistema de memoria tipo Supermemory con:
- Hechos estáticos (nombre, ciudad, trabajo) → profile/static
- Contexto dinámico (proyectos actuales, temas) → profile/dynamic
- Memorias con resolución de contradicciones
"""
import re

# ═══════════════════════════════════════
#  Static facts (permanent profile)
# ═══════════════════════════════════════

STATIC_PATTERNS = [
    # Identity
    (r"(?:me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ]\w+)",
     "El usuario se llama {}", "identity"),
    (r"(?:my name is)\s+([A-Z]\w+)",
     "El usuario se llama {}", "identity"),
    (r"(?:tengo)\s+(\d+)\s+años",
     "El usuario tiene {} años", "identity"),

    # Location
    (r"(?:vivo en|soy de)\s+([A-ZÁÉÍÓÚÑ]\w+(?:\s+\w+)?)",
     "El usuario vive en {}", "location"),
    (r"(?:i live in|i'm from)\s+([A-Z]\w+(?:\s+\w+)?)",
     "El usuario vive en {}", "location"),
    (r"(?:me he mudado a|me mudé a|ahora vivo en)\s+([A-ZÁÉÍÓÚÑ]\w+(?:\s+\w+)?)",
     "El usuario vive en {}", "location"),

    # Work
    (r"(?:trabajo en|trabajo como)\s+(.+?)(?:\.|,|$)",
     "El usuario trabaja en/como {}", "work"),
    (r"(?:i work (?:at|as|for))\s+(.+?)(?:\.|,|$)",
     "El usuario trabaja en/como {}", "work"),

    # Preferences (permanent)
    (r"(?:me gusta|me encanta|me apasiona)\s+(.+?)(?:\.|,|y\s|$)",
     "Al usuario le gusta {}", "interests"),
    (r"(?:mi (?:color|comida|deporte|música|película) favorit[oa] es)\s+(.+?)(?:\.|,|$)",
     "Favorito del usuario: {}", "interests"),
    (r"(?:odio|no soporto|no me gusta)\s+(.+?)(?:\.|,|$)",
     "Al usuario no le gusta {}", "interests"),

    # Relationships
    (r"(?:mi (?:pareja|novia|novio|esposa|esposo|mujer|marido) se llama)\s+(\w+)",
     "La pareja del usuario se llama {}", "relationship"),
    (r"(?:tengo (?:un|una) (?:perro|gato|mascota) (?:que se llama|llamado))\s+(\w+)",
     "La mascota del usuario se llama {}", "relationship"),
]

# ═══════════════════════════════════════
#  Dynamic context (temporal, decays)
# ═══════════════════════════════════════

DYNAMIC_PATTERNS = [
    # Projects
    (r"(?:estoy (?:construyendo|creando|haciendo|desarrollando|trabajando en))\s+(.+?)(?:\.|,|$)",
     "Proyecto actual: {}", "project"),
    (r"(?:i'm (?:building|creating|working on|developing))\s+(.+?)(?:\.|,|$)",
     "Proyecto actual: {}", "project"),

    # Current situation
    (r"(?:estoy (?:aprendiendo|estudiando))\s+(.+?)(?:\.|,|$)",
     "Está aprendiendo: {}", "learning"),
    (r"(?:necesito|quiero|busco)\s+(.+?)(?:\.|,|$)",
     "Necesita/quiere: {}", "needs"),
    (r"(?:acabo de|he (?:comprado|terminado|empezado))\s+(.+?)(?:\.|,|$)",
     "Acción reciente: {}", "activity"),

    # Plans
    (r"(?:voy a|planeo|pienso)\s+(.+?)(?:\.|,|$)",
     "Plan: {}", "plans"),
]


def extract_facts(text: str) -> list[dict]:
    """
    Extract all facts from a user message.
    Returns list of dicts with: fact, profile_type, category
    """
    results = []
    seen = set()

    # Static facts
    for pattern, template, category in STATIC_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if len(value) > 2:
                fact = template.format(value)
                if fact not in seen:
                    seen.add(fact)
                    results.append({
                        "fact": fact,
                        "profile_type": "static",
                        "category": category,
                    })

    # Dynamic context
    for pattern, template, category in DYNAMIC_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if len(value) > 3:
                fact = template.format(value)
                if fact not in seen:
                    seen.add(fact)
                    results.append({
                        "fact": fact,
                        "profile_type": "dynamic",
                        "category": category,
                    })

    return results
