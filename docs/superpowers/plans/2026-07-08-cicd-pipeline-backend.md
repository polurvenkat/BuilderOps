# CI/CD & Lower Environments — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the backend half of the CI/CD & Lower Environments Phase 0 design spec (`docs/superpowers/specs/2026-07-08-cicd-lower-envs-phase0-design.md`): a new Azure Pipelines connector, `dockerize_eligible`/`PipelineLink` data, five new `ReadinessCheck` stage keys that power the **Piped** card, the `piped` stage becoming a real (non-clamped) `current_stage` value, and a live on-demand pipeline-status endpoint. The frontend half (Journey/Fleet/Repos-table UI, §8 of the spec) is a separate follow-up plan, written after this one is merged — same sequencing as Track 1.

**Architecture:** Pure extension of the existing `backend/app/` package, following the two-data-freshness-tier split from §4 of the spec: a new `ado_pipelines_connector.py` feeds a scheduled sync (`run_ado_pipelines_sync`) for the link/migration-status/gate-visibility data that changes rarely, while a separate live-only connector function (`fetch_pipeline_run_status`) is called directly by a new API endpoint and never persisted. No new service pattern — this plan reuses `upsert_readiness_check`, `compute_readiness_checks`'s pure-function shape, and the existing `run_github_sync`/`run_ado_sync` structure as templates.

**Tech Stack:** Same as the existing backend — Python, FastAPI, SQLAlchemy 2.0, Pydantic v2, httpx, pytest, pytest-asyncio, APScheduler.

## Global Constraints

- No new secrets or config fields — the new connector reuses `settings.ado_org`/`ado_project`/`ado_pat` from Key Vault, exactly like `ado_connector.py` already does (spec §4).
- The pipeline-link/migration-status/gate-visibility sync is **scheduled** (batch, stored in Postgres); the current-run stage-by-stage status is **live** (fetched on demand, never persisted, only from the single-repo pipeline-status endpoint) — never blur this line (spec §4).
- `deployed_aca` ships as `"unknown"` for every repo in this phase, unconditionally — no Resource Graph connector is built in this plan (spec §3, §9).
- `ReadinessCheck` writes go through `upsert_readiness_check` only (status-change-aware `status_changed_at`) — same rule as the existing backend-api-extensions plan, extended to every new check this plan adds.
- Repos whose pipeline shape doesn't match the expected Build→DEV/QA/UAT/Prod stage-naming convention degrade to `"unknown"`, never to an error or a hidden row (spec §3).
- `current_stage` derivation stays a pure function with no DB access (`app/services/stage.py`) — this plan extends it, doesn't change that discipline.
- SQLite in-memory for all tests, consistent with the existing suite.

---

## File Structure

```
backend/
  app/
    models.py                              # MODIFY: add PipelineLink table, Repo.dockerize_eligible
    schemas.py                             # MODIFY: RepoPatchIn.dockerize_eligible, PipelineStatusOut
    connectors/
      github_connector.py                  # MODIFY: add dockerfile_present to the batched query
      ado_pipelines_connector.py           # NEW: fetch_pipeline_links, fetch_release_definitions,
                                            #      fetch_environment_checks, fetch_pipeline_run_status
    services/
      readiness.py                         # MODIFY: compute_readiness_checks gains dockerized/deployed_aca
      readiness_pipeline.py                # NEW: compute_pipeline_readiness_checks (pure)
      sync_service.py                      # MODIFY: run_github_sync passes dockerize_eligible;
                                            #         NEW run_ado_pipelines_sync
      stage.py                             # MODIFY: STAGE_ORDER/REASON_TEXT gain the piped stage
    api/
      repos.py                             # MODIFY: PATCH dockerize_eligible, GET pipeline-status
      sync.py                              # MODIFY: POST /sync/ado-pipelines, status includes ado_pipelines
    scheduler.py                           # MODIFY: register the ado_pipelines_sync job
  tests/
    connectors/
      test_github_connector.py             # MODIFY: dockerfile_present assertions
      test_ado_pipelines_connector.py      # NEW
    services/
      test_readiness.py                    # MODIFY: dockerized/deployed_aca assertions
      test_readiness_pipeline.py           # NEW
      test_sync_service.py                 # MODIFY: run_ado_pipelines_sync tests
      test_stage.py                        # MODIFY: piped-stage clamp/stuck tests
    api/
      test_repos_api.py                    # MODIFY: dockerize_eligible PATCH, pipeline-status endpoint
      test_sync_api.py                     # MODIFY: /sync/ado-pipelines, status shape
    test_scheduler.py                      # MODIFY: third job id
```

---

### Task 1: Data model — `PipelineLink` table and `Repo.dockerize_eligible`

**Files:**
- Modify: `backend/app/models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `class PipelineLink(Base)` with `id`, `repo_id` (FK to `repos.id`, unique — one link per repo), `ado_pipeline_id: int`, `ado_pipeline_name: str`, `is_yaml: bool`, `last_synced_at: datetime`. Every later task that reads/writes a repo's pipeline link imports this class.
- Produces: `Repo.dockerize_eligible: Mapped[bool | None]` (nullable, default `None` — "not yet assessed"), PATCH-able starting in Task 9.

- [ ] **Step 1: Add the field and table to `app/models.py`**

Add `dockerize_eligible` to `Repo`, immediately after `migration_wave`:

```python
    migration_wave: Mapped[str] = mapped_column(String, nullable=False, default="not_started")
    dockerize_eligible: Mapped[bool | None] = mapped_column(nullable=True, default=None)
```

Add a new `PipelineLink` class after `ReadinessCheck`:

```python
class PipelineLink(Base):
    __tablename__ = "pipeline_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), unique=True, nullable=False)
    ado_pipeline_id: Mapped[int] = mapped_column(nullable=False)
    ado_pipeline_name: Mapped[str] = mapped_column(String, nullable=False)
    is_yaml: Mapped[bool] = mapped_column(nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 2: Verify the models module still imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app import models; print(models.PipelineLink.__tablename__, models.Repo.dockerize_eligible)"`
Expected: prints `pipeline_links` and a SQLAlchemy `InstrumentedAttribute` repr, no errors

- [ ] **Step 3: Run the full existing suite to confirm nothing broke**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every existing test — this task only adds columns/tables, doesn't change behavior)

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add PipelineLink table and Repo.dockerize_eligible field"
```

---

### Task 2: GitHub connector — `dockerfile_present` detection

**Files:**
- Modify: `backend/app/connectors/github_connector.py`
- Modify: `backend/tests/connectors/test_github_connector.py`

**Interfaces:**
- Consumes: nothing new — extends the existing batched GraphQL query.
- Produces: `GitHubRepoData.dockerfile_present: bool` — Task 3 consumes this to compute the `dockerized` readiness check.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/connectors/test_github_connector.py`, and update `REPO_CHECKS_RESPONSE`'s two entries to include a `dockerfile` key:

```python
REPO_CHECKS_RESPONSE = {
    "data": {
        "r0": {
            "readme": {"id": "readme-1"},
            "codeowners": {"id": "codeowners-1"},
            "dockerfile": {"id": "dockerfile-1"},
            "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 2}]},
        },
        "r1": {
            "readme": None,
            "codeowners": None,
            "dockerfile": None,
            "branchProtectionRules": {"nodes": []},
        },
    }
}
```

Update the two `GitHubRepoData(...)` assertions in `test_fetch_repos_combines_list_and_checks` to include the new field:

```python
    assert repos[0] == GitHubRepoData(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        dockerfile_present=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
    )
    assert repos[1] == GitHubRepoData(
        name="payments-api",
        url="https://github.com/acme-org/payments-api",
        has_readme=False,
        has_codeowners=False,
        dockerfile_present=False,
        branch_protection_enabled=False,
        required_reviewer_count=0,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_github_connector.py -v`
Expected: FAIL with `TypeError: GitHubRepoData.__init__() missing 1 required positional argument: 'dockerfile_present'`

- [ ] **Step 3: Update `app/connectors/github_connector.py`**

Add the field to the dataclass:

```python
@dataclass
class GitHubRepoData:
    name: str
    url: str
    has_readme: bool
    has_codeowners: bool
    dockerfile_present: bool
    branch_protection_enabled: bool
    required_reviewer_count: int
```

Add the aliased path to `_checks_query`:

```python
def _checks_query(repo_names: list[str], org: str) -> str:
    aliases = []
    for i, name in enumerate(repo_names):
        aliases.append(f'''
        r{i}: repository(owner: "{org}", name: "{name}") {{
          readme: object(expression: "HEAD:README.md") {{ id }}
          codeowners: object(expression: "HEAD:.github/CODEOWNERS") {{ id }}
          dockerfile: object(expression: "HEAD:Dockerfile") {{ id }}
          branchProtectionRules(first: 10) {{
            nodes {{ pattern requiredApprovingReviewCount }}
          }}
        }}''')
    return "query {" + "".join(aliases) + "\n}"
```

Update the result-building loop in `fetch_repos`:

```python
            results.append(
                GitHubRepoData(
                    name=repo["name"],
                    url=repo["url"],
                    has_readme=check.get("readme") is not None,
                    has_codeowners=check.get("codeowners") is not None,
                    dockerfile_present=check.get("dockerfile") is not None,
                    branch_protection_enabled=bool(protection_nodes),
                    required_reviewer_count=required_reviewers,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_github_connector.py -v`
Expected: PASS (all tests — `test_fetch_repos_raises_clear_error_when_graphql_returns_errors` and `test_fetch_repos_sends_bearer_token` are unaffected since they don't construct `GitHubRepoData`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/github_connector.py backend/tests/connectors/test_github_connector.py
git commit -m "feat: detect Dockerfile presence in the GitHub connector's batched query"
```

---

### Task 3: Readiness service — `dockerized` and `deployed_aca` checks

**Files:**
- Modify: `backend/app/services/readiness.py`
- Modify: `backend/tests/services/test_readiness.py`

**Interfaces:**
- Consumes: `GitHubRepoData.dockerfile_present` (Task 2), `Repo.dockerize_eligible` (Task 1).
- Produces: `compute_readiness_checks(..., dockerize_eligible: bool | None = None)` now returns 7 checks instead of 5, adding `dockerized` and `deployed_aca`. Task 7's `sync_service.py` passes `repo.dockerize_eligible` at the call site.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/test_readiness.py` (update `make_github_repo`'s defaults to include the new field, and add these tests):

```python
def make_github_repo(**overrides):
    defaults = dict(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        dockerfile_present=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
    )
    defaults.update(overrides)
    return GitHubRepoData(**defaults)


def test_dockerized_passes_when_not_yet_assessed():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=1, now=NOW, dockerize_eligible=None)
    dockerized = next(c for c in checks if c.stage_key == "dockerized")
    assert dockerized.status == "pass"
    assert dockerized.detail == {"eligible": None, "dockerfile_present": True}


def test_dockerized_passes_when_assessed_not_eligible_regardless_of_dockerfile():
    checks = compute_readiness_checks(
        make_github_repo(dockerfile_present=False), ado_repo_names=set(), repo_id=1, now=NOW, dockerize_eligible=False,
    )
    dockerized = next(c for c in checks if c.stage_key == "dockerized")
    assert dockerized.status == "pass"
    assert dockerized.detail == {"eligible": False, "dockerfile_present": False}


def test_dockerized_passes_when_eligible_and_dockerfile_present():
    checks = compute_readiness_checks(
        make_github_repo(dockerfile_present=True), ado_repo_names=set(), repo_id=1, now=NOW, dockerize_eligible=True,
    )
    dockerized = next(c for c in checks if c.stage_key == "dockerized")
    assert dockerized.status == "pass"
    assert dockerized.detail == {"eligible": True, "dockerfile_present": True}


def test_dockerized_fails_only_when_eligible_and_dockerfile_missing():
    checks = compute_readiness_checks(
        make_github_repo(dockerfile_present=False), ado_repo_names=set(), repo_id=1, now=NOW, dockerize_eligible=True,
    )
    dockerized = next(c for c in checks if c.stage_key == "dockerized")
    assert dockerized.status == "fail"
    assert dockerized.detail == {"eligible": True, "dockerfile_present": False}


def test_deployed_aca_always_ships_as_unknown():
    checks = compute_readiness_checks(make_github_repo(), ado_repo_names=set(), repo_id=1, now=NOW)
    deployed_aca = next(c for c in checks if c.stage_key == "deployed_aca")
    assert deployed_aca.status == "unknown"
    assert deployed_aca.source == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness.py -v`
Expected: FAIL — `TypeError` (missing `dockerfile_present` in `make_github_repo`) and `StopIteration` (no `dockerized`/`deployed_aca` stage keys yet)

- [ ] **Step 3: Update `app/services/readiness.py`**

```python
def compute_readiness_checks(
    github_repo: GitHubRepoData,
    ado_repo_names: set[str],
    repo_id: int,
    now: datetime,
    dockerize_eligible: bool | None = None,
) -> list[ReadinessCheck]:
    migrated = github_repo.name not in ado_repo_names

    dockerized_status = "fail" if (dockerize_eligible and not github_repo.dockerfile_present) else "pass"

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
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="dockerized",
            status=dockerized_status,
            source="auto",
            detail={"eligible": dockerize_eligible, "dockerfile_present": github_repo.dockerfile_present},
            updated_at=now,
        ),
        ReadinessCheck(
            repo_id=repo_id,
            stage_key="deployed_aca",
            status="unknown",
            source="auto",
            detail=None,
            updated_at=now,
        ),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: FAIL only in `tests/services/test_sync_service.py::test_run_github_sync_creates_repo_and_readiness_checks` and `test_run_github_sync_is_idempotent_on_rerun` — these assert the exact stage-key set / check count from before `dockerized`/`deployed_aca` existed. This is expected; Task 7 fixes them. Confirm no *other* file fails.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/readiness.py backend/tests/services/test_readiness.py
git commit -m "feat: compute dockerized and deployed_aca readiness checks"
```

---

### Task 4: Azure Pipelines connector — link discovery and classic-vs-YAML detection

**Files:**
- Create: `backend/app/connectors/ado_pipelines_connector.py`
- Create: `backend/tests/connectors/test_ado_pipelines_connector.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — a fresh connector module, same shape as `ado_connector.py`.
- Produces: `@dataclass PipelineLinkData(pipeline_id: int, pipeline_name: str, repository_url: str, is_yaml: bool)`, `async def fetch_pipeline_links(client, org: str, project: str, pat: str) -> list[PipelineLinkData]`, `@dataclass ReleaseDefinitionData(definition_id: int, name: str)`, `async def fetch_release_definitions(client, org: str, project: str, pat: str) -> list[ReleaseDefinitionData]`. Task 6 (readiness) and Task 7 (sync) both import these.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/connectors/test_ado_pipelines_connector.py
import httpx
import pytest

from app.connectors.ado_pipelines_connector import (
    PipelineLinkData,
    ReleaseDefinitionData,
    fetch_pipeline_links,
    fetch_release_definitions,
)

PIPELINES_LIST_RESPONSE = {"value": [{"id": 7, "name": "checkout-web-ci"}]}

PIPELINE_DETAIL_RESPONSE = {
    "id": 7,
    "name": "checkout-web-ci",
    "configuration": {
        "type": "yaml",
        "repository": {"url": "https://github.com/acme-org/checkout-web"},
    },
}

RELEASE_DEFINITIONS_RESPONSE = {"value": [{"id": 3, "name": "legacy-batch-classic-release"}]}


@pytest.mark.asyncio
async def test_fetch_pipeline_links_combines_list_and_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        return httpx.Response(200, json=PIPELINE_DETAIL_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links == [
        PipelineLinkData(
            pipeline_id=7,
            pipeline_name="checkout-web-ci",
            repository_url="https://github.com/acme-org/checkout-web",
            is_yaml=True,
        )
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_links_flags_classic_pipelines_as_not_yaml():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        return httpx.Response(200, json={
            "id": 7, "name": "checkout-web-ci",
            "configuration": {"type": "designerJson", "repository": {"url": "https://github.com/acme-org/checkout-web"}},
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links[0].is_yaml is False


@pytest.mark.asyncio
async def test_fetch_release_definitions_parses_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RELEASE_DEFINITIONS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://vsrm.dev.azure.com/acme-ado") as client:
        defs = await fetch_release_definitions(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert defs == [ReleaseDefinitionData(definition_id=3, name="legacy-batch-classic-release")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors.ado_pipelines_connector'`

- [ ] **Step 3: Implement `app/connectors/ado_pipelines_connector.py`**

```python
from dataclasses import dataclass

import httpx

from app.connectors.ado_connector import _basic_auth_header


@dataclass
class PipelineLinkData:
    pipeline_id: int
    pipeline_name: str
    repository_url: str
    is_yaml: bool


@dataclass
class ReleaseDefinitionData:
    definition_id: int
    name: str


async def fetch_pipeline_links(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[PipelineLinkData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    list_resp = await client.get(f"/{project}/_apis/pipelines", params={"api-version": "7.1"}, headers=headers)
    list_resp.raise_for_status()
    pipelines = list_resp.json()["value"]

    results: list[PipelineLinkData] = []
    for pipeline in pipelines:
        detail_resp = await client.get(
            f"/{project}/_apis/pipelines/{pipeline['id']}", params={"api-version": "7.1"}, headers=headers,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
        configuration = detail.get("configuration") or {}
        repository = configuration.get("repository") or {}
        results.append(
            PipelineLinkData(
                pipeline_id=detail["id"],
                pipeline_name=detail["name"],
                repository_url=repository.get("url", ""),
                is_yaml=configuration.get("type") == "yaml",
            )
        )
    return results


async def fetch_release_definitions(
    client: httpx.AsyncClient, org: str, project: str, pat: str
) -> list[ReleaseDefinitionData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(f"/{project}/_apis/release/definitions", params={"api-version": "7.1"}, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return [ReleaseDefinitionData(definition_id=item["id"], name=item["name"]) for item in body["value"]]
```

Note: `fetch_release_definitions` takes a client pointed at the Release Management API host (`vsrm.dev.azure.com`) — a *different* host than the Pipelines/Environments calls (`dev.azure.com`), matching real Azure DevOps API topology (spec §4). Task 7 wires up two separate `httpx.AsyncClient` instances for this reason; this connector function itself stays host-agnostic, exactly like every other connector function in this codebase.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/ado_pipelines_connector.py backend/tests/connectors/test_ado_pipelines_connector.py
git commit -m "feat: add Azure Pipelines connector for link discovery and classic-vs-YAML detection"
```

---

### Task 5: Azure Pipelines connector — environment gate visibility

**Files:**
- Modify: `backend/app/connectors/ado_pipelines_connector.py`
- Modify: `backend/tests/connectors/test_ado_pipelines_connector.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `async def fetch_environment_checks(client, org: str, project: str, pat: str, environment_names: list[str]) -> dict[str, bool]` — returns one entry per name in `environment_names` that could be matched (case-insensitive substring match) against a real ADO Environment; unmatched names are simply absent from the returned dict (caller — Task 6 — treats absence as "couldn't be matched"). Task 7 calls this with `environment_names=["dev", "qa", "uat", "prod"]`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/connectors/test_ado_pipelines_connector.py`:

```python
from app.connectors.ado_pipelines_connector import fetch_environment_checks

ENVIRONMENTS_RESPONSE = {
    "value": [
        {"id": 10, "name": "Dev Deployment"},
        {"id": 11, "name": "QA Deployment"},
        {"id": 12, "name": "UAT Deployment"},
        {"id": 13, "name": "Prod Deployment"},
    ]
}


@pytest.mark.asyncio
async def test_fetch_environment_checks_reports_configured_gates():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines/environments"):
            return httpx.Response(200, json=ENVIRONMENTS_RESPONSE)
        env_id = int(request.url.params["resourceId"])
        has_check = env_id in (12, 13)  # UAT and Prod are gated; Dev and QA are not
        return httpx.Response(200, json={"value": [{"id": 1}] if has_check else []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        gates = await fetch_environment_checks(
            client, org="acme-ado", project="acme-project", pat="ado-pat",
            environment_names=["dev", "qa", "uat", "prod"],
        )

    assert gates == {"dev": False, "qa": False, "uat": True, "prod": True}


@pytest.mark.asyncio
async def test_fetch_environment_checks_omits_unmatched_environment_names():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines/environments"):
            return httpx.Response(200, json={"value": [{"id": 12, "name": "UAT Deployment"}]})
        return httpx.Response(200, json={"value": [{"id": 1}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        gates = await fetch_environment_checks(
            client, org="acme-ado", project="acme-project", pat="ado-pat",
            environment_names=["dev", "qa", "uat", "prod"],
        )

    assert gates == {"uat": True}
    assert "dev" not in gates and "qa" not in gates and "prod" not in gates
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v -k environment_checks`
Expected: FAIL with `ImportError: cannot import name 'fetch_environment_checks'`

- [ ] **Step 3: Add `fetch_environment_checks` to `app/connectors/ado_pipelines_connector.py`**

```python
async def fetch_environment_checks(
    client: httpx.AsyncClient, org: str, project: str, pat: str, environment_names: list[str]
) -> dict[str, bool]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/pipelines/environments", params={"api-version": "7.1-preview.1"}, headers=headers,
    )
    resp.raise_for_status()
    environments = resp.json()["value"]

    result: dict[str, bool] = {}
    for target_name in environment_names:
        match = next((e for e in environments if target_name.lower() in e["name"].lower()), None)
        if match is None:
            continue
        checks_resp = await client.get(
            f"/{project}/_apis/pipelines/checks/configurations",
            params={"api-version": "7.1-preview.1", "resourceType": "environment", "resourceId": match["id"]},
            headers=headers,
        )
        checks_resp.raise_for_status()
        result[target_name] = len(checks_resp.json()["value"]) > 0
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v`
Expected: PASS (5 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/ado_pipelines_connector.py backend/tests/connectors/test_ado_pipelines_connector.py
git commit -m "feat: add environment gate-visibility check to the Azure Pipelines connector"
```

---

### Task 6: Readiness service — pipeline checks (`pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`)

**Files:**
- Create: `backend/app/services/readiness_pipeline.py`
- Create: `backend/tests/services/test_readiness_pipeline.py`

**Interfaces:**
- Consumes: nothing from a live call — a pure function, same design discipline as `compute_readiness_checks`. Task 7 supplies its arguments from `PipelineLinkData`/`ReleaseDefinitionData`/`fetch_environment_checks`'s dict output.
- Produces: `def compute_pipeline_readiness_checks(repo_id: int, has_pipeline_link: bool, is_yaml: bool | None, has_classic_release_def: bool, environment_gates: dict[str, bool], now: datetime) -> list[ReadinessCheck]` returning exactly 3 checks: `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_readiness_pipeline.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.readiness_pipeline'`

- [ ] **Step 3: Implement `app/services/readiness_pipeline.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_readiness_pipeline.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/readiness_pipeline.py backend/tests/services/test_readiness_pipeline.py
git commit -m "feat: add pure readiness computation for pipeline_linked/pipeline_is_yaml/environment_gates_configured"
```

---

### Task 7: Sync service — wire dockerize_eligible into GitHub sync, add `run_ado_pipelines_sync`

**Files:**
- Modify: `backend/app/services/sync_service.py`
- Modify: `backend/tests/services/test_sync_service.py`

**Interfaces:**
- Consumes: `compute_readiness_checks(..., dockerize_eligible=...)` (Task 3), `fetch_pipeline_links`/`fetch_release_definitions` (Task 4), `fetch_environment_checks` (Task 5), `compute_pipeline_readiness_checks` (Task 6), `PipelineLink` model (Task 1).
- Produces: `run_github_sync` now passes `repo.dockerize_eligible` when computing checks. New `async def run_ado_pipelines_sync(session: Session, pipelines_client: httpx.AsyncClient, release_client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime) -> SyncRun` — matches an existing repo (by `github_url`) to a discovered pipeline link, upserts `PipelineLink`, fetches environment gates only for matched repos, and upserts the three pipeline readiness checks for every repo. Task 10 wires this into the scheduler and a new `POST /sync/ado-pipelines` endpoint.

- [ ] **Step 1: Fix the two tests broken by Task 3, and add new tests**

In `backend/tests/services/test_sync_service.py`, update the two assertions broken by `dockerized`/`deployed_aca` now always being present:

```python
@pytest.mark.asyncio
async def test_run_github_sync_creates_repo_and_readiness_checks(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        sync_run = await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert _naive(repo.last_synced_at) == _naive(NOW)
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    assert {c.stage_key for c in checks} == {
        "migrated_from_ado", "codeowners_assigned", "readme_present", "branch_protection",
        "naming_standardized", "dockerized", "deployed_aca",
    }


@pytest.mark.asyncio
async def test_run_github_sync_is_idempotent_on_rerun(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert session.query(Repo).count() == 1
    assert session.query(ReadinessCheck).count() == 7
```

Also update the `github_handler` fixture used throughout the file to include a `dockerfile` entry (avoids a `KeyError` once `github_connector.py` looks for it):

```python
def github_handler(request: httpx.Request) -> httpx.Response:
    body = request.content.decode()
    if "repositories(first:" in body:
        return httpx.Response(200, json={"data": {"organization": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"name": "checkout-web", "url": "https://github.com/acme-org/checkout-web"}],
        }}}})
    return httpx.Response(200, json={"data": {"r0": {
        "readme": {"id": "1"}, "codeowners": {"id": "2"}, "dockerfile": None,
        "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 1}]},
    }}})
```

Add new tests to the same file for `run_ado_pipelines_sync`:

```python
from app.connectors.ado_pipelines_connector import fetch_pipeline_links  # noqa: F401 - imported for readability of intent
from app.models import PipelineLink
from app.services.sync_service import run_ado_pipelines_sync

PIPELINES_LIST = {"value": [{"id": 7, "name": "checkout-web-ci"}]}
PIPELINE_DETAIL = {
    "id": 7, "name": "checkout-web-ci",
    "configuration": {"type": "yaml", "repository": {"url": "https://github.com/acme-org/checkout-web"}},
}
ENVIRONMENTS = {"value": [
    {"id": 10, "name": "Dev Deployment"}, {"id": 11, "name": "QA Deployment"},
    {"id": 12, "name": "UAT Deployment"}, {"id": 13, "name": "Prod Deployment"},
]}


def pipelines_handler(request: httpx.Request) -> httpx.Response:
    path = str(request.url.path)
    if path.endswith("/_apis/pipelines"):
        return httpx.Response(200, json=PIPELINES_LIST)
    if path.endswith("/_apis/pipelines/7"):
        return httpx.Response(200, json=PIPELINE_DETAIL)
    if path.endswith("/_apis/pipelines/environments"):
        return httpx.Response(200, json=ENVIRONMENTS)
    env_id = int(request.url.params["resourceId"])
    return httpx.Response(200, json={"value": [{"id": 1}] if env_id in (12, 13) else []})


def release_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"value": []})


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_links_matching_repo_and_computes_checks(session):
    session.add(Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web"))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    link = session.query(PipelineLink).filter_by(repo_id=repo.id).one()
    assert link.ado_pipeline_id == 7
    assert link.is_yaml is True

    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "pass"
    assert checks["pipeline_is_yaml"].status == "pass"
    assert checks["environment_gates_configured"].status == "pass"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_leaves_unmatched_repo_without_a_link(session):
    session.add(Repo(name="no-pipeline-repo", github_url="https://github.com/acme-org/no-pipeline-repo"))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    repo = session.query(Repo).filter_by(name="no-pipeline-repo").one()
    assert session.query(PipelineLink).filter_by(repo_id=repo.id).one_or_none() is None
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "fail"
    assert checks["environment_gates_configured"].status == "unknown"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_sync_service.py -v`
Expected: FAIL — the two updated assertions now match reality already fixed by Step 1's own edits only once `run_github_sync` passes `dockerize_eligible` through (still missing); the three new `run_ado_pipelines_sync` tests FAIL with `ImportError: cannot import name 'run_ado_pipelines_sync'`

- [ ] **Step 3: Update `app/services/sync_service.py`**

Update imports:

```python
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.connectors.ado_connector import fetch_ado_repos
from app.connectors.ado_pipelines_connector import fetch_environment_checks, fetch_pipeline_links, fetch_release_definitions
from app.connectors.github_connector import fetch_repos
from app.models import AdoRepoSnapshot, PipelineLink, Repo, SyncRun
from app.services.readiness import compute_readiness_checks
from app.services.readiness_pipeline import compute_pipeline_readiness_checks
from app.services.readiness_store import upsert_readiness_check
```

Update the per-repo loop inside `run_github_sync` to pass `dockerize_eligible`:

```python
            for check in compute_readiness_checks(
                github_repo, ado_repo_names, repo.id, now, dockerize_eligible=repo.dockerize_eligible,
            ):
                upsert_readiness_check(session, check)
```

Add `run_ado_pipelines_sync` at the end of the file:

```python
_GATE_ENVIRONMENT_NAMES = ["dev", "qa", "uat", "prod"]


async def run_ado_pipelines_sync(
    session: Session,
    pipelines_client: httpx.AsyncClient,
    release_client: httpx.AsyncClient,
    org: str,
    project: str,
    pat: str,
    now: datetime,
) -> SyncRun:
    sync_run = SyncRun(connector="ado_pipelines", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        pipeline_links = await fetch_pipeline_links(pipelines_client, org=org, project=project, pat=pat)
        release_defs = await fetch_release_definitions(release_client, org=org, project=project, pat=pat)

        for repo in session.query(Repo).all():
            link_match = next((p for p in pipeline_links if p.repository_url == repo.github_url), None)
            has_classic = any(repo.name.lower() in rd.name.lower() for rd in release_defs)

            if link_match is not None:
                link_row = session.query(PipelineLink).filter_by(repo_id=repo.id).one_or_none()
                if link_row is None:
                    link_row = PipelineLink(repo_id=repo.id)
                    session.add(link_row)
                link_row.ado_pipeline_id = link_match.pipeline_id
                link_row.ado_pipeline_name = link_match.pipeline_name
                link_row.is_yaml = link_match.is_yaml
                link_row.last_synced_at = now
                session.flush()

                environment_gates = await fetch_environment_checks(
                    pipelines_client, org=org, project=project, pat=pat,
                    environment_names=_GATE_ENVIRONMENT_NAMES,
                )
            else:
                environment_gates = {}

            for check in compute_pipeline_readiness_checks(
                repo_id=repo.id,
                has_pipeline_link=link_match is not None,
                is_yaml=link_match.is_yaml if link_match else None,
                has_classic_release_def=has_classic,
                environment_gates=environment_gates,
                now=now,
            ):
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
Expected: PASS everywhere except `tests/services/test_stage.py` and `tests/api/test_repos_api.py`'s stage-derivation-related tests — Task 8 fixes those.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/services/test_sync_service.py
git commit -m "feat: add run_ado_pipelines_sync, wire dockerize_eligible into run_github_sync"
```

---

### Task 8: Stage derivation — the Piped stage becomes real

**Files:**
- Modify: `backend/app/services/stage.py`
- Modify: `backend/tests/services/test_stage.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: the seven new `ReadinessCheck` stage keys from Tasks 3 and 6.
- Produces: `derive_stage_info` can now return `current_stage == "piped"`. `STAGE_ORDER` gains a third entry: `("piped", ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized"])` — `deployed_aca` is deliberately excluded (non-blocking, same treatment `naming_standardized` already gets). The final "everything passed" branch now clamps at `STAGE_ORDER[-1][0]` (`"piped"`) instead of the hardcoded string `"standardized"` — this is the "removes the clamp one stage further" change from spec §5. **Behavioral consequence:** a repo that has cleared every Standardized check but has never been touched by `run_ado_pipelines_sync` now correctly reports `current_stage="piped"`, `is_stuck=True`, `stuck_reason="No pipeline linked in Azure DevOps — ..."` — because `pipeline_linked` defaults to `"fail"` when its `ReadinessCheck` row doesn't exist yet, exactly like every other missing check already does. This is intended, not a regression.

- [ ] **Step 1: Update `backend/tests/services/test_stage.py`**

Replace the single `test_fully_passing_repo_clamps_at_standardized_and_is_not_stuck` test with these (delete the old one; the rest of the file's helpers/tests are unchanged):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: FAIL — new tests expect `current_stage == "piped"`, but `stage.py` doesn't know about that stage yet, so they'll get `"standardized"` instead

- [ ] **Step 3: Update `app/services/stage.py`**

```python
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
```

Change the final line of `derive_stage_info` from the hardcoded clamp to a generic one:

```python
    return StageInfo(current_stage=STAGE_ORDER[-1][0], is_stuck=False, dwell_days=None, stuck_reason=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_stage.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full suite and fix the ripple in `test_repos_api.py`**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: FAIL in `tests/api/test_repos_api.py::test_list_repos_sorts_by_dwell_desc` — the `not_stuck`/`all-clear` repo is seeded with only Standardized checks, so it now derives to `current_stage="piped", is_stuck=True` (missing `pipeline_linked` defaults to fail) instead of `"standardized", is_stuck=False`. The sort assertion happens to still pass by coincidence (0 dwell days still sorts after 3 and 30), but the test's variable names (`not_stuck`, `all-clear`) would now be misleading. Fix the helper to make the intent true again:

In `test_list_repos_sorts_by_dwell_desc`, update `add_all_standardized_checks` to also seed passing Piped checks:

```python
    def add_all_standardized_checks(repo, extra_status="pass", extra_changed=now):
        keys = [
            "migrated_from_ado", "codeowners_assigned", "domain_assigned", "branch_protection", "readme_present",
            "pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized",
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
git commit -m "feat: derive the Piped stage as real, non-clamped current_stage data"
```

---

### Task 9: API — `dockerize_eligible` on `PATCH /repos/{id}`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `Repo.dockerize_eligible` (Task 1).
- Produces: `RepoPatchIn.dockerize_eligible: bool | None = None`. `patch_repo` writes it straight through to `repo.dockerize_eligible` when provided — no immediate `dockerized` check recompute (that check is auto-derived from both this flag and the GitHub-synced `dockerfile_present`, so it refreshes on the next `run_github_sync`, same latency-acceptance already established for every other GitHub-sourced check).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_repos_api.py`:

```python
def test_patch_repo_updates_dockerize_eligible():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"dockerize_eligible": True})

    assert response.status_code == 200
    session = app.state.sessionmaker()
    repo = session.get(Repo, repo_id)
    assert repo.dockerize_eligible is True
    session.close()


def test_patch_repo_can_set_dockerize_eligible_false():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"dockerize_eligible": False})

    assert response.status_code == 200
    session = app.state.sessionmaker()
    repo = session.get(Repo, repo_id)
    assert repo.dockerize_eligible is False
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k dockerize_eligible`
Expected: FAIL with `pydantic.ValidationError` (`dockerize_eligible` is an unrecognized field on `RepoPatchIn`)

- [ ] **Step 3: Update `app/schemas.py`**

```python
class RepoPatchIn(BaseModel):
    domain: str | None = None
    team: str | None = None
    migration_wave: Literal["not_started", "pilot", "rolling_out", "migrated"] | None = None
    dockerize_eligible: bool | None = None
```

- [ ] **Step 4: Update `patch_repo` in `app/api/repos.py`**

Add this branch alongside the existing `if body.team is not None` / `if body.migration_wave is not None` checks:

```python
    if body.dockerize_eligible is not None:
        repo.dockerize_eligible = body.dockerize_eligible
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: allow dockerize_eligible via PATCH /repos/{id}"
```

---

### Task 10: API + scheduler — `POST /sync/ado-pipelines` and the scheduled job

**Files:**
- Modify: `backend/app/api/sync.py`
- Modify: `backend/app/scheduler.py`
- Modify: `backend/tests/api/test_sync_api.py`
- Modify: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_ado_pipelines_sync` (Task 7).
- Produces: `POST /sync/ado-pipelines` (same synchronous-v1-simplification pattern as `/sync/github` and `/sync/ado`), `GET /sync/status` now reports a third key, `"ado_pipelines"`, alongside `"github"`/`"ado"`. Scheduler registers a fourth-hour-interval job `"ado_pipelines_sync"` (same cadence as `github_sync` — matches the spec's "synced on the same cadence as other structural checks" framing, since pipeline-link/migration-status data changes about as often as CODEOWNERS/branch-protection data).

- [ ] **Step 1: Write the failing tests**

Update `backend/tests/api/test_sync_api.py`'s existing status test:

```python
def test_sync_status_returns_null_when_nothing_has_run():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json() == {"github": None, "ado": None, "ado_pipelines": None}
```

Add a new test to the same file:

```python
def test_post_sync_ado_pipelines_triggers_a_run(monkeypatch):
    app = create_app(make_test_settings())

    async def fake_run_ado_pipelines_sync(session, pipelines_client, release_client, org, project, pat, now):
        return SyncRun(id=1, connector="ado_pipelines", started_at=now, status="success", finished_at=now)

    monkeypatch.setattr("app.api.sync.run_ado_pipelines_sync", fake_run_ado_pipelines_sync)

    client = TestClient(app)
    response = client.post("/sync/ado-pipelines")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

Update `backend/tests/test_scheduler.py`'s job-registration test:

```python
def test_start_scheduler_registers_github_and_ado_jobs():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"github_sync", "ado_sync", "ado_pipelines_sync"}
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_sync_api.py tests/test_scheduler.py -v`
Expected: FAIL — status dict missing `ado_pipelines` key, `/sync/ado-pipelines` 404s, job set missing `ado_pipelines_sync`

- [ ] **Step 3: Update `app/api/sync.py`**

```python
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync


router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status")
def sync_status(session: Session = Depends(get_db)):
    result = {}
    for connector in ("github", "ado", "ado_pipelines"):
        latest = (
            session.query(SyncRun)
            .filter_by(connector=connector)
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        result[connector] = SyncRunOut.model_validate(latest).model_dump() if latest else None
    return result
```

Add the new trigger endpoint after the existing `trigger_ado_sync`:

```python
# Runs synchronously within the request (deliberate v1 simplification - no background-task
# infrastructure yet). Revisit with a background task if org size makes this slow enough to
# risk a gateway timeout.
@router.post("/ado-pipelines", response_model=SyncRunOut, status_code=200)
async def trigger_ado_pipelines_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as pipelines_client, \
            httpx.AsyncClient(base_url=f"https://vsrm.dev.azure.com/{settings.ado_org}", timeout=30.0) as release_client:
        return await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org=settings.ado_org, project=settings.ado_project,
            pat=settings.ado_pat, now=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Update `app/scheduler.py`**

Update the import:

```python
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync
```

Add the job function after `_run_ado_sync_job`:

```python
def _run_ado_pipelines_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as pipelines_client, \
                httpx.AsyncClient(base_url=f"https://vsrm.dev.azure.com/{settings.ado_org}", timeout=30.0) as release_client:
            await run_ado_pipelines_sync(
                session, pipelines_client, release_client, org=settings.ado_org, project=settings.ado_project,
                pat=settings.ado_pat, now=datetime.now(timezone.utc),
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
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_sync_api.py tests/test_scheduler.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/sync.py backend/app/scheduler.py backend/tests/api/test_sync_api.py backend/tests/test_scheduler.py
git commit -m "feat: add ado-pipelines sync trigger endpoint and 4-hour scheduled job"
```

---

### Task 11: Azure Pipelines connector — live run status, and `GET /repos/{id}/pipeline-status`

**Files:**
- Modify: `backend/app/connectors/ado_pipelines_connector.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/connectors/test_ado_pipelines_connector.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `PipelineLink` (Task 1) to look up the repo's `ado_pipeline_id`.
- Produces: `@dataclass PipelineStageStatus(name: str, status: str, pending_approval_description: str | None = None)`, `async def fetch_pipeline_run_status(client, org: str, project: str, pat: str, pipeline_id: int) -> list[PipelineStageStatus]`. `class PipelineStageStatusOut(BaseModel)` / `class PipelineStatusOut(BaseModel)` in `schemas.py`. `GET /repos/{repo_id}/pipeline-status` — 404 if the repo doesn't exist or has no `PipelineLink` row, 502 if the live ADO call fails, 200 with the stage breakdown otherwise. This is the **only** live (non-persisted) call path in the whole backend — never cached, never falls back to stale data (spec §7).

- [ ] **Step 1: Write the failing connector test**

Add to `backend/tests/connectors/test_ado_pipelines_connector.py`:

```python
from app.connectors.ado_pipelines_connector import PipelineStageStatus, fetch_pipeline_run_status

RUNS_RESPONSE = {"value": [{"id": 555, "createdDate": "2026-07-08T10:00:00Z"}]}

TIMELINE_RESPONSE = {
    "records": [
        {"name": "Build", "type": "Stage", "order": 1, "state": "completed", "result": "succeeded"},
        {"name": "DEV", "type": "Stage", "order": 2, "state": "completed", "result": "succeeded"},
        {"name": "QA", "type": "Stage", "order": 3, "state": "inProgress", "result": None},
        {
            "name": "UAT", "type": "Stage", "order": 4, "state": "pending", "result": None,
            "checkpoint": {"pendingApprovals": [{"description": "Waiting on release manager sign-off"}]},
        },
        {"name": "Prod", "type": "Stage", "order": 5, "state": "pending", "result": None},
        {"name": "Publish artifacts", "type": "Job", "order": 6, "state": "completed", "result": "succeeded"},
    ]
}


@pytest.mark.asyncio
async def test_fetch_pipeline_run_status_maps_stages_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/runs"):
            return httpx.Response(200, json=RUNS_RESPONSE)
        return httpx.Response(200, json=TIMELINE_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        stages = await fetch_pipeline_run_status(client, org="acme-ado", project="acme-project", pat="ado-pat", pipeline_id=7)

    assert stages == [
        PipelineStageStatus(name="Build", status="succeeded"),
        PipelineStageStatus(name="DEV", status="succeeded"),
        PipelineStageStatus(name="QA", status="in_progress"),
        PipelineStageStatus(name="UAT", status="waiting_approval", pending_approval_description="Waiting on release manager sign-off"),
        PipelineStageStatus(name="Prod", status="not_started"),
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_run_status_returns_empty_list_when_no_runs_exist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        stages = await fetch_pipeline_run_status(client, org="acme-ado", project="acme-project", pat="ado-pat", pipeline_id=7)

    assert stages == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v -k run_status`
Expected: FAIL with `ImportError: cannot import name 'fetch_pipeline_run_status'`

- [ ] **Step 3: Add `PipelineStageStatus` and `fetch_pipeline_run_status` to `app/connectors/ado_pipelines_connector.py`**

```python
@dataclass
class PipelineStageStatus:
    name: str
    status: str
    pending_approval_description: str | None = None


async def fetch_pipeline_run_status(
    client: httpx.AsyncClient, org: str, project: str, pat: str, pipeline_id: int
) -> list[PipelineStageStatus]:
    headers = {"Authorization": _basic_auth_header(pat)}
    runs_resp = await client.get(
        f"/{project}/_apis/pipelines/{pipeline_id}/runs", params={"api-version": "7.1"}, headers=headers,
    )
    runs_resp.raise_for_status()
    runs = runs_resp.json()["value"]
    if not runs:
        return []
    latest_run = max(runs, key=lambda r: r["createdDate"])

    timeline_resp = await client.get(
        f"/{project}/_apis/build/builds/{latest_run['id']}/timeline", params={"api-version": "7.1"}, headers=headers,
    )
    timeline_resp.raise_for_status()
    records = timeline_resp.json()["records"]
    stage_records = sorted((r for r in records if r["type"] == "Stage"), key=lambda r: r.get("order", 0))

    stages: list[PipelineStageStatus] = []
    for record in stage_records:
        pending_approvals = (record.get("checkpoint") or {}).get("pendingApprovals") or []
        if pending_approvals:
            stages.append(PipelineStageStatus(
                name=record["name"], status="waiting_approval",
                pending_approval_description=pending_approvals[0]["description"],
            ))
        elif record["state"] == "completed" and record["result"] == "succeeded":
            stages.append(PipelineStageStatus(name=record["name"], status="succeeded"))
        elif record["state"] == "completed" and record["result"] == "failed":
            stages.append(PipelineStageStatus(name=record["name"], status="failed"))
        elif record["state"] == "inProgress":
            stages.append(PipelineStageStatus(name=record["name"], status="in_progress"))
        else:
            stages.append(PipelineStageStatus(name=record["name"], status="not_started"))
    return stages
```

- [ ] **Step 4: Run the connector tests**

Run: `cd backend && .venv/bin/python -m pytest tests/connectors/test_ado_pipelines_connector.py -v`
Expected: PASS (7 tests total in the file)

- [ ] **Step 5: Write the failing API tests**

Add to `backend/tests/api/test_repos_api.py`:

```python
from app.models import PipelineLink


def test_get_pipeline_status_404_when_repo_has_no_pipeline_link():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.get(f"/repos/{repo_id}/pipeline-status")

    assert response.status_code == 404


def test_get_pipeline_status_404_for_missing_repo():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/repos/999/pipeline-status")

    assert response.status_code == 404


def test_get_pipeline_status_returns_live_stage_breakdown(monkeypatch):
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    session = app.state.sessionmaker()
    session.add(PipelineLink(
        repo_id=repo_id, ado_pipeline_id=7, ado_pipeline_name="checkout-web-ci", is_yaml=True,
    ))
    session.commit()
    session.close()

    from app.connectors.ado_pipelines_connector import PipelineStageStatus

    async def fake_fetch_pipeline_run_status(client, org, project, pat, pipeline_id):
        assert pipeline_id == 7
        return [
            PipelineStageStatus(name="Build", status="succeeded"),
            PipelineStageStatus(name="UAT", status="waiting_approval", pending_approval_description="Needs sign-off"),
        ]

    monkeypatch.setattr("app.api.repos.fetch_pipeline_run_status", fake_fetch_pipeline_run_status)

    client = TestClient(app)
    response = client.get(f"/repos/{repo_id}/pipeline-status")

    assert response.status_code == 200
    body = response.json()
    assert body["stages"] == [
        {"name": "Build", "status": "succeeded", "pending_approval_description": None},
        {"name": "UAT", "status": "waiting_approval", "pending_approval_description": "Needs sign-off"},
    ]


def test_get_pipeline_status_502_when_ado_call_fails(monkeypatch):
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    session = app.state.sessionmaker()
    session.add(PipelineLink(
        repo_id=repo_id, ado_pipeline_id=7, ado_pipeline_name="checkout-web-ci", is_yaml=True,
    ))
    session.commit()
    session.close()

    async def failing_fetch(client, org, project, pat, pipeline_id):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.api.repos.fetch_pipeline_run_status", failing_fetch)

    client = TestClient(app)
    response = client.get(f"/repos/{repo_id}/pipeline-status")

    assert response.status_code == 502
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k pipeline_status`
Expected: FAIL with 404s (route doesn't exist yet)

- [ ] **Step 7: Update `app/schemas.py`**

```python
class PipelineStageStatusOut(BaseModel):
    name: str
    status: str
    pending_approval_description: str | None = None

    model_config = {"from_attributes": True}


class PipelineStatusOut(BaseModel):
    stages: list[PipelineStageStatusOut]
```

- [ ] **Step 8: Update `app/api/repos.py`**

Add imports:

```python
import httpx
from fastapi import Request

from app.connectors.ado_pipelines_connector import fetch_pipeline_run_status
from app.models import PipelineLink
from app.schemas import PipelineStageStatusOut, PipelineStatusOut
```

Add the endpoint at the end of the file:

```python
@router.get("/{repo_id}/pipeline-status", response_model=PipelineStatusOut)
async def get_pipeline_status(repo_id: int, request: Request, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    link = session.query(PipelineLink).filter_by(repo_id=repo_id).one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Repo has no linked pipeline")

    settings = request.app.state.settings
    try:
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
            stages = await fetch_pipeline_run_status(
                client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                pipeline_id=link.ado_pipeline_id,
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach Azure DevOps")

    return PipelineStatusOut(stages=[
        PipelineStageStatusOut(
            name=s.name, status=s.status, pending_approval_description=s.pending_approval_description,
        )
        for s in stages
    ])
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 10: Run the full backend suite one final time**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: PASS (every test in the backend, output pristine)

- [ ] **Step 11: Commit**

```bash
git add backend/app/connectors/ado_pipelines_connector.py backend/app/schemas.py backend/app/api/repos.py backend/tests/connectors/test_ado_pipelines_connector.py backend/tests/api/test_repos_api.py
git commit -m "feat: add live pipeline-status endpoint backed by the Azure Pipelines Timeline API"
```

---

## Self-Review Notes

- **Spec coverage:** §4 connector (`fetch_pipeline_links`/`fetch_release_definitions` → Task 4, `fetch_environment_checks` → Task 5, `fetch_pipeline_run_status` → Task 11) and GitHub connector extension → Task 2. §5 data model (`PipelineLink`, `dockerize_eligible` → Task 1; five new `ReadinessCheck` stage keys → Tasks 3 & 6; stage-derivation clamp removal → Task 8) all covered. §6 API surface (`GET /repos/{id}/pipeline-status` → Task 11, `PATCH .../dockerize_eligible` → Task 9) covered — the third bullet ("no other change to `GET /repos` response shape beyond new `stages` entries") requires no task, since `stages` is already a generic dict. §7 error handling (scheduled-sync stale-on-failure → Task 7's try/except mirrors the existing pattern; live-query hard-fail-no-fallback → Task 11's 502) covered. §10 future phases (self-service provisioning, gate policy, template rollout, E2E annotation) are explicitly out of scope for this plan and untouched.
- **Placeholder scan:** no TBD/TODO; every step has runnable code and exact assertions.
- **Type consistency:** `PipelineLinkData`, `ReleaseDefinitionData`, `PipelineStageStatus` field names checked identical across Tasks 4/5/6/7/11's usages. `compute_pipeline_readiness_checks`'s parameter names match exactly what Task 7's `run_ado_pipelines_sync` passes. `RepoPatchIn.dockerize_eligible` / `Repo.dockerize_eligible` / `compute_readiness_checks(..., dockerize_eligible=...)` all use the identical name throughout.
- **Cross-task risk flagged for the implementer:** Task 3 deliberately leaves `tests/services/test_sync_service.py` red until Task 7 — this is intentional sequencing (readiness logic before the sync wiring that exercises it), not a mistake; Task 3's own step 5 explains what's expected to still be failing. Task 8 similarly documents the exact ripple into `test_repos_api.py`'s dwell-sort test and fixes it in the same task rather than leaving a dangling regression for Task 9+ to trip over.
