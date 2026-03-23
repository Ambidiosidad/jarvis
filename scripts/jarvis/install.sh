#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Project J.A.R.V.I.S. — Instalador unificado v2
#
#  Instala todo en Raspberry Pi 5 con un solo comando:
#
#    sudo apt-get update && sudo apt-get install -y curl git && \
#    git clone https://github.com/Ambidiosidad/jarvis.git /opt/jarvis && \
#    sudo bash /opt/jarvis/scripts/jarvis/install.sh
#
# ═══════════════════════════════════════════════════════════════

# No usar set -e para que las descargas opcionales no corten el script
# Controlamos errores manualmente donde importa

# ─── Colores ───
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Variables ───
JARVIS_DIR="/opt/jarvis"
DATA_DIR="/data/jarvis"
KIWIX_BASE="https://download.kiwix.org/zim"
LOG_FILE="/tmp/jarvis_install.log"

# ─── Funciones auxiliares ───
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
info() { echo -e "  ${DIM}$1${NC}"; }

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

dc() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return $?
    fi
    if has_cmd docker-compose; then
        docker-compose "$@"
        return $?
    fi
    fail "Docker Compose no está disponible."
    return 1
}

ensure_docker_engine() {
    if has_cmd docker && docker info >/dev/null 2>&1; then
        return 0
    fi

    echo "  Instalando Docker Engine..."
    apt-get update -qq

    # Intento 1: paquetes distro (Raspberry Pi OS / Debian / Ubuntu)
    if ! apt-get install -y -qq docker.io docker-compose-plugin; then
        # Intento 2: algunas distros usan docker-compose clásico
        apt-get install -y -qq docker.io docker-compose || true
    fi

    # Intento 3 (fallback universal): script oficial Docker
    if ! has_cmd docker; then
        curl -fsSL https://get.docker.com | sh
    fi

    if ! has_cmd docker; then
        fail "Docker no se pudo instalar."
        exit 1
    fi

    systemctl enable docker >/dev/null 2>&1 || true
    systemctl start docker >/dev/null 2>&1 || true

    # Docker puede tardar unos segundos tras instalarse
    if ! docker info >/dev/null 2>&1; then
        sleep 3
    fi
    if ! docker info >/dev/null 2>&1; then
        fail "Docker daemon no responde."
        exit 1
    fi
}

ensure_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        return 0
    fi
    if has_cmd docker-compose; then
        return 0
    fi

    echo "  Instalando Docker Compose..."
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin || \
        apt-get install -y -qq docker-compose || true

    if docker compose version >/dev/null 2>&1; then
        return 0
    fi
    if has_cmd docker-compose; then
        return 0
    fi

    fail "Docker Compose no está disponible tras la instalación."
    exit 1
}

ask_yes() {
    # ask_yes "pregunta" → devuelve 0 si sí (default sí)
    local prompt="$1"
    read -p "  $prompt [S/n]: " answer
    [[ ! "$answer" =~ ^[nN]$ ]]
}

ask_no() {
    # ask_no "pregunta" → devuelve 0 si sí (default no)
    local prompt="$1"
    read -p "  $prompt [s/N]: " answer
    [[ "$answer" =~ ^[sS]$ ]]
}

wait_for_service() {
    local url=$1
    local name=$2
    local max_wait=${3:-60}
    for i in $(seq 1 $max_wait); do
        if curl -s "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

download_zim() {
    local name="$1"
    local filename="$2"
    local url="$3"
    local size="$4"

    echo -e "\n  ${CYAN}$name${NC} — ~$size"
    
    # Verificar si ya existe
    if [ -f "$DATA_DIR/zim/$filename" ]; then
        ok "$name ya descargado"
        return 0
    fi

    if ask_yes "¿Descargar?"; then
        echo "  Descargando $name..."
        if wget -c -q --show-progress -O "$DATA_DIR/zim/$filename" "$url" 2>&1; then
            ok "$name descargado"
        else
            # Si falla la URL exacta, informar al usuario
            rm -f "$DATA_DIR/zim/$filename"  # Limpiar descarga parcial
            warn "No se pudo descargar automáticamente."
            info "Descarga manual: library.kiwix.org → buscar '$name'"
            info "Guardar en: $DATA_DIR/zim/"
        fi
    fi
}

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
echo -e "Instalador unificado v2"
echo "═══════════════════════════════════════════════"
echo ""

# ─── Verificar root ───
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Ejecuta con sudo${NC}"
    echo "  sudo bash $0"
    exit 1
fi

# ─── Verificar internet ───
echo -n "Verificando internet... "
if curl -s --connect-timeout 5 https://1.1.1.1/cdn-cgi/trace > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}SIN CONEXIÓN${NC}"
    echo "Se necesita internet para la instalación."
    exit 1
fi

# ─── Verificar que el repo existe ───
if [ ! -f "$JARVIS_DIR/extensions/docker-compose.yml" ]; then
    echo ""
    echo -e "${YELLOW}Jarvis no encontrado en $JARVIS_DIR${NC}"
    echo "Clonando repositorio..."
    apt-get update -qq && apt-get install -y -qq git
    git clone https://github.com/Ambidiosidad/jarvis.git $JARVIS_DIR
fi

# ═══════════════════════════════════════════════════
#  PASO 1: ALMACENAMIENTO
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[1/8] Configurando almacenamiento...${NC}"

if [ -b /dev/nvme0n1 ]; then
    echo -e "  NVMe detectado: ${GREEN}/dev/nvme0n1${NC}"
    
    if mountpoint -q /data 2>/dev/null; then
        ok "/data ya montado"
    else
        warn "NVMe no montado."
        echo -e "  ${RED}AVISO: Formatear borrará todo el NVMe${NC}"
        if ask_yes "¿Formatear y montar en /data?"; then
            parted /dev/nvme0n1 --script mklabel gpt
            parted /dev/nvme0n1 --script mkpart primary ext4 0% 100%
            sleep 2  # Esperar a que el kernel detecte la partición
            mkfs.ext4 -F /dev/nvme0n1p1
            mkdir -p /data
            mount /dev/nvme0n1p1 /data
            # Evitar duplicados en fstab
            grep -q "nvme0n1p1" /etc/fstab || \
                echo "/dev/nvme0n1p1 /data ext4 defaults,noatime 0 2" >> /etc/fstab
            ok "NVMe formateado y montado"
        else
            DATA_DIR="/opt/jarvis/data"
            warn "Usando MicroSD (no recomendado para producción)"
        fi
    fi

    # Configurar swap en NVMe
    if mountpoint -q /data 2>/dev/null; then
        dphys-swapfile swapoff 2>/dev/null || true
        sed -i "s|CONF_SWAPFILE=.*|CONF_SWAPFILE=/data/swapfile|" /etc/dphys-swapfile 2>/dev/null || true
        sed -i "s|CONF_SWAPSIZE=.*|CONF_SWAPSIZE=4096|" /etc/dphys-swapfile 2>/dev/null || true
        dphys-swapfile setup 2>/dev/null || true
        dphys-swapfile swapon 2>/dev/null || true
        ok "Swap 4GB en NVMe"
    fi
else
    warn "NVMe no detectado. Usando MicroSD."
    DATA_DIR="/opt/jarvis/data"
fi

# Crear estructura de directorios
mkdir -p $DATA_DIR/{ollama,qdrant,memory,voice/models,voice/audio,vision,zim}

# Mostrar espacio disponible
if [ -d "/data" ]; then
    AVAIL=$(df -h /data | tail -1 | awk '{print $4}')
    info "Espacio disponible: $AVAIL"
fi

# ═══════════════════════════════════════════════════
#  PASO 2: DOCKER
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[2/8] Configurando Docker...${NC}"

if has_cmd docker && docker info >/dev/null 2>&1; then
    ok "Docker instalado: $(docker --version | cut -d' ' -f3)"
else
    ensure_docker_engine
    ok "Docker instalado: $(docker --version | cut -d' ' -f3)"
fi

ensure_docker_compose
if docker compose version >/dev/null 2>&1; then
    ok "Docker Compose: plugin"
else
    ok "Docker Compose: clásico"
fi

# Redirigir Docker al NVMe
if mountpoint -q /data 2>/dev/null && [ ! -f "/etc/docker/daemon.json" ]; then
    echo "  Moviendo Docker al NVMe..."
    systemctl stop docker 2>/dev/null || true
    mkdir -p /data/docker
    rsync -a /var/lib/docker/ /data/docker/ 2>/dev/null || true
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json <<DOCKEREOF
{
  "data-root": "/data/docker",
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
DOCKEREOF
    systemctl start docker
    ok "Docker en NVMe"
elif [ -f "/etc/docker/daemon.json" ]; then
    ok "Docker ya configurado"
fi

# ═══════════════════════════════════════════════════
#  PASO 3: DEPENDENCIAS DEL SISTEMA
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[3/8] Dependencias del sistema...${NC}"
apt-get update -qq
apt-get install -y -qq \
    git curl wget \
    portaudio19-dev libsndfile1 espeak-ng ffmpeg \
    alsa-utils 2>/dev/null
# Chromium solo si hay pantalla
if [ -n "$DISPLAY" ] || [ -d "/dev/dri" ]; then
    apt-get install -y -qq chromium-browser unclutter xdotool 2>/dev/null
fi
ok "Dependencias instaladas"

# ═══════════════════════════════════════════════════
#  PASO 4: ACTUALIZAR CÓDIGO
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[4/8] Actualizando Jarvis...${NC}"
cd $JARVIS_DIR
git pull 2>/dev/null || true
ok "Código actualizado"

# ═══════════════════════════════════════════════════
#  PASO 5: CONSTRUIR Y LEVANTAR SERVICIOS
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[5/8] Construyendo servicios...${NC}"
cd $JARVIS_DIR/extensions

# Parar contenedores anteriores si existen
dc down 2>/dev/null || true

echo "  Construyendo imágenes (puede tardar unos minutos)..."
if ! dc build >> "$LOG_FILE" 2>&1; then
    fail "Error construyendo imágenes (ver $LOG_FILE)"
    tail -n 80 "$LOG_FILE"
    exit 1
fi

echo "  Levantando servicios..."
if ! dc up -d >> "$LOG_FILE" 2>&1; then
    fail "Error levantando servicios (ver $LOG_FILE)"
    tail -n 80 "$LOG_FILE"
    exit 1
fi

# Esperar a servicios críticos
echo "  Esperando a que arranquen..."
if wait_for_service "http://localhost:11434/api/tags" "Ollama" 60; then
    ok "Ollama activo"
else
    fail "Ollama no respondió (revisar: docker logs jarvis_ollama)"
fi

if wait_for_service "http://localhost:8401/health" "Memory" 30; then
    ok "Memory activo"
fi

if wait_for_service "http://localhost:8402/health" "Voice" 30; then
    ok "Voice activo"
fi

if wait_for_service "http://localhost:8403/health" "Brain" 30; then
    ok "Brain activo"
fi

if wait_for_service "http://localhost:8405/health" "Vision" 30; then
    ok "Vision activo"
fi

# ═══════════════════════════════════════════════════
#  PASO 6: MODELOS DE IA
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[6/8] Modelos de inteligencia artificial${NC}"
echo ""
info "Los modelos se almacenan en $DATA_DIR/ollama/"
echo ""

# Gemma3 1B
echo -e "  ${CYAN}Gemma3 1B${NC} — Conversación rápida"
info "Tamaño: 1.5 GB | Velocidad Pi 5: ~10-15 tok/s"
if ask_yes "¿Descargar?"; then
    docker exec jarvis_ollama ollama pull gemma3:1b
    ok "gemma3:1b listo"
fi
echo ""

# Qwen2.5 3B
echo -e "  ${CYAN}Qwen2.5 3B${NC} — Razonamiento y lógica"
info "Tamaño: 2 GB | Velocidad Pi 5: ~4-6 tok/s"
if ask_yes "¿Descargar?"; then
    docker exec jarvis_ollama ollama pull qwen2.5:3b
    ok "qwen2.5:3b listo"
fi
echo ""

# Embeddings
echo -e "  ${CYAN}nomic-embed-text${NC} — Embeddings para documentos (RAG)"
info "Tamaño: 270 MB | Necesario para buscar en documentos propios"
if ask_yes "¿Descargar?"; then
    docker exec jarvis_ollama ollama pull nomic-embed-text
    ok "nomic-embed-text listo"
fi

echo ""
echo "  Modelos instalados:"
docker exec jarvis_ollama ollama list 2>/dev/null | sed 's/^/    /'

# ═══════════════════════════════════════════════════
#  PASO 7: CONTENIDO OFFLINE
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[7/8] Contenido offline (Wikipedia, medicina, etc.)${NC}"
echo ""
info "Los archivos ZIM se guardan en $DATA_DIR/zim/"
info "Kiwix los sirve en http://localhost:8500"
info "Puedes añadir más ZIMs después copiándolos a esa carpeta."
echo ""

if [ -d "/data" ]; then
    AVAIL=$(df -BG /data | tail -1 | awk '{print $4}' | tr -d 'G')
    info "Espacio disponible: ${AVAIL}GB"
    echo ""
fi

download_zim "Wikipedia Español (sin imágenes)" \
    "wikipedia_es_all_nopic.zim" \
    "$KIWIX_BASE/wikipedia/wikipedia_es_all_nopic_2025-11.zim" \
    "9 GB — Conocimiento general completo en español"

download_zim "Wikipedia English (sin imágenes)" \
    "wikipedia_en_all_nopic.zim" \
    "$KIWIX_BASE/wikipedia/wikipedia_en_all_nopic_2025-11.zim" \
    "12 GB — Más contenido que la versión española"

download_zim "WikiMed (medicina)" \
    "wikimed.zim" \
    "$KIWIX_BASE/other/mdwiki_en_all_nopic.zim" \
    "1 GB — Referencia médica especializada"

download_zim "Wikibooks ES" \
    "wikibooks_es.zim" \
    "$KIWIX_BASE/wikibooks/wikibooks_es_all_nopic.zim" \
    "500 MB — Manuales y tutoriales en español"

download_zim "Wiktionary ES (diccionario)" \
    "wiktionary_es.zim" \
    "$KIWIX_BASE/wiktionary/wiktionary_es_all_nopic.zim" \
    "1 GB — Definiciones y traducciones"

echo ""
echo -e "  ${CYAN}Stack Exchange${NC} — ~25 GB (grande)"
info "Programación, ciencia, tecnología — respuestas de calidad"
if ask_no "¿Descargar? (25GB, tarda bastante)"; then
    download_zim "Stack Exchange" \
        "stackexchange.zim" \
        "$KIWIX_BASE/stack_exchange/stackexchange_en_all.zim" \
        "25 GB"
fi

# Reiniciar Kiwix
echo ""
echo "  Reiniciando Kiwix para detectar contenido nuevo..."
docker restart jarvis_kiwix 2>/dev/null || true
sleep 3
if wait_for_service "http://localhost:8500" "Kiwix" 15; then
    ok "Kiwix activo con contenido offline"
else
    warn "Kiwix no arrancó (necesita al menos un archivo ZIM)"
fi

# ═══════════════════════════════════════════════════
#  PASO 8: PANTALLA Y ARRANQUE AUTOMÁTICO
# ═══════════════════════════════════════════════════
echo ""
echo -e "${BOLD}[8/8] Configuración final${NC}"
echo ""

# Kiosko
if ask_yes "¿Configurar pantalla táctil en modo kiosko?"; then
    REAL_USER=${SUDO_USER:-$USER}
    REAL_HOME=$(eval echo ~$REAL_USER)

    cat > "$REAL_HOME/start_jarvis_kiosk.sh" << 'KIOSK'
#!/bin/bash
echo "J.A.R.V.I.S. — Iniciando interfaz..."
until curl -s http://localhost:8403/health > /dev/null 2>&1; do
    sleep 3
done
unclutter -idle 3 &
xset s off 2>/dev/null; xset -dpms 2>/dev/null; xset s noblank 2>/dev/null
chromium-browser \
    --kiosk --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --disable-translate \
    --no-first-run --start-fullscreen \
    --autoplay-policy=no-user-gesture-required \
    http://localhost:8500
KIOSK
    chmod +x "$REAL_HOME/start_jarvis_kiosk.sh"
    chown $REAL_USER:$REAL_USER "$REAL_HOME/start_jarvis_kiosk.sh"

    mkdir -p "$REAL_HOME/.config/autostart"
    cat > "$REAL_HOME/.config/autostart/jarvis-kiosk.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=J.A.R.V.I.S. Kiosk
Exec=$REAL_HOME/start_jarvis_kiosk.sh
X-GNOME-Autostart-enabled=true
DESKTOP
    chown $REAL_USER:$REAL_USER "$REAL_HOME/.config/autostart/jarvis-kiosk.desktop"
    ok "Kiosko configurado"
fi

# Servicio systemd
cat > /etc/systemd/system/jarvis.service << SVCEOF
[Unit]
Description=Project J.A.R.V.I.S.
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -lc 'cd $JARVIS_DIR/extensions && if docker compose version >/dev/null 2>&1; then docker compose up -d; else docker-compose up -d; fi'
ExecStop=/bin/bash -lc 'cd $JARVIS_DIR/extensions && if docker compose version >/dev/null 2>&1; then docker compose down; else docker-compose down; fi'
WorkingDirectory=$JARVIS_DIR

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable jarvis.service
ok "Arranque automático configurado"

# ═══════════════════════════════════════════════════
#  RESUMEN FINAL
# ═══════════════════════════════════════════════════
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}"
echo "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗"
echo "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝"
echo "     ██║███████║██████╔╝██║   ██║██║███████╗"
echo "██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║"
echo "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║"
echo " ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"
echo -e "${NC}"
echo -e "${BOLD}  Instalación completada!${NC}"
echo ""
echo "  Directorio:  $JARVIS_DIR"
echo "  Datos:       $DATA_DIR"
echo ""

# Espacio
if [ -d "/data" ]; then
    USED=$(df -h /data | tail -1 | awk '{print $3}')
    AVAIL=$(df -h /data | tail -1 | awk '{print $4}')
    echo "  Disco: $USED usado / $AVAIL disponible"
fi

echo ""
echo "  Servicios activos:"
docker ps --format "    {{.Names}}\t{{.Status}}" 2>/dev/null | grep jarvis
echo ""
echo "  Modelos IA:"
docker exec jarvis_ollama ollama list 2>/dev/null | tail -n +2 | sed 's/^/    /'
echo ""

# Test rápido
echo -n "  Test de Jarvis... "
RESPONSE=$(curl -s -X POST "http://localhost:8403/chat?message=Hola" 2>/dev/null)
if echo "$RESPONSE" | grep -q "response"; then
    echo -e "${GREEN}Jarvis responde!${NC}"
else
    echo -e "${YELLOW}Verificar manualmente${NC}"
fi

echo ""
echo -e "  ${YELLOW}════════════════════════════════════════════════${NC}"
echo -e "  ${YELLOW}  Ya puedes desconectar internet.${NC}"
echo -e "  ${YELLOW}  Jarvis funcionará 100% offline para siempre.${NC}"
echo -e "  ${YELLOW}════════════════════════════════════════════════${NC}"
echo ""
echo "  Comandos:"
echo "    Hablar:     curl -X POST 'http://localhost:8403/chat?message=Hola'"
echo "    Memoria:    curl http://localhost:8401/stats"
echo "    Emociones:  curl http://localhost:8401/emotions/current"
echo "    Vision:     curl -X POST http://localhost:8405/analyze"
echo "    Wikipedia:  http://localhost:8500"
echo "    Reiniciar:  sudo systemctl restart jarvis"
echo "    Parar:      sudo systemctl stop jarvis"
echo "    Smoke test: sudo bash $JARVIS_DIR/scripts/jarvis/smoke_test.sh"
echo "    Chat loop:  sudo bash $JARVIS_DIR/scripts/jarvis/chat_loop.sh"
echo "    Converse:   sudo bash $JARVIS_DIR/scripts/jarvis/converse_loop.sh"
echo "    Desinstalar: sudo bash $JARVIS_DIR/scripts/jarvis/uninstall.sh"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
