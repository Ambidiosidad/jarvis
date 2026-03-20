"""
J.A.R.V.I.S. Voice Service — STT (Whisper) + TTS (espeak-ng)
Todo offline. Whisper tiny corre en CPU.
"""
import os, tempfile, whisper
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse

app = FastAPI(title="Jarvis Voice")
_model = None


@app.on_event("startup")
async def load():
    global _model
    _model = whisper.load_model("tiny")


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...), language: str = "es"):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await audio.read())
        path = tmp.name
    try:
        r = _model.transcribe(path, language=language)
        return {"text": r["text"].strip(), "language": r.get("language", language)}
    finally:
        os.unlink(path)


@app.post("/tts")
async def text_to_speech(text: str, language: str = "es"):
    path = tempfile.mktemp(suffix=".wav")
    os.system(f'espeak-ng -v {language} -s 150 -w {path} "{text[:1000]}"')
    return FileResponse(path, media_type="audio/wav", filename="jarvis.wav")


@app.get("/health")
async def health():
    return {"status": "ok", "whisper": _model is not None}
