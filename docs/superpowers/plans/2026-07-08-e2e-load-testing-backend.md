# E2E & Load Testing Phase 0 — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the backend half of the E2E & Load Testing Phase 0 design spec (`docs/superpowers/specs/2026-07-08-e2e-load-testing-phase0-design.md`): a manual mapping from each app repo to the Azure Test Plan representing its E2E coverage, a new Azure Test Plans connector, four new `ReadinessCheck` stage keys powering the **Tested** card, and the `tested` stage becoming a real, reachable `current_stage` value.

**Architecture:** Pure extension of the existing `backend/app/` package, following the exact connector → pure-readiness-function → sync-orchestrator → API layering already used for GitHub/ADO/ADO-Pipelines sync. Simpler than the CI/CD Track 2 plan it follows: no live-query tier (test-run freshness doesn't need on-demand querying), no new table (the repo↔Test-Plan link is one manual column, and the connector's result lives in `ReadinessCheck.detail`, same as `branch_protection`/`environment_gates_configured` already do), and a single ADO host (`dev.azure.com` — Test Plans doesn't split across hosts the way Release Management did).

**Tech Stack:** Same as the existing backend — Python, FastAPI, SQLAlchemy 2.0, Pydantic v2, httpx, pytest, pytest-asyncio, APScheduler.

## Global Constraints

- No new secrets or config fields — the new connector reuses `settings.ado_org`/`ado_project`/`ado_pat` from Key Vault, exactly like `ado_connector.py`/`ado_pipelines_connector.py` already do (spec §4).
- `Repo.e2e_test_plan_id` is a manually-asserted field — there is no auto-derivable link between an app repo and its covering E2E repo's Test Plan yet (confirmed: one E2E repo commonly covers many app repos). Same "no existing source of truth" rationale that made `domain` a manual field in Track 1 (spec §3, §5).
- `unit_tested` and `integration_tested` ship as `"pending_convention"` unconditionally this phase — confirmed no standard test-plan/location convention exists for either yet, varies by team. Do not build any auto-detection logic for them (spec §3, §5).
- `load_tested` ships as `"unknown"` unconditionally this phase — no Azure Load Testing connector is built in this plan (spec §3, §5).
- Only `e2e_covered` is a blocking key for the `tested` stage; `unit_tested`/`integration_tested`/`load_tested` are non-blocking, the same treatment `naming_standardized`/`deployed_aca` already get (spec §5).
- No live-query endpoint this phase — everything is scheduled-sync only, one data-freshness tier (spec §4).
- `ReadinessCheck` writes go through `upsert_readiness_check` only (status-change-aware `status_changed_at`) — same rule as every prior sync in this codebase.
- `current_stage` derivation stays a pure function with no DB access (`app/services/stage.py`) — this plan extends it, doesn't change that discipline.
- SQLite in-memory for all tests, consistent with the existing suite.

---

## File Structure

```
backend/
  app/
    models.py                              # MODIFY: add Repo.e2e_test_plan_id
    schemas.py                             # MODIFY: RepoPatchIn.e2e_test_plan_id
    connectors/
      ado_test_plans_connector.py          # NEW: fetch_test_plan_latest_run
    services/
      test_readiness.py                    # NEW: compute_e2e_readiness_checks (pure)
      sync_service.py                      # MODIFY: NEW run_test_plans_sync
      stage.py                             # MODIFY: STAGE_ORDER/REASON_TEXT gain the tested stage
    api/
      repos.py                             # MODIFY: PATCH e2e_test_plan_id
      sync.py                              # MODIFY: POST /sync/test-plans, status includes test_plans
    scheduler.py                           # MODIFY: register the test_plans_sync job
  tests/
    test_models.py                         # MODIFY: e2e_test_plan_id default assertion
    connectors/
      test_ado_test_plans_connector.py     # NEW
    services/
      test_test_readiness.py               # NEW
      test_sync_service.py                 # MODIFY: run_test_plans_sync tests
      test_stage.py                        # MODIFY: tested-stage clamp/stuck tests, fix 2 ripple tests
    api/
      test_repos_api.py                    # MODIFY: e2e_test_plan_id PATCH, fix 2 ripple tests
      test_sync_api.py                     # MODIFY: /sync/test-plans, status shape
    test_scheduler.py                      # MODIFY: fourth job id
```

---

### Task 1: Data model — `Repo.e2e_test_plan_id`

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `Repo.e2e_test_plan_id: int | None` (nullable, manual, `PATCH`-able, defaults to `None`).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`:

```python
def test_repo_e2e_test_plan_id_defaults_to_none():
    session = make_session()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    fetched = session.query(Repo).filter_by(name="checkout-web").one()
    assert fetched.e2e_test_plan_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_models.py -v -k e2e_test_plan_id`
Expected: FAIL with `AttributeError: 'Repo' object has no attribute 'e2e_test_plan_id'`

- [ ] **Step 3: Add the column**

In `backend/app/models.py`, add to `Repo` (after `dockerize_eligible`):

```python
    e2e_test_plan_id: Mapped[int | None] = mapped_column(nullable=True, default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full suite and commit**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all tests pass

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add Repo.e2e_test_plan_id column"
```

---

### Task 2: Azure Test Plans connector

**Files:**
- Create: `backend/app/connectors/ado_test_plans_connector.py`
- Create: `backend/tests/connectors/test_ado_test_plans_connector.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — a fresh connector module, same shape as `ado_connector.py`/`ado_pipelines_connector.py`, reusing `_basic_auth_header` from `ado_connector.py`.
- Produces: `@dataclass TestPlanRunResult(passed_count: int, failed_count: int, total_count: int, completed_date: str)`, `async def fetch_test_plan_latest_run(client, org: str, project: str, pat: str, test_plan_id: int) -> TestPlanRunResult | None`. Task 3 and Task 4 both import these.

**Note on simplification:** the real Azure Test Plans/Test Results API is broader than this; this connector models each test run as directly carrying `state`, `completedDate`, `totalTests`, `passedTests` fields, and derives `failed_count` as `total_count - passed_count` (anything not explicitly passed counts as a failure, for Phase 0 simplicity — the same "any failure blocks" simplicity level `branch_protection`/`dockerized` already use).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/connectors/test_ado_test_plans_connector.py`:

```python
import httpx
import pytest

from app.connectors.ado_test_plans_connector import TestPlanRunResult, fetch_test_plan_latest_run

RUNS_RESPONSE = {"value": [
    {"id": 501, "state": "InProgress", "completedDate": None, "totalTests": 10, "passedTests": 0},
    {"id": 500, "state": "Completed", "completedDate": "2026-07-01T00:00:00Z", "totalTests": 20, "passedTests": 20},
    {"id": 502, "state": "Completed", "completedDate": "2026-07-08T00:00:00Z", "totalTests": 15, "passedTests": 13},
]}


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_picks_most_recent_completed_run():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url.path).endswith("/_apis/test/runs")
        assert request.url.params["planId"] == "42"
        return httpx.Response(200, json=RUNS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result == TestPlanRunResult(
        passed_count=13, failed_count=2, total_count=15, completed_date="2026-07-08T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_ignores_incomplete_runs():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [
            {"id": 501, "state": "InProgress", "completedDate": None, "totalTests": 10, "passedTests": 0},
        ]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_returns_none_when_no_runs_exist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_sends_basic_auth_with_pat():
    import base64

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await fetch_test_plan_latest_run(client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42)

    expected_token = base64.b64encode(b":ado-pat").decode()
    assert seen["authorization"] == f"Basic {expected_token}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_test_plans_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors.ado_test_plans_connector'`

- [ ] **Step 3: Implement**

Create `backend/app/connectors/ado_test_plans_connector.py`:

```python
from dataclasses import dataclass

import httpx

from app.connectors.ado_connector import _basic_auth_header


@dataclass
class TestPlanRunResult:
    passed_count: int
    failed_count: int
    total_count: int
    completed_date: str


async def fetch_test_plan_latest_run(
    client: httpx.AsyncClient, org: str, project: str, pat: str, test_plan_id: int
) -> TestPlanRunResult | None:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/test/runs",
        params={"api-version": "7.1", "planId": test_plan_id},
        headers=headers,
    )
    resp.raise_for_status()
    runs = resp.json()["value"]

    completed_runs = [r for r in runs if r.get("state") == "Completed"]
    if not completed_runs:
        return None

    latest_run = max(completed_runs, key=lambda r: r["completedDate"])
    total_count = latest_run["totalTests"]
    passed_count = latest_run["passedTests"]
    return TestPlanRunResult(
        passed_count=passed_count,
        failed_count=total_count - passed_count,
        total_count=total_count,
        completed_date=latest_run["completedDate"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_test_plans_connector.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/ado_test_plans_connector.py backend/tests/connectors/test_ado_test_plans_connector.py
git commit -m "feat: add Azure Test Plans connector for latest-run results"
```

---

### Task 3: E2E readiness computation

**Files:**
- Create: `backend/app/services/test_readiness.py`
- Create: `backend/tests/services/test_test_readiness.py`

**Interfaces:**
- Consumes: `TestPlanRunResult` (Task 2).
- Produces: `compute_e2e_readiness_checks(repo_id: int, e2e_test_plan_id: int | None, latest_run: TestPlanRunResult | None, now: datetime) -> list[ReadinessCheck]` — always returns exactly 4 checks: `e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_test_readiness.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_test_readiness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.test_readiness'`

- [ ] **Step 3: Implement**

Create `backend/app/services/test_readiness.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_test_readiness.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/test_readiness.py backend/tests/services/test_test_readiness.py
git commit -m "feat: compute Tested-card readiness checks from Test Plans connector data"
```

---

### Task 4: Test Plans sync orchestration

**Files:**
- Modify: `backend/app/services/sync_service.py`
- Modify: `backend/tests/services/test_sync_service.py`

**Interfaces:**
- Consumes: `fetch_test_plan_latest_run` (Task 2), `compute_e2e_readiness_checks` (Task 3).
- Produces: `async def run_test_plans_sync(session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime) -> SyncRun` — iterates every repo, calls the connector only for repos with `e2e_test_plan_id` set, and upserts all four Tested-card checks for every repo either way. Task 7 wires this into the scheduler and a new `POST /sync/test-plans` endpoint.

- [ ] **Step 1: Write the failing test**

Update the existing `from app.services.sync_service import ...` line in `backend/tests/services/test_sync_service.py` to add `run_test_plans_sync`:

```python
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync, run_test_plans_sync
```

Then add to the same file:

```python
TEST_RUNS_RESPONSE = {"value": [
    {"id": 500, "state": "Completed", "completedDate": "2026-07-01T00:00:00Z", "totalTests": 20, "passedTests": 20},
]}


def test_plans_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=TEST_RUNS_RESPONSE)


@pytest.mark.asyncio
async def test_run_test_plans_sync_computes_e2e_covered_for_mapped_repo(session):
    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(test_plans_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_test_plans_sync(
            session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["e2e_covered"].status == "pass"
    assert checks["unit_tested"].status == "pending_convention"
    assert checks["integration_tested"].status == "pending_convention"
    assert checks["load_tested"].status == "unknown"


@pytest.mark.asyncio
async def test_run_test_plans_sync_skips_connector_call_for_unmapped_repo(session):
    session.add(Repo(name="no-e2e-repo", github_url="https://github.com/acme-org/no-e2e-repo"))
    session.commit()

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=TEST_RUNS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    assert len(calls) == 0
    repo = session.query(Repo).filter_by(name="no-e2e-repo").one()
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["e2e_covered"].status == "pending_convention"


@pytest.mark.asyncio
async def test_run_test_plans_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_test_plans_sync(
            session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error


@pytest.mark.asyncio
async def test_run_test_plans_sync_is_idempotent_on_rerun(session):
    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(test_plans_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert session.query(ReadinessCheck).filter_by(repo_id=repo.id).count() == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_sync_service.py -v -k test_plans`
Expected: FAIL with `ImportError: cannot import name 'run_test_plans_sync'`

- [ ] **Step 3: Implement**

Update the imports at the top of `backend/app/services/sync_service.py` (add these two lines alongside the existing imports):

```python
from app.connectors.ado_test_plans_connector import fetch_test_plan_latest_run
from app.services.test_readiness import compute_e2e_readiness_checks
```

Add at the end of the file:

```python
async def run_test_plans_sync(
    session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="test_plans", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        for repo in session.query(Repo).all():
            latest_run = None
            if repo.e2e_test_plan_id is not None:
                latest_run = await fetch_test_plan_latest_run(
                    client, org=org, project=project, pat=pat, test_plan_id=repo.e2e_test_plan_id,
                )

            for check in compute_e2e_readiness_checks(repo.id, repo.e2e_test_plan_id, latest_run, now):
                upsert_readiness_check(session, check)

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: record any failure on the SyncRun
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_sync_service.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS everywhere except `tests/services/test_stage.py` and 2 tests in `tests/api/test_repos_api.py` — Task 5 fixes those.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/services/test_sync_service.py
git commit -m "feat: add run_test_plans_sync orchestrating the Tested-card checks"
```

---

### Task 5: Stage derivation — the Tested stage becomes real

**Files:**
- Modify: `backend/app/services/stage.py`
- Modify: `backend/tests/services/test_stage.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: the four new `ReadinessCheck` stage keys from Task 3.
- Produces: `derive_stage_info` can now return `current_stage == "tested"`. `STAGE_ORDER` gains a fourth entry: `("tested", ["e2e_covered"])` — `unit_tested`/`integration_tested`/`load_tested` are deliberately excluded (non-blocking, same treatment `naming_standardized`/`deployed_aca` already get). The existing generalized clamp (`STAGE_ORDER[-1][0]`) needs no further code change — a repo clearing every check now derives all the way to `"tested"` automatically. **Behavioral consequence:** since `e2e_covered` defaults to `"pending_convention"` (not `"fail"`) once `run_test_plans_sync` has run for a repo — even one with no `e2e_test_plan_id` mapped — most repos will reach `"tested"` cleanly without becoming newly stuck. This is unlike Track 2's `pipeline_linked`, which is a real `"fail"` when genuinely unlinked; here the common "not yet mapped" case is honestly non-blocking by design.

- [ ] **Step 1: Update `backend/tests/services/test_stage.py`**

Replace the single `test_fully_passing_repo_including_piped_clamps_at_piped_and_is_not_stuck` test with these (delete the old one; the rest of the file's helpers/tests are unchanged), and fix `test_naming_standardized_never_blocks_progression` (it currently clamps at `"piped"` via `passing_piped_checks()`, which is now one stage short of the new "everything passes" ceiling):

```python
def passing_tested_checks(now=NOW):
    checks = passing_piped_checks(now)
    checks["e2e_covered"] = CheckStatus(status="pass", status_changed_at=now)
    return checks


def test_fully_passing_repo_including_tested_clamps_at_tested_and_is_not_stuck():
    info = derive_stage_info(passing_tested_checks(), team="Growth", now=NOW)

    assert info.current_stage == "tested"
    assert info.is_stuck is False
    assert info.dwell_days is None
    assert info.stuck_reason is None


def test_piped_repo_with_e2e_covered_pending_convention_clamps_at_tested_not_stuck():
    checks = passing_piped_checks()
    checks["e2e_covered"] = CheckStatus(status="pending_convention", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "tested"
    assert info.is_stuck is False


def test_repo_stuck_at_tested_when_e2e_covered_fails():
    checks = passing_tested_checks()
    checks["e2e_covered"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=4))

    info = derive_stage_info(checks, team="Jiju", now=NOW)

    assert info.current_stage == "tested"
    assert info.is_stuck is True
    assert info.dwell_days == 4
    assert info.stuck_reason == "E2E tests failing on the latest run — waiting on Jiju team"


def test_unit_integration_and_load_tested_never_block_progression():
    checks = passing_tested_checks()
    checks["unit_tested"] = CheckStatus(status="pending_convention", status_changed_at=NOW)
    checks["integration_tested"] = CheckStatus(status="pending_convention", status_changed_at=NOW)
    checks["load_tested"] = CheckStatus(status="unknown", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "tested"
    assert info.is_stuck is False


def test_piped_failure_still_blocks_tested_from_being_reached():
    checks = passing_tested_checks()
    checks["dockerized"] = CheckStatus(status="fail", status_changed_at=NOW - timedelta(days=6))

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "piped"
    assert info.is_stuck is True
```

Update `test_naming_standardized_never_blocks_progression` (existing test) to use `passing_tested_checks()` instead of `passing_piped_checks()`, and expect `"tested"` instead of `"piped"`:

```python
def test_naming_standardized_never_blocks_progression():
    checks = passing_tested_checks()
    checks["naming_standardized"] = CheckStatus(status="pending_convention", status_changed_at=NOW)

    info = derive_stage_info(checks, team=None, now=NOW)

    assert info.current_stage == "tested"
    assert info.is_stuck is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: FAIL — new tests expect `current_stage == "tested"`, but `stage.py` doesn't know about that stage yet

- [ ] **Step 3: Update `app/services/stage.py`**

```python
STAGE_ORDER: list[tuple[str, list[str]]] = [
    ("onboarded", ["migrated_from_ado"]),
    ("standardized", ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]),
    ("piped", ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized"]),
    ("tested", ["e2e_covered"]),
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
    "e2e_covered": "E2E tests failing on the latest run",
}
```

(No change needed to the final `return StageInfo(current_stage=STAGE_ORDER[-1][0], ...)` line — it already generalizes to whatever the last `STAGE_ORDER` entry is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full suite and fix the ripple in `test_repos_api.py`**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: FAIL in `tests/api/test_repos_api.py::test_repo_with_domain_set_directly_is_not_falsely_stuck` and `test_list_repos_sorts_by_dwell_desc` — both seed a repo with every Standardized+Piped check passing but no `e2e_covered` row at all, so it now derives to `current_stage="tested", is_stuck=True` (missing `e2e_covered` defaults to fail) instead of `is_stuck=False`. Fix both to seed a passing `e2e_covered` check too, making the intent ("this repo is fully clear, not stuck") true again:

In `test_repo_with_domain_set_directly_is_not_falsely_stuck`, add `"e2e_covered"` to the existing `for key in [...]:` list:

```python
    for key in [
        "migrated_from_ado", "codeowners_assigned", "branch_protection", "readme_present",
        "pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized", "e2e_covered",
    ]:
```

In `test_list_repos_sorts_by_dwell_desc`'s `add_all_standardized_checks` helper, add `"e2e_covered"` to its `keys` list:

```python
    def add_all_standardized_checks(repo, extra_status="pass", extra_changed=now):
        keys = [
            "migrated_from_ado", "codeowners_assigned", "domain_assigned", "branch_protection", "readme_present",
            "pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized", "e2e_covered",
        ]
        for key in keys:
            status = extra_status if key == "codeowners_assigned" else "pass"
            changed = extra_changed if key == "codeowners_assigned" else now
            session.add(ReadinessCheck(
                repo_id=repo.id, stage_key=key, status=status, source="auto",
                detail=None, updated_at=now, status_changed_at=changed,
            ))
```

- [ ] **Step 6: Run the full suite again**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/stage.py backend/tests/services/test_stage.py backend/tests/api/test_repos_api.py
git commit -m "feat: derive the Tested stage as real, non-clamped current_stage data"
```

---

### Task 6: API — `e2e_test_plan_id` on `PATCH /repos/{id}`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `Repo.e2e_test_plan_id` (Task 1).
- Produces: `RepoPatchIn.e2e_test_plan_id: int | None = None`. `patch_repo` writes it straight through to `repo.e2e_test_plan_id` when provided — no immediate `e2e_covered` recompute (it refreshes on the next `run_test_plans_sync`, same latency-acceptance already established for `dockerize_eligible`).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_repos_api.py`:

```python
def test_patch_repo_updates_e2e_test_plan_id():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"e2e_test_plan_id": 42})

    assert response.status_code == 200
    session = app.state.sessionmaker()
    repo = session.get(Repo, repo_id)
    assert repo.e2e_test_plan_id == 42
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k e2e_test_plan_id`
Expected: FAIL with `pydantic.ValidationError` (`e2e_test_plan_id` is an unrecognized field on `RepoPatchIn`)

- [ ] **Step 3: Update `app/schemas.py`**

```python
class RepoPatchIn(BaseModel):
    domain: str | None = None
    team: str | None = None
    migration_wave: Literal["not_started", "pilot", "rolling_out", "migrated"] | None = None
    dockerize_eligible: bool | None = None
    e2e_test_plan_id: int | None = None
```

- [ ] **Step 4: Update `patch_repo` in `app/api/repos.py`**

Add this branch alongside the existing `if body.dockerize_eligible is not None` check:

```python
    if body.e2e_test_plan_id is not None:
        repo.e2e_test_plan_id = body.e2e_test_plan_id
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: allow e2e_test_plan_id via PATCH /repos/{id}"
```

---

### Task 7: API + scheduler — `POST /sync/test-plans` and the scheduled job

**Files:**
- Modify: `backend/app/api/sync.py`
- Modify: `backend/app/scheduler.py`
- Modify: `backend/tests/api/test_sync_api.py`
- Modify: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_test_plans_sync` (Task 4).
- Produces: `POST /sync/test-plans` (same synchronous-v1-simplification pattern as the other three sync endpoints). `GET /sync/status` now reports a fourth key, `"test_plans"`, alongside `"github"`/`"ado"`/`"ado_pipelines"`. Scheduler registers a fourth 4-hour-interval job, `"test_plans_sync"` (same cadence as `github_sync`/`ado_pipelines_sync"` — Test Plans results change about as often as other structural checks).

- [ ] **Step 1: Write the failing tests**

Update `backend/tests/api/test_sync_api.py`'s existing status test:

```python
def test_sync_status_returns_null_when_nothing_has_run():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json() == {"github": None, "ado": None, "ado_pipelines": None, "test_plans": None}
```

Add a new test to the same file:

```python
def test_post_sync_test_plans_triggers_a_run(monkeypatch):
    app = create_app(make_test_settings())

    async def fake_run_test_plans_sync(session, client, org, project, pat, now):
        return SyncRun(id=1, connector="test_plans", started_at=now, status="success", finished_at=now)

    monkeypatch.setattr("app.api.sync.run_test_plans_sync", fake_run_test_plans_sync)

    client = TestClient(app)
    response = client.post("/sync/test-plans")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

Update `backend/tests/test_scheduler.py`'s job-registration test:

```python
def test_start_scheduler_registers_github_and_ado_jobs():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"github_sync", "ado_sync", "ado_pipelines_sync", "test_plans_sync"}
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_sync_api.py tests/test_scheduler.py -v`
Expected: FAIL — status dict missing `test_plans` key, `/sync/test-plans` 404s, job set missing `test_plans_sync`

- [ ] **Step 3: Update `app/api/sync.py`**

Update the import:

```python
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync, run_test_plans_sync
```

Update the status endpoint's connector tuple:

```python
@router.get("/status")
def sync_status(session: Session = Depends(get_db)):
    result = {}
    for connector in ("github", "ado", "ado_pipelines", "test_plans"):
        latest = (
            session.query(SyncRun)
            .filter_by(connector=connector)
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        result[connector] = SyncRunOut.model_validate(latest).model_dump() if latest else None
    return result
```

Add the new trigger endpoint after the existing `trigger_ado_pipelines_sync`:

```python
# Runs synchronously within the request (deliberate v1 simplification - no background-task
# infrastructure yet). Revisit with a background task if org size makes this slow enough to
# risk a gateway timeout.
@router.post("/test-plans", response_model=SyncRunOut, status_code=200)
async def trigger_test_plans_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
        return await run_test_plans_sync(
            session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
            now=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Update `app/scheduler.py`**

Update the import:

```python
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync, run_test_plans_sync
```

Add the job function after `_run_ado_pipelines_sync_job`:

```python
def _run_test_plans_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
            await run_test_plans_sync(
                session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()
```

Register it in `start_scheduler`:

```python
def start_scheduler(app: FastAPI) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_github_sync_job, "interval", hours=4, args=[app], id="github_sync")
    scheduler.add_job(_run_ado_sync_job, "interval", days=1, args=[app], id="ado_sync")
    scheduler.add_job(_run_ado_pipelines_sync_job, "interval", hours=4, args=[app], id="ado_pipelines_sync")
    scheduler.add_job(_run_test_plans_sync_job, "interval", hours=4, args=[app], id="test_plans_sync")
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_sync_api.py tests/test_scheduler.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full backend suite one final time**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test in the backend, output pristine)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/sync.py backend/app/scheduler.py backend/tests/api/test_sync_api.py backend/tests/test_scheduler.py
git commit -m "feat: add test-plans sync trigger endpoint and 4-hour scheduled job"
```

---

## Self-Review Notes

- **Spec coverage:** §4 architecture (single freshness tier, new connector, no new table) → Tasks 2, 4. §5 data model (`Repo.e2e_test_plan_id` → Task 1; four new `ReadinessCheck` stage keys → Task 3; stage-derivation extension → Task 5) all covered. §6 API surface (`PATCH .../e2e_test_plan_id` → Task 6, `POST /sync/test-plans` + status key → Task 7) covered — the "no other `GET /repos` shape change" bullet requires no task, `stages` is already a generic dict. §7 error handling (scheduled-sync stale-on-failure → Task 4's try/except mirrors the existing pattern) covered. §9/§10 open questions and future phases are explicitly out of scope and untouched.
- **Placeholder scan:** no TBD/TODO; every step has runnable code and exact assertions.
- **Type consistency:** `TestPlanRunResult` field names checked identical across Tasks 2/3/4's usages. `compute_e2e_readiness_checks`'s parameter names/order match exactly what Task 4's `run_test_plans_sync` passes (`repo.id, repo.e2e_test_plan_id, latest_run, now`). `Repo.e2e_test_plan_id` / `RepoPatchIn.e2e_test_plan_id` use the identical name throughout.
- **Cross-task ripple risk flagged for implementers:** Task 4 deliberately leaves `tests/services/test_stage.py` and 2 tests in `tests/api/test_repos_api.py` red until Task 5 — this is intentional sequencing (readiness computation before the stage-derivation change that exercises it), not a mistake. Task 5's own Step 5 explains both ripple fixes precisely, mirroring how Track 2's Task 8 handled the equivalent ripple when `piped` was added.
