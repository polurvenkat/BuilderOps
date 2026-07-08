from datetime import datetime

from app.connectors.ado_test_plans_connector import TestPlanRunResult
from app.models import ReadinessCheck


def compute_e2e_readiness_checks(
    repo_id: int,
    e2e_test_plan_id: int | None,
    latest_run: TestPlanRunResult | None,
    now: datetime,
) -> list[ReadinessCheck]:
    if e2e_test_plan_id is None:
        e2e_status = "pending_convention"
        e2e_detail = None
    elif latest_run is None:
        e2e_status = "unknown"
        e2e_detail = {"test_plan_id": e2e_test_plan_id}
    else:
        e2e_status = "pass" if latest_run.failed_count == 0 else "fail"
        e2e_detail = {
            "test_plan_id": e2e_test_plan_id,
            "passed_count": latest_run.passed_count,
            "failed_count": latest_run.failed_count,
            "total_count": latest_run.total_count,
            "completed_date": latest_run.completed_date,
        }

    return [
        ReadinessCheck(
            repo_id=repo_id, stage_key="e2e_covered", status=e2e_status,
            source="auto", detail=e2e_detail, updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id, stage_key="unit_tested", status="pending_convention",
            source="auto", detail=None, updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id, stage_key="integration_tested", status="pending_convention",
            source="auto", detail=None, updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id, stage_key="load_tested", status="unknown",
            source="auto", detail=None, updated_at=now,
        ),
    ]
