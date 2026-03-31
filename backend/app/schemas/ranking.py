from pydantic import BaseModel


class RankingItem(BaseModel):
    candidate_id: int
    candidate_name: str
    email: str | None
    phone: str | None
    linkedin: str | None
    address: str | None
    match_percent: float
    match_breakdown: dict
    justification: str | None
    professional_summary: str | None
    strengths: list[str]
    stage: str | None = None
    application_id: int | None = None
    resume_id: int | None = None
    scoring_profile: dict | None = None
    primary_role: str | None = None
    secondary_roles: list[str] = []
    role_confidence: float | None = None
    role_needs_review: bool | None = None
    rank_position: int | None = None
    rank_reason: str | None = None


class JobRankingResponse(BaseModel):
    job_id: int
    job_title: str | None = None
    department: str | None = None
    count: int
    items: list[RankingItem]


class ScoringProfileWeights(BaseModel):
    cargo: float = 0.30
    formacao: float = 0.20
    cursos: float = 0.25
    experiencia: float = 0.25


class CustomRankingFilter(BaseModel):
    label: str
    keywords: list[str] = []
    mode: str = "bonus"  # bonus | required
    points: float = 3.0


class RankingFilters(BaseModel):
    required_courses: list[str] = []
    minimum_years_experience: float = 0.0
    preferred_cities: list[str] = []
    residence_required: bool = False
    custom_filters: list[CustomRankingFilter] = []


class ScoringProfileUpdate(BaseModel):
    weights: ScoringProfileWeights | None = None
    porto_alegre_bonus: float | None = None
    minimum_signal_floor: float | None = None
    ranking_filters: RankingFilters | None = None


class ScoringProfileOut(BaseModel):
    weights: ScoringProfileWeights
    porto_alegre_bonus: float
    minimum_signal_floor: float
    ranking_filters: RankingFilters


class RankingFeedbackIn(BaseModel):
    application_id: int
    decision: str  # approved | promoted | rejected
    note: str | None = None


class RankingFeedbackOut(BaseModel):
    job_id: int
    application_id: int
    decision: str
    updated_profile: dict


class RankingAuditOut(BaseModel):
    job_id: int
    current_profile: dict
    feedback_events: list[dict]
    ranking_snapshot: list[dict]
