"""Pydantic schemas for VoiceGuard AI API request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Context analysis
# ---------------------------------------------------------------------------

class ContextAnalysisRequest(BaseModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_known: bool = False
    transaction_type: str = Field(default="other", max_length=60)
    transaction_amount: float = Field(default=0.0, ge=0, le=1_000_000_000)
    urgent_request: bool = False
    sensitive_information_requested: bool = False
    voice_synthetic_probability: float = Field(default=0.0, ge=0, le=100)
    voice_risk_score: float = Field(default=0.0, ge=0, le=100)
    # Deployment scenario for threshold selection
    scenario: str = Field(default="default", max_length=30)


class ContextAnalysisResponse(BaseModel):
    caller_name: str
    voice_synthetic_probability: float
    # Fixed: was typed as int but the value can be a float
    contextual_risk_score: float
    final_risk_score: int
    risk_level: str
    indicators: list[str]
    recommended_action: str
    alert_events: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Speaker voiceprint enrolment / verification
# ---------------------------------------------------------------------------

class VoiceprintEnrollResponse(BaseModel):
    speaker_id: str
    enrolled_at: str
    voiceprint_count: int
    message: str


class VoiceprintVerifyResponse(BaseModel):
    speaker_id: str
    cross_session_anomaly_score: float
    risk_level: str
    message: str


# ---------------------------------------------------------------------------
# Alert events
# ---------------------------------------------------------------------------

class AlertEvent(BaseModel):
    id: str
    analysis_id: str
    level: str
    risk_score: int
    recommended_action: str
    indicators: list[str]
    channel: str
    dispatched_at: str


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_analyses: int
    average_risk_score: float
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
