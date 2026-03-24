"""
J.A.R.V.I.S. Voice Service v2
================================
STT: Whisper (tiny) — reconocimiento de voz offline
TTS: Piper Neural — voz natural offline (reemplaza espeak-ng)

Piper usa modelos ONNX pre-entrenados. Voces disponibles en:
https://github.com/rhasspy/piper/blob/master/VOICES.md

Voces español recomendadas:
- es_ES-sharvard-medium (masculina, España)
- es_ES-davefx-medium (masculina, España)
- es_MX-ald-medium (masculina, México)
"""
import os, io, wave, subprocess, tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Jarvis Voice v2 — Piper Neural TTS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

MODELS_DIR = Path("/app/models")
AUDIO_DIR = Path("/app/audio")
MODELS_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

# TTS Configuration
PIPER_VOICE = os.getenv("PIPER_VOICE", "es_ES-sharvard-medium")
PIPER_SPEED = float(os.getenv("PIPER_SPEED", "1.0"))

# Whisper model for STT
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
_whisper_model = None


# ═══════════════════════════════════════
#  STT — Whisper (unchanged)
# ═══════════════════════════════════════

def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Transcribe audio to text using Whisper."""
    tmp = AUDIO_DIR / f"stt_{audio.filename}"
    try:
        content = await audio.read()
        tmp.write_bytes(content)
        model = _get_whisper()
        result = model.transcribe(str(tmp), language="es")
        text = result.get("text", "").strip()
        return {"text": text, "language": result.get("language", "es")}
    except Exception as e:
        return {"text": "", "error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)


# ═══════════════════════════════════════
#  TTS — Piper Neural (NEW)
# ═══════════════════════════════════════

def _ensure_piper_voice():
    """Download Piper voice model if not present."""
    model_path = MODELS_DIR / f"{PIPER_VOICE}.onnx"
    config_path = MODELS_DIR / f"{PIPER_VOICE}.onnx.json"

    if model_path.exists() and config_path.exists():
        return str(model_path)

    # Auto-download using piper CLI
    try:
        print(f"[VOICE] Downloading Piper voice: {PIPER_VOICE}...")
        result = subprocess.run(
            ["piper", "--model", PIPER_VOICE,
             "--data-dir", str(MODELS_DIR),
             "--download-dir", str(MODELS_DIR),
             "--update-voices"],
            input="test",
            capture_output=True, text=True, timeout=120
        )
        print(f"[VOICE] Piper download complete")
    except Exception as e:
        print(f"[VOICE] Piper download error: {e}")
        # Fallback: try direct download from HuggingFace
        _download_voice_manual()

    return str(model_path) if model_path.exists() else None


def _download_voice_manual():
    """Manual download from HuggingFace if piper auto-download fails."""
    import urllib.request
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

    # Parse voice name: es_ES-sharvard-medium
    parts = PIPER_VOICE.split("-")
    lang_region = parts[0]  # es_ES
    lang = lang_region.split("_")[0]  # es
    name = parts[1]  # sharvard
    quality = parts[2] if len(parts) > 2 else "medium"

    onnx_url = f"{base_url}/{lang}/{lang_region}/{name}/{quality}/{PIPER_VOICE}.onnx"
    json_url = f"{onnx_url}.json"

    model_path = MODELS_DIR / f"{PIPER_VOICE}.onnx"
    config_path = MODELS_DIR / f"{PIPER_VOICE}.onnx.json"

    try:
        if not model_path.exists():
            print(f"[VOICE] Downloading {onnx_url}")
            urllib.request.urlretrieve(onnx_url, str(model_path))
        if not config_path.exists():
            print(f"[VOICE] Downloading {json_url}")
            urllib.request.urlretrieve(json_url, str(config_path))
        print(f"[VOICE] Voice {PIPER_VOICE} downloaded successfully")
    except Exception as e:
        print(f"[VOICE] Manual download failed: {e}")


def _synthesize_piper(text: str) -> bytes:
    """Synthesize speech using Piper TTS. Returns WAV bytes."""
    model_path = _ensure_piper_voice()

    if model_path is None:
        # Ultimate fallback to espeak-ng
        return _synthesize_espeak(text)

    try:
        # Use piper CLI: echo text | piper --model X --output_raw
        proc = subprocess.run(
            ["piper", "--model", model_path,
             "--output_raw", "--length-scale", str(1.0 / PIPER_SPEED)],
            input=text, capture_output=True, text=True,
            timeout=30
        )

        if proc.returncode != 0 or not proc.stdout:
            # Try alternative: pipe through piper binary
            proc = subprocess.run(
                ["piper", "--model", model_path,
                 "--output_file", "/tmp/jarvis_tts.wav"],
                input=text, capture_output=True, text=True,
                timeout=30
            )
            if Path("/tmp/jarvis_tts.wav").exists():
                return Path("/tmp/jarvis_tts.wav").read_bytes()
            return _synthesize_espeak(text)

        # Raw PCM to WAV
        raw_audio = proc.stdout.encode('latin-1') if isinstance(proc.stdout, str) else proc.stdout
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(22050)  # Piper default
            wf.writeframes(raw_audio)
        return wav_buffer.getvalue()

    except Exception as e:
        print(f"[VOICE] Piper synthesis error: {e}")
        return _synthesize_espeak(text)


def _synthesize_espeak(text: str) -> bytes:
    """Fallback TTS using espeak-ng."""
    output_path = "/tmp/jarvis_espeak.wav"
    try:
        subprocess.run(
            ["espeak-ng", "-v", "es", "-w", output_path, text],
            capture_output=True, timeout=10
        )
        if Path(output_path).exists():
            return Path(output_path).read_bytes()
    except Exception:
        pass
    return b""


@app.get("/tts")
async def text_to_speech(text: str, voice: str = None):
    """Convert text to speech using Piper Neural TTS."""
    if not text:
        return {"error": "No text provided"}

    wav_data = _synthesize_piper(text[:500])  # Limit to 500 chars

    if not wav_data:
        return {"error": "TTS synthesis failed"}

    return StreamingResponse(
        io.BytesIO(wav_data),
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"}
    )


@app.get("/tts/voices")
async def list_voices():
    """List available Piper voices."""
    voices = []
    for f in MODELS_DIR.glob("*.onnx"):
        if not f.name.endswith(".onnx.json"):
            voices.append(f.stem)
    return {
        "current": PIPER_VOICE,
        "available": voices,
        "engine": "piper-neural",
    }


# ═══════════════════════════════════════
#  Health
# ═══════════════════════════════════════

@app.get("/health")
async def health():
    model_exists = (MODELS_DIR / f"{PIPER_VOICE}.onnx").exists()
    return {
        "status": "ok",
        "service": "jarvis-voice",
        "version": "2.0",
        "stt_engine": "whisper",
        "stt_model": WHISPER_MODEL,
        "tts_engine": "piper-neural",
        "tts_voice": PIPER_VOICE,
        "tts_model_ready": model_exists,
    }
