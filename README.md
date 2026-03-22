# Project J.A.R.V.I.S.

### Just A Rather Very Intelligent System

Un asistente de IA autónomo y 100% offline con memoria persistente, conversación
por voz, estado emocional evolutivo, pantalla táctil, y capacidad de movimiento
robótico — todo corriendo en una Raspberry Pi 5.

---

## Qué es Jarvis

Jarvis es un robot conversacional con inteligencia artificial que funciona
completamente sin internet. Tiene memoria a largo plazo, emociones que
evolucionan con cada conversación, razonamiento lógico con selección
automática de modelo, y una base de conocimiento offline que incluye
Wikipedia, Stack Exchange, referencia médica y mapas.

### Características

- **100% offline** — Internet solo se necesita durante la instalación
- **Modelo dual inteligente** — Gemma3 1B (conversación rápida) + Qwen2.5 3B (razonamiento)
- **Memoria persistente** — Recuerda hechos, conversaciones y patrones entre sesiones
- **Estado emocional** — Humor, energía, paciencia y vínculo que evolucionan
- **Voz** — Reconocimiento (Whisper) y síntesis (espeak-ng) offline
- **Conocimiento** — Wikipedia ES/EN, Stack Exchange, WikiMed, Wikibooks offline
- **Mapas** — Navegación offline con ProtoMaps
- **RAG** — Sube tus propios documentos y Jarvis los consulta
- **Movimiento** — Control de motores DC (Fase 2)
- **Pantalla táctil** — Interfaz directa en el robot

---

## Instalación en Raspberry Pi 5

### Modo privado (actual para testing)

Este repositorio está en privado mientras se valida la instalación.
Usa clone + script local:

```bash
sudo apt-get update && sudo apt-get install -y git curl
git clone git@github.com:Ambidiosidad/jarvis.git /opt/jarvis
# alternativa HTTPS con credenciales/PAT:
# git clone https://github.com/Ambidiosidad/jarvis.git /opt/jarvis
sudo bash /opt/jarvis/scripts/jarvis/install.sh
```

El instalador te guía paso a paso: configura el NVMe, instala Docker,
construye los servicios, y te pregunta qué modelos de IA y contenido
offline quieres descargar.

Cuando termine, desconecta internet. Jarvis es autónomo.

### Modo público (opcional)

Cuando el repo sea público, también puedes usar:

```bash
curl -fsSL https://raw.githubusercontent.com/Ambidiosidad/jarvis/main/scripts/jarvis/install.sh | sudo bash
```

## Desarrollo local (sin Raspberry Pi)

```bash
git clone https://github.com/Ambidiosidad/jarvis.git
cd jarvis/extensions
docker compose -f docker-compose.dev.yml up -d --build
docker exec jarvis_ollama ollama pull gemma3:1b
docker exec jarvis_ollama ollama pull qwen2.5:3b
```

Prueba:
```bash
curl -X POST "http://localhost:8403/chat?message=Hola Jarvis"
```

---

## Arquitectura

```
┌──────────────────────────────────────────┐
│            J.A.R.V.I.S.                  │
│                                          │
│  jarvis-brain    — Orquestador (v3)      │
│  jarvis-memory   — Memoria + emociones   │
│  jarvis-voice    — STT + TTS offline     │
│  jarvis-ollama   — LLM local             │
│  jarvis-qdrant   — RAG vectorial         │
│  jarvis-kiwix    — Wikipedia offline     │
│  jarvis-motors   — Control GPIO (Fase 2) │
└──────────────────────────────────────────┘
```

### Sistema de modelo dual

| Situación | Modelo | Velocidad Pi 5 |
|---|---|---|
| Conversación, saludos, emociones | Gemma3 1B | ~10-15 tok/s |
| Lógica, matemáticas, preguntas complejas | Qwen2.5 3B | ~4-6 tok/s |

El clasificador de intención selecciona automáticamente el modelo
según el tipo de pregunta.

### Sistema emocional

| Dimensión | Efecto |
|---|---|
| Humor | Tono de las respuestas (curious, happy, empathetic, thoughtful) |
| Energía | Nivel de actividad y entusiasmo |
| Paciencia | Tolerancia ante frustración del usuario |
| Vínculo | Cercanía con el usuario — solo sube, nunca baja |

---

## Estructura del proyecto

```
jarvis/
├── extensions/                  ← Servicios Jarvis
│   ├── docker-compose.yml       ←   Producción (Pi 5)
│   ├── docker-compose.dev.yml   ←   Desarrollo (PC)
│   ├── brain/                   ←   Orquestador v3
│   ├── memory/                  ←   Memoria + emociones
│   ├── voice/                   ←   STT + TTS
│   └── motors/                  ←   GPIO (Fase 2)
├── scripts/jarvis/
│   ├── install.sh               ←   Instalador unificado
│   ├── smoke_test.sh            ←   Validación post-instalación
│   ├── start.sh                 ←   Arranque
│   ├── stop.sh                  ←   Parada
│   └── uninstall.sh             ←   Desinstalación
├── config/jarvis/
│   └── jarvis.env               ←   Configuración
├── docs/jarvis/                 ←   Documentación
└── README.md
```

## Endpoints

| Servicio | URL | Función |
|---|---|---|
| Chat | POST http://localhost:8403/chat?message=... | Conversación |
| Voz | POST http://localhost:8403/voice-chat | Enviar audio WAV |
| Memoria stats | GET http://localhost:8401/stats | Estado de la memoria |
| Emociones | GET http://localhost:8401/emotions/current | Estado emocional |
| Status | GET http://localhost:8403/status | Estado completo del brain |
| Wikipedia | http://localhost:8500 | Wikipedia offline |
| Qdrant | http://localhost:6333 | Base vectorial RAG |

## Comandos útiles

```bash
# Arrancar
sudo systemctl start jarvis

# Parar
sudo systemctl stop jarvis

# Reiniciar
sudo systemctl restart jarvis

# Ver logs
cd /opt/jarvis/extensions && docker compose logs -f jarvis-brain

# Smoke test completo (health + chat)
sudo bash /opt/jarvis/scripts/jarvis/smoke_test.sh

# Hablar con Jarvis
curl -X POST "http://localhost:8403/chat?message=Hola"

# Ver qué recuerda
curl http://localhost:8401/context

# Ver emociones
curl http://localhost:8401/emotions/current
```

## Hardware

| Componente | Modelo | Precio aprox. |
|---|---|---|
| Raspberry Pi 5 8GB | Oficial | ~75€ |
| Pantalla táctil 7" | RPi Touch Display 2 | ~60€ |
| NVMe SSD 128GB | Kingston/WD + Pimoroni Base | ~55€ |
| Active Cooler | Oficial Pi 5 | ~5€ |
| Fuente 27W | USB-C oficial | ~12€ |
| MicroSD 32GB | Samsung/SanDisk | ~9€ |
| Micrófono USB | Mini USB | ~12€ |
| Altavoz | USB/3.5mm | ~10€ |
| **Total** | | **~238€** |

## Roadmap

- [x] Arquitectura y diseño
- [x] Brain v3 con modelo dual y clasificador de intención
- [x] Sistema emocional automático
- [x] Memoria persistente con hechos y resúmenes
- [x] Multi-turno y chain-of-thought
- [x] Instalador unificado interactivo
- [ ] **Fase 1** — Despliegue en Raspberry Pi 5
- [ ] **Fase 2** — Movimiento robótico
- [ ] **Fase 3** — Cámara + Visión

## Créditos

Jarvis incorpora tecnología de los siguientes proyectos open-source:

- [Project N.O.M.A.D.](https://github.com/Crosstalk-Solutions/project-nomad) (Apache 2.0) — Inspiración y referencia de arquitectura
- [Ollama](https://ollama.com/) — Inferencia LLM local
- [Whisper](https://github.com/openai/whisper) — Speech-to-text
- [Qdrant](https://qdrant.tech/) — Base de datos vectorial
- [Kiwix](https://kiwix.org/) — Contenido offline
- [Gemma](https://ai.google.dev/gemma) — Modelo de conversación
- [Qwen](https://github.com/QwenLM/Qwen2.5) — Modelo de razonamiento

## Licencia

Apache License 2.0
