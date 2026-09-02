"""Backend test suite for VoiceGuard AI.

Run with:
    cd voiceguard-ai
    python -m pytest tests/ -v
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Make the backend package importable from the tests directory
sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from audio_processor import extract_features
from detector import EvidenceBasedDetector
from main import app
from risk_engine import calculate_contextual_risk, risk_level_for

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wav_bytes(frequency: int = 220, duration: float = 0.5) -> bytes:
    """Synthesise a short PCM WAV clip at 16 kHz."""
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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "VoiceGuard AI"
    assert "version" in data


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_endpoint_returns_expected_shape() -> None:
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    required_keys = {
        "total_analyses", "average_risk_score",
        "critical_count", "high_count", "medium_count", "low_count",
    }
    assert required_keys.issubset(data.keys())
    assert data["total_analyses"] >= 0


# ---------------------------------------------------------------------------
# Real-time WebSocket
# ---------------------------------------------------------------------------

def test_realtime_websocket_returns_rolling_assessment() -> None:
    samples = np.zeros(16_000, dtype=np.float32)
    with client.websocket_connect("/api/realtime") as websocket:
        websocket.send_json({"type": "start", "sample_rate": 16_000})
        websocket.send_bytes(samples.tobytes())
        payload = websocket.receive_json()

    assert payload["status"] == "update"
    assert payload["stream_seconds"] == pytest.approx(1.0, abs=0.01)
    assert payload["sample_rate"] == 16_000


# ---------------------------------------------------------------------------
# Audio analysis — upload
# ---------------------------------------------------------------------------

def test_audio_analysis_returns_features_and_cleans_upload() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("voice.wav", wav_bytes(duration=0.5), "audio/wav")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["detection_mode"] == "trained-demo-v1"
    # Duration should be approximately what we synthesised (padded internally)
    assert payload["features"]["duration_seconds"] >= 0.25
    # Minimum feature count — should have ≥ 45 features with the new additions
    assert len(payload["features"]) >= 45
    # Verify no temporary files were left behind
    uploads = list((Path(__file__).parents[1] / "backend" / "uploads").glob("voiceguard-*"))
    assert not uploads, f"Temporary upload files not cleaned up: {uploads}"


def test_new_features_present_in_analysis() -> None:
    """Verify that all discriminative features are returned by the analysis endpoint."""
    response = client.post(
        "/api/analyze",
        files={"file": ("voice.wav", wav_bytes(duration=0.5), "audio/wav")},
    )
    assert response.status_code == 200
    features = response.json()["features"]
    expected_keys = (
        "spectral_flatness", "harmonic_to_noise_ratio", "jitter", "shimmer",
        "spectral_flux_mean", "spectral_flux_std",
        "sub_band_ratio_high", "sub_band_ratio_mid", "sub_band_ratio_low",
        "f0_range", "f0_range_pct", "rms_modulation",
        "mfcc_delta_std", "mfcc_delta_mean",
    )
    for key in expected_keys:
        assert key in features, f"Missing feature: {key}"
        assert np.isfinite(features[key]), f"Feature {key} is not finite"


def test_alert_events_included_in_response() -> None:
    """alert_events key is always present in an analysis response."""
    response = client.post(
        "/api/analyze",
        files={"file": ("voice.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    assert "alert_events" in response.json()


def test_invalid_file_is_rejected() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]


# ---------------------------------------------------------------------------
# History & privacy delete
# ---------------------------------------------------------------------------

def test_delete_history_record() -> None:
    # Create a record first
    response = client.post(
        "/api/analyze",
        files={"file": ("voice.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]

    # Delete it
    del_response = client.delete(f"/api/history/{analysis_id}")
    assert del_response.status_code == 200
    assert del_response.json()["status"] == "deleted"

    # Confirm it no longer appears in history
    history_ids = [item["id"] for item in client.get("/api/history").json()]
    assert analysis_id not in history_ids


def test_delete_nonexistent_record_returns_404() -> None:
    response = client.delete("/api/history/does-not-exist-99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Feature extraction unit tests
# ---------------------------------------------------------------------------

def test_feature_extraction_handles_silence() -> None:
    features = extract_features(np.zeros(16_000, dtype=np.float32), 16_000)
    assert features["silence_ratio"] == pytest.approx(1.0, abs=0.01)
    assert all(np.isfinite(v) for v in features.values()), "Non-finite feature detected"


def test_zcr_std_differs_from_mean_for_varying_signal() -> None:
    """Regression test: ZCR std was previously a copy of ZCR mean (bug)."""
    # A chirp signal has varying ZCR across frames
    sr = 16_000
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    # Linearly increasing frequency: high ZCR variation across time
    chirp = np.sin(2 * np.pi * (100 + 3000 * t) * t).astype(np.float32)
    features = extract_features(chirp, sr)
    # The std should NOT equal the mean (the old bug made them identical)
    assert features["zero_crossing_rate_std"] != pytest.approx(
        features["zero_crossing_rate_mean"], abs=1e-6
    ), "ZCR std equals ZCR mean — copy-paste bug still present"


def test_new_feature_values_are_finite() -> None:
    sr = 16_000
    audio = (0.3 * np.sin(2 * np.pi * 200 * np.arange(sr) / sr)).astype(np.float32)
    features = extract_features(audio, sr)
    for key in (
        "spectral_flatness", "harmonic_to_noise_ratio", "jitter", "shimmer",
        "spectral_flux_mean", "spectral_flux_std",
        "sub_band_ratio_high", "f0_range", "rms_modulation",
        "mfcc_delta_std", "mfcc_delta_mean",
    ):
        assert key in features
        assert np.isfinite(features[key]), f"{key} is not finite"


def test_detector_does_not_classify_non_speech_as_synthetic() -> None:
    result = EvidenceBasedDetector().detect(
        {
            "pitch_voiced_ratio": 0.0,
            "spectral_flux_mean": 0.0,
            "spectral_centroid_mean": 1000.0,
            "mfcc_delta_std": 0.0,
            "rms_modulation": 0.0,
            "sub_band_ratio_high": 0.0,
            "spectral_flatness": 0.0,
            "silence_ratio": 1.0,
        }
    )

    assert result.synthetic_probability == 50.0
    assert result.human_probability == 50.0
    assert result.acoustic_anomaly_score == 0.0


def test_detector_preserves_clustered_synthetic_evidence() -> None:
    result = EvidenceBasedDetector().detect(
        {
            "pitch_voiced_ratio": 0.8,
            "jitter": 0.003,
            "shimmer": 0.012,
            "harmonic_to_noise_ratio": 29.0,
            "f0_range": 55.0,
            "spectral_flux_mean": 120.0,
            "spectral_centroid_mean": 1400.0,
            "mfcc_delta_std": 1.2,
            "rms_modulation": 0.14,
            "sub_band_ratio_high": 0.2,
            "spectral_flatness": 0.25,
            "silence_ratio": 0.1,
        }
    )

    assert result.synthetic_probability >= 73.1
    assert result.detection_details["synthetic_marker_count"] >= 3


@pytest.mark.parametrize(
    ("case_name", "minimum_ai", "maximum_ai"),
    [("human", 0, 20), ("synthetic", 80, 100), ("no-speech", 40, 60)],
)
def test_demo_cases_have_stable_presentation_verdicts(
    case_name: str, minimum_ai: float, maximum_ai: float
) -> None:
    response = client.get(f"/api/demo/{case_name}")

    assert response.status_code == 200
    probability = response.json()["synthetic_probability"]
    assert minimum_ai <= probability <= maximum_ai


# ---------------------------------------------------------------------------
# Risk engine
# ---------------------------------------------------------------------------

def test_contextual_risk_and_thresholds() -> None:
    score, indicators = calculate_contextual_risk(False, "fund_transfer", 1_500_000, True, True)
    assert score == 100
    assert "Unknown caller" in " ".join(indicators)
    assert risk_level_for(30) == "LOW"
    assert risk_level_for(31) == "MEDIUM"
    assert risk_level_for(61) == "HIGH"
    assert risk_level_for(81) == "CRITICAL"


# ---------------------------------------------------------------------------
# Context enrichment endpoint
# ---------------------------------------------------------------------------

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
            "scenario": "banking",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] == "CRITICAL"
    assert data["final_risk_score"] >= 90
    # contextual_risk_score should be a number (float or int), not a string
    assert isinstance(data["contextual_risk_score"], (int, float))
    assert "alert_events" in data
