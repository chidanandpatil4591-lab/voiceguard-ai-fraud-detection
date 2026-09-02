"""Division 2: Evidence v3.2 Production Anti-Spoofing Classifier."""
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
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

class EvidenceBasedDetector(VoiceDetector):
    detection_mode = "evidence-v3.2-production"
    PRIOR_LOG_ODDS: float = 0.0

    def detect(self, features: dict[str, float]) -> DetectionResult:
        log_odds = self.PRIOR_LOG_ODDS
        indicators: list[str] = []
        details: dict[str, float] = {}

        voiced = features.get("pitch_voiced_ratio", 0.0)
        is_voiced = voiced > 0.08
        hnr = features.get("harmonic_to_noise_ratio", 0.0)
        jitter = features.get("jitter", 0.0)
        shimmer = features.get("shimmer", 0.0)
        f0_range = features.get("f0_range", 0.0)
        flux = features.get("spectral_flux_mean", 0.0)
        centroid = features.get("spectral_centroid_mean", 1000.0) + 1.0
        flux_norm = flux / centroid
        mfcc_delta_std = features.get("mfcc_delta_std", 0.0)
        rms_mod = features.get("rms_modulation", 0.0)
        sbr_high = features.get("sub_band_ratio_high", 0.0)
        flatness = features.get("spectral_flatness", 0.0)

        is_live_mic = hnr < 16.0 and hnr > 0.0
        if is_live_mic:
            log_odds -= 1.8
            details["environment"] = "Live Room Acoustics (Human Indicator)"
        elif hnr > 28.0:
            log_odds += 2.2
            indicators.append(f"Elevated HNR ({hnr:.1f} dB) — synthetic vocoder clean spectrum")

        if is_voiced:
            if jitter < 0.0025:
                log_odds += 3.2
                indicators.append("Sub-threshold pitch jitter — synthetic pitch regularity")
            elif jitter < 0.0045:
                log_odds += 1.8
                indicators.append("Low pitch jitter — AI voice synthesis signature")
            elif jitter > 0.008:
                log_odds -= 2.2
            elif jitter > 0.006:
                log_odds -= 1.2

            if shimmer < 0.012:
                log_odds += 2.6
                indicators.append("Unnaturally smooth amplitude envelope — AI TTS artifact")
            elif shimmer < 0.020:
                log_odds += 1.2
            elif shimmer > 0.032:
                log_odds -= 2.0

        if is_voiced:
            if f0_range < 45.0 and voiced > 0.15:
                log_odds += 2.2
                indicators.append("Compressed pitch trajectory — robotic monotone prosody")
            elif f0_range > 120.0:
                log_odds -= 1.8
            elif f0_range > 80.0:
                log_odds -= 0.9

        if flux_norm < 0.075:
            log_odds += 2.8
            indicators.append("Ultra-low spectral flux — synthetic transition over-smoothing")
        elif flux_norm < 0.14:
            log_odds += 1.4
        elif flux_norm > 0.32:
            log_odds -= 1.8

        if mfcc_delta_std < 1.0:
            log_odds += 2.2
            indicators.append("Over-smoothed cepstral delta — TTS vocoder trajectory")
        elif mfcc_delta_std > 4.5:
            log_odds -= 1.5

        if sbr_high > 0.24:
            log_odds += 2.4
            indicators.append("3.5kHz–8kHz high-band energy peak — neural vocoder fingerprint")
        elif sbr_high < 0.04 and not is_live_mic:
            log_odds += 1.2

        if flatness > 0.35:
            log_odds += 1.6
            indicators.append("Elevated spectral flatness — neural synthesis residual noise")

        prob_ai = _sigmoid(log_odds) * 100.0
        prob_ai = _clamp(prob_ai, 2.0, 98.0)
        prob_human = 100.0 - prob_ai

        confidence = _clamp(65.0 + abs(prob_ai - 50.0) * 0.65, 65.0, 98.0)
        acoustic_anomaly = _clamp(prob_ai * 0.96, 0.0, 100.0)

        details["log_odds_total"] = log_odds
        details["jitter"] = jitter
        details["shimmer"] = shimmer
        details["hnr"] = hnr
        details["f0_range"] = f0_range
        details["spectral_flux_norm"] = flux_norm

        if not indicators:
            indicators = ["Natural acoustic perturbations consistent with authentic human speech"]

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
    detection_mode = "evidence-v3.2+voiceprint"
    _SPEAKER_DIMS = ["pitch_mean", "spectral_centroid_mean", "mfcc_1_mean", "mfcc_2_mean", "mfcc_3_mean", "mfcc_4_mean", "harmonic_to_noise_ratio", "spectral_bandwidth_mean"]

    def __init__(self, reference_features: list[dict[str, float]] | None = None) -> None:
        self.reference_features = reference_features or []
        self._base = EvidenceBasedDetector()

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
    return EvidenceBasedDetector()
