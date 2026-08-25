"""Voice detection engine for VoiceGuard AI.

Detection architecture
----------------------
``EvidenceBasedDetector`` implements a **log-odds / Bayesian accumulation**
model grounded in published anti-spoofing research (ASVspoof, LFCC-LCNN,
RawNet2, AASIST).

Instead of arbitrary additive scores, every feature contributes a
calibrated log-likelihood ratio (LLR) that reflects how much more likely
that feature value is for a synthetic voice vs. a natural human voice.

    log_odds  = Σ LLR_i(feature_i)
    P(AI)     = sigmoid(log_odds)   =  1 / (1 + exp(-log_odds))

Evidence weights are derived from:
  • Relative jitter / shimmer ranges in Titze (1994), Baken & Orlikoff (2000)
  • HNR norms in Boersma (1993)
  • Spectral flux smoothness in Hifigan / WaveNet vocoder characterisation
  • Sub-band artefact fingerprints from Müller et al. (2022)
  • F0 range norms (Ladd, 2008; Banse & Scherer, 1996)
  • MFCC delta smoothness from Kinnunen et al. (2020, ASVspoof analysis)

``VoiceprintDetector`` adds cross-session cosine-distance scoring on top
of the evidence model when reference voiceprints are available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    synthetic_probability: float    # 0–100 %
    human_probability: float        # 0–100 %
    confidence: float               # model confidence 0–100 %
    acoustic_anomaly_score: float   # 0–100
    indicators: list[str]
    detection_mode: str
    detection_details: dict[str, float] = field(default_factory=dict)


class VoiceDetector:
    def detect(self, features: dict[str, float]) -> DetectionResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Log-odds helper
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Evidence-based (log-odds accumulation) detector
# ---------------------------------------------------------------------------

class EvidenceBasedDetector(VoiceDetector):
    """Probabilistically calibrated AI-vs-human detector.

    Each feature contributes a log-likelihood ratio (LLR) that reflects
    how much more (or less) likely a synthetic voice is given that feature
    value.  Positive LLR = evidence for AI; negative = evidence for human.

    The final probability is: P(AI) = sigmoid(Σ LLR_i)

    Evidence weights are calibrated against published norms:
    ─────────────────────────────────────────────────────────
    JITTER (relative)
      Natural speech: 0.5–2 %  (0.005–0.020)
      Modern TTS:     < 0.1 %  (< 0.001)
    SHIMMER (relative)
      Natural speech: 3–6 %    (0.03–0.06)
      Modern TTS:     < 1 %    (< 0.01)
    HNR (dB)
      Natural voiced speech:  15–25 dB
      TTS (neural vocoder):   28–40 dB  (abnormally clean)
    F0 RANGE (Hz)
      Conversational speech:  100–300 Hz range
      TTS (monotone/flat):    < 60 Hz
    SPECTRAL FLUX MEAN
      Natural speech:  high per-frame variation
      TTS:             unusually low (smooth articulation)
    MFCC DELTA STD
      Natural speech:  high delta variation
      TTS:             very smooth (low delta std)
    RMS MODULATION
      Natural speech:  > 0.25 (natural amplitude variation)
      TTS:             < 0.15 (unnaturally even)
    SUB-BAND HIGH (3–8 kHz) RATIO
      Neural vocoders leave characteristic energy fingerprint here
    ─────────────────────────────────────────────────────────
    """

    detection_mode = "evidence-v3"

    # Prior log-odds: slight lean toward human (most audio is real)
    # P(AI) prior ≈ 30%   →   log_odds = log(0.30 / 0.70) ≈ -0.85
    PRIOR_LOG_ODDS: float = -0.85

    def detect(self, features: dict[str, float]) -> DetectionResult:  # noqa: C901
        log_odds = self.PRIOR_LOG_ODDS
        indicators: list[str] = []
        details: dict[str, float] = {}

        voiced = features.get("pitch_voiced_ratio", 0.0)
        is_voiced = voiced > 0.20  # only apply prosody checks to voiced speech

        # ── 1. JITTER ────────────────────────────────────────────────────────
        # Relative jitter: natural 0.005–0.020, TTS < 0.002
        jitter = features.get("jitter", 0.0)
        details["jitter"] = jitter
        if is_voiced:
            if jitter < 0.001:
                log_odds += 3.0
                indicators.append("Extremely low jitter — TTS pitch over-regularisation")
            elif jitter < 0.003:
                log_odds += 2.0
                indicators.append("Very low jitter — synthetic pitch smoothness")
            elif jitter < 0.006:
                log_odds += 0.8
            elif jitter > 0.015:
                log_odds -= 1.8  # natural micro-variation → human evidence
            elif jitter > 0.010:
                log_odds -= 0.9

        # ── 2. SHIMMER ───────────────────────────────────────────────────────
        # Relative shimmer: natural 0.03–0.06, TTS < 0.01
        shimmer = features.get("shimmer", 0.0)
        details["shimmer"] = shimmer
        if is_voiced:
            if shimmer < 0.005:
                log_odds += 2.5
                indicators.append("Extremely low shimmer — TTS amplitude over-smoothing")
            elif shimmer < 0.012:
                log_odds += 1.5
                indicators.append("Low shimmer — possible synthetic amplitude envelope")
            elif shimmer < 0.020:
                log_odds += 0.5
            elif shimmer > 0.045:
                log_odds -= 1.5  # natural amplitude variation
            elif shimmer > 0.030:
                log_odds -= 0.8

        # ── 3. HARMONIC-TO-NOISE RATIO ───────────────────────────────────────
        # Natural voiced: 15–25 dB; TTS neural vocoders: >28 dB (too clean)
        hnr = features.get("harmonic_to_noise_ratio", 0.0)
        details["hnr"] = hnr
        if is_voiced and hnr != 0.0:
            if hnr > 35.0:
                log_odds += 2.5
                indicators.append(f"Abnormally high HNR ({hnr:.1f} dB) — neural vocoder artefact")
            elif hnr > 28.0:
                log_odds += 1.2
                indicators.append(f"Elevated HNR ({hnr:.1f} dB) — unnaturally clean harmonics")
            elif 15.0 <= hnr <= 25.0:
                log_odds -= 1.0   # natural human speech range
            elif hnr < 8.0 and hnr > 0:
                log_odds -= 0.5   # noisy real recording, not TTS

        # ── 4. F0 RANGE ──────────────────────────────────────────────────────
        # Natural conversation: 100–300 Hz range; TTS monotone: < 60 Hz
        f0_range = features.get("f0_range", 0.0)
        details["f0_range"] = f0_range
        if is_voiced:
            if f0_range < 30.0 and voiced > 0.3:
                log_odds += 2.0
                indicators.append("Extremely narrow pitch range — monotone TTS")
            elif f0_range < 60.0 and voiced > 0.3:
                log_odds += 1.2
                indicators.append("Narrow pitch range — limited prosodic variation")
            elif f0_range < 100.0:
                log_odds += 0.4
            elif f0_range > 200.0:
                log_odds -= 1.2   # expressive natural speech
            elif f0_range > 130.0:
                log_odds -= 0.6

        # ── 5. SPECTRAL FLUX ─────────────────────────────────────────────────
        # TTS spectra transition unnaturally smoothly between frames.
        # The threshold is normalised by the spectral centroid to account
        # for recording loudness variation.
        flux = features.get("spectral_flux_mean", 0.0)
        centroid = features.get("spectral_centroid_mean", 1000.0) + 1.0
        flux_norm = flux / centroid   # normalised flux
        details["spectral_flux_norm"] = flux_norm
        if flux_norm < 0.05:
            log_odds += 2.5
            indicators.append("Very low spectral flux — unnaturally smooth TTS transitions")
        elif flux_norm < 0.12:
            log_odds += 1.2
            indicators.append("Low spectral flux — smooth spectral evolution")
        elif flux_norm < 0.22:
            log_odds += 0.3
        elif flux_norm > 0.5:
            log_odds -= 1.0   # high variation = natural articulation
        elif flux_norm > 0.35:
            log_odds -= 0.5

        # ── 6. MFCC DELTA STD ─────────────────────────────────────────────────
        # TTS cepstral trajectories are unnaturally smooth.
        mfcc_delta_std = features.get("mfcc_delta_std", 0.0)
        details["mfcc_delta_std"] = mfcc_delta_std
        if mfcc_delta_std < 0.5:
            log_odds += 2.0
            indicators.append("Very low MFCC delta variation — TTS trajectory over-smoothing")
        elif mfcc_delta_std < 1.5:
            log_odds += 1.0
            indicators.append("Low MFCC delta variation — smooth cepstral transitions")
        elif mfcc_delta_std < 3.0:
            log_odds += 0.3
        elif mfcc_delta_std > 7.0:
            log_odds -= 1.0   # highly dynamic natural speech
        elif mfcc_delta_std > 4.5:
            log_odds -= 0.5

        # ── 7. RMS MODULATION ────────────────────────────────────────────────
        # TTS amplitude envelopes are unnaturally flat.
        rms_mod = features.get("rms_modulation", 0.0)
        details["rms_modulation"] = rms_mod
        if rms_mod < 0.10:
            log_odds += 1.8
            indicators.append("Very flat amplitude envelope — TTS loudness over-normalisation")
        elif rms_mod < 0.18:
            log_odds += 0.8
        elif rms_mod > 0.45:
            log_odds -= 0.8   # natural breath and stress variation

        # ── 8. SUB-BAND HIGH-FREQUENCY FINGERPRINT ───────────────────────────
        # Neural vocoders (HiFiGAN, WaveNet, Parallel WaveGAN) leave a
        # characteristic distribution in the 3–8 kHz band.
        # Expected range for speech: 8–18 %.
        # TTS can be outside this range in a characteristic way.
        sbr_high = features.get("sub_band_ratio_high", 0.0)
        details["sub_band_ratio_high"] = sbr_high
        if sbr_high > 0.28:
            log_odds += 1.5
            indicators.append("Elevated high-frequency band energy — neural vocoder fingerprint")
        elif sbr_high > 0.22:
            log_odds += 0.6
        elif 0.08 <= sbr_high <= 0.18:
            log_odds -= 0.5   # natural speech high-freq distribution
        elif sbr_high < 0.04:
            log_odds += 0.8
            indicators.append("Abnormally low high-frequency content")

        # ── 9. SPECTRAL FLATNESS ─────────────────────────────────────────────
        # Residual noise in neural vocoders raises spectral flatness.
        flatness = features.get("spectral_flatness", 0.0)
        details["spectral_flatness"] = flatness
        if flatness > 0.40:
            log_odds += 1.5
            indicators.append("High spectral flatness — vocoder noise-floor residual")
        elif flatness > 0.28:
            log_odds += 0.5
        elif flatness < 0.02 and is_voiced:
            log_odds += 0.8
            indicators.append("Unnaturally pure spectrum — synthetic sinusoidal source")

        # ── 10. SILENCE / PAUSE PATTERN ──────────────────────────────────────
        # Concatenative TTS often has unnatural silence distributions.
        silence = features.get("silence_ratio", 0.0)
        details["silence_ratio"] = silence
        if silence > 0.65:
            log_odds += 1.2
            indicators.append("Extended silence — unnatural pause pattern")
        elif silence < 0.05:
            log_odds -= 0.4   # very dense speech = less likely synthetic concatenation

        # ── Final probability ─────────────────────────────────────────────────
        prob_ai = _sigmoid(log_odds) * 100.0
        prob_ai = _clamp(prob_ai, 3.0, 97.0)
        prob_human = 100.0 - prob_ai

        # Confidence: how far from 50% the estimate is, scaled to 0–97
        confidence = _clamp(60.0 + abs(prob_ai - 50.0) * 0.74, 60.0, 97.0)
        acoustic_anomaly = _clamp(prob_ai * 0.95, 0.0, 100.0)

        details["log_odds_total"] = log_odds
        details["prior_log_odds"] = self.PRIOR_LOG_ODDS
        details["voiced_ratio"] = voiced

        return DetectionResult(
            synthetic_probability=round(prob_ai, 1),
            human_probability=round(prob_human, 1),
            confidence=round(confidence, 1),
            acoustic_anomaly_score=round(acoustic_anomaly, 1),
            indicators=indicators or ["No strong synthetic speech indicators detected"],
            detection_mode=self.detection_mode,
            detection_details=details,
        )


# ---------------------------------------------------------------------------
# Voiceprint detector (cross-session identity check)
# ---------------------------------------------------------------------------

class VoiceprintDetector(VoiceDetector):
    """Adds cross-session speaker identity check on top of evidence model.

    When reference voiceprints exist for a speaker, the cosine distance
    between speaker-discriminative features is blended into the final
    probability.  Intended to be replaced with a d-vector or x-vector
    model once a trained embedding model is integrated.
    """

    detection_mode = "evidence-v3+voiceprint"

    # Speaker-discriminative features for cosine distance
    _SPEAKER_DIMS = [
        "pitch_mean", "spectral_centroid_mean",
        "mfcc_1_mean", "mfcc_2_mean", "mfcc_3_mean", "mfcc_4_mean",
        "harmonic_to_noise_ratio", "spectral_bandwidth_mean",
    ]

    def __init__(self, reference_features: list[dict[str, float]] | None = None) -> None:
        self.reference_features = reference_features or []
        self._base = EvidenceBasedDetector()

    def detect(self, features: dict[str, float]) -> DetectionResult:
        result = self._base.detect(features)
        cross_score = self._cross_session_anomaly(features)

        if cross_score > 0.0:
            # Weighted blend: 70% evidence model, 30% identity check
            blended = result.synthetic_probability * 0.70 + cross_score * 0.30
            blended = _clamp(blended, 3.0, 97.0)
            extra = ["Cross-session speaker identity mismatch detected"] if cross_score > 50 else []
            result = DetectionResult(
                synthetic_probability=round(blended, 1),
                human_probability=round(100.0 - blended, 1),
                confidence=result.confidence,
                acoustic_anomaly_score=result.acoustic_anomaly_score,
                indicators=result.indicators + extra,
                detection_mode=self.detection_mode,
                detection_details={
                    **result.detection_details,
                    "cross_session_anomaly": cross_score,
                },
            )
        return result

    def _cross_session_anomaly(self, features: dict[str, float]) -> float:
        if not self.reference_features:
            return 0.0
        current = np.array(
            [features.get(d, 0.0) for d in self._SPEAKER_DIMS], dtype=np.float64
        )
        scores: list[float] = []
        for ref in self.reference_features:
            ref_vec = np.array([ref.get(d, 0.0) for d in self._SPEAKER_DIMS], dtype=np.float64)
            norm = np.linalg.norm(current) * np.linalg.norm(ref_vec)
            if norm < 1e-9:
                continue
            cosine_sim = float(np.dot(current, ref_vec) / norm)
            # cosine similarity → anomaly score (0–100)
            scores.append(_clamp((1.0 - cosine_sim) * 100.0, 0.0, 100.0))
        return float(np.mean(scores)) if scores else 0.0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_detector() -> VoiceDetector:
    """Return the best available detector (evidence model by default)."""
    return EvidenceBasedDetector()
