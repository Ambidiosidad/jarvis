"""
J.A.R.V.I.S. Emotion Analyzer
================================
Analiza la conversación y actualiza el estado emocional
automáticamente, sin depender de que el LLM genere JSONs.

Funciona con CUALQUIER modelo, incluido Gemma3 1B.
"""
import re


# Keywords that indicate emotional signals
_POSITIVE = {
    "gracias", "genial", "perfecto", "me encanta", "increíble",
    "muy bien", "excelente", "fantástico", "maravilla", "guay",
    "mola", "thanks", "great", "awesome", "love", "amazing",
    "jaja", "jeje", "haha", "😊", "👍", ":)", "bien hecho"
}
_NEGATIVE = {
    "mal", "error", "equivocado", "no entiendes", "incorrecto",
    "wrong", "bad", "horrible", "fatal", "no sirve", "inútil",
    "no funciona", "falla", "bug", "frustra", "pesado"
}
_PERSONAL = {
    "me llamo", "mi nombre", "vivo en", "trabajo en", "mi familia",
    "mi pareja", "mis hijos", "tengo", "años", "mi hobby",
    "me gusta", "mi favorito", "prefiero", "odio", "mi casa",
    "my name", "i live", "i work", "i like", "i love", "i hate"
}
_CURIOSITY = {
    "qué opinas", "qué piensas", "crees que", "sabes sobre",
    "cuéntame", "explica", "por qué", "cómo funciona",
    "what do you think", "tell me about", "how does", "why"
}
_DEEP = {
    "sientes", "emoción", "consciencia", "alma", "sentir",
    "humano", "vivo", "existir", "pensar", "feel", "emotion",
    "conscious", "alive", "soul", "exist"
}


def analyze_user_message(text: str) -> dict:
    """
    Analyze user message and return emotion deltas.
    Returns dict with mood suggestion and value adjustments.
    """
    lower = text.lower()
    words = set(lower.split())
    result = {
        "mood": None,
        "energy_delta": 0.0,
        "patience_delta": 0.0,
        "bond_delta": 0.0,
        "reason": None
    }

    # Check message length (longer = more engagement)
    if len(text) > 200:
        result["energy_delta"] += 0.05
        result["bond_delta"] += 0.02

    # Positive signals
    if any(kw in lower for kw in _POSITIVE):
        result["mood"] = "happy"
        result["energy_delta"] += 0.1
        result["patience_delta"] += 0.05
        result["bond_delta"] += 0.05
        result["reason"] = "El usuario expresó satisfacción"

    # Negative signals
    if any(kw in lower for kw in _NEGATIVE):
        result["mood"] = "empathetic"
        result["energy_delta"] -= 0.05
        result["patience_delta"] += 0.1  # More patient when user is frustrated
        result["reason"] = "El usuario parece frustrado, aumento paciencia"

    # Personal sharing
    if any(kw in lower for kw in _PERSONAL):
        result["mood"] = "empathetic"
        result["bond_delta"] += 0.08
        result["energy_delta"] += 0.05
        result["reason"] = "El usuario compartió información personal"

    # Curiosity triggers
    if any(kw in lower for kw in _CURIOSITY):
        result["mood"] = "curious"
        result["energy_delta"] += 0.05
        result["reason"] = "El usuario hizo una pregunta interesante"

    # Deep/philosophical questions
    if any(kw in lower for kw in _DEEP):
        result["mood"] = "thoughtful"
        result["energy_delta"] += 0.1
        result["bond_delta"] += 0.05
        result["reason"] = "Conversación profunda sobre consciencia"

    # Question marks = engagement
    if text.count("?") >= 2:
        result["energy_delta"] += 0.03
        if not result["mood"]:
            result["mood"] = "curious"
            result["reason"] = "El usuario hace muchas preguntas"

    # Default: gradual bond increase just from talking
    if not result["reason"]:
        result["bond_delta"] += 0.01
        result["energy_delta"] += 0.02
        result["reason"] = "Conversación continuada"

    return result


def analyze_conversation_sentiment(user_msg: str, bot_response: str,
                                   current_emotion: dict) -> dict:
    """
    Full analysis: user message + bot response + current state.
    Returns a complete new emotional state.
    """
    analysis = analyze_user_message(user_msg)

    # Calculate new values with bounds
    new_energy = max(0.0, min(1.0,
        current_emotion.get("energy", 0.5) + analysis["energy_delta"]))
    new_patience = max(0.0, min(1.0,
        current_emotion.get("patience", 0.8) + analysis["patience_delta"]))
    new_bond = max(0.0, min(1.0,
        current_emotion.get("bond", 0.1) + analysis["bond_delta"]))

    # Bond grows slowly, never decreases from conversation
    if new_bond < current_emotion.get("bond", 0.1):
        new_bond = current_emotion.get("bond", 0.1)

    # Energy slowly decays toward 0.5 (equilibrium)
    energy_diff = new_energy - 0.5
    new_energy = 0.5 + energy_diff * 0.95  # 5% decay toward center

    return {
        "mood": analysis["mood"] or current_emotion.get("mood", "neutral"),
        "energy": round(new_energy, 2),
        "patience": round(new_patience, 2),
        "bond": round(new_bond, 3),
        "reason": analysis["reason"] or "Estado estable"
    }
