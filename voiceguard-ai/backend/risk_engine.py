"""Division 3: Decisive Contextual Risk Engine & Policy Dispatch (VoiceGuard AI)."""
from __future__ import annotations
from typing import Any

ALERT_THRESHOLDS = {
    "banking": {"score": 50.0, "risk_level": "HIGH"},
    "enterprise": {"score": 60.0, "risk_level": "HIGH"},
    "government": {"score": 45.0, "risk_level": "HIGH"},
    "standard": {"score": 65.0, "risk_level": "HIGH"},
}


def calculate_voice_risk(
    synthetic_probability: float,
    acoustic_anomaly_score: float,
    scenario: str = "banking",
    transaction_amount: float = 0.0,
    urgent_request: bool = False,
) -> dict[str, Any]:
    # Decisive direct risk calculation
    base_risk = (synthetic_probability * 0.90) + (acoustic_anomaly_score * 0.10)

    context_multiplier = 1.0
    if scenario == "banking":
        context_multiplier += 0.10
        if transaction_amount > 50000:
            context_multiplier += 0.15
    elif scenario == "government":
        context_multiplier += 0.20

    if urgent_request:
        context_multiplier += 0.15

    final_score = round(min(100.0, max(0.0, base_risk * context_multiplier)), 1)

    if final_score >= 75.0:
        level = "CRITICAL"
        action = "BLOCK_IMMEDIATELY"
        explanation = "High-confidence synthetic voice attack detected. Transaction blocked & security team notified."
    elif final_score >= 50.0:
        level = "HIGH"
        action = "HOLD_AND_STEP_UP_AUTH"
        explanation = "Probable AI voice impersonation detected. Require out-of-band video verification."
    elif final_score >= 30.0:
        level = "MEDIUM"
        action = "FLAG_FOR_REVIEW"
        explanation = "Suspicious acoustic traits detected. Secondary confirmation recommended."
    else:
        level = "LOW"
        action = "PROCEED"
        explanation = "Acoustic signatures verified: Authentic human biological speaker."

    return {
        "contextual_risk_score": final_score,
        "risk_level": level,
        "recommended_action": action,
        "scenario": scenario,
        "explanation": explanation,
    }
