<img width="483" height="198" alt="image" src="https://github.com/user-attachments/assets/66bd9ec8-a496-46a8-b67e-63ee20d6fcc2" />


# Project J.A.R.V.I.S.

## Offline AI Assistant (Voice + Memory + UI)

JARVIS is an offline-first AI assistant designed for Raspberry Pi and Docker-capable systems.
It includes local LLM inference, persistent memory, neural TTS, speech input, and a built-in web chat UI.

## Key Capabilities

- Fully local runtime after setup
- Dual-model routing with Ollama (`gemma3:1b`, `qwen2.5:3b`)
- Supermemory-style memory engine
  - contradiction resolution
  - static vs dynamic profile
  - memory relationships
  - deduplication
- Semantic memory search via Qdrant + `nomic-embed-text`
- Voice I/O
  - STT: Whisper
  - TTS: Piper neural voice (with fallback)
- Built-in web chat UI served by `jarvis-brain` at `http://localhost:8403`
- Optional wake-word module (`openWakeWord`) included in `voice/wake_word.py`

<img width="938" height="567" alt="image" src="https://github.com/user-attachments/assets/7291d50e-dac9-4d14-a8f5-adc35f7771c1" />


## Installation (Raspberry Pi / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/Ambidiosidad/jarvis/main/scripts/jarvis/install.sh | sudo bash
```

## Desktop Development Quick Start

### Windows (PowerShell + Docker Desktop)

```powershell
cd C:\Users\your-user\path\jarvis\extensions
docker compose -f docker-compose.dev.yml up -d --build

docker exec jarvis_ollama ollama pull gemma3:1b
docker exec jarvis_ollama ollama pull qwen2.5:3b
docker exec jarvis_ollama ollama pull nomic-embed-text
```

### Linux/macOS

```bash
git clone https://github.com/Ambidiosidad/jarvis.git
cd jarvis/extensions
docker compose -f docker-compose.dev.yml up -d --build

docker exec jarvis_ollama ollama pull gemma3:1b
docker exec jarvis_ollama ollama pull qwen2.5:3b
docker exec jarvis_ollama ollama pull nomic-embed-text
```

## Run Without Terminal Chat Commands (Web UI)

Open:

```text
http://localhost:8403
```

You can type directly in the UI and use the microphone button.



## Core Services

- `jarvis-brain` (port `8403`) - orchestration + UI serving
- `jarvis-memory` (port `8401`) - Supermemory-style storage
- `jarvis-voice` (port `8402`) - Whisper STT + Piper TTS
- `jarvis-vision` (port `8405`) - vision service
- `jarvis_ollama` (port `11434`) - local model runtime
- `jarvis_qdrant` (ports `6333/6334`) - vector search

## Main API Endpoints

### Brain

- `GET  /` - web UI
- `POST /chat?message=...`
- `POST /voice-chat` (multipart audio)
- `GET  /voice-proxy/tts?text=...`
- `GET  /status`
- `GET  /health`

### Memory

- `GET  http://localhost:8401/health`
- `GET  http://localhost:8401/stats`
- `GET  http://localhost:8401/context`
- `GET  http://localhost:8401/profile`
- `GET  http://localhost:8401/memories/search?q=...`
- `GET  http://localhost:8401/memories/semantic?q=...`

### Voice

- `GET  http://localhost:8402/health`

### Vision

- `GET  http://localhost:8405/health`
- `POST http://localhost:8405/analyze`

## Minimum / Recommended Specs

### Raspberry Pi target

| Component | Minimum | Recommended |
|---|---|---|
| CPU | Raspberry Pi 4/5 (64-bit) | Raspberry Pi 5 |
| RAM | 4 GB | 8 GB |
| Storage | 256 GB SSD/NVMe | 512 GB NVMe |
| Audio | optional | USB mic + speaker |
| Camera | optional | Pi camera or USB webcam |

### Desktop testing

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 4 vCPU | 6+ vCPU |
| RAM | 8 GB host | 16 GB host |
| Storage | 80 GB free | 120+ GB free |

## Project Structure

```text
jarvis/
|-- extensions/
|   |-- docker-compose.yml
|   |-- docker-compose.dev.yml
|   |-- brain/
|   |-- memory/
|   |-- voice/
|   |-- vision/
|   `-- motors/
|-- scripts/jarvis/
|   |-- install.sh
|   |-- smoke_test.sh
|   |-- chat_loop.sh
|   |-- converse_loop.sh
|   |-- start_dev_converse.ps1
|   |-- start.sh
|   |-- stop.sh
|   `-- uninstall.sh
`-- README.md
```

## Notes

- `wake_word.py` is included and ready, but not auto-wired by default in the current web flow.
- If Docker build cache gets corrupted on Windows, run `docker buildx prune -af` and rebuild.

## License

Apache License 2.0
