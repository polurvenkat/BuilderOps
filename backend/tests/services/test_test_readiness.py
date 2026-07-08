from datetime import datetime, timezone

from app.connectors.ado_test_plans_connector import TestPlanRunResult
from app.services.test_readiness import compute_e2e_readiness_checks

NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)


def test_e2e_covered_pending_convention_when_no_test_plan_mapped():
    checks = compute_e2e_readiness_checks(repo_id=1, e2e_test_plan_id=None, latest_run=None, now=NOW)
    e2e = next(c for c in checks if c.stage_key == "e2e_covered")
    assert e2e.status == "pending_convention"
    assert e2e.detail is None


def test_e2e_covered_unknown_when_mapped_but_no_completed_run_yet():
    checks = compute_e2e_readiness_checks(repo_id=1, e2e_test_plan_id=42, latest_run=None, now=NOW)
    e2e = next(c for c in checks if c.stage_key == "e2e_covered")
    assert e2e.status == "unknown"
    assert e2e.detail == {"test_plan_id": 42}


def test_e2e_covered_passes_when_latest_run_has_zero_failures():
    run = TestPlanRunResult(passed_count=20, failed_count=0, total_count=20, completed_date="2026-07-08T00:00:00Z")
    checks = compute_e2e_readiness_checks(repo_id=1, e2e_test_plan_id=42, latest_run=run, now=NOW)
    e2e = next(c for c in checks if c.stage_key == "e2e_covered")
    assert e2e.status == "pass"
    assert e2e.detail == {
        "test_plan_id": 42, "passed_count": 20, "failed_count": 0, "total_count": 20,
        "completed_date": "2026-07-08T00:00:00Z",
    }


def test_e2e_covered_fails_when_latest_run_has_failures():
    run = TestPlanRunResult(passed_count=13, failed_count=2, total_count=15, completed_date="2026-07-08T00:00:00Z")
    checks = compute_e2e_readiness_checks(repo_id=1, e2e_test_plan_id=42, latest_run=run, now=NOW)
    e2e = next(c for c in checks if c.stage_key == "e2e_covered")
    assert e2e.status == "fail"


def test_unit_and_integration_and_load_ship_as_placeholder_statuses():
    checks = compute_e2e_readiness_checks(repo_id=1, e2e_test_plan_id=None, latest_run=None, now=NOW)
    by_key = {c.stage_key: c for c in checks}
    assert by_key["unit_tested"].status == "pending_convention"
    assert by_key["integration_tested"].status == "pending_convention"
    assert by_key["load_tested"].status == "unknown"


def test_all_checks_are_stamped_with_repo_id_and_timestamp():
    checks = compute_e2e_readiness_checks(repo_id=99, e2e_test_plan_id=None, latest_run=None, now=NOW)
    assert all(c.repo_id == 99 and c.updated_at == NOW for c in checks)
    assert {c.stage_key for c in checks} == {"e2e_covered", "unit_tested", "integration_tested", "load_tested"}
