from dataclasses import dataclass
from datetime import datetime

STAGE_ORDER: list[tuple[str, list[str]]] = [
    ("onboarded", ["migrated_from_ado"]),
    ("standardized", ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]),
    ("piped", ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized"]),
]

REASON_TEXT: dict[str, str] = {
    "migrated_from_ado": "Still active in Azure DevOps",
    "codeowners_assigned": "No CODEOWNERS assigned",
    "domain_assigned": "No domain assigned",
    "branch_protection": "Missing branch protection",
    "readme_present": "Missing README",
    "pipeline_linked": "No pipeline linked in Azure DevOps",
    "pipeline_is_yaml": "Pipeline hasn't migrated to YAML",
    "environment_gates_configured": "Missing an approval/check on UAT or Prod",
    "dockerized": "Dockerfile missing for a dockerize-eligible repo",
}


@dataclass
class CheckStatus:
    status: str
    status_changed_at: datetime


@dataclass
class StageInfo:
    current_stage: str
    is_stuck: bool
    dwell_days: int | None
    stuck_reason: str | None


def _waiting_on(team: str | None) -> str:
    return f"waiting on {team} team" if team else "waiting on repo owner"


def derive_stage_info(checks: dict[str, CheckStatus], team: str | None, now: datetime) -> StageInfo:
    for stage_name, stage_keys in STAGE_ORDER:
        failing_keys = [
            key for key in stage_keys
            if checks.get(key, CheckStatus(status="fail", status_changed_at=now)).status == "fail"
        ]
        if not failing_keys:
            continue

        oldest_key = min(
            failing_keys,
            key=lambda key: checks.get(key, CheckStatus(status="fail", status_changed_at=now)).status_changed_at,
        )
        oldest_changed_at = checks.get(oldest_key, CheckStatus(status="fail", status_changed_at=now)).status_changed_at
        dwell_days = (now - oldest_changed_at).days

        return StageInfo(
            current_stage=stage_name,
            is_stuck=True,
            dwell_days=dwell_days,
            stuck_reason=f"{REASON_TEXT[oldest_key]} — {_waiting_on(team)}",
        )

    return StageInfo(current_stage=STAGE_ORDER[-1][0], is_stuck=False, dwell_days=None, stuck_reason=None)
