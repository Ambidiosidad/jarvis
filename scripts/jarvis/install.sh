#!/bin/bash
# ═══════════════════════════════════════════════════════
#  Project J.A.R.V.I.S. — Instalador unificado
#  
#  Un solo comando para instalar todo en Raspberry Pi 5:
#    curl -fsSL https://raw.githubusercontent.com/Ambidiosidad/jarvis/main/scripts/jarvis/install.sh | sudo bash
#
#  O desde el repo clonado:
#    sudo bash scripts/jarvis/install.sh
# ═══════════════════════════════════════════════════════
set -e

# ─── Colores ───
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Variables ───
JARVIS_DIR="/opt/jarvis"
DATA_DIR="/data/jarvis"
REPO_URL="https://github.com/Ambidiosidad/jarvis.git"
KIWIX_DOWNLOAD="https://download.kiwix.org/zim"

# ─── Banner ───
clear
echo -e "${CYAN}"
echo "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗"
echo "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝"
echo "     ██║███████║██████╔╝██║   ██║██║███████╗"
echo "██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║"
echo "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║"
echo " ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"
echo -e "${NC}"
echo -e "${BOLD}Just A Rather Very Intelligent System${NC}"
echo ""
echo "Instalador unificado para Raspberry Pi 5"
echo "═══════════════════════════════════════════"
echo ""

# ─── Verificar root ───
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Ejecuta este script con sudo${NC}"
    echo "  sudo bash install.sh"
    exit 1
fi

# ─── Verificar internet ───
echo -n "Verificando conexión a internet... "
if curl -s --connect-timeout 5 https://1.1.1.1/cdn-cgi/trace > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}SIN CONEXIÓN${NC}"
    echo "Se necesita internet para la instalación inicial."
    exit 1
fi

# ─── Detectar NVMe ───
echo ""
echo -e "${BOLD}[1/8] Detectando almacenamiento...${NC}"
NVME_DEVICE=""
if [ -b /dev/nvme0n1 ]; then
    NVME_DEVICE="/dev/nvme0n1"
    echo -e "  NVMe detectado: ${GREEN}$NVME_DEVICE${NC}"
    
    # Verificar si ya está montado
    if mountpoint -q /data 2>/dev/null; then
        echo -e "  /data ya está montado: ${GREEN}OK${NC}"
    else
        echo -e "  ${YELLOW}NVMe no está montado. ¿Formatear y montar en /data?${NC}"
        echo -e "  ${RED}AVISO: Esto borrará todo el contenido del NVMe${NC}"
        read -p "  ¿Continuar? (s/N): " FORMAT_NVME
        if [[ "$FORMAT_NVME" =~ ^[sS]$ ]]; then
            echo "  Formateando NVMe..."
            parted $NVME_DEVICE --script mklabel gpt
            parted $NVME_DEVICE --script mkpart primary ext4 0% 100%
            mkfs.ext4 -F ${NVME_DEVICE}p1
            mkdir -p /data
            mount ${NVME_DEVICE}p1 /data
            echo "${NVME_DEVICE}p1 /data ext4 defaults,noatime 0 2" >> /etc/fstab
            echo -e "  ${GREEN}NVMe formateado y montado en /data${NC}"
        else
            echo "  Usando almacenamiento en MicroSD (no recomendado)"
            DATA_DIR="/opt/jarvis/data"
        fi
    fi
else
    echo -e "  ${YELLOW}NVMe no detectado. Usando MicroSD.${NC}"
    DATA_DIR="/opt/jarvis/data"
fi

# ─── Configurar swap ───
if [ -d "/data" ]; then
    echo "  Configurando swap en NVMe..."
    dphys-swapfile swapoff 2>/dev/null || true
    sed -i "s|CONF_SWAPFILE=.*|CONF_SWAPFILE=/data/swapfile|" /etc/dphys-swapfile
    sed -i "s|CONF_SWAPSIZE=.*|CONF_SWAPSIZE=4096|" /etc/dphys-swapfile
    dphys-swapfile setup
    dphys-swapfile swapon
    echo -e "  Swap 4GB en NVMe: ${GREEN}OK${NC}"
fi

# ─── Instalar Docker ───
echo ""
echo -e "${BOLD}[2/8] Instalando Docker...${NC}"
if command -v docker &> /dev/null; then
    echo -e "  Docker ya instalado: ${GREEN}$(docker --version)${NC}"
else
    echo "  Instalando Docker..."
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo -e "  ${GREEN}Docker instalado${NC}"
fi

# Redirigir Docker al NVMe si disponible
if [ -d "/data" ] && [ ! -d "/data/docker" ]; then
    echo "  Moviendo Docker al NVMe..."
    systemctl stop docker
    mkdir -p /data/docker
    if [ -d "/var/lib/docker" ]; then
        rsync -aP /var/lib/docker/ /data/docker/ 2>/dev/null || true
    fi
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json <<EOF
{
  "data-root": "/data/docker",
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
    systemctl start docker
    echo -e "  Docker en NVMe: ${GREEN}OK${NC}"
fi

# ─── Instalar dependencias ───
echo ""
echo -e "${BOLD}[3/8] Instalando dependencias del sistema...${NC}"
apt-get update -qq
apt-get install -y -qq \
    git curl wget \
    portaudio19-dev libsndfile1 espeak-ng ffmpeg \
    chromium-browser unclutter xdotool \
    alsa-utils pulseaudio 2>/dev/null
echo -e "  ${GREEN}Dependencias instaladas${NC}"

# ─── Clonar Jarvis ───
echo ""
echo -e "${BOLD}[4/8] Descargando Jarvis...${NC}"
if [ -d "$JARVIS_DIR" ]; then
    echo "  Directorio $JARVIS_DIR ya existe. Actualizando..."
    cd $JARVIS_DIR && git pull 2>/dev/null || true
else
    git clone $REPO_URL $JARVIS_DIR
fi
echo -e "  ${GREEN}Jarvis descargado en $JARVIS_DIR${NC}"

# ─── Crear directorios de datos ───
mkdir -p $DATA_DIR/{ollama,qdrant,memory,voice/models,voice/audio,zim,maps}

# ─── Construir y levantar servicios ───
echo ""
echo -e "${BOLD}[5/8] Construyendo servicios Jarvis...${NC}"
cd $JARVIS_DIR/extensions
docker compose build
docker compose up -d
echo ""

# Esperar a que los servicios arranquen
echo "  Esperando servicios..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8401/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done
echo -e "  ${GREEN}Servicios activos${NC}"

# ─── Modelos de IA ───
echo ""
echo -e "${BOLD}[6/8] Modelos de inteligencia artificial${NC}"
echo ""

# Gemma3 1B
echo -e "  ${CYAN}Gemma3 1B${NC} — Conversación rápida (1.5 GB)"
echo "  Velocidad: ~10-15 tok/s en Pi 5"
read -p "  ¿Descargar? [S/n]: " DL_GEMMA
if [[ ! "$DL_GEMMA" =~ ^[nN]$ ]]; then
    echo "  Descargando gemma3:1b..."
    docker exec jarvis_ollama ollama pull gemma3:1b
    echo -e "  ${GREEN}gemma3:1b instalado${NC}"
fi
echo ""

# Qwen2.5 3B
echo -e "  ${CYAN}Qwen2.5 3B${NC} — Razonamiento y lógica (2 GB)"
echo "  Velocidad: ~4-6 tok/s en Pi 5"
read -p "  ¿Descargar? [S/n]: " DL_QWEN
if [[ ! "$DL_QWEN" =~ ^[nN]$ ]]; then
    echo "  Descargando qwen2.5:3b..."
    docker exec jarvis_ollama ollama pull qwen2.5:3b
    echo -e "  ${GREEN}qwen2.5:3b instalado${NC}"
fi
echo ""

# Embeddings
echo -e "  ${CYAN}nomic-embed-text${NC} — Embeddings para RAG (270 MB)"
echo "  Necesario para búsqueda en documentos"
read -p "  ¿Descargar? [S/n]: " DL_EMBED
if [[ ! "$DL_EMBED" =~ ^[nN]$ ]]; then
    echo "  Descargando nomic-embed-text..."
    docker exec jarvis_ollama ollama pull nomic-embed-text
    echo -e "  ${GREEN}nomic-embed-text instalado${NC}"
fi

echo ""
echo "  Modelos instalados:"
docker exec jarvis_ollama ollama list

# ─── Contenido offline ───
echo ""
echo -e "${BOLD}[7/8] Contenido offline${NC}"
echo ""
echo "  Los archivos ZIM se descargan en $DATA_DIR/zim/"
echo "  Kiwix los servirá automáticamente en http://localhost:8500"
echo ""

SPACE_USED=0

# Wikipedia ES
echo -e "  ${CYAN}Wikipedia Español${NC} (sin imágenes) — ~9 GB"
echo "  Conocimiento general completo en español"
read -p "  ¿Descargar? [S/n]: " DL_WIKI_ES
if [[ ! "$DL_WIKI_ES" =~ ^[nN]$ ]]; then
    echo "  Descargando Wikipedia ES (esto tarda un rato)..."
    wget -q --show-progress -O "$DATA_DIR/zim/wikipedia_es_all_nopic.zim" \
        "$KIWIX_DOWNLOAD/wikipedia/wikipedia_es_all_nopic_2025-11.zim" 2>&1 || \
    echo -e "  ${YELLOW}Descarga no disponible. Descárgala manualmente desde library.kiwix.org${NC}"
    SPACE_USED=$((SPACE_USED + 9))
fi
echo ""

# Wikipedia EN
echo -e "  ${CYAN}Wikipedia English${NC} (sin imágenes) — ~12 GB"
echo "  Contenido más extenso que la versión española"
read -p "  ¿Descargar? [S/n]: " DL_WIKI_EN
if [[ ! "$DL_WIKI_EN" =~ ^[nN]$ ]]; then
    echo "  Descargando Wikipedia EN (esto tarda bastante)..."
    wget -q --show-progress -O "$DATA_DIR/zim/wikipedia_en_all_nopic.zim" \
        "$KIWIX_DOWNLOAD/wikipedia/wikipedia_en_all_nopic_2025-11.zim" 2>&1 || \
    echo -e "  ${YELLOW}Descarga no disponible. Descárgala manualmente desde library.kiwix.org${NC}"
    SPACE_USED=$((SPACE_USED + 12))
fi
echo ""

# Stack Exchange
echo -e "  ${CYAN}Stack Exchange${NC} — ~25 GB"
echo "  Programación, ciencia, tecnología (respuestas de calidad)"
read -p "  ¿Descargar? [s/N]: " DL_STACK
if [[ "$DL_STACK" =~ ^[sS]$ ]]; then
    echo "  Descargando Stack Exchange..."
    wget -q --show-progress -O "$DATA_DIR/zim/stackexchange.zim" \
        "$KIWIX_DOWNLOAD/stack_exchange/stackexchange_en_all.zim" 2>&1 || \
    echo -e "  ${YELLOW}Descarga no disponible. Descárgala manualmente desde library.kiwix.org${NC}"
    SPACE_USED=$((SPACE_USED + 25))
fi
echo ""

# WikiMed
echo -e "  ${CYAN}WikiMed${NC} — ~1 GB"
echo "  Referencia médica especializada"
read -p "  ¿Descargar? [S/n]: " DL_MED
if [[ ! "$DL_MED" =~ ^[nN]$ ]]; then
    echo "  Descargando WikiMed..."
    wget -q --show-progress -O "$DATA_DIR/zim/wikimed.zim" \
        "$KIWIX_DOWNLOAD/other/mdwiki_en_all_nopic.zim" 2>&1 || \
    echo -e "  ${YELLOW}Descarga no disponible. Descárgala manualmente desde library.kiwix.org${NC}"
    SPACE_USED=$((SPACE_USED + 1))
fi
echo ""

# Wikibooks
echo -e "  ${CYAN}Wikibooks ES+EN${NC} — ~2 GB"
echo "  Manuales y tutoriales"
read -p "  ¿Descargar? [S/n]: " DL_BOOKS
if [[ ! "$DL_BOOKS" =~ ^[nN]$ ]]; then
    echo "  Descargando Wikibooks..."
    wget -q --show-progress -O "$DATA_DIR/zim/wikibooks_es.zim" \
        "$KIWIX_DOWNLOAD/wikibooks/wikibooks_es_all_nopic.zim" 2>&1 || true
    wget -q --show-progress -O "$DATA_DIR/zim/wikibooks_en.zim" \
        "$KIWIX_DOWNLOAD/wikibooks/wikibooks_en_all_nopic.zim" 2>&1 || true
    SPACE_USED=$((SPACE_USED + 2))
fi
echo ""

# Wiktionary
echo -e "  ${CYAN}Wiktionary ES${NC} (diccionario) — ~1 GB"
read -p "  ¿Descargar? [S/n]: " DL_DICT
if [[ ! "$DL_DICT" =~ ^[nN]$ ]]; then
    echo "  Descargando Wiktionary ES..."
    wget -q --show-progress -O "$DATA_DIR/zim/wiktionary_es.zim" \
        "$KIWIX_DOWNLOAD/wiktionary/wiktionary_es_all_nopic.zim" 2>&1 || true
    SPACE_USED=$((SPACE_USED + 1))
fi
echo ""

# Reiniciar Kiwix para que detecte los nuevos ZIMs
echo "  Reiniciando Kiwix..."
docker restart jarvis_kiwix 2>/dev/null || true

# ─── Configurar kiosko ───
echo ""
echo -e "${BOLD}[8/8] Configurando pantalla${NC}"
echo ""

read -p "  ¿Configurar pantalla táctil en modo kiosko? [S/n]: " SETUP_KIOSK
if [[ ! "$SETUP_KIOSK" =~ ^[nN]$ ]]; then
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(eval echo ~$REAL_USER)
    
    # Script de arranque del kiosko
    cat > "$REAL_HOME/start_jarvis_kiosk.sh" << 'KIOSK'
#!/bin/bash
echo "J.A.R.V.I.S. — Iniciando interfaz..."
until curl -s http://localhost:8403/health > /dev/null 2>&1; do
    sleep 3
done
unclutter -idle 3 &
xset s off; xset -dpms; xset s noblank
chromium-browser \
    --kiosk --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --disable-translate \
    --no-first-run --start-fullscreen \
    --autoplay-policy=no-user-gesture-required \
    http://localhost:8403/chat
KIOSK
    chmod +x "$REAL_HOME/start_jarvis_kiosk.sh"
    
    # Autostart
    mkdir -p "$REAL_HOME/.config/autostart"
    cat > "$REAL_HOME/.config/autostart/jarvis-kiosk.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=J.A.R.V.I.S. Kiosk
Exec=$REAL_HOME/start_jarvis_kiosk.sh
X-GNOME-Autostart-enabled=true
DESKTOP
    echo -e "  ${GREEN}Kiosko configurado${NC}"
else
    echo "  Kiosko omitido"
fi

# ─── Crear servicio systemd ───
cat > /etc/systemd/system/jarvis.service << EOF
[Unit]
Description=Project J.A.R.V.I.S.
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c "cd $JARVIS_DIR/extensions && docker compose up -d"
ExecStop=/bin/bash -c "cd $JARVIS_DIR/extensions && docker compose down"
WorkingDirectory=$JARVIS_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jarvis.service

# ─── Resumen final ───
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  J.A.R.V.I.S. instalado correctamente!${NC}"
echo ""
echo "  Directorio:    $JARVIS_DIR"
echo "  Datos:         $DATA_DIR"
echo ""
echo "  Servicios:"
echo "    Brain:       http://localhost:8403"
echo "    Memory:      http://localhost:8401"
echo "    Voice:       http://localhost:8402"
echo "    Ollama:      http://localhost:11434"
echo "    Kiwix:       http://localhost:8500"
echo "    Qdrant:      http://localhost:6333"
echo ""

# Calcular espacio
if [ -d "/data" ]; then
    USED=$(df -h /data | tail -1 | awk '{print $3}')
    AVAIL=$(df -h /data | tail -1 | awk '{print $4}')
    echo "  Almacenamiento: $USED usado / $AVAIL disponible"
fi

echo ""
echo "  Modelos IA:"
docker exec jarvis_ollama ollama list 2>/dev/null || echo "    (verificar después)"
echo ""
echo -e "  ${YELLOW}Ya puedes desconectar internet.${NC}"
echo -e "  ${YELLOW}Jarvis funcionará 100% offline.${NC}"
echo ""
echo "  Comandos útiles:"
echo "    Hablar con Jarvis:   curl -X POST 'http://localhost:8403/chat?message=Hola'"
echo "    Ver memoria:         curl http://localhost:8401/stats"
echo "    Ver emociones:       curl http://localhost:8401/emotions/current"
echo "    Estado del sistema:  curl http://localhost:8403/status"
echo "    Reiniciar:           sudo systemctl restart jarvis"
echo "    Parar:               sudo systemctl stop jarvis"
echo "    Wikipedia offline:   http://localhost:8500"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
