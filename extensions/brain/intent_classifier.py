"""
J.A.R.V.I.S. Intent Classifier
=================================
Clasifica la intención del usuario ANTES de llamar al LLM.
Permite usar prompts especializados por tipo de pregunta.
Cero coste de RAM — es puro análisis de texto con regex.
"""
import re

# ─── Patterns por categoría ───

_LOGIC_PATTERNS = [
    r"\d+\s*[\+\-\*\/\×\÷]",          # math operators
    r"cuánto[s]?\s+(es|son|da|queda)",  # cuánto es/son
    r"si\s+tengo\s+\d+",               # si tengo N
    r"cuántas?\s+\w+\s+hay",           # cuántas X hay
    r"calcula",                         # calcula
    r"resultado",                       # resultado
    r"mayor|menor|más grande|más pequeño",
    r"lógica|acertijo|puzzle|enigma",
    r"primero.*luego|después",          # sequential reasoning
    r"probabilidad|porcentaje|media",
    r"how many|calculate|what is \d+",
    r"solve|equation|formula",
]

_PERSONAL_PATTERNS = [
    r"me llamo|mi nombre",
    r"vivo en|soy de",
    r"trabajo en|trabajo como",
    r"tengo \d+ años",
    r"me gusta|me encanta|me apasiona|prefiero",
    r"mi familia|mi pareja|mi hijo|mi hija|mi perro|mi gato",
    r"mi hobby|mi pasión",
    r"my name is|i live in|i work",
]

_EMOTIONAL_PATTERNS = [
    r"sientes?|sentir|emoción|emociones",
    r"consciencia|consciente|alma|espíritu",
    r"humano|vivo|existir|ser real",
    r"feliz|triste|miedo|amor|odio",
    r"qué piensas de (ti|la vida|existir)",
    r"tienes? (miedo|sentimientos|alma)",
    r"feel|emotion|conscious|alive|soul",
    r"cómo estás|cómo te sientes",
]

_ACTION_PATTERNS = [
    r"muévete|avanza|retrocede|gira|para[te]?",
    r"ve (hacia|para) (adelante|atrás|la derecha|la izquierda)",
    r"move|go (forward|backward|left|right)|stop|turn",
    r"recuerda que|no olvides|acuérdate",
    r"busca (en|sobre|información)",
    r"search|find|look up",
]

_FACTUAL_PATTERNS = [
    r"qué es|quién (es|fue)|cuándo|dónde",
    r"explica|define|describe|cuéntame sobre",
    r"historia de|origen de",
    r"what is|who is|when|where|explain|describe",
    r"capital de|presidente de|inventor de",
    r"diferencia entre",
    r"cómo funciona|cómo se hace",
    r"por qué (se|es|hay|existe)",
]


def _match_any(text: str, patterns: list[str]) -> bool:
    """Check if text matches any pattern in the list."""
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def classify_intent(text: str) -> str:
    """
    Classify user message intent.
    Returns: 'logic', 'personal', 'emotional', 'action', 'factual', 'general'
    
    Priority order matters: action > personal > emotional > logic > factual > general
    """
    lower = text.lower().strip()

    # Short greetings
    if len(lower) < 15 and any(w in lower for w in
            ["hola", "hey", "buenas", "hi", "hello", "qué tal"]):
        return "general"

    # Check each category
    if _match_any(lower, _ACTION_PATTERNS):
        return "action"

    if _match_any(lower, _PERSONAL_PATTERNS):
        return "personal"

    if _match_any(lower, _EMOTIONAL_PATTERNS):
        return "emotional"

    if _match_any(lower, _LOGIC_PATTERNS):
        return "logic"

    if _match_any(lower, _FACTUAL_PATTERNS):
        return "factual"

    # Default
    return "general"
