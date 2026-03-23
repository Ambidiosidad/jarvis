#!/bin/bash
# Interactive terminal chat loop for JARVIS brain service.

set -u

BRAIN_URL="${JARVIS_BRAIN_URL:-http://localhost:8403}"
USE_VISION="${JARVIS_USE_VISION:-false}"

echo "JARVIS chat loop"
echo "Endpoint: ${BRAIN_URL}/chat"
echo "Vision mode: ${USE_VISION}"
echo "Type your message and press Enter."
echo "Type 'salir', 'exit', or 'quit' to finish."
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
        --data-urlencode "use_vision=${USE_VISION}" \
        "${BRAIN_URL}/chat" 2>/dev/null || true)"

    if [ -z "${raw}" ]; then
        echo "Jarvis: No pude conectar con el servicio brain en ${BRAIN_URL}."
        echo "        Revisa que jarvis-brain este levantado."
        continue
    fi

    if command -v jq >/dev/null 2>&1; then
        response="$(printf "%s" "${raw}" | jq -r '.response // empty')"
        intent="$(printf "%s" "${raw}" | jq -r '.intent // empty')"
        model="$(printf "%s" "${raw}" | jq -r '.model_used // empty')"
        vision_summary="$(printf "%s" "${raw}" | jq -r '.vision.summary // empty')"

        if [ -n "${response}" ]; then
            echo "Jarvis: ${response}"
        else
            echo "Jarvis: ${raw}"
        fi

        if [ -n "${intent}" ] || [ -n "${model}" ]; then
            echo "        [intent=${intent:-n/a} model=${model:-n/a}]"
        fi
        if [ -n "${vision_summary}" ]; then
            echo "        [vision=${vision_summary}]"
        fi
    else
        # Fallback without jq: print raw JSON.
        echo "Jarvis: ${raw}"
    fi

    echo ""
done
