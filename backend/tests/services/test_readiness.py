from datetime import datetime, timezone

from app.connectors.github_connector import GitHubRepoData
from app.services.readiness import compute_readiness_checks

NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


def make_github_repo(**overrides):
    defaults = dict(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
    )
    defaults.update(overrides)
    return GitHubRepoData(**defaults)


def test_migrated_from_ado_passes_when_repo_absent_from_ado_snapshot():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=1, now=NOW)
    migrated = next(c for c in checks if c.stage_key == "migrated_from_ado")
    assert migrated.status == "pass"
    assert migrated.source == "auto"


def test_migrated_from_ado_fails_when_repo_still_present_in_ado():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names={"checkout-web"}, repo_id=1, now=NOW)
    migrated = next(c for c in checks if c.stage_key == "migrated_from_ado")
    assert migrated.status == "fail"


def test_codeowners_and_readme_and_branch_protection_map_directly():
    checks = compute_readiness_checks(
        make_github_repo(has_codeowners=False, has_readme=True, branch_protection_enabled=False),
        ado_repo_names=set(),
        repo_id=1,
        now=NOW,
    )
    by_key = {c.stage_key: c for c in checks}
    assert by_key["codeowners_assigned"].status == "fail"
    assert by_key["readme_present"].status == "pass"
    assert by_key["branch_protection"].status == "fail"
    assert by_key["branch_protection"].detail == {"required_reviewer_count": 0}


def test_naming_standardized_is_always_pending_convention_for_now():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=1, now=NOW)
    naming = next(c for c in checks if c.stage_key == "naming_standardized")
    assert naming.status == "pending_convention"
    assert naming.source == "auto"


def test_domain_assigned_is_never_produced_by_the_readiness_service():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=1, now=NOW)
    assert all(c.stage_key != "domain_assigned" for c in checks)


def test_all_checks_are_stamped_with_repo_id_and_timestamp():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=42, now=NOW)
    assert all(c.repo_id == 42 and c.updated_at == NOW for c in checks)
