"""VoiceGuard AI — FastAPI application entry point.

Endpoints
---------
GET  /api/health                        — liveness probe
GET  /api/stats                         — aggregate dashboard statistics
POST /api/analyze                       — upload-based voice analysis
POST /api/analyze/context               — contextual risk enrichment
GET  /api/history                       — recent analysis records
DELETE /api/history/{analysis_id}       — privacy-compliant record deletion
POST /api/speakers/{speaker_id}/enroll  — voiceprint enrolment
GET  /api/speakers/{speaker_id}/verify  — cross-session identity check
WS   /api/realtime                      — real-time streaming analysis
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from alerts import build_alert_events, dispatch_alerts
from audio_processor import (
    AudioProcessingError,
    AudioValidationError,
    extract_features,
    process_audio_file,
    save_upload_temporarily,
    validate_audio_metadata,
)
from database import (
    count_voiceprints_for_speaker,
    delete_analysis,
    delete_old_voiceprints,
    get_stats,
    get_voiceprints_for_speaker,
    init_database,
    list_analyses,
    log_alert,
    save_analysis,
    save_voiceprint,
    utc_now,
)
from detector import VoiceprintDetector, create_detector
from risk_engine import (
    calculate_contextual_risk,
    calculate_voice_risk,
    combine_risk,
    generate_alert_events,
)
from schemas import (
    ContextAnalysisRequest,
    ContextAnalysisResponse,
    DashboardStats,
    VoiceprintEnrollResponse,
    VoiceprintVerifyResponse,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voiceguard")

app = FastAPI(
    title="VoiceGuard AI",
    description=(
        "Real-Time Voice Integrity & Impersonation Detection — "
        "AI-powered defence against voice cloning and synthetic speech attacks."
    ),
    version="1.0.0",
)

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _raw_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_database()
detector = create_detector()

# Real-time streaming constants
REALTIME_WINDOW_SECONDS = 4
REALTIME_UPDATE_SECONDS = 1
MAX_REALTIME_SECONDS = 120


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _realtime_assessment(audio: np.ndarray, sample_rate: int) -> dict:
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


# ---------------------------------------------------------------------------
# Health & stats
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "service": "VoiceGuard AI", "version": "1.0.0"}


@app.get("/api/stats", response_model=DashboardStats)
def dashboard_stats() -> DashboardStats:
    """Return aggregate statistics for the dashboard summary cards."""
    data = get_stats()
    return DashboardStats(**data)


# ---------------------------------------------------------------------------
# Audio analysis
# ---------------------------------------------------------------------------

DEMO_FEATURES: dict[str, dict[str, float]] = {
    "human": {
        "pitch_voiced_ratio": 0.82, "jitter": 0.009, "shimmer": 0.038,
        "harmonic_to_noise_ratio": 18.0, "f0_range": 165.0,
        "spectral_flux_mean": 620.0, "spectral_centroid_mean": 1450.0,
        "mfcc_delta_std": 5.8, "rms_modulation": 0.42,
        "sub_band_ratio_high": 0.10, "spectral_flatness": 0.12,
        "silence_ratio": 0.08,
    },
    "synthetic": {
        "pitch_voiced_ratio": 0.86, "jitter": 0.001, "shimmer": 0.005,
        "harmonic_to_noise_ratio": 35.0, "f0_range": 18.0,
        "spectral_flux_mean": 25.0, "spectral_centroid_mean": 1450.0,
        "mfcc_delta_std": 0.3, "rms_modulation": 0.05,
        "sub_band_ratio_high": 0.32, "spectral_flatness": 0.50,
        "silence_ratio": 0.08,
    },
    "no-speech": {
        "pitch_voiced_ratio": 0.0, "spectral_flux_mean": 0.0,
        "spectral_centroid_mean": 0.0, "mfcc_delta_std": 0.0,
        "rms_modulation": 0.0, "sub_band_ratio_high": 0.0,
        "spectral_flatness": 0.0, "silence_ratio": 1.0,
    },
}


@app.get("/api/demo/{case_name}")
def demo_analysis(case_name: str) -> dict:
    """Return a repeatable labelled fixture for presentations and QA."""
    features = DEMO_FEATURES.get(case_name)
    if features is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown demo case. Use human, synthetic, or no-speech.",
        )

    detection = detector.detect(features)
    voice_risk = calculate_voice_risk(
        detection.synthetic_probability,
        detection.acoustic_anomaly_score,
    )
    labels = {
        "human": "Demo human voice",
        "synthetic": "Demo AI-generated voice",
        "no-speech": "Demo silence / no speech",
    }
    return {
        "status": "demo",
        "message": "Repeatable presentation fixture; no audio was uploaded.",
        "analysis_id": f"demo-{case_name}",
        "filename": labels[case_name],
        "duration_seconds": 4.0,
        "sample_rate": 16_000,
        "features": features,
        "human_probability": detection.human_probability,
        "synthetic_probability": detection.synthetic_probability,
        "confidence": detection.confidence,
        "acoustic_anomaly_score": detection.acoustic_anomaly_score,
        "indicators": detection.indicators,
        "detection_details": detection.detection_details,
        "risk_score": voice_risk.risk_score,
        "risk_level": voice_risk.risk_level,
        "recommended_action": voice_risk.recommended_action,
        "detection_mode": detection.detection_mode,
        "alert_events": [],
    }

@app.post("/api/analyze")
async def analyze_audio(file: UploadFile = File(...)) -> dict:
    """Analyse an uploaded audio file for voice cloning / synthetic speech."""
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
        analysis_id = str(uuid4())
        analysis = {
            "id": analysis_id,
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

        # Alert dispatch
        alert_events = build_alert_events(
            analysis_id=analysis_id,
            risk_score=voice_risk.risk_score,
            risk_level=voice_risk.risk_level,
            recommended_action=voice_risk.recommended_action,
            indicators=detection.indicators,
        )
        dispatch_alerts(alert_events)
        for event in alert_events:
            log_alert(event)

        return {
            "status": "accepted",
            "message": "Voice integrity assessment completed.",
            "analysis_id": analysis_id,
            "filename": analysis["filename"],
            "duration_seconds": analysis["duration"],
            "sample_rate": metadata["sample_rate"],
            "features": features,
            "human_probability": detection.human_probability,
            "synthetic_probability": detection.synthetic_probability,
            "confidence": detection.confidence,
            "acoustic_anomaly_score": detection.acoustic_anomaly_score,
            "indicators": detection.indicators,
            "detection_details": detection.detection_details,
            "risk_score": voice_risk.risk_score,
            "risk_level": voice_risk.risk_level,
            "recommended_action": voice_risk.recommended_action,
            "detection_mode": detection.detection_mode,
            "alert_events": alert_events,
        }

    except AudioValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AudioProcessingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@app.post("/api/analyze/context", response_model=ContextAnalysisResponse)
def analyze_context(request: ContextAnalysisRequest) -> ContextAnalysisResponse:
    """Enrich a voice risk score with call-context metadata."""
    contextual_score, context_indicators = calculate_contextual_risk(
        request.caller_known,
        request.transaction_type,
        request.transaction_amount,
        request.urgent_request,
        request.sensitive_information_requested,
    )
    final_risk = combine_risk(request.voice_risk_score, contextual_score)

    # Generate alert events for the combined risk
    alert_events = generate_alert_events(
        analysis_id="context-" + str(uuid4()),
        risk=final_risk,
        indicators=context_indicators or [],
        scenario=request.scenario,
    )

    return ContextAnalysisResponse(
        caller_name=request.caller_name,
        voice_synthetic_probability=request.voice_synthetic_probability,
        contextual_risk_score=float(contextual_score),
        final_risk_score=final_risk.risk_score,
        risk_level=final_risk.risk_level,
        indicators=context_indicators or ["No additional contextual indicators"],
        recommended_action=final_risk.recommended_action,
        alert_events=alert_events,
    )


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

@app.get("/api/history")
def analysis_history(limit: int = 50) -> list[dict]:
    return list_analyses(limit=min(limit, 200))


@app.delete("/api/history/{analysis_id}")
def delete_history_record(analysis_id: str) -> dict:
    """Privacy-compliant deletion of a single analysis record."""
    deleted = delete_analysis(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis record not found.")
    return {"status": "deleted", "analysis_id": analysis_id}


# ---------------------------------------------------------------------------
# Speaker voiceprint enrolment & verification
# ---------------------------------------------------------------------------

@app.post("/api/speakers/{speaker_id}/enroll", response_model=VoiceprintEnrollResponse)
async def enroll_speaker(
    speaker_id: str, file: UploadFile = File(...)
) -> VoiceprintEnrollResponse:
    """Enrol a speaker by uploading a reference audio clip.

    A minimum of 3 seconds of clean speech is recommended.
    The audio is analysed for features and stored as a voiceprint — no
    raw audio is retained.
    """
    if not speaker_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid speaker ID format.")

    temporary_path = None
    try:
        extension = validate_audio_metadata(file.filename, file.content_type)
        temporary_path, size_bytes = await save_upload_temporarily(file, extension)
        metadata = process_audio_file(temporary_path, extension, size_bytes)
        features = metadata["features"]

        if features["duration_seconds"] < 1.5:
            raise HTTPException(
                status_code=400,
                detail="Reference clip too short — please provide at least 1.5 seconds of speech.",
            )

        save_voiceprint(speaker_id, features)
        delete_old_voiceprints(speaker_id, keep=10)
        count = count_voiceprints_for_speaker(speaker_id)

        return VoiceprintEnrollResponse(
            speaker_id=speaker_id,
            enrolled_at=utc_now(),
            voiceprint_count=count,
            message=f"Voiceprint enrolled successfully. Speaker '{speaker_id}' now has {count} reference(s).",
        )
    except AudioValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AudioProcessingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@app.post("/api/speakers/{speaker_id}/verify", response_model=VoiceprintVerifyResponse)
async def verify_speaker(
    speaker_id: str, file: UploadFile = File(...)
) -> VoiceprintVerifyResponse:
    """Verify a live audio clip against the enrolled voiceprint for *speaker_id*."""
    references = get_voiceprints_for_speaker(speaker_id, limit=5)
    if not references:
        raise HTTPException(
            status_code=404,
            detail=f"No voiceprint found for speaker '{speaker_id}'. Please enrol first.",
        )

    temporary_path = None
    try:
        extension = validate_audio_metadata(file.filename, file.content_type)
        temporary_path, size_bytes = await save_upload_temporarily(file, extension)
        metadata = process_audio_file(temporary_path, extension, size_bytes)
        features = metadata["features"]

        vp_detector = VoiceprintDetector(reference_features=references)
        result = vp_detector.detect(features)
        cross_anomaly = result.detection_details.get("cross_session_anomaly", 0.0)

        return VoiceprintVerifyResponse(
            speaker_id=speaker_id,
            cross_session_anomaly_score=round(cross_anomaly, 1),
            risk_level=result.risk_level if hasattr(result, "risk_level") else "LOW",
            message=(
                "Identity mismatch detected — possible impersonation."
                if cross_anomaly > 50
                else "Voice matches enrolled voiceprint."
            ),
        )
    except AudioValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AudioProcessingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


# ---------------------------------------------------------------------------
# Real-time WebSocket streaming
# ---------------------------------------------------------------------------

@app.websocket("/api/realtime")
async def realtime_audio(websocket: WebSocket) -> None:
    """Stream raw PCM float32 audio frames and receive rolling risk updates."""
    await websocket.accept()
    sample_rate = 16_000
    audio_chunks: list[np.ndarray] = []
    sample_count = 0
    next_update_at = REALTIME_UPDATE_SECONDS * sample_rate

    try:
        # First message must be a JSON settings handshake
        settings = json.loads(await websocket.receive_text())
        sample_rate = int(settings.get("sample_rate", sample_rate))
        if not (8_000 <= sample_rate <= 48_000):
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
                await websocket.close(code=1009, reason="Realtime stream too long")
                return
            audio_chunks.append(chunk)

            if sample_count >= next_update_at:
                audio = np.concatenate(audio_chunks)
                window_size = REALTIME_WINDOW_SECONDS * sample_rate
                assessment = _realtime_assessment(audio[-window_size:], sample_rate)
                assessment["stream_seconds"] = sample_count / sample_rate
                await websocket.send_json(assessment)
                next_update_at += REALTIME_UPDATE_SECONDS * sample_rate

    except (WebSocketDisconnect, json.JSONDecodeError, ValueError):
        return


# ---------------------------------------------------------------------------
# Static frontend (production build)
# ---------------------------------------------------------------------------

frontend_directory = Path(__file__).parent / "static"
if frontend_directory.exists():
    app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
