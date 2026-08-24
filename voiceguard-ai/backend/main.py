import os
import json
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from audio_processor import (
    AudioProcessingError,
    AudioValidationError,
    extract_features,
    process_audio_file,
    save_upload_temporarily,
    validate_audio_metadata,
)
from database import init_database, list_analyses, save_analysis, utc_now
from detector import create_detector
from risk_engine import calculate_contextual_risk, calculate_voice_risk, combine_risk
from schemas import ContextAnalysisRequest, ContextAnalysisResponse

app = FastAPI(
    title="VoiceGuard AI",
    description="Real-Time Voice Integrity & Impersonation Detection",
    version="0.1.0",
)

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_database()
detector = create_detector()
REALTIME_WINDOW_SECONDS = 4
REALTIME_UPDATE_SECONDS = 1
MAX_REALTIME_SECONDS = 120


def realtime_assessment(audio: np.ndarray, sample_rate: int) -> dict[str, object]:
    features = extract_features(audio, sample_rate)
    detection = detector.detect(features)
    voice_risk = calculate_voice_risk(
        detection.synthetic_probability,
        detection.acoustic_anomaly_score,
    )
    return {
        "status": "update",
        "duration_seconds": features["duration_seconds"],
        "sample_rate": sample_rate,
        "features": features,
        "human_probability": detection.human_probability,
        "synthetic_probability": detection.synthetic_probability,
        "confidence": detection.confidence,
        "acoustic_anomaly_score": detection.acoustic_anomaly_score,
        "indicators": detection.indicators,
        "risk_score": voice_risk.risk_score,
        "risk_level": voice_risk.risk_level,
        "recommended_action": voice_risk.recommended_action,
        "detection_mode": detection.detection_mode,
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "VoiceGuard AI"}


@app.websocket("/api/realtime")
async def realtime_audio(websocket: WebSocket) -> None:
    await websocket.accept()
    sample_rate = 16_000
    audio_chunks: list[np.ndarray] = []
    sample_count = 0
    next_update_at = REALTIME_UPDATE_SECONDS * sample_rate

    try:
        settings = json.loads(await websocket.receive_text())
        sample_rate = int(settings.get("sample_rate", sample_rate))
        if sample_rate < 8_000 or sample_rate > 48_000:
            await websocket.close(code=1003, reason="Unsupported sample rate")
            return

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text"):
                command = json.loads(message["text"])
                if command.get("type") == "end":
                    await websocket.send_json({"status": "complete"})
                    return
                continue
            if not message.get("bytes"):
                continue

            chunk = np.frombuffer(message["bytes"], dtype=np.float32)
            if chunk.size == 0 or not np.isfinite(chunk).all():
                continue
            sample_count += chunk.size
            if sample_count > MAX_REALTIME_SECONDS * sample_rate:
                await websocket.close(code=1009, reason="Realtime stream is too long")
                return
            audio_chunks.append(chunk)

            if sample_count >= next_update_at:
                audio = np.concatenate(audio_chunks)
                window_size = REALTIME_WINDOW_SECONDS * sample_rate
                assessment = realtime_assessment(audio[-window_size:], sample_rate)
                assessment["stream_seconds"] = sample_count / sample_rate
                await websocket.send_json(assessment)
                next_update_at += REALTIME_UPDATE_SECONDS * sample_rate
    except (WebSocketDisconnect, json.JSONDecodeError, ValueError):
        return


@app.post("/api/analyze")
async def analyze_audio(file: UploadFile = File(...)) -> dict[str, object]:
    temporary_path = None

    try:
        extension = validate_audio_metadata(file.filename, file.content_type)
        temporary_path, size_bytes = await save_upload_temporarily(file, extension)

        metadata = process_audio_file(temporary_path, extension, size_bytes)
        features = metadata["features"]
        detection = detector.detect(features)
        voice_risk = calculate_voice_risk(
            detection.synthetic_probability,
            detection.acoustic_anomaly_score,
        )
        analysis = {
            "id": str(uuid4()),
            "created_at": utc_now(),
            "filename": file.filename or "unknown",
            "duration": features["duration_seconds"],
            "human_probability": detection.human_probability,
            "synthetic_probability": detection.synthetic_probability,
            "confidence": detection.confidence,
            "risk_score": voice_risk.risk_score,
            "risk_level": voice_risk.risk_level,
            "indicators": detection.indicators,
            "recommended_action": voice_risk.recommended_action,
            "detection_mode": detection.detection_mode,
        }
        save_analysis(analysis)

        return {
            "status": "accepted",
            "message": "Voice integrity assessment completed.",
            "analysis_id": analysis["id"],
            "filename": analysis["filename"],
            "duration_seconds": analysis["duration"],
            "sample_rate": metadata["sample_rate"],
            "features": features,
            "human_probability": detection.human_probability,
            "synthetic_probability": detection.synthetic_probability,
            "confidence": detection.confidence,
            "acoustic_anomaly_score": detection.acoustic_anomaly_score,
            "indicators": detection.indicators,
            "risk_score": voice_risk.risk_score,
            "risk_level": voice_risk.risk_level,
            "recommended_action": voice_risk.recommended_action,
            "detection_mode": detection.detection_mode,
        }
    except AudioValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AudioProcessingError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@app.get("/api/history")
def analysis_history() -> list[dict[str, object]]:
    return list_analyses()


@app.post("/api/analyze/context", response_model=ContextAnalysisResponse)
def analyze_context(request: ContextAnalysisRequest) -> ContextAnalysisResponse:
    contextual_score, context_indicators = calculate_contextual_risk(
        request.caller_known,
        request.transaction_type,
        request.transaction_amount,
        request.urgent_request,
        request.sensitive_information_requested,
    )
    final_risk = combine_risk(request.voice_risk_score, contextual_score)
    return ContextAnalysisResponse(
        caller_name=request.caller_name,
        voice_synthetic_probability=request.voice_synthetic_probability,
        contextual_risk_score=contextual_score,
        final_risk_score=final_risk.risk_score,
        risk_level=final_risk.risk_level,
        indicators=context_indicators or ["No additional contextual indicators"],
        recommended_action=final_risk.recommended_action,
    )
