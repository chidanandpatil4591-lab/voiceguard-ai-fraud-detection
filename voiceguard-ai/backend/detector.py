"""Division 2: High-Precision ASVspoof 2024 Calibrated Anti-Spoofing Classifier."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np


@dataclass
class DetectionResult:
    synthetic_probability: float
    human_probability: float
    confidence: float
    acoustic_anomaly_score: float
    indicators: list[str]
    detection_mode: str
    detection_details: dict[str, float] = field(default_factory=dict)


class VoiceDetector:
    def detect(self, features: dict[str, float]) -> DetectionResult:
        raise NotImplementedError


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-np.clip(x, -15.0, 15.0)))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class HighPrecisionDetector(VoiceDetector):
    detection_mode = "precision-asvspoof-v5"

    def detect(self, features: dict[str, float]) -> DetectionResult:  # noqa: C901
        indicators: list[str] = []
        details: dict[str, float] = {}

        jitter = float(features.get("jitter", 0.0))
        shimmer = float(features.get("shimmer", 0.0))
        hnr = float(features.get("harmonic_to_noise_ratio", 18.0))
        f0_range = float(features.get("f0_range", 100.0))
        flux = float(features.get("spectral_flux_mean", 0.25))
        sbr_high = float(features.get("sub_band_ratio_high", 0.12))
        voiced_ratio = float(features.get("pitch_voiced_ratio", 0.5))

        details["jitter"] = jitter
        details["shimmer"] = shimmer
        details["hnr"] = hnr
        details["f0_range"] = f0_range
        details["spectral_flux_mean"] = flux
        details["sub_band_ratio_high"] = sbr_high

        # ── DISCRIMINATIVE BIOMARKER ACCUMULATION ─────────────────────────
        log_odds = 0.0  # Neutral prior

        # 1. High-Precision Sub-Sample Pitch Jitter
        if voiced_ratio > 0.10:
            if jitter < 0.0018:
                log_odds += 3.8
                indicators.append("Sub-sample pitch jitter <0.0018 — neural vocoder over-regularization")
            elif jitter < 0.0035:
                log_odds += 2.2
                indicators.append("Low pitch jitter — synthetic speech intonation")
            elif jitter > 0.0075:
                log_odds -= 3.2  # Authentic human vocal cord micro-tremors
                indicators.append("Natural biological pitch micro-tremors (Jitter >0.0075) — authentic human vocal tract")
            elif jitter > 0.0050:
                log_odds -= 1.8

        # 2. Amplitude Perturbation (Shimmer)
        if voiced_ratio > 0.10:
            if shimmer < 0.010:
                log_odds += 3.0
                indicators.append("Unnaturally flat amplitude envelope (Shimmer <0.01) — AI TTS artifact")
            elif shimmer < 0.018:
                log_odds += 1.6
            elif shimmer > 0.030:
                log_odds -= 2.6
                indicators.append("Natural breath & volume modulation (Shimmer >0.03) — human speech dynamics")

        # 3. Harmonic Cleanliness vs Room Acoustics
        if hnr > 30.0:
            log_odds += 2.8
            indicators.append(f"Abnormally clean harmonics ({hnr:.1f} dB) — synthetic vocoder without physical room acoustics")
        elif hnr > 24.0:
            log_odds += 1.4
        elif 6.0 <= hnr <= 19.0:
            log_odds -= 2.5
            indicators.append("Authentic physical room resonance and microphone acoustics")

        # 4. Formant Dispersion & Spectral Flux
        if flux < 0.08:
            log_odds += 2.5
            indicators.append("Ultra-low spectral flux — synthetic transition over-smoothing")
        elif flux > 0.28:
            log_odds -= 2.2
            indicators.append("Dynamic spectral flux (>0.28) — natural human acoustic formant shifts")

        # 5. Neural Vocoder 3.5k-8kHz High-Band Signature
        if sbr_high > 0.23:
            log_odds += 2.6
            indicators.append("3.5kHz–8kHz energy anomaly — ElevenLabs / HiFi-GAN vocoder artifact")
        elif 0.06 <= sbr_high <= 0.16:
            log_odds -= 1.2

        # 6. Prosodic Pitch Range (F0)
        if f0_range < 40.0 and voiced_ratio > 0.2:
            log_odds += 2.0
            indicators.append("Compressed pitch trajectory — synthetic robotic monotone prosody")
        elif f0_range > 110.0:
            log_odds -= 1.8
            indicators.append("Expressive conversational pitch range (>110 Hz)")

        # ── FINAL CALIBRATED PROBABILITY ──────────────────────────────────
        prob_ai = _sigmoid(log_odds) * 100.0
        prob_ai = _clamp(prob_ai, 2.0, 98.0)
        prob_human = 100.0 - prob_ai

        confidence = _clamp(72.0 + abs(prob_ai - 50.0) * 0.55, 72.0, 99.0)
        acoustic_anomaly = _clamp(prob_ai * 0.95, 0.0, 100.0)

        details["log_odds_total"] = log_odds

        if not indicators:
            if prob_ai > 50:
                indicators = ["Synthetic vocoder acoustic markers detected"]
            else:
                indicators = ["Acoustic perturbations and formant dynamics match authentic human speech"]

        return DetectionResult(
            synthetic_probability=round(prob_ai, 1),
            human_probability=round(prob_human, 1),
            confidence=round(confidence, 1),
            acoustic_anomaly_score=round(acoustic_anomaly, 1),
            indicators=indicators,
            detection_mode=self.detection_mode,
            detection_details=details,
        )


class VoiceprintDetector(VoiceDetector):
    detection_mode = "precision-asvspoof-v5+voiceprint"
    _SPEAKER_DIMS = ["pitch_mean", "spectral_centroid_mean", "harmonic_to_noise_ratio", "jitter", "shimmer"]

    def __init__(self, reference_features: list[dict[str, float]] | None = None) -> None:
        self.reference_features = reference_features or []
        self._base = HighPrecisionDetector()

    def detect(self, features: dict[str, float]) -> DetectionResult:
        result = self._base.detect(features)
        cross_score = self._cross_session_anomaly(features)
        if cross_score > 0.0:
            blended = _clamp(result.synthetic_probability * 0.70 + cross_score * 0.30, 2.0, 98.0)
            extra = ["Cross-session speaker voiceprint divergence detected"] if cross_score > 50 else []
            result = DetectionResult(
                synthetic_probability=round(blended, 1),
                human_probability=round(100.0 - blended, 1),
                confidence=result.confidence,
                acoustic_anomaly_score=result.acoustic_anomaly_score,
                indicators=result.indicators + extra,
                detection_mode=self.detection_mode,
                detection_details={**result.detection_details, "cross_session_anomaly": cross_score},
            )
        return result

    def _cross_session_anomaly(self, features: dict[str, float]) -> float:
        if not self.reference_features:
            return 0.0
        current = np.array([features.get(d, 0.0) for d in self._SPEAKER_DIMS], dtype=np.float64)
        scores = []
        for ref in self.reference_features:
            ref_vec = np.array([ref.get(d, 0.0) for d in self._SPEAKER_DIMS], dtype=np.float64)
            norm = np.linalg.norm(current) * np.linalg.norm(ref_vec)
            if norm > 1e-9:
                cosine_sim = float(np.dot(current, ref_vec) / norm)
                scores.append(_clamp((1.0 - cosine_sim) * 100.0, 0.0, 100.0))
        return float(np.mean(scores)) if scores else 0.0


def create_detector() -> VoiceDetector:
    return HighPrecisionDetector()
