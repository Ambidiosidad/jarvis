#!/bin/bash
# JARVIS smoke test
# Verifies Docker, core services and basic chat flow.

set -u

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

ok() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo -e "  ${GREEN}OK${NC}  $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo -e "  ${RED}FAIL${NC} $1"
}

warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    echo -e "  ${YELLOW}WARN${NC} $1"
}

dc() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return $?
    fi
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return $?
    fi
    return 1
}

wait_http() {
    local url="$1"
    local label="$2"
    local tries="${3:-30}"
    local i
    for i in $(seq 1 "$tries"); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            ok "$label reachable ($url)"
            return 0
        fi
        sleep 2
    done
    fail "$label not reachable ($url)"
    return 1
}

echo -e "${CYAN}JARVIS smoke test${NC}"
echo ""

if ! command -v docker >/dev/null 2>&1; then
    fail "docker command not found"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    fail "docker daemon is not reachable"
    exit 1
fi
ok "docker daemon reachable"

if ! dc version >/dev/null 2>&1; then
    fail "docker compose is not available (plugin or classic)"
    exit 1
fi
ok "docker compose available"

CORE_CONTAINERS="jarvis_ollama jarvis-memory jarvis-voice jarvis-vision jarvis-brain"
for c in $CORE_CONTAINERS; do
    if docker ps --format '{{.Names}}' | grep -Fxq "$c"; then
        ok "container running: $c"
    else
        fail "container not running: $c"
    fi
done

wait_http "http://localhost:11434/api/tags" "Ollama API" 40
wait_http "http://localhost:8401/health" "jarvis-memory" 30
wait_http "http://localhost:8402/health" "jarvis-voice" 30
wait_http "http://localhost:8405/health" "jarvis-vision" 30
wait_http "http://localhost:8403/health" "jarvis-brain" 30

CHAT_RESPONSE="$(curl -fsS -X POST --get --data-urlencode "message=Hola Jarvis" http://localhost:8403/chat 2>/dev/null || true)"
if echo "$CHAT_RESPONSE" | grep -q '"response"'; then
    ok "chat endpoint returned response payload"
else
    fail "chat endpoint did not return expected JSON"
fi

if docker exec jarvis_ollama ollama list >/dev/null 2>&1; then
    ok "ollama list works inside jarvis_ollama"
else
    warn "ollama list failed inside jarvis_ollama"
fi

VISION_HEALTH="$(curl -fsS http://localhost:8405/health 2>/dev/null || true)"
if echo "$VISION_HEALTH" | grep -q '"camera_available":false'; then
    warn "jarvis-vision is up but no camera device is available"
elif echo "$VISION_HEALTH" | grep -q '"camera_available":true'; then
    ok "jarvis-vision camera device is available"
fi

echo ""
echo "Summary: PASS=$PASS_COUNT FAIL=$FAIL_COUNT WARN=$WARN_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
