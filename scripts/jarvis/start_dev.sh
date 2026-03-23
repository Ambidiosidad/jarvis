#!/bin/bash
echo "J.A.R.V.I.S. — Arrancando entorno de desarrollo..."
cd "$(dirname "$0")/../../extensions"
docker compose -f docker-compose.dev.yml up -d --build
echo ""
echo "Esperando servicios..."
sleep 10
echo "Descargando modelo (si es la primera vez)..."
docker exec jarvis_ollama ollama pull gemma3:1b 2>/dev/null || true
echo ""
echo "════════════════════════════════════════"
echo "  J.A.R.V.I.S. dev listo!"
echo "  Chat:    curl -X POST 'http://localhost:8403/chat?message=Hola'"
echo "  Converse loop:  bash scripts/jarvis/converse_loop.sh"
echo "  Memory:  http://localhost:8401/stats"
echo "  Voice:   http://localhost:8402/health"
echo "  Ollama:  http://localhost:11434"
echo "════════════════════════════════════════"
