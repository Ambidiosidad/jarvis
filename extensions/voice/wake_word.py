"""
J.A.R.V.I.S. Wake Word Detector
==================================
Detecta "Hey Jarvis" usando openWakeWord (100% offline).
Cuando detecta la wake word, activa la grabación de voz
y envía el audio al brain para procesamiento.

Repositorio: https://github.com/dscripka/openWakeWord
"""
import os, time, threading, queue
import numpy as np
from pathlib import Path

# Configuration
WAKE_WORD = os.getenv("WAKE_WORD", "hey_jarvis")
THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))
BRAIN_URL = os.getenv("BRAIN_URL", "http://jarvis-brain:8403")
RECORD_SECONDS = int(os.getenv("RECORD_SECONDS", "5"))
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # openWakeWord expects 80ms chunks at 16kHz


class WakeWordDetector:
    """Continuous wake word detection."""

    def __init__(self):
        self._model = None
        self._running = False
        self._callback = None

    def load_model(self):
        """Load openWakeWord model."""
        try:
            import openwakeword
            from openwakeword.model import Model

            # Download default models if needed
            openwakeword.utils.download_models()

            self._model = Model(
                wakeword_models=[WAKE_WORD],
                inference_framework="onnx",
            )
            print(f"[WAKEWORD] Model loaded: {WAKE_WORD}")
            return True
        except Exception as e:
            print(f"[WAKEWORD] Failed to load model: {e}")
            return False

    def start(self, on_wake_callback):
        """Start listening for wake word in background thread."""
        if self._model is None:
            if not self.load_model():
                print("[WAKEWORD] Cannot start - model not loaded")
                return False

        self._callback = on_wake_callback
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        print(f"[WAKEWORD] Listening for '{WAKE_WORD}'...")
        return True

    def stop(self):
        """Stop listening."""
        self._running = False

    def _listen_loop(self):
        """Main detection loop."""
        try:
            import pyaudio

            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            print("[WAKEWORD] Audio stream opened")

            while self._running:
                audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                # Feed to model
                prediction = self._model.predict(audio_array)

                # Check if wake word detected
                for model_name, score in prediction.items():
                    if score > THRESHOLD:
                        print(f"[WAKEWORD] Detected '{model_name}' "
                              f"(score: {score:.2f})")
                        if self._callback:
                            self._callback()
                        # Cooldown to avoid double triggers
                        time.sleep(2)
                        # Reset model state
                        self._model.reset()

            stream.stop_stream()
            stream.close()
            audio.terminate()

        except Exception as e:
            print(f"[WAKEWORD] Error in listen loop: {e}")
            self._running = False


# ═══════════════════════════════════════
#  Standalone usage (for testing)
# ═══════════════════════════════════════

if __name__ == "__main__":
    def on_wake():
        print("*** WAKE WORD DETECTED! ***")
        print("Recording for 5 seconds...")
        # In production, this would trigger recording
        # and send audio to the brain service

    detector = WakeWordDetector()
    if detector.start(on_wake):
        print("Say 'Hey Jarvis' to test...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            detector.stop()
            print("Stopped.")
    else:
        print("Could not start wake word detector")
