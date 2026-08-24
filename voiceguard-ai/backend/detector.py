from dataclasses import dataclass


@dataclass
class DetectionResult:
    synthetic_probability: float
    human_probability: float
    confidence: float
    acoustic_anomaly_score: float
    indicators: list[str]
    detection_mode: str


class VoiceDetector:
    def detect(self, features: dict[str, float]) -> DetectionResult:
        raise NotImplementedError


class DemoVoiceDetector(VoiceDetector):
    """Deterministic feature-based demo until a trained anti-spoofing model exists."""

    detection_mode = "demo"

    def detect(self, features: dict[str, float]) -> DetectionResult:
        indicators: list[str] = []
        signals: list[float] = []

        pitch_voiced_ratio = features.get("pitch_voiced_ratio", 0.0)
        pitch_std = features.get("pitch_std", 0.0)
        spectral_centroid_std = features.get("spectral_centroid_std", 0.0)
        mfcc_1_std = features.get("mfcc_1_std", 0.0)
        silence_ratio = features.get("silence_ratio", 0.0)
        zcr_mean = features.get("zero_crossing_rate_mean", 0.0)

        if pitch_voiced_ratio > 0.25 and pitch_std < 18:
            signals.append(0.76)
            indicators.append("Low prosodic variation")
        else:
            signals.append(0.25)

        if spectral_centroid_std < 180:
            signals.append(0.68)
            indicators.append("Stable spectral profile")
        else:
            signals.append(0.25)

        if mfcc_1_std < 95:
            signals.append(0.64)
            indicators.append("Frequency distribution anomaly")
        else:
            signals.append(0.25)

        if zcr_mean > 0.16:
            signals.append(0.58)
            indicators.append("Elevated high-frequency activity")
        else:
            signals.append(0.2)

        if silence_ratio > 0.55:
            signals.append(0.42)
            indicators.append("Extended silence or pause pattern")

        synthetic_probability = round(max(1.0, min(99.0, sum(signals) / len(signals) * 100)), 1)
        human_probability = round(100 - synthetic_probability, 1)
        confidence = round(min(95.0, 55.0 + abs(synthetic_probability - 50.0) * 0.8), 1)
        acoustic_anomaly_score = round(min(100.0, synthetic_probability * 0.9), 1)

        return DetectionResult(
            synthetic_probability=synthetic_probability,
            human_probability=human_probability,
            confidence=confidence,
            acoustic_anomaly_score=acoustic_anomaly_score,
            indicators=indicators or ["No strong acoustic anomaly detected"],
            detection_mode=self.detection_mode,
        )


def create_detector() -> VoiceDetector:
    return DemoVoiceDetector()
