import os
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Jarvis Vision")

CAMERA_INDEX = int(os.getenv("VISION_CAMERA_INDEX", "0"))
SNAPSHOT_DIR = Path(os.getenv("VISION_SNAPSHOT_DIR", "/app/data/snapshots"))

_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
_SMILE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_smile.xml"
)


@app.on_event("startup")
async def startup() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _capture_frame(camera_index: int = CAMERA_INDEX) -> np.ndarray | None:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    return frame


def _glasses_estimate(face_gray: np.ndarray) -> bool:
    h, w = face_gray.shape[:2]
    if h < 30 or w < 30:
        return False

    eye_band = face_gray[int(0.18 * h):int(0.45 * h), :]
    if eye_band.size == 0:
        return False

    edges = cv2.Canny(eye_band, 60, 140)
    edge_density = float(np.count_nonzero(edges)) / float(edges.size)
    return edge_density > 0.11


def _analyze_frame(frame: np.ndarray) -> dict:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    faces = _FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.2,
        minNeighbors=5,
        minSize=(40, 40),
    )

    people_count = len(faces)
    glasses_count = 0
    smile_count = 0

    for (x, y, fw, fh) in faces:
        roi_gray = gray[y:y + fh, x:x + fw]
        if roi_gray.size == 0:
            continue

        smiles = _SMILE_CASCADE.detectMultiScale(
            roi_gray,
            scaleFactor=1.5,
            minNeighbors=20,
            minSize=(25, 25),
        )
        if len(smiles) > 0:
            smile_count += 1

        if _glasses_estimate(roi_gray):
            glasses_count += 1

    brightness = float(np.mean(gray))
    if brightness < 75:
        lighting = "dark"
    elif brightness > 170:
        lighting = "bright"
    else:
        lighting = "normal"

    mood_estimate = "unknown"
    mood_confidence = 0.35
    if people_count > 0:
        mood_estimate = "positive" if smile_count > 0 else "neutral"
        mood_confidence = 0.78 if smile_count > 0 else 0.62

    labels: list[str] = [f"lighting_{lighting}"]
    if people_count == 0:
        labels.append("no_person_detected")
    elif people_count == 1:
        labels.append("person_detected")
    else:
        labels.append("multiple_people_detected")

    if glasses_count > 0:
        labels.append("glasses_detected")
    if smile_count > 0:
        labels.append("smile_detected")

    summary_parts = [f"Lighting is {lighting}."]
    if people_count == 0:
        summary_parts.append("No person was detected.")
    elif people_count == 1:
        summary_parts.append("One person detected.")
    else:
        summary_parts.append(f"{people_count} people detected.")

    if glasses_count > 0:
        summary_parts.append(
            "Possible glasses detected on "
            f"{glasses_count} face(s)."
        )
    if smile_count > 0:
        summary_parts.append("Smile cues detected.")

    return {
        "timestamp": time.time(),
        "image": {"width": w, "height": h},
        "people_count": people_count,
        "faces_detected": people_count,
        "glasses_detected": glasses_count > 0,
        "glasses_count": glasses_count,
        "smiles_detected": smile_count,
        "mood_estimate": mood_estimate,
        "mood_confidence": round(mood_confidence, 2),
        "lighting": lighting,
        "labels": labels,
        "summary": " ".join(summary_parts),
    }


def _save_snapshot(frame: np.ndarray) -> str:
    filename = f"frame_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    target = SNAPSHOT_DIR / filename
    cv2.imwrite(str(target), frame)
    return str(target)


@app.get("/health")
async def health() -> dict:
    frame = _capture_frame()
    return {
        "status": "ok",
        "service": "jarvis-vision",
        "version": "1.0",
        "camera_index": CAMERA_INDEX,
        "camera_available": frame is not None,
    }


@app.post("/capture")
async def capture(save_frame: bool = True) -> dict:
    frame = _capture_frame()
    if frame is None:
        raise HTTPException(
            status_code=503,
            detail="Camera is unavailable. Check /dev/video mapping.",
        )

    path = _save_snapshot(frame) if save_frame else None
    height, width = frame.shape[:2]

    return {
        "ok": True,
        "saved": save_frame,
        "path": path,
        "image": {"width": width, "height": height},
    }


@app.post("/analyze")
async def analyze(save_frame: bool = False) -> dict:
    frame = _capture_frame()
    if frame is None:
        raise HTTPException(
            status_code=503,
            detail="Camera is unavailable. Check /dev/video mapping.",
        )

    result = _analyze_frame(frame)
    if save_frame:
        result["snapshot_path"] = _save_snapshot(frame)
    return result


@app.post("/analyze-image")
async def analyze_image(image: UploadFile = File(...)) -> dict:
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty image payload")

    arr = np.frombuffer(payload, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image format")

    result = _analyze_frame(frame)
    result["source"] = image.filename or "upload"
    return result
