#!/bin/bash
# ═══════════════════════════════════════════════════════
#  J.A.R.V.I.S. — Desinstalador
# ═══════════════════════════════════════════════════════
set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${YELLOW}J.A.R.V.I.S. — Desinstalación${NC}"
echo ""
echo -e "${RED}AVISO: Esto eliminará Jarvis y todos sus datos.${NC}"
echo "Esto incluye: memoria, emociones, modelos IA, Wikipedia, mapas."
echo ""
read -p "¿Estás seguro? Escribe 'BORRAR' para confirmar: " CONFIRM

if [ "$CONFIRM" != "BORRAR" ]; then
    echo "Cancelado."
    exit 0
fi

echo ""
echo "Parando servicios..."
cd /opt/jarvis/extensions 2>/dev/null && docker compose down 2>/dev/null || true

echo "Eliminando contenedores e imágenes..."
docker rm -f jarvis_ollama jarvis_qdrant jarvis_kiwix jarvis-memory jarvis-voice jarvis-brain jarvis-motors 2>/dev/null || true

echo "Eliminando servicio systemd..."
systemctl stop jarvis 2>/dev/null || true
systemctl disable jarvis 2>/dev/null || true
rm -f /etc/systemd/system/jarvis.service
systemctl daemon-reload

read -p "¿Borrar también los datos (/data/jarvis)? [s/N]: " DEL_DATA
if [[ "$DEL_DATA" =~ ^[sS]$ ]]; then
    echo "Eliminando datos..."
    rm -rf /data/jarvis
    echo -e "${GREEN}Datos eliminados${NC}"
fi

echo "Eliminando código..."
rm -rf /opt/jarvis

echo ""
echo -e "${GREEN}J.A.R.V.I.S. desinstalado.${NC}"
