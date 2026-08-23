from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class ProjectBase(BaseModel):
    project_name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    constituency: Optional[str] = None
    project_type: Optional[str] = None
    sanctioned_amount: Optional[float] = 0.0
    expenditure: Optional[float] = 0.0
    completion_percentage: Optional[float] = 0.0
    status: Optional[str] = "Ongoing"

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class RiskInfo(BaseModel):
    risk_score: int
    risk_level: str
    is_anomaly: bool
    ml_anomaly: bool = False
    ml_score: float = 0.0
    reasons: List[str] = []

class ProjectDetailResponse(BaseModel):
    project: ProjectResponse
    risk: RiskInfo

class PaginatedProjects(BaseModel):
    total: int
    skip: int
    limit: int
    results: List[ProjectResponse]

class OverviewStats(BaseModel):
    total_projects: int
    completed_projects: int
    ongoing_projects: int
    total_allocated_amount: float
    total_expenditure: float
    utilization_percentage: float
    average_completion_percentage: float
    total_mps: int
    total_states: int
    recommended_works: int
