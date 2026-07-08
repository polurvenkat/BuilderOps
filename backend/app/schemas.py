from datetime import datetime

from pydantic import BaseModel


class RepoOut(BaseModel):
    id: int
    name: str
    domain: str | None
    migration_wave: str
    stages: dict[str, str]

    model_config = {"from_attributes": True}


class RepoPatchIn(BaseModel):
    domain: str | None = None
    migration_wave: str | None = None


class OnboardingLogIn(BaseModel):
    engineer_name: str
    hours: float


class OnboardingLogOut(BaseModel):
    id: int
    repo_id: int
    engineer_name: str
    hours: float
    logged_at: datetime

    model_config = {"from_attributes": True}
