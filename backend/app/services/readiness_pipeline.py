from datetime import datetime

from app.models import ReadinessCheck

_GATE_ENVIRONMENTS = ("dev", "qa", "uat", "prod")


def compute_pipeline_readiness_checks(
    repo_id: int,
    has_pipeline_link: bool,
    is_yaml: bool | None,
    has_classic_release_def: bool,
    environment_gates: dict[str, bool],
    now: datetime,
) -> list[ReadinessCheck]:
    pipeline_linked_status = "pass" if has_pipeline_link else "fail"

    if has_pipeline_link and is_yaml:
        pipeline_is_yaml_status = "pass"
    elif has_classic_release_def:
        pipeline_is_yaml_status = "fail"
    else:
        pipeline_is_yaml_status = "unknown"

    uat_prod_matched = "uat" in environment_gates and "prod" in environment_gates
    if not uat_prod_matched:
        gates_status = "unknown"
    elif environment_gates["uat"] and environment_gates["prod"]:
        gates_status = "pass"
    else:
        gates_status = "fail"
    gates_detail = {env: environment_gates.get(env, False) for env in _GATE_ENVIRONMENTS}

    return [
        ReadinessCheck(
            repo_id=repo_id, stage_key="pipeline_linked", status=pipeline_linked_status,
            source="auto", detail=None, updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id, stage_key="pipeline_is_yaml", status=pipeline_is_yaml_status,
            source="auto", detail=None, updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id, stage_key="environment_gates_configured", status=gates_status,
            source="auto", detail=gates_detail, updated_at=now,
        ),
    ]
