FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg portaudio19-dev libsndfile1 espeak-ng curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip "setuptools<81" wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --no-build-isolation -r requirements.txt

# Pre-download Whisper tiny model
RUN python3 -c "import whisper; whisper.load_model('tiny')"

COPY app.py .

EXPOSE 8402
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8402"]
