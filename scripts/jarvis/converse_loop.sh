#!/bin/bash
# Conversational loop with semantic controls for JARVIS.

set -u

BRAIN_URL="${JARVIS_BRAIN_URL:-http://localhost:8403}"
SESSION_ID="${JARVIS_SESSION_ID:-default}"
USE_VISION="${JARVIS_USE_VISION:-false}"

echo "JARVIS converse loop"
echo "Endpoint: ${BRAIN_URL}/converse"
echo "Session: ${SESSION_ID}"
echo "Base vision flag: ${USE_VISION}"
echo "Type 'salir', 'exit', or 'quit' to finish."
echo "Natural controls examples: 'modo silencio', 'habla', 'activa camara', 'desactiva camara'."
echo ""

while true; do
    read -r -p "Tu: " user_msg

    if [ -z "${user_msg}" ]; then
        continue
    fi

    case "${user_msg}" in
        salir|SALIR|exit|EXIT|quit|QUIT)
            echo "Jarvis: Hasta luego."
            break
            ;;
    esac

    raw="$(curl -fsS -X POST --get \
        --data-urlencode "message=${user_msg}" \
        --data-urlencode "session_id=${SESSION_ID}" \
        --data-urlencode "use_vision=${USE_VISION}" \
        "${BRAIN_URL}/converse" 2>/dev/null || true)"

    if [ -z "${raw}" ]; then
        echo "Jarvis: No pude conectar con ${BRAIN_URL}."
        continue
    fi

    if command -v jq >/dev/null 2>&1; then
        response="$(printf "%s" "${raw}" | jq -r '.response // empty')"
        intent="$(printf "%s" "${raw}" | jq -r '.intent // empty')"
        model="$(printf "%s" "${raw}" | jq -r '.model_used // empty')"
        vision_summary="$(printf "%s" "${raw}" | jq -r '.vision.summary // empty')"
        speaker="$(printf "%s" "${raw}" | jq -r '.session_state.speaker_enabled // empty')"
        mic="$(printf "%s" "${raw}" | jq -r '.session_state.mic_enabled // empty')"
        auto_vision="$(printf "%s" "${raw}" | jq -r '.session_state.auto_vision // empty')"
        controls="$(printf "%s" "${raw}" | jq -c '.controls_applied // {}')"

        if [ -n "${response}" ]; then
            echo "Jarvis: ${response}"
        else
            echo "Jarvis: ${raw}"
        fi

        echo "        [intent=${intent:-n/a} model=${model:-n/a}]"
        echo "        [speaker=${speaker:-n/a} mic=${mic:-n/a} auto_vision=${auto_vision:-n/a}]"
        if [ "${controls}" != "{}" ]; then
            echo "        [controls=${controls}]"
        fi
        if [ -n "${vision_summary}" ]; then
            echo "        [vision=${vision_summary}]"
        fi
    else
        echo "Jarvis: ${raw}"
    fi

    echo ""
done
