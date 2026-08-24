from dataclasses import dataclass


@dataclass
class RiskResult:
    risk_score: int
    risk_level: str
    recommended_action: str


def risk_level_for(score: float) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MEDIUM"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


def recommended_action_for(level: str) -> str:
    actions = {
        "LOW": "Proceed with standard verification.",
        "MEDIUM": "Use caution and confirm the caller before proceeding.",
        "HIGH": "Pause the request and perform secondary verification.",
        "CRITICAL": "Do not authorize sensitive action. Perform secondary verification.",
    }
    return actions[level]


def calculate_voice_risk(synthetic_probability: float, acoustic_anomaly_score: float) -> RiskResult:
    score = round(max(0.0, min(100.0, synthetic_probability * 0.65 + acoustic_anomaly_score * 0.35)))
    level = risk_level_for(score)
    return RiskResult(score, level, recommended_action_for(level))


def calculate_contextual_risk(
    caller_known: bool,
    transaction_type: str,
    transaction_amount: float,
    urgent_request: bool,
    sensitive_information_requested: bool,
) -> tuple[int, list[str]]:
    score = 0
    indicators: list[str] = []
    if not caller_known:
        score += 22
        indicators.append("Unknown caller")
    if transaction_amount >= 1_000_000:
        score += 32
        indicators.append("High-value transaction")
    elif transaction_amount >= 100_000:
        score += 22
        indicators.append("Elevated transaction value")
    elif transaction_amount > 0:
        score += 8
    if transaction_type in {"fund_transfer", "credential_reset", "payment_change"}:
        score += 12
        indicators.append("Sensitive transaction type")
    if urgent_request:
        score += 18
        indicators.append("Urgent request")
    if sensitive_information_requested:
        score += 16
        indicators.append("Sensitive information requested")
    return min(score, 100), indicators


def combine_risk(voice_risk_score: float, contextual_risk_score: float) -> RiskResult:
    score = round(max(0.0, min(100.0, voice_risk_score * 0.55 + contextual_risk_score * 0.45)))
    level = risk_level_for(score)
    return RiskResult(score, level, recommended_action_for(level))
