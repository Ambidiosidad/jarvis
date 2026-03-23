# Project J.A.R.V.I.S.

## Just A Rather Very Intelligent System

JARVIS is a fully offline AI assistant designed to run on a Raspberry Pi 5 with:

- Persistent memory across sessions
- Voice input/output (STT + TTS)
- Emotion-aware responses
- Optional robotics control (motors, phase 2)
- Optional offline knowledge stack (Wikipedia, medical, education, maps)

The goal is simple: once installed, JARVIS can operate without internet.

---

## Features

- 100% offline runtime after setup
- Dual-model routing:
  - `gemma3:1b` for fast conversation
  - `qwen2.5:3b` for logic and reasoning
- Long-term memory (facts, summaries, patterns)
- Automatic emotional state updates
- Voice stack with Whisper + espeak-ng
- Local RAG with Qdrant + embeddings
- One-command installer for Raspberry Pi
- Local development stack for desktop testing

---

## System Requirements

### Production target (Raspberry Pi)

| Component | Minimum | Recommended | Notes |
|---|---|---|---|
| CPU | Raspberry Pi 4/5 (64-bit quad-core ARM) | Raspberry Pi 5 (4x Cortex-A76 @ 2.4GHz) | Pi 5 recommended for better voice/chat latency |
| RAM | 4 GB | 8 GB | 8 GB strongly recommended for dual-model routing |
| Storage | 256 GB SSD/NVMe | 512 GB NVMe | 256 GB is a practical floor, 512 GB leaves comfortable room for models + offline content |
| OS | Raspberry Pi OS 64-bit (Bookworm or newer) | Latest Raspberry Pi OS 64-bit | Keep system updated before install |
| Power | Stable 5V/3A | Official 27W PSU | Prevents throttling/undervoltage under load |
| Cooling | Passive cooling | Active cooler | Recommended for sustained LLM workloads |
| Audio | Optional | USB mic + speaker/headset | Required for voice interaction |
| Internet | Required only for setup | Required only for setup | Runtime can be fully offline |

### Desktop / VM testing target

| Component | Minimum | Recommended | Notes |
|---|---|---|---|
| CPU | 4 vCPU x86_64 | 6+ vCPU x86_64 | More cores reduce build/pull time |
| RAM | 8 GB host (6 GB VM) | 16 GB host (8 GB VM) | For smooth Docker builds and model pulls |
| Storage | 80 GB free | 120+ GB free | Image layers + models consume space quickly |
| Virtualization | VirtualBox 7+ | VirtualBox 7+ (bridged networking if needed) | Useful when Docker Hub pulls fail in NAT |
| Docker | Docker Engine + Compose | Docker Engine + Compose v2 plugin | Script supports plugin/classic compose |

### Model profile requirements

| Runtime profile | Minimum RAM | Recommended RAM | Notes |
|---|---|---|---|
| Fast chat only (`gemma3:1b`) | 4 GB | 8 GB | Best for low-latency conversational flow |
| Dual model (`gemma3:1b` + `qwen2.5:3b`) | 8 GB | 8 GB + swap on SSD/NVMe | Ollama loads one model at a time, but swaps between them |

---

## Raspberry Pi Installation

### Public repo mode

```bash
curl -fsSL https://raw.githubusercontent.com/Ambidiosidad/jarvis/main/scripts/jarvis/install.sh | sudo bash
```

### Private repo mode

```bash
sudo apt-get update && sudo apt-get install -y git curl
git clone git@github.com:Ambidiosidad/jarvis.git /opt/jarvis
# or HTTPS + PAT:
# git clone https://github.com/Ambidiosidad/jarvis.git /opt/jarvis
sudo bash /opt/jarvis/scripts/jarvis/install.sh
```

The installer configures storage, Docker, services, models, and optional offline content.

---

## Local Development (Desktop)

```bash
git clone https://github.com/Ambidiosidad/jarvis.git
cd jarvis/extensions
docker compose -f docker-compose.dev.yml up -d --build
docker exec jarvis_ollama ollama pull gemma3:1b
docker exec jarvis_ollama ollama pull qwen2.5:3b
```

Quick test:

```bash
curl -X POST "http://localhost:8403/chat?message=Hello Jarvis"
```

---

## Architecture

Core services:

- `jarvis-brain` (orchestrator, tool-use, model routing)
- `jarvis-memory` (messages, facts, summaries, emotion state)
- `jarvis-voice` (speech-to-text + text-to-speech)
- `jarvis_ollama` (local LLM runtime)
- `jarvis_qdrant` (vector database for RAG)
- `jarvis_kiwix` (offline knowledge serving, optional content)
- `jarvis-motors` (GPIO control, phase 2)

---

## Project Structure

```text
jarvis/
|-- extensions/
|   |-- docker-compose.yml
|   |-- docker-compose.dev.yml
|   |-- brain/
|   |-- memory/
|   |-- voice/
|   `-- motors/
|-- scripts/jarvis/
|   |-- install.sh
|   |-- smoke_test.sh
|   |-- chat_loop.sh
|   |-- start.sh
|   |-- stop.sh
|   `-- uninstall.sh
|-- config/jarvis/
|   `-- jarvis.env
`-- README.md
```

---

## Useful Endpoints

- `POST http://localhost:8403/chat?message=...`
- `POST http://localhost:8403/voice-chat`
- `GET  http://localhost:8401/stats`
- `GET  http://localhost:8401/context`
- `GET  http://localhost:8401/emotions/current`
- `GET  http://localhost:8403/status`
- `GET  http://localhost:8403/health`
- `GET  http://localhost:8500` (Kiwix, if content exists)

---

## Useful Commands

```bash
# Start/stop with systemd
sudo systemctl start jarvis
sudo systemctl stop jarvis
sudo systemctl restart jarvis

# Logs
cd /opt/jarvis/extensions && docker compose logs -f jarvis-brain

# Automated smoke test
sudo bash /opt/jarvis/scripts/jarvis/smoke_test.sh

# Interactive terminal chat
sudo bash /opt/jarvis/scripts/jarvis/chat_loop.sh

# One-shot chat
curl -X POST "http://localhost:8403/chat?message=Hello"
```

---

## Hardware Baseline (Phase 1)

- Raspberry Pi 5 (8GB)
- 7-inch touch display
- NVMe SSD (recommended: 256GB minimum, 512GB preferred)
- Official 27W USB-C PSU
- Active cooler
- USB microphone
- Speaker (USB or 3.5mm)

---

## Roadmap

- [x] Core architecture
- [x] Brain v3 with intent routing
- [x] Memory + emotional state
- [x] Unified installer
- [ ] Motor/chassis integration
- [ ] Camera + multimodal phase

---

## Credits

JARVIS builds on and integrates multiple open-source projects:

- Ollama
- Whisper
- Qdrant
- Kiwix
- Gemma
- Qwen

---

## License

Apache License 2.0


