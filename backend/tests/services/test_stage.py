from datetime import datetime, timedelta, timezone

from app.services.stage import CheckStatus, derive_stage_info

NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)


def passing_standardized_checks(now=NOW):
    return {
        "migrated_from_ado": CheckStatus(status="pass", status_changed_at=now),
        "codeowners_assigned": CheckStatus(status="pass", status_changed_at=now),
        "domain_assigned": CheckStatus(status="pass", status_changed_at=now),
        "branch_protection": CheckStatus(status="pass", status_changed_at=now),
        "readme_present": CheckStatus(status="pass", status_changed_at=now),
    }


def passing_piped_checks(now=NOW):
    checks = passing_standardized_checks(now)
    checks.update({
        "pipeline_linked": CheckStatus(status="pass", status_changed_at=now),
        "pipeline_is_yaml": CheckStatus(status="pass", status_changed_at=now),
        "environment_gates_configured": CheckStatus(status="pass", status_changed_at=now),
        "dockerized": CheckStatus(status="pass", status_changed_at=now),
    })
    return checks


def test_fully_passing_repo_including_piped_clamps_at_piped_and_is_not_stuck():
    info = derive_stage_info(passing_piped_checks(), team="Growth", now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is False
    assert info.dwell_days is None
    assert info.stuck_reason is None


def test_standardized_repo_with_no_piped_data_yet_shows_stuck_at_piped():
    checks = passing_standardized_checks()  # no piped keys present at all

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is True
    assert info.stuck_reason == "No pipeline linked in Azure DevOps — waiting on repo owner"


def test_repo_stuck_at_piped_uses_oldest_failing_check():
    checks = passing_piped_checks()
    checks["pipeline_is_yaml"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=15))
    checks["dockerized"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=2))

    info = derive_stage_info(checks, team="Luke", now=NOW)

    assert info.current_stage == "piped"
    assert info.dwell_days == 15
    assert info.stuck_reason == "Pipeline hasn't migrated to YAML — waiting on Luke team"


def test_environment_gates_unknown_does_not_block_piped_progression():
    checks = passing_piped_checks()
    checks["environment_gates_configured"] = CheckStatus(status="unknown", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is False


def test_deployed_aca_unknown_never_blocks_progression():
    checks = passing_piped_checks()
    checks["deployed_aca"] = CheckStatus(status="unknown", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is False


def test_repo_stuck_at_onboarded_reports_that_stage():
    checks = passing_standardized_checks()
    checks["migrated_from_ado"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=28))

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "onboarded"
    assert info.is_stuck is True
    assert info.dwell_days == 28
    assert info.stuck_reason == "Still active in Azure DevOps — waiting on repo owner"


def test_repo_stuck_at_standardized_uses_oldest_failing_check_and_names_team():
    checks = passing_standardized_checks()
    checks["codeowners_assigned"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=10))
    checks["branch_protection"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=41))

    info = derive_stage_info(checks, team="Platform", now=NOW)

    assert info.current_stage == "standardized"
    assert info.dwell_days == 41  # the OLDER of the two failing checks, not the newer
    assert info.stuck_reason == "Missing branch protection — waiting on Platform team"


def test_onboarded_failure_takes_priority_over_standardized_failure():
    checks = passing_standardized_checks()
    checks["migrated_from_ado"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=5))
    checks["codeowners_assigned"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=99))

    info = derive_stage_info(checks, team=None, now=NOW)

    # onboarded comes first in journey order, even though standardized has been failing longer
    assert info.current_stage == "onboarded"
    assert info.dwell_days == 5


def test_naming_standardized_never_blocks_progression():
    checks = passing_piped_checks()
    checks["naming_standardized"] = CheckStatus(status="pending_convention", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is False


def test_missing_check_key_defaults_to_failing():
    checks = passing_standardized_checks()
    del checks["readme_present"]

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "standardized"
    assert info.is_stuck is True
    assert info.stuck_reason == "Missing README — waiting on repo owner"
