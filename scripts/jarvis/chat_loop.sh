#!/bin/bash
# Interactive terminal chat loop for JARVIS brain service.

set -u

BRAIN_URL="${JARVIS_BRAIN_URL:-http://localhost:8403}"

echo "JARVIS chat loop"
echo "Endpoint: ${BRAIN_URL}/chat"
echo "Type your message and press Enter."
echo "Type 'exit' or 'quit' to finish."
echo ""

while true; do
    read -r -p "You: " user_msg

    if [ -z "${user_msg}" ]; then
        continue
    fi

    case "${user_msg}" in
        exit|EXIT|quit|QUIT|salir|SALIR)
            echo "Jarvis: Goodbye."
            break
            ;;
    esac

    raw="$(curl -fsS -X POST --get \
        --data-urlencode "message=${user_msg}" \
        "${BRAIN_URL}/chat" 2>/dev/null || true)"

    if [ -z "${raw}" ]; then
        echo "Jarvis: Could not connect to ${BRAIN_URL}."
        echo "        Verify that jarvis-brain is running."
        continue
    fi

    if command -v jq >/dev/null 2>&1; then
        response="$(printf "%s" "${raw}" | jq -r '.response // empty')"
        intent="$(printf "%s" "${raw}" | jq -r '.intent // empty')"
        model="$(printf "%s" "${raw}" | jq -r '.model_used // empty')"

        if [ -n "${response}" ]; then
            echo "Jarvis: ${response}"
        else
            echo "Jarvis: ${raw}"
        fi

        if [ -n "${intent}" ] || [ -n "${model}" ]; then
            echo "        [intent=${intent:-n/a} model=${model:-n/a}]"
        fi
    else
        echo "Jarvis: ${raw}"
    fi

    echo ""
done
