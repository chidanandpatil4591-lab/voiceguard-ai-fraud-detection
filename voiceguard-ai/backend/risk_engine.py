"""Risk scoring engine for VoiceGuard AI.

Calculates voice-based and contextual risk scores, combines them into a
final assessment, and generates structured alert events when thresholds
are exceeded.

Risk levels
-----------
- LOW      (0 – 30)
- MEDIUM   (31 – 60)
- HIGH     (61 – 80)
- CRITICAL (81 – 100)

Alert thresholds are configurable per deployment scenario:
- ``banking``    — HIGH triggers an alert
- ``enterprise`` — CRITICAL triggers an alert
- ``government`` — MEDIUM triggers an alert
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RiskResult:
    risk_score: int
    risk_level: str
    recommended_action: str


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

# Minimum risk level (inclusive) at which an alert event is generated,
# keyed by deployment scenario.  Override via the ALERT_THRESHOLD env var.
ALERT_THRESHOLDS: dict[str, str] = {
    "banking": "HIGH",
    "enterprise": "CRITICAL",
    "government": "MEDIUM",
    "default": "HIGH",
}

_LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def level_meets_threshold(level: str, threshold: str) -> bool:
    """Return True when *level* is at or above *threshold*."""
    return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER.get(threshold, 2)


# ---------------------------------------------------------------------------
# Risk level helpers
# ---------------------------------------------------------------------------

def risk_level_for(score: float) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MEDIUM"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


def recommended_action_for(level: str) -> str:
    actions: dict[str, str] = {
        "LOW": "Proceed with standard verification.",
        "MEDIUM": "Use caution — confirm the caller's identity before proceeding.",
        "HIGH": "Pause the request and perform independent secondary verification.",
        "CRITICAL": (
            "Do NOT authorize any sensitive action. Escalate immediately and "
            "perform multi-factor out-of-band verification."
        ),
    }
    return actions.get(level, actions["LOW"])


# ---------------------------------------------------------------------------
# Voice risk calculation
# ---------------------------------------------------------------------------

def calculate_voice_risk(
    synthetic_probability: float,
    acoustic_anomaly_score: float,
) -> RiskResult:
    """Convert model outputs into a normalised 0-100 risk score.

    At very high synthetic probability (≥ 80 %) the acoustic anomaly score
    has little marginal value; at lower probabilities it acts as a useful
    tie-breaker.
    """
    if synthetic_probability >= 80:
        score = max(0.0, min(100.0, 70.0 + (synthetic_probability - 80) * 1.5))
    elif synthetic_probability >= 60:
        score = max(
            0.0,
            min(
                100.0,
                synthetic_probability * 0.80 + acoustic_anomaly_score * 0.20,
            ),
        )
    else:
        score = max(
            0.0,
            min(
                100.0,
                synthetic_probability * 0.65 + acoustic_anomaly_score * 0.35,
            ),
        )

    score = round(score)
    level = risk_level_for(score)
    return RiskResult(score, level, recommended_action_for(level))


# ---------------------------------------------------------------------------
# Contextual risk calculation
# ---------------------------------------------------------------------------

def calculate_contextual_risk(
    caller_known: bool,
    transaction_type: str,
    transaction_amount: float,
    urgent_request: bool,
    sensitive_information_requested: bool,
) -> tuple[int, list[str]]:
    """Compute a 0-100 contextual risk score based on call metadata.

    Returns ``(score, indicators)`` where *indicators* is a list of
    human-readable strings describing what elevated the score.
    """
    score = 0
    indicators: list[str] = []

    if not caller_known:
        score += 22
        indicators.append("Unknown caller — identity unverified")

    if transaction_amount >= 1_000_000:
        score += 32
        indicators.append("High-value transaction (≥ ₹10 L)")
    elif transaction_amount >= 100_000:
        score += 22
        indicators.append("Elevated transaction value (≥ ₹1 L)")
    elif transaction_amount > 0:
        score += 8

    if transaction_type in {"fund_transfer", "credential_reset", "payment_change"}:
        score += 12
        indicators.append(f"Sensitive transaction type: {transaction_type.replace('_', ' ')}")

    if urgent_request:
        score += 18
        indicators.append("Caller creating urgency — social-engineering indicator")

    if sensitive_information_requested:
        score += 16
        indicators.append("Request for sensitive information")

    return min(score, 100), indicators


# ---------------------------------------------------------------------------
# Combined risk
# ---------------------------------------------------------------------------

def combine_risk(voice_risk_score: float, contextual_risk_score: float) -> RiskResult:
    """Combine voice and contextual scores (55 % / 45 % weighted blend)."""
    score = round(
        max(0.0, min(100.0, voice_risk_score * 0.55 + contextual_risk_score * 0.45))
    )
    level = risk_level_for(score)
    return RiskResult(score, level, recommended_action_for(level))


# ---------------------------------------------------------------------------
# Alert event generation
# ---------------------------------------------------------------------------

def generate_alert_events(
    analysis_id: str,
    risk: RiskResult,
    indicators: list[str],
    scenario: str = "default",
) -> list[dict]:
    """Return alert dicts when the risk level meets the scenario threshold.

    The returned list is empty for LOW / sub-threshold levels so callers
    can use ``if alert_events:`` as a gate.
    """
    threshold = ALERT_THRESHOLDS.get(scenario, ALERT_THRESHOLDS["default"])
    if not level_meets_threshold(risk.risk_level, threshold):
        return []

    return [
        {
            "analysis_id": analysis_id,
            "level": risk.risk_level,
            "risk_score": risk.risk_score,
            "recommended_action": risk.recommended_action,
            "indicators": indicators,
            "scenario": scenario,
        }
    ]
