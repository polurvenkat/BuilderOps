from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StageCheckOut(BaseModel):
    status: str
    source: str
    detail: dict | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class RepoOut(BaseModel):
    id: int
    name: str
    domain: str | None
    migration_wave: str
    stages: dict[str, StageCheckOut]

    model_config = {"from_attributes": True}


class RepoPatchIn(BaseModel):
    domain: str | None = None
    migration_wave: Literal["not_started", "pilot", "rolling_out", "migrated"] | None = None


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


class SyncRunOut(BaseModel):
    id: int
    connector: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    error: str | None

    model_config = {"from_attributes": True}
