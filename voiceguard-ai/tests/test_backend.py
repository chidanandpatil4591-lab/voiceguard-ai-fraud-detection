import io
import sys
import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from audio_processor import extract_features
from main import app
from risk_engine import calculate_contextual_risk, risk_level_for

client = TestClient(app)


def wav_bytes(frequency: int = 220, duration: float = 0.25) -> bytes:
    sample_rate = 16_000
    time = np.arange(int(sample_rate * duration)) / sample_rate
    samples = (0.2 * np.sin(2 * np.pi * frequency * time) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(sample_rate)
        recording.writeframes(samples.tobytes())
    return buffer.getvalue()


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "VoiceGuard AI"}


def test_realtime_websocket_returns_rolling_assessment() -> None:
    samples = np.zeros(16_000, dtype=np.float32)
    with client.websocket_connect("/api/realtime") as websocket:
        websocket.send_json({"type": "start", "sample_rate": 16_000})
        websocket.send_bytes(samples.tobytes())
        payload = websocket.receive_json()

    assert payload["status"] == "update"
    assert payload["stream_seconds"] == 1.0
    assert payload["sample_rate"] == 16_000


def test_audio_analysis_returns_features_and_cleans_upload() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("voice.wav", wav_bytes(), "audio/wav")},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["detection_mode"] == "demo"
    assert payload["features"]["duration_seconds"] == 0.25
    assert len(payload["features"]) >= 40
    assert not list((Path(__file__).parents[1] / "backend" / "uploads").glob("voiceguard-*"))


def test_invalid_file_is_rejected() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported audio format."


def test_feature_extraction_handles_silence() -> None:
    features = extract_features(np.zeros(128, dtype=np.float32), 16_000)
    assert features["silence_ratio"] == 1.0
    assert all(np.isfinite(value) for value in features.values())


def test_contextual_risk_and_thresholds() -> None:
    score, indicators = calculate_contextual_risk(False, "fund_transfer", 1_500_000, True, True)
    assert score == 100
    assert "Unknown caller" in indicators
    assert risk_level_for(30) == "LOW"
    assert risk_level_for(31) == "MEDIUM"
    assert risk_level_for(81) == "CRITICAL"


def test_context_endpoint_combines_voice_and_context() -> None:
    response = client.post(
        "/api/analyze/context",
        json={
            "caller_name": "CEO",
            "caller_known": False,
            "transaction_type": "fund_transfer",
            "transaction_amount": 1_500_000,
            "urgent_request": True,
            "sensitive_information_requested": True,
            "voice_synthetic_probability": 78,
            "voice_risk_score": 87,
        },
    )
    assert response.status_code == 200
    assert response.json()["risk_level"] == "CRITICAL"
    assert response.json()["final_risk_score"] >= 90
