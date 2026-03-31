from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_resumes: int
    total_open_jobs: int
    total_applications: int
    avg_days_to_hire: float | None = None

    resumes_by_job: list[dict]
    resumes_by_channel: list[dict]
    applications_by_stage: list[dict]
    conversion_by_stage: list[dict]
    funnel_by_stage: list[dict]
    monthly_performance: list[dict]


class DashboardDiagnostics(BaseModel):
    total_processing_logs: int
    processing_success_rate: float
    processing_avg_duration_ms: float
    processing_p95_duration_ms: float | None = None

    resumes_missing_in_storage: int
    resumes_with_extracted_text: int
    extraction_coverage_rate: float
    resumes_requires_manual_review: int
    manual_review_rate: float
    review_pending_over_24h: int
    review_pending_over_72h: int
    avg_review_resolution_hours: float | None = None

    candidates_with_email: int
    candidates_with_phone: int
    candidates_with_contact_rate: float
