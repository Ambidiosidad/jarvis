"""
J.A.R.V.I.S. Motor Service — Control de motores DC vía GPIO + L298N.
Fase 2: En dev mode simula los movimientos por consola.
"""
import time
from fastapi import FastAPI

app = FastAPI(title="Jarvis Motors")
HW = False  # Se activa en Pi 5 con RPi.GPIO

@app.post("/move/{direction}")
async def move(direction: str, duration: float = 1.0, speed: float = 0.7):
    valid = ["forward", "backward", "left", "right", "stop"]
    if direction not in valid:
        return {"error": f"Dirección desconocida: {direction}"}
    print(f"[MOTOR-SIM] {direction} speed={speed} duration={duration}s")
    if direction != "stop" and duration > 0:
        time.sleep(min(duration, 5.0))  # Cap en 5s para dev
    return {"ok": True, "direction": direction, "duration": duration, "simulated": not HW}

@app.get("/health")
async def health():
    return {"status": "ok", "hardware": HW, "service": "jarvis-motors"}
