# 🤖 Project J.A.R.V.I.S.

### Just A Rather Very Intelligent System

Un asistente de IA offline con memoria persistente, conversación por voz,
pantalla táctil integrada y capacidad de movimiento robótico — todo corriendo
en una Raspberry Pi 5.

> Construido sobre la base de [Project N.O.M.A.D.](https://github.com/Crosstalk-Solutions/project-nomad)
> (Apache 2.0) de Crosstalk Solutions, al que extendemos con capas de
> memoria, voz, orquestación inteligente y control robótico.

---

## ¿Qué es Jarvis?

Jarvis toma el stack de N.O.M.A.D. (servidor offline con Wikipedia, mapas, IA local
y herramientas) y lo transforma en un **robot conversacional autónomo** con
personalidad, memoria a largo plazo y cuerpo físico.

**Todo funciona 100% offline.** Internet solo se necesita durante la instalación.

### Stack base (heredado de N.O.M.A.D.)

| Capacidad | Motor | Descripción |
|---|---|---|
| IA conversacional | Ollama + Qdrant | Chat con RAG y búsqueda semántica |
| Biblioteca offline | Kiwix | Wikipedia, medicina, supervivencia |
| Educación | Kolibri | Khan Academy offline |
| Mapas | ProtoMaps | Mapas regionales offline |
| Herramientas | CyberChef | Cifrado, codificación, análisis |
| Notas | FlatNotes | Notas Markdown locales |

### Extensiones Jarvis (nuevas)

| Servicio | Puerto | Descripción |
|---|---|---|
| `jarvis-memory` | 8401 | Memoria persistente entre sesiones (SQLite) |
| `jarvis-voice` | 8402 | STT (Whisper) + TTS (espeak-ng) offline |
| `jarvis-brain` | 8403 | Orquestador con personalidad y tool-use |
| `jarvis-motors` | 8404 | Control de motores DC vía GPIO (Fase 2) |

---

## Desarrollo local (sin Raspberry Pi)

Puedes desarrollar y testear Jarvis en tu PC con Docker:

```bash
# Clonar
git clone https://github.com/Ambidiosidad/project-jarvis.git
cd project-jarvis

# Levantar entorno de desarrollo
cd extensions
docker compose -f docker-compose.dev.yml up -d --build

# Descargar modelo de IA (primera vez, requiere internet)
docker exec nomad_ollama ollama pull gemma3:1b

# Hablar con Jarvis
curl -X POST "http://localhost:8403/chat?message=Hola Jarvis, quién eres?"
```

## Despliegue en Raspberry Pi 5

```bash
# 1. Instalar N.O.M.A.D. base
sudo apt-get update && sudo apt-get install -y curl
curl -fsSL https://raw.githubusercontent.com/Crosstalk-Solutions/project-nomad/refs/heads/main/install/install_nomad.sh \
  -o install_nomad.sh && sudo bash install_nomad.sh

# 2. Clonar Jarvis
cd /data && git clone https://github.com/Ambidiosidad/project-jarvis.git
cd project-jarvis/extensions

# 3. Levantar extensiones (usa la red de N.O.M.A.D.)
docker compose up -d --build
```

---

## Estructura del proyecto

```
project-jarvis/
├── admin/                       ← N.O.M.A.D. Command Center (TypeScript)
├── collections/                 ← N.O.M.A.D. colecciones de contenido
├── install/                     ← N.O.M.A.D. scripts de instalación
├── extensions/                  ← JARVIS — extensiones nuevas
│   ├── docker-compose.yml       ←   Producción (Pi 5 + N.O.M.A.D.)
│   ├── docker-compose.dev.yml   ←   Desarrollo (PC, standalone)
│   ├── memory/                  ←   Memoria persistente
│   ├── voice/                   ←   STT + TTS offline
│   ├── brain/                   ←   Orquestador inteligente
│   └── motors/                  ←   Control GPIO (Fase 2)
├── scripts/jarvis/              ← Scripts Jarvis
├── config/jarvis/               ← Configuración
├── docs/jarvis/                 ← Documentación
├── Dockerfile                   ← N.O.M.A.D. original
└── README.md                    ← Este archivo
```

## Verificación offline

| Componente | Tecnología | Offline |
|---|---|---|
| Conversación IA | Ollama (Gemma3 1B) | ✅ ~5-15 tok/s en Pi 5 |
| Voz → Texto | Whisper tiny | ✅ Modelo local 75MB |
| Texto → Voz | espeak-ng | ✅ Motor TTS local |
| Memoria | SQLite | ✅ Archivo en NVMe |
| Wikipedia | Kiwix (ZIM) | ✅ Pre-descargado |
| Mapas | ProtoMaps | ✅ Pre-descargado |
| RAG documentos | Qdrant + Ollama | ✅ Embeddings locales |
| Control motores | RPi.GPIO | ✅ Hardware directo |

## Roadmap

- [x] Arquitectura y diseño
- [x] Código de extensiones (memory, voice, brain, motors)
- [x] Docker Compose dev + producción
- [ ] **Fase 1** — Cerebro + Pantalla + Voz en Pi 5
- [ ] **Fase 2** — Movimiento robótico
- [ ] **Fase 3** — Cámara + Visión
- [ ] **Fase 4** — Personalidad avanzada

## Créditos

- [Project N.O.M.A.D.](https://github.com/Crosstalk-Solutions/project-nomad) (Apache 2.0) — Base del sistema
- [Ollama](https://ollama.com/) — LLM local
- [Whisper](https://github.com/openai/whisper) — Speech-to-text
- [Qdrant](https://qdrant.tech/) — Vector database
- [Kiwix](https://kiwix.org/) — Contenido offline

## Licencia

Apache License 2.0 — Basado en Project N.O.M.A.D. de Crosstalk Solutions
