# Backend API Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Phase 0 backend API so it can power the Repo Fleet landing page (§7.1 of the design spec) — add real dwell-time tracking, a server-computed "current stage" per repo, filter/sort support on `GET /repos`, and a read endpoint for onboarding logs.

**Architecture:** All additions are extensions to the existing backend (`backend/app/`), not a new service. A new `upsert_readiness_check` helper centralizes the status-change-detection logic every write path needs; a new pure `stage.py` service derives each repo's current station from its checks, exactly the way `readiness.py` already derives checks from connector data.

**Tech Stack:** Same as the existing backend — Python, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest.

## Global Constraints

- `ReadinessCheck.status_changed_at` only updates when `status` actually changes — never on every sync, or dwell time becomes meaningless (this was the whole reason this plan exists).
- Current-stage derivation is a **pure function** (no DB access) — same testability discipline as `compute_readiness_checks` in the original backend plan.
- Current-stage derivation is **clamped at `standardized`** — Phase 0 has no real Piped/Tested data, so a repo that clears every Standardized check must never be reported as being in a stage we can't verify.
- No credential handling changes in this plan — skip any task that would touch `config.py`.
- SQLite in-memory for all tests, consistent with the existing suite.

---

## File Structure

```
backend/
  app/
    models.py                    # MODIFY: add ReadinessCheck.status_changed_at
    schemas.py                   # MODIFY: extend RepoOut, add OnboardingSummaryOut
    services/
      readiness_store.py         # NEW: upsert_readiness_check (status-change-aware upsert)
      stage.py                   # NEW: derive_stage_info (pure current-stage/dwell/reason logic)
      sync_service.py            # MODIFY: use upsert_readiness_check instead of session.merge
    api/
      repos.py                   # MODIFY: wire stage.py into _to_repo_out, add query params,
                                  #         add GET onboarding-log endpoint, materialize domain_assigned
  tests/
    services/
      test_readiness_store.py    # NEW
      test_stage.py               # NEW
      test_sync_service.py        # MODIFY: assert status_changed_at behavior
    api/
      test_repos_api.py           # MODIFY: new fields, filters, sort, onboarding-log endpoint
```

---

### Task 1: `status_changed_at` field + status-change-aware upsert helper

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/services/readiness_store.py`
- Create: `backend/tests/services/test_readiness_store.py`

**Interfaces:**
- Consumes: `ReadinessCheck` model, `Session` (SQLAlchemy).
- Produces: `ReadinessCheck.status_changed_at: Mapped[datetime]` (non-nullable, default `_utcnow`).
- Produces: `def upsert_readiness_check(session: Session, check: ReadinessCheck) -> None` — looks up any existing row by `(check.repo_id, check.stage_key)`. If none exists, or the existing row's `status` differs from `check.status`, sets `check.status_changed_at = check.updated_at` (i.e., "now"). Otherwise, preserves the existing row's `status_changed_at`. Then calls `session.merge(check)`. This is the ONLY function anywhere in the codebase allowed to write a `ReadinessCheck` row — Task 2's `sync_service.py` and `api/repos.py` changes both route through it.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_readiness_store.py
from datetime import datetime, timedelta, timezone

from app.db import Base, get_engine, get_sessionmaker
from app.models import ReadinessCheck, Repo
from app.services.readiness_store import upsert_readiness_check

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=5)


def make_session():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = get_sessionmaker(engine)()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()
    return session, repo.id


def test_first_write_sets_status_changed_at_to_updated_at():
    session, repo_id = make_session()

    check = ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    )
    upsert_readiness_check(session, check)
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert row.status_changed_at == T0


def test_status_unchanged_preserves_original_status_changed_at():
    session, repo_id = make_session()
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    ))
    session.commit()

    # second sync, same status, later timestamp
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T1,
    ))
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert row.updated_at == T1
    assert row.status_changed_at == T0  # unchanged, since status didn't change


def test_status_change_updates_status_changed_at():
    session, repo_id = make_session()
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    ))
    session.commit()

    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="pass",
        source="auto", detail=None, updated_at=T1,
    ))
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert row.status == "pass"
    assert row.status_changed_at == T1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.readiness_store'`

- [ ] **Step 3: Add the column to `app/models.py`**

Add this field to the `ReadinessCheck` class, immediately after `updated_at`:

```python
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Implement `app/services/readiness_store.py`**

```python
# backend/app/services/readiness_store.py
from sqlalchemy.orm import Session

from app.models import ReadinessCheck


def upsert_readiness_check(session: Session, check: ReadinessCheck) -> None:
    existing = session.get(ReadinessCheck, (check.repo_id, check.stage_key))
    if existing is None or existing.status != check.status:
        check.status_changed_at = check.updated_at
    else:
        check.status_changed_at = existing.status_changed_at
    session.merge(check)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness_store.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/services/readiness_store.py backend/tests/services/test_readiness_store.py
git commit -m "feat: add status_changed_at tracking via a status-change-aware upsert helper"
```

---

### Task 2: Wire the upsert helper into sync_service, materialize `domain_assigned`, expose `team`

**Files:**
- Modify: `backend/app/services/sync_service.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/services/test_sync_service.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `upsert_readiness_check` (Task 1).
- Produces: `RepoPatchIn.team: str | None` — `team` becomes PATCH-able, same pattern as `domain`.
- Produces: `RepoOut.team: str | None`, `RepoOut.github_url: str`, `RepoOut.last_synced_at: datetime | None` — previously-hidden `Repo` columns now exposed.
- Produces: `patch_repo` now upserts a real `ReadinessCheck(stage_key="domain_assigned", source="manual", ...)` row via `upsert_readiness_check` whenever `domain` changes, instead of `_to_repo_out` synthesizing a fake one — this is what gives `domain_assigned` a real `status_changed_at` for dwell-time purposes.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_sync_service.py — add this test; keep all existing tests
```

Add to the existing file:

```python
@pytest.mark.asyncio
async def test_run_github_sync_preserves_status_changed_at_across_unchanged_runs(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    later = NOW.replace(year=NOW.year + 1)  # clearly-later timestamp, same mocked (unchanged) data
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=later)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    check = session.query(ReadinessCheck).filter_by(repo_id=repo.id, stage_key="codeowners_assigned").one()
    assert check.updated_at == later          # touched every sync
    assert check.status_changed_at == NOW     # unchanged, since status didn't change
```

```python
# backend/tests/api/test_repos_api.py — add these tests; keep all existing tests, updating seed_repo if needed
```

Add to the existing file:

```python
def test_patch_repo_updates_team():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"team": "Growth"})

    assert response.status_code == 200
    assert response.json()["team"] == "Growth"


def test_repo_out_exposes_github_url_and_last_synced_at():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["github_url"] == "https://github.com/acme-org/checkout-web"
    assert "last_synced_at" in body


def test_patch_repo_domain_materializes_a_real_domain_assigned_check():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    client.patch(f"/repos/{repo_id}", json={"domain": "Checkout"})
    body = client.get(f"/repos/{repo_id}").json()

    assert body["stages"]["domain_assigned"]["status"] == "pass"
    assert body["stages"]["domain_assigned"]["source"] == "manual"
    assert body["stages"]["domain_assigned"]["updated_at"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_sync_service.py tests/api/test_repos_api.py -v`
Expected: FAIL — `test_patch_repo_updates_team` (no `team` field on `RepoPatchIn`/`RepoOut`), `test_repo_out_exposes_github_url_and_last_synced_at` (`KeyError: 'github_url'`), `test_patch_repo_domain_materializes_a_real_domain_assigned_check` (`updated_at` will be `None`, since it's still synthesized), `test_run_github_sync_preserves_status_changed_at_across_unchanged_runs` (`AttributeError` or `None` since `status_changed_at` isn't populated by the raw `session.merge` call yet)

- [ ] **Step 3: Update `app/schemas.py`**

```python
# In RepoOut, add these three fields alongside the existing ones:
class RepoOut(BaseModel):
    id: int
    name: str
    domain: str | None
    team: str | None
    migration_wave: str
    github_url: str
    last_synced_at: datetime | None
    stages: dict[str, StageCheckOut]

    model_config = {"from_attributes": True}


# In RepoPatchIn, add team:
class RepoPatchIn(BaseModel):
    domain: str | None = None
    team: str | None = None
    migration_wave: Literal["not_started", "pilot", "rolling_out", "migrated"] | None = None
```

- [ ] **Step 4: Update `app/services/sync_service.py`**

Replace the import and the merge call:

```python
from app.services.readiness_store import upsert_readiness_check
```

Replace:
```python
            for check in compute_readiness_checks(github_repo, ado_repo_names, repo.id, now):
                session.merge(check)
```
with:
```python
            for check in compute_readiness_checks(github_repo, ado_repo_names, repo.id, now):
                upsert_readiness_check(session, check)
```

- [ ] **Step 5: Update `app/api/repos.py`**

Replace the `_to_repo_out` function and `patch_repo` endpoint:

```python
from datetime import datetime, timezone

from app.services.readiness_store import upsert_readiness_check
from app.models import ReadinessCheck


def _to_repo_out(repo: Repo, session: Session) -> RepoOut:
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    stages = {
        c.stage_key: StageCheckOut(status=c.status, source=c.source, detail=c.detail, updated_at=c.updated_at)
        for c in checks
    }
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        team=repo.team,
        migration_wave=repo.migration_wave,
        github_url=repo.github_url,
        last_synced_at=repo.last_synced_at,
        stages=stages,
    )


@router.patch("/{repo_id}", response_model=RepoOut)
def patch_repo(repo_id: int, body: RepoPatchIn, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if body.domain is not None:
        repo.domain = body.domain
        now = datetime.now(timezone.utc)
        upsert_readiness_check(session, ReadinessCheck(
            repo_id=repo_id,
            stage_key="domain_assigned",
            status="pass" if body.domain else "fail",
            source="manual",
            detail=None,
            updated_at=now,
        ))
    if body.team is not None:
        repo.team = body.team
    if body.migration_wave is not None:
        repo.migration_wave = body.migration_wave
    session.commit()
    return _to_repo_out(repo, session)
```

Note: `RepoPatchIn.domain` is `str | None` with no way to distinguish "not provided" from "explicitly cleared to empty string" — this matches the existing pattern (same ambiguity already exists for `migration_wave`) and is not a regression this task needs to solve.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_sync_service.py tests/api/test_repos_api.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 7: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test — this task touches shared code paths, so a full-suite check matters here)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/sync_service.py backend/app/schemas.py backend/app/api/repos.py backend/tests/services/test_sync_service.py backend/tests/api/test_repos_api.py
git commit -m "feat: expose team/github_url/last_synced_at, materialize domain_assigned as a real tracked check"
```

---

### Task 3: Current-stage derivation service

**Files:**
- Create: `backend/app/services/stage.py`
- Create: `backend/tests/services/test_stage.py`

**Interfaces:**
- Consumes: nothing from earlier tasks directly — this is a pure function operating on plain data, decoupled from SQLAlchemy so it's independently testable (matching `compute_readiness_checks`'s design).
- Produces: `@dataclass class CheckStatus` with fields `status: str`, `status_changed_at: datetime`.
- Produces: `@dataclass class StageInfo` with fields `current_stage: str`, `is_stuck: bool`, `dwell_days: int | None`, `stuck_reason: str | None`.
- Produces: `def derive_stage_info(checks: dict[str, CheckStatus], team: str | None, now: datetime) -> StageInfo` — used by Task 4's `_to_repo_out`.
  - Stage order (Phase 0, clamped): `onboarded` (needs `migrated_from_ado`), `standardized` (needs `codeowners_assigned`, `domain_assigned`, `branch_protection`, `readme_present` — `naming_standardized` is intentionally excluded, since `pending_convention` must never block progression).
  - For the first stage in order with at least one failing check: `current_stage` = that stage's name, `is_stuck` = `True`, `dwell_days` = days since the **oldest** `status_changed_at` among that stage's failing checks (the longest-failing check is the real blocker), `stuck_reason` = a plain-language sentence for that same longest-failing check, suffixed with `" — waiting on {team}"` if `team` is set, else `" — waiting on repo owner"`.
  - If every stage's checks pass: `current_stage` = `"standardized"` (the clamp — Phase 0 never reports `piped`/`tested`/`paved_road`, since no real checks exist for them), `is_stuck` = `False`, `dwell_days` = `None`, `stuck_reason` = `None`.
  - Missing dict keys are treated as `status="fail"` with `status_changed_at=now` (defensive default — every stage_key should be present in practice, since `compute_readiness_checks` always produces the full set).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_stage.py
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


def test_fully_passing_repo_clamps_at_standardized_and_is_not_stuck():
    info = derive_stage_info(passing_standardized_checks(), team="Growth", now=NOW)

    assert info.current_stage == "standardized"
    assert info.is_stuck is False
    assert info.dwell_days is None
    assert info.stuck_reason is None


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
    checks = passing_standardized_checks()
    checks["naming_standardized"] = CheckStatus(status="pending_convention", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "standardized"
    assert info.is_stuck is False


def test_missing_check_key_defaults_to_failing():
    checks = passing_standardized_checks()
    del checks["readme_present"]

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "standardized"
    assert info.is_stuck is True
    assert info.stuck_reason == "Missing README — waiting on repo owner"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.stage'`

- [ ] **Step 3: Implement `app/services/stage.py`**

```python
# backend/app/services/stage.py
from dataclasses import dataclass
from datetime import datetime

STAGE_ORDER: list[tuple[str, list[str]]] = [
    ("onboarded", ["migrated_from_ado"]),
    ("standardized", ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]),
]

REASON_TEXT: dict[str, str] = {
    "migrated_from_ado": "Still active in Azure DevOps",
    "codeowners_assigned": "No CODEOWNERS assigned",
    "domain_assigned": "No domain assigned",
    "branch_protection": "Missing branch protection",
    "readme_present": "Missing README",
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

    return StageInfo(current_stage="standardized", is_stuck=False, dwell_days=None, stuck_reason=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stage.py backend/tests/services/test_stage.py
git commit -m "feat: add pure current-stage/dwell-time derivation service, clamped at Standardized"
```

---

### Task 4: Wire stage derivation into the Repos API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `derive_stage_info`, `CheckStatus` (Task 3).
- Produces: `RepoOut.current_stage: str`, `RepoOut.is_stuck: bool`, `RepoOut.dwell_days: int | None`, `RepoOut.stuck_reason: str | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_repos_api.py — add this test
def test_list_repos_includes_derived_stage_info():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)  # seed_repo only sets codeowners_assigned=pass; everything else defaults missing/fail
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["current_stage"] in ("onboarded", "standardized")
    assert isinstance(body["is_stuck"], bool)
    if body["is_stuck"]:
        assert body["stuck_reason"] is not None
        assert isinstance(body["dwell_days"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py::test_list_repos_includes_derived_stage_info -v`
Expected: FAIL with `KeyError: 'current_stage'`

- [ ] **Step 3: Update `app/schemas.py`**

Add these four fields to `RepoOut`, alongside the existing ones:

```python
    current_stage: str
    is_stuck: bool
    dwell_days: int | None
    stuck_reason: str | None
```

- [ ] **Step 4: Update `_to_repo_out` in `app/api/repos.py`**

```python
from datetime import datetime, timezone

from app.services.stage import CheckStatus, derive_stage_info


def _to_repo_out(repo: Repo, session: Session) -> RepoOut:
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    stages = {
        c.stage_key: StageCheckOut(status=c.status, source=c.source, detail=c.detail, updated_at=c.updated_at)
        for c in checks
    }
    stage_info = derive_stage_info(
        checks={c.stage_key: CheckStatus(status=c.status, status_changed_at=c.status_changed_at) for c in checks},
        team=repo.team,
        now=datetime.now(timezone.utc),
    )
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        team=repo.team,
        migration_wave=repo.migration_wave,
        github_url=repo.github_url,
        last_synced_at=repo.last_synced_at,
        stages=stages,
        current_stage=stage_info.current_stage,
        is_stuck=stage_info.is_stuck,
        dwell_days=stage_info.dwell_days,
        stuck_reason=stage_info.stuck_reason,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: surface current_stage/dwell_days/stuck_reason on RepoOut"
```

---

### Task 5: Filter and sort query params on `GET /repos`

**Files:**
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: nothing new — operates on the `RepoOut` list `list_repos` already builds.
- Produces: `GET /repos?stage=standardized` (filters to repos whose `current_stage` matches), `GET /repos?domain=Growth` (filters to exact `domain` match), `GET /repos?sort=dwell_desc` (sorts stuck repos first, longest-dwelling first; non-stuck repos last, in their existing order). All params optional and combinable; omitting all returns exactly today's behavior (unfiltered, unsorted) — this is what the Repo Fleet page's "View all N repos →" links (filtered by stage) and the stuck-now panel (sorted by dwell) both need.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/api/test_repos_api.py — add these tests
def test_list_repos_filters_by_stage():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    onboarded_repo = Repo(name="stuck-in-migration", github_url="https://github.com/acme-org/stuck-in-migration")
    standardized_repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web")
    session.add_all([onboarded_repo, standardized_repo])
    session.commit()
    now = datetime.now(timezone.utc)
    session.add(ReadinessCheck(
        repo_id=onboarded_repo.id, stage_key="migrated_from_ado", status="fail", source="auto",
        detail=None, updated_at=now, status_changed_at=now,
    ))
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"stage": "onboarded"})

    names = {r["name"] for r in response.json()}
    assert names == {"stuck-in-migration"}


def test_list_repos_filters_by_domain():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    session.add_all([
        Repo(name="growth-repo", github_url="https://github.com/acme-org/growth-repo", domain="Growth"),
        Repo(name="platform-repo", github_url="https://github.com/acme-org/platform-repo", domain="Platform"),
    ])
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"domain": "Growth"})

    names = {r["name"] for r in response.json()}
    assert names == {"growth-repo"}


def test_list_repos_sorts_by_dwell_desc():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    short_stuck = Repo(name="short-stuck", github_url="https://github.com/acme-org/short-stuck")
    long_stuck = Repo(name="long-stuck", github_url="https://github.com/acme-org/long-stuck")
    not_stuck = Repo(name="all-clear", github_url="https://github.com/acme-org/all-clear")
    session.add_all([short_stuck, long_stuck, not_stuck])
    session.commit()
    now = datetime.now(timezone.utc)

    def add_all_standardized_checks(repo, extra_status="pass", extra_changed=now):
        for key in ["migrated_from_ado", "codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]:
            status = extra_status if key == "codeowners_assigned" else "pass"
            changed = extra_changed if key == "codeowners_assigned" else now
            session.add(ReadinessCheck(
                repo_id=repo.id, stage_key=key, status=status, source="auto",
                detail=None, updated_at=now, status_changed_at=changed,
            ))

    add_all_standardized_checks(short_stuck, "fail", now - timedelta(days=3))
    add_all_standardized_checks(long_stuck, "fail", now - timedelta(days=30))
    add_all_standardized_checks(not_stuck, "pass", now)
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"sort": "dwell_desc"})

    names_in_order = [r["name"] for r in response.json()]
    assert names_in_order.index("long-stuck") < names_in_order.index("short-stuck") < names_in_order.index("all-clear")
```

Add these imports at the top of the test file if not already present: `from datetime import timedelta` and `from app.models import ReadinessCheck`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k "filters_by or sorts_by"`
Expected: FAIL — `list_repos` doesn't accept query params yet, so filters/sort have no effect (tests will fail on the assertions, not on a crash)

- [ ] **Step 3: Update `list_repos` in `app/api/repos.py`**

```python
@router.get("", response_model=list[RepoOut])
def list_repos(
    stage: str | None = None,
    domain: str | None = None,
    sort: str | None = None,
    session: Session = Depends(get_db),
):
    query = session.query(Repo)
    if domain is not None:
        query = query.filter(Repo.domain == domain)
    repos = [_to_repo_out(r, session) for r in query.all()]

    if stage is not None:
        repos = [r for r in repos if r.current_stage == stage]

    if sort == "dwell_desc":
        repos.sort(key=lambda r: (not r.is_stuck, -(r.dwell_days or 0)))

    return repos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: add stage/domain filters and dwell_desc sort to GET /repos"
```

---

### Task 6: Onboarding log read endpoint

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `OnboardingLog` model (already exists).
- Produces: `class OnboardingSummaryOut(BaseModel)` with `entries: list[OnboardingLogOut]`, `median_hours: float | None`.
- Produces: `GET /repos/{repo_id}/onboarding-log` → `OnboardingSummaryOut`, 404 if repo doesn't exist, `median_hours=None` and `entries=[]` if no entries logged yet. This closes the gap flagged in the original backend's final review — §7.3 of the design spec needs "existing entries + a running median," and there was previously no way to read them back.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_repos_api.py — add these tests
def test_get_onboarding_log_returns_empty_summary_when_none_logged():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.get(f"/repos/{repo_id}/onboarding-log")

    assert response.status_code == 200
    assert response.json() == {"entries": [], "median_hours": None}


def test_get_onboarding_log_returns_entries_and_median():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)
    client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Sam", "hours": 4.0})
    client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Alex", "hours": 8.0})
    client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Jo", "hours": 6.0})

    response = client.get(f"/repos/{repo_id}/onboarding-log")

    body = response.json()
    assert len(body["entries"]) == 3
    assert body["median_hours"] == 6.0


def test_get_onboarding_log_404_for_missing_repo():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/repos/999/onboarding-log")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k onboarding_log`
Expected: FAIL with `404` (route doesn't exist) — note `test_get_onboarding_log_404_for_missing_repo` will pass by coincidence for the wrong reason at this stage; the other two will fail with a real 404 from the missing route

- [ ] **Step 3: Add `OnboardingSummaryOut` to `app/schemas.py`**

```python
class OnboardingSummaryOut(BaseModel):
    entries: list[OnboardingLogOut]
    median_hours: float | None
```

- [ ] **Step 4: Add the endpoint to `app/api/repos.py`**

```python
import statistics

from app.schemas import OnboardingSummaryOut


@router.get("/{repo_id}/onboarding-log", response_model=OnboardingSummaryOut)
def get_onboarding_log(repo_id: int, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    entries = session.query(OnboardingLog).filter_by(repo_id=repo_id).order_by(OnboardingLog.logged_at).all()
    hours = [e.hours for e in entries]
    median_hours = statistics.median(hours) if hours else None
    return OnboardingSummaryOut(entries=entries, median_hours=median_hours)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full suite one final time**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test in the backend, output pristine)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: add GET /repos/{id}/onboarding-log read endpoint with median"
```

---

## Self-Review Notes

- **Spec coverage:** `status_changed_at` (§5 addition) → Task 1. `team`/`github_url`/`last_synced_at` exposure and materialized `domain_assigned` → Task 2. Current-stage derivation clamped at Standardized (§5) → Task 3. Wiring onto `RepoOut` → Task 4. Filter/sort for the Fleet page's "View all" links and stuck panel (§7.1) → Task 5. Onboarding-log read for §7.3's median display → Task 6.
- **Placeholder scan:** no TBD/TODO; every step has runnable code.
- **Type consistency:** `CheckStatus`, `StageInfo`, `RepoOut` field names checked identical across Tasks 3/4/5's usages.
- **Cross-task risk carried forward from the original backend plan:** the SQLite in-memory thread-safety fix (`StaticPool`) and the lazy-import circular-dependency pattern both still apply here — no task in this plan touches `db.py` or adds a new router, so neither risk resurfaces, but flagging for the implementer's awareness.
