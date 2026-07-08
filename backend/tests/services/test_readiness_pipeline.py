from datetime import datetime, timezone

from app.services.readiness_pipeline import compute_pipeline_readiness_checks

NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)


def test_pipeline_linked_passes_when_link_exists():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"uat": True, "prod": True}, now=NOW,
    )
    linked = next(c for c in checks if c.stage_key == "pipeline_linked")
    assert linked.status == "pass"
    assert linked.source == "auto"


def test_pipeline_linked_fails_when_no_link_even_if_classic_release_exists():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=False, is_yaml=None, has_classic_release_def=True,
        environment_gates={}, now=NOW,
    )
    linked = next(c for c in checks if c.stage_key == "pipeline_linked")
    assert linked.status == "fail"


def test_pipeline_is_yaml_passes_when_linked_pipeline_is_yaml():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"uat": True, "prod": True}, now=NOW,
    )
    is_yaml = next(c for c in checks if c.stage_key == "pipeline_is_yaml")
    assert is_yaml.status == "pass"


def test_pipeline_is_yaml_fails_when_classic_release_definition_found_instead():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=False, is_yaml=None, has_classic_release_def=True,
        environment_gates={}, now=NOW,
    )
    is_yaml = next(c for c in checks if c.stage_key == "pipeline_is_yaml")
    assert is_yaml.status == "fail"


def test_pipeline_is_yaml_fails_when_linked_pipeline_is_not_yaml():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=False, has_classic_release_def=False,
        environment_gates={}, now=NOW,
    )
    is_yaml = next(c for c in checks if c.stage_key == "pipeline_is_yaml")
    assert is_yaml.status == "fail"


def test_pipeline_is_yaml_unknown_when_neither_yaml_nor_classic_found():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=False, is_yaml=None, has_classic_release_def=False,
        environment_gates={}, now=NOW,
    )
    is_yaml = next(c for c in checks if c.stage_key == "pipeline_is_yaml")
    assert is_yaml.status == "unknown"


def test_environment_gates_pass_when_uat_and_prod_both_configured():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"dev": False, "qa": False, "uat": True, "prod": True}, now=NOW,
    )
    gates = next(c for c in checks if c.stage_key == "environment_gates_configured")
    assert gates.status == "pass"
    assert gates.detail == {"dev": False, "qa": False, "uat": True, "prod": True}


def test_environment_gates_fail_when_prod_ungated():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"dev": False, "qa": False, "uat": True, "prod": False}, now=NOW,
    )
    gates = next(c for c in checks if c.stage_key == "environment_gates_configured")
    assert gates.status == "fail"


def test_environment_gates_unknown_when_uat_or_prod_could_not_be_matched():
    checks = compute_pipeline_readiness_checks(
        repo_id=1, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"dev": True, "qa": True}, now=NOW,
    )
    gates = next(c for c in checks if c.stage_key == "environment_gates_configured")
    assert gates.status == "unknown"
    assert gates.detail == {"dev": True, "qa": True, "uat": False, "prod": False}


def test_all_checks_are_stamped_with_repo_id_and_timestamp():
    checks = compute_pipeline_readiness_checks(
        repo_id=42, has_pipeline_link=True, is_yaml=True, has_classic_release_def=False,
        environment_gates={"uat": True, "prod": True}, now=NOW,
    )
    assert all(c.repo_id == 42 and c.updated_at == NOW for c in checks)
    assert {c.stage_key for c in checks} == {"pipeline_linked", "pipeline_is_yaml", "environment_gates_configured"}
