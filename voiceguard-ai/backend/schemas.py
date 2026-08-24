from pydantic import BaseModel, Field


class ContextAnalysisRequest(BaseModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_known: bool = False
    transaction_type: str = Field(default="other", max_length=60)
    transaction_amount: float = Field(default=0, ge=0, le=1_000_000_000)
    urgent_request: bool = False
    sensitive_information_requested: bool = False
    voice_synthetic_probability: float = Field(default=0, ge=0, le=100)
    voice_risk_score: float = Field(default=0, ge=0, le=100)


class ContextAnalysisResponse(BaseModel):
    caller_name: str
    voice_synthetic_probability: float
    contextual_risk_score: int
    final_risk_score: int
    risk_level: str
    indicators: list[str]
    recommended_action: str
