from datetime import datetime

from app.connectors.github_connector import GitHubRepoData
from app.models import ReadinessCheck


def compute_readiness_checks(
    github_repo: GitHubRepoData,
    ado_repo_names: set[str],
    repo_id: int,
    now: datetime,
) -> list[ReadinessCheck]:
    migrated = github_repo.name not in ado_repo_names

    return [
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="migrated_from_ado",
            status="pass" if migrated else "fail",
            source="auto",
            detail=None,
            updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="codeowners_assigned",
            status="pass" if github_repo.has_codeowners else "fail",
            source="auto",
            detail=None,
            updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="readme_present",
            status="pass" if github_repo.has_readme else "fail",
            source="auto",
            detail=None,
            updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="branch_protection",
            status="pass" if github_repo.branch_protection_enabled else "fail",
            source="auto",
            detail={"required_reviewer_count": github_repo.required_reviewer_count if github_repo.branch_protection_enabled else 0},
            updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="naming_standardized",
            status="pending_convention",
            source="auto",
            detail=None,
            updated_at=now,
        ),
    ]
