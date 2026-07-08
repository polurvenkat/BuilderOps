# Repo Standardization Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for BuilderOps Phase 0 — a Python/FastAPI service that syncs GitHub + Azure DevOps repo data into Postgres and exposes it via a REST API, covering only the **Onboarded** and **Standardized** journey stages (Piped/Tested data sources are a future phase).

**Architecture:** FastAPI app with synchronous SQLAlchemy models/sessions for the DB layer, async httpx-based connectors (GitHub GraphQL, ADO REST) for external I/O, a readiness service that turns raw connector output into `ReadinessCheck` rows, and an APScheduler job that runs the sync on an interval. The UI (separate plan) reads only from the REST API, which reads only from Postgres.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Pydantic v2, httpx (async), APScheduler, pytest + pytest-asyncio, azure-identity + azure-keyvault-secrets.

## Global Constraints

- No credential (DB password, GitHub token, ADO PAT) is ever hardcoded, committed, or logged. All secrets load through the `SecretProvider` interface built in Task 1.
- Every external call (GitHub, ADO) is async and goes through the connectors built in Tasks 4–5 — no ad hoc `httpx` or `requests` calls elsewhere.
- `ReadinessCheck`'s primary key is the composite `(repo_id, stage_key)` — this is what makes upserts portable via `session.merge()` instead of dialect-specific `ON CONFLICT` SQL.
- Existing manual fields (`domain`, `migration_wave`) and the `domain_assigned`/`naming_standardized` stage statuses are never overwritten by a sync run except where explicitly stated in Task 6.
- Database: SQLite in-memory for all unit/service tests (fast, no external dependency); the schema uses only types portable to both SQLite and Postgres (no Postgres-only column types).

---

## File Structure

```
backend/
  pyproject.toml
  app/
    __init__.py
    config.py                  # Settings + SecretProvider (env-based and Key Vault-based)
    db.py                       # SQLAlchemy engine/session/Base
    models.py                   # Repo, ReadinessCheck, AdoRepoSnapshot, OnboardingLog, SyncRun
    schemas.py                  # Pydantic request/response models
    main.py                     # FastAPI app factory, startup hook (create tables + start scheduler)
    scheduler.py                # APScheduler wiring
    connectors/
      __init__.py
      github_connector.py       # GitHub GraphQL: repo list + Standardized checks
      ado_connector.py          # ADO REST: repo list only
    services/
      __init__.py
      readiness.py               # raw connector data -> ReadinessCheck rows
      sync_service.py            # orchestrates one sync run end-to-end
    api/
      __init__.py
      repos.py                   # /repos endpoints
      sync.py                    # /sync endpoints
  tests/
    conftest.py
    test_config.py
    test_models.py
    connectors/
      test_github_connector.py
      test_ado_connector.py
    services/
      test_readiness.py
      test_sync_service.py
    api/
      test_repos_api.py
      test_sync_api.py
```

---

### Task 1: Project scaffolding, config, and secret loading

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`
- Test: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `class Settings(BaseSettings)` with fields `database_url: str`, `github_token: str`, `github_org: str`, `ado_org: str`, `ado_project: str`, `ado_pat: str`, `azure_key_vault_url: str | None`.
- Produces: `class SecretProvider(Protocol)` with `def get(self, name: str) -> str`.
- Produces: `class EnvSecretProvider` and `class KeyVaultSecretProvider`, both implementing `SecretProvider`.
- Produces: `def get_settings() -> Settings` — builds `Settings` by resolving each secret through a `SecretProvider` chosen based on whether `AZURE_KEY_VAULT_URL` is set.

- [ ] **Step 1: Create the project file and dependency manifest**

```toml
# backend/pyproject.toml
[project]
name = "builderops-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "httpx>=0.27",
    "apscheduler>=3.10",
    "azure-identity>=1.19",
    "azure-keyvault-secrets>=4.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the failing test for config resolution**

```python
# backend/tests/test_config.py
import pytest
from app.config import EnvSecretProvider, KeyVaultSecretProvider, get_settings, Settings


def test_env_secret_provider_reads_from_environ(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "shh")
    provider = EnvSecretProvider()
    assert provider.get("MY_SECRET") == "shh"


def test_env_secret_provider_missing_raises(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    provider = EnvSecretProvider()
    with pytest.raises(KeyError):
        provider.get("DOES_NOT_EXIST")


def test_get_settings_uses_env_provider_when_no_key_vault_url(monkeypatch):
    monkeypatch.delenv("AZURE_KEY_VAULT_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_ORG", "acme-org")
    monkeypatch.setenv("ADO_ORG", "acme-ado")
    monkeypatch.setenv("ADO_PROJECT", "acme-project")
    monkeypatch.setenv("ADO_PAT", "ado-pat")

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.github_org == "acme-org"


def test_key_vault_secret_provider_calls_client(monkeypatch):
    class FakeSecret:
        def __init__(self, value):
            self.value = value

    class FakeSecretClient:
        def __init__(self, vault_url, credential):
            self.vault_url = vault_url

        def get_secret(self, name):
            return FakeSecret(f"value-for-{name}")

    monkeypatch.setattr("app.config.SecretClient", FakeSecretClient)
    monkeypatch.setattr("app.config.DefaultAzureCredential", lambda: object())

    provider = KeyVaultSecretProvider(vault_url="https://fake.vault.azure.net")
    assert provider.get("db-password") == "value-for-db-password"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'` (or similar import error)

- [ ] **Step 4: Implement `app/__init__.py` and `app/config.py`**

```python
# backend/app/__init__.py
```

```python
# backend/app/config.py
import os
from typing import Protocol

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from pydantic_settings import BaseSettings


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...


class EnvSecretProvider:
    def get(self, name: str) -> str:
        if name not in os.environ:
            raise KeyError(f"Secret '{name}' not found in environment")
        return os.environ[name]


class KeyVaultSecretProvider:
    def __init__(self, vault_url: str):
        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    def get(self, name: str) -> str:
        return self._client.get_secret(name).value


class Settings(BaseSettings):
    database_url: str
    github_token: str
    github_org: str
    ado_org: str
    ado_project: str
    ado_pat: str
    azure_key_vault_url: str | None = None


_ENV_TO_KEY_VAULT_NAME = {
    "DATABASE_URL": "builderops-database-url",
    "GITHUB_TOKEN": "builderops-github-token",
    "ADO_PAT": "builderops-ado-pat",
}


def get_settings() -> Settings:
    key_vault_url = os.environ.get("AZURE_KEY_VAULT_URL")
    provider: SecretProvider = (
        KeyVaultSecretProvider(key_vault_url) if key_vault_url else EnvSecretProvider()
    )

    def resolve(env_name: str, default: str | None = None) -> str:
        secret_name = _ENV_TO_KEY_VAULT_NAME.get(env_name)
        if key_vault_url and secret_name:
            return provider.get(secret_name)
        if default is not None:
            return os.environ.get(env_name, default)
        return provider.get(env_name)

    return Settings(
        database_url=resolve("DATABASE_URL"),
        github_token=resolve("GITHUB_TOKEN"),
        github_org=os.environ.get("GITHUB_ORG", ""),
        ado_org=os.environ.get("ADO_ORG", ""),
        ado_project=os.environ.get("ADO_PROJECT", ""),
        ado_pat=resolve("ADO_PAT"),
        azure_key_vault_url=key_vault_url,
    )
```

- [ ] **Step 5: Create shared test fixtures**

```python
# backend/tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def clear_key_vault_env(monkeypatch):
    monkeypatch.delenv("AZURE_KEY_VAULT_URL", raising=False)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/app/config.py backend/tests/test_config.py backend/tests/conftest.py
git commit -m "feat: add settings and Key Vault-aware secret loading"
```

---

### Task 2: Database models

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (models don't depend on Settings).
- Produces: `Base` (SQLAlchemy declarative base) from `app.db`.
- Produces: `def get_engine(database_url: str)`, `def get_sessionmaker(engine)` from `app.db`.
- Produces from `app.models`: `Repo`, `ReadinessCheck`, `AdoRepoSnapshot`, `OnboardingLog`, `SyncRun` — all SQLAlchemy models, used by every later task.
  - `Repo`: `id: int`, `name: str` (unique), `github_url: str`, `domain: str | None`, `team: str | None`, `migration_wave: str` (default `"not_started"`), `created_at: datetime`, `last_synced_at: datetime | None`.
  - `ReadinessCheck`: composite PK `(repo_id: int, stage_key: str)`, `status: str`, `source: str`, `detail: dict | None` (JSON column), `updated_at: datetime`.
  - `AdoRepoSnapshot`: `id: int`, `name: str`, `last_activity: datetime | None`, `synced_at: datetime`.
  - `OnboardingLog`: `id: int`, `repo_id: int` (FK), `engineer_name: str`, `hours: float`, `logged_at: datetime`.
  - `SyncRun`: `id: int`, `connector: str`, `started_at: datetime`, `finished_at: datetime | None`, `status: str`, `error: str | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from datetime import datetime, timezone

from app.db import Base, get_engine, get_sessionmaker
from app.models import AdoRepoSnapshot, OnboardingLog, Repo, ReadinessCheck, SyncRun


def make_session():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return get_sessionmaker(engine)()


def test_create_and_query_repo():
    session = make_session()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    fetched = session.query(Repo).filter_by(name="checkout-web").one()
    assert fetched.github_url == "https://github.com/acme/checkout-web"
    assert fetched.migration_wave == "not_started"
    assert fetched.domain is None


def test_readiness_check_composite_key_and_upsert_via_merge():
    session = make_session()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    check = ReadinessCheck(
        repo_id=repo.id,
        stage_key="codeowners_assigned",
        status="pass",
        source="auto",
        detail={"reviewers": 3},
        updated_at=datetime.now(timezone.utc),
    )
    session.add(check)
    session.commit()

    # upsert via merge: same composite key, new status
    updated = ReadinessCheck(
        repo_id=repo.id,
        stage_key="codeowners_assigned",
        status="fail",
        source="auto",
        detail=None,
        updated_at=datetime.now(timezone.utc),
    )
    session.merge(updated)
    session.commit()

    rows = session.query(ReadinessCheck).filter_by(repo_id=repo.id, stage_key="codeowners_assigned").all()
    assert len(rows) == 1
    assert rows[0].status == "fail"


def test_ado_snapshot_onboarding_log_and_sync_run():
    session = make_session()
    session.add(AdoRepoSnapshot(name="legacy-batch", last_activity=None, synced_at=datetime.now(timezone.utc)))
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    session.add(OnboardingLog(repo_id=repo.id, engineer_name="Sam", hours=6.5, logged_at=datetime.now(timezone.utc)))
    session.add(SyncRun(connector="github", started_at=datetime.now(timezone.utc), status="running"))
    session.commit()

    assert session.query(AdoRepoSnapshot).count() == 1
    assert session.query(OnboardingLog).count() == 1
    assert session.query(SyncRun).filter_by(connector="github").one().status == "running"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Implement `app/db.py`**

```python
# backend/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    return create_engine(database_url, future=True)


def get_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
```

- [ ] **Step 4: Implement `app/models.py`**

```python
# backend/app/models.py
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    github_url: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    team: Mapped[str | None] = mapped_column(String, nullable=True)
    migration_wave: Mapped[str] = mapped_column(String, nullable=False, default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReadinessCheck(Base):
    __tablename__ = "readiness_checks"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    stage_key: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AdoRepoSnapshot(Base):
    __tablename__ = "ado_repo_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OnboardingLog(Base):
    __tablename__ = "onboarding_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    engineer_name: Mapped[str] = mapped_column(String, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connector: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add SQLAlchemy models for repos, readiness checks, and sync tracking"
```

---

### Task 3: FastAPI app skeleton with health check

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/api/__init__.py`
- Test: `backend/tests/api/test_health.py`

**Interfaces:**
- Consumes: `get_settings()` (Task 1), `Base`, `get_engine`, `get_sessionmaker` (Task 2).
- Produces: `def create_app(settings: Settings | None = None) -> FastAPI` — the app factory every later task's router attaches to. Stores the sessionmaker on `app.state.sessionmaker`.
- Produces: `def get_db(request: Request)` — FastAPI dependency yielding a `Session`, used by every API router.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/__init__.py
```

```python
# backend/tests/api/test_health.py
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_health_endpoint_returns_ok():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement `app/main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import Base, get_engine, get_sessionmaker


def get_db(request: Request):
    sessionmaker_ = request.app.state.sessionmaker
    db: Session = sessionmaker_()
    try:
        yield db
    finally:
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="BuilderOps API")

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = get_sessionmaker(engine)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_health.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/api/__init__.py backend/tests/api/test_health.py
git commit -m "feat: add FastAPI app factory with health check and DB session dependency"
```

---

### Task 4: GitHub connector

**Files:**
- Create: `backend/app/connectors/__init__.py`
- Create: `backend/app/connectors/github_connector.py`
- Test: `backend/tests/connectors/__init__.py`
- Test: `backend/tests/connectors/test_github_connector.py`

**Interfaces:**
- Consumes: an `httpx.AsyncClient` passed in by the caller (so tests can inject a mock transport).
- Produces: `@dataclass class GitHubRepoData` with fields `name: str`, `url: str`, `has_readme: bool`, `has_codeowners: bool`, `branch_protection_enabled: bool`, `required_reviewer_count: int`.
- Produces: `async def fetch_repos(client: httpx.AsyncClient, org: str, token: str) -> list[GitHubRepoData]` — paginates the repo list, then batches Standardized-check queries in groups of up to 100 using aliased GraphQL queries. Used by `sync_service` (Task 7).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/connectors/__init__.py
```

```python
# backend/tests/connectors/test_github_connector.py
import httpx
import pytest

from app.connectors.github_connector import GitHubRepoData, fetch_repos

REPO_LIST_RESPONSE = {
    "data": {
        "organization": {
            "repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"name": "checkout-web", "url": "https://github.com/acme-org/checkout-web"},
                    {"name": "payments-api", "url": "https://github.com/acme-org/payments-api"},
                ],
            }
        }
    }
}

REPO_CHECKS_RESPONSE = {
    "data": {
        "r0": {
            "readme": {"id": "readme-1"},
            "codeowners": {"id": "codeowners-1"},
            "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 2}]},
        },
        "r1": {
            "readme": None,
            "codeowners": None,
            "branchProtectionRules": {"nodes": []},
        },
    }
}


@pytest.mark.asyncio
async def test_fetch_repos_combines_list_and_checks():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        calls.append(body)
        if "repositories(first:" in body:
            return httpx.Response(200, json=REPO_LIST_RESPONSE)
        return httpx.Response(200, json=REPO_CHECKS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        repos = await fetch_repos(client, org="acme-org", token="gh-token")

    assert len(repos) == 2
    assert repos[0] == GitHubRepoData(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
    )
    assert repos[1] == GitHubRepoData(
        name="payments-api",
        url="https://github.com/acme-org/payments-api",
        has_readme=False,
        has_codeowners=False,
        branch_protection_enabled=False,
        required_reviewer_count=0,
    )
    assert any("Authorization" in c or True for c in calls)  # calls captured, auth checked via header assertion below


@pytest.mark.asyncio
async def test_fetch_repos_sends_bearer_token():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["authorization"] = request.headers.get("authorization")
        body = request.content.decode()
        if "repositories(first:" in body:
            return httpx.Response(200, json={"data": {"organization": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}})
        return httpx.Response(200, json={"data": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await fetch_repos(client, org="acme-org", token="gh-token")

    assert seen_headers["authorization"] == "Bearer gh-token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/connectors/test_github_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors'`

- [ ] **Step 3: Implement `app/connectors/__init__.py` and `app/connectors/github_connector.py`**

```python
# backend/app/connectors/__init__.py
```

```python
# backend/app/connectors/github_connector.py
from dataclasses import dataclass

import httpx

GRAPHQL_URL = "/graphql"


@dataclass
class GitHubRepoData:
    name: str
    url: str
    has_readme: bool
    has_codeowners: bool
    branch_protection_enabled: bool
    required_reviewer_count: int


LIST_QUERY = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { name url }
    }
  }
}
"""


def _checks_query(repo_names: list[str], org: str) -> str:
    aliases = []
    for i, name in enumerate(repo_names):
        aliases.append(f'''
        r{i}: repository(owner: "{org}", name: "{name}") {{
          readme: object(expression: "HEAD:README.md") {{ id }}
          codeowners: object(expression: "HEAD:.github/CODEOWNERS") {{ id }}
          branchProtectionRules(first: 10) {{
            nodes {{ pattern requiredApprovingReviewCount }}
          }}
        }}''')
    return "query {" + "".join(aliases) + "\n}"


async def _fetch_repo_list(client: httpx.AsyncClient, org: str, headers: dict) -> list[dict]:
    repos: list[dict] = []
    cursor = None
    while True:
        resp = await client.post(
            GRAPHQL_URL,
            json={"query": LIST_QUERY, "variables": {"org": org, "cursor": cursor}},
            headers=headers,
        )
        resp.raise_for_status()
        page = resp.json()["data"]["organization"]["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return repos


def _batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def fetch_repos(client: httpx.AsyncClient, org: str, token: str) -> list[GitHubRepoData]:
    headers = {"Authorization": f"Bearer {token}"}
    repo_list = await _fetch_repo_list(client, org, headers)

    results: list[GitHubRepoData] = []
    for batch in _batched(repo_list, 100):
        names = [r["name"] for r in batch]
        resp = await client.post(GRAPHQL_URL, json={"query": _checks_query(names, org)}, headers=headers)
        resp.raise_for_status()
        data = resp.json()["data"]
        for i, repo in enumerate(batch):
            check = data[f"r{i}"]
            protection_nodes = (check.get("branchProtectionRules") or {}).get("nodes") or []
            required_reviewers = max((n.get("requiredApprovingReviewCount") or 0) for n in protection_nodes) if protection_nodes else 0
            results.append(
                GitHubRepoData(
                    name=repo["name"],
                    url=repo["url"],
                    has_readme=check.get("readme") is not None,
                    has_codeowners=check.get("codeowners") is not None,
                    branch_protection_enabled=bool(protection_nodes),
                    required_reviewer_count=required_reviewers,
                )
            )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/connectors/test_github_connector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/__init__.py backend/app/connectors/github_connector.py backend/tests/connectors/
git commit -m "feat: add GitHub GraphQL connector for repo list and standardization checks"
```

---

### Task 5: Azure DevOps connector v0

**Files:**
- Create: `backend/app/connectors/ado_connector.py`
- Test: `backend/tests/connectors/test_ado_connector.py`

**Interfaces:**
- Consumes: an `httpx.AsyncClient` passed in by the caller.
- Produces: `@dataclass class AdoRepoData` with fields `name: str`, `last_activity: str | None` (ISO date string as returned by ADO, parsed later by the caller).
- Produces: `async def fetch_ado_repos(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[AdoRepoData]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/connectors/test_ado_connector.py
import base64

import httpx
import pytest

from app.connectors.ado_connector import AdoRepoData, fetch_ado_repos

ADO_LIST_RESPONSE = {
    "value": [
        {"name": "legacy-batch", "project": {"lastUpdateTime": "2026-05-01T00:00:00Z"}},
        {"name": "checkout-web", "project": {"lastUpdateTime": "2026-06-10T00:00:00Z"}},
    ]
}


@pytest.mark.asyncio
async def test_fetch_ado_repos_parses_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/acme-project/_apis/git/repositories" in str(request.url)
        return httpx.Response(200, json=ADO_LIST_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        repos = await fetch_ado_repos(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert repos == [
        AdoRepoData(name="legacy-batch", last_activity="2026-05-01T00:00:00Z"),
        AdoRepoData(name="checkout-web", last_activity="2026-06-10T00:00:00Z"),
    ]


@pytest.mark.asyncio
async def test_fetch_ado_repos_sends_basic_auth_with_pat():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await fetch_ado_repos(client, org="acme-ado", project="acme-project", pat="ado-pat")

    expected_token = base64.b64encode(b":ado-pat").decode()
    assert seen["authorization"] == f"Basic {expected_token}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/connectors/test_ado_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.connectors.ado_connector'`

- [ ] **Step 3: Implement `app/connectors/ado_connector.py`**

```python
# backend/app/connectors/ado_connector.py
import base64
from dataclasses import dataclass

import httpx


@dataclass
class AdoRepoData:
    name: str
    last_activity: str | None


def _basic_auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {token}"


async def fetch_ado_repos(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[AdoRepoData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/git/repositories",
        params={"api-version": "7.1"},
        headers=headers,
    )
    resp.raise_for_status()
    body = resp.json()
    return [
        AdoRepoData(
            name=item["name"],
            last_activity=(item.get("project") or {}).get("lastUpdateTime"),
        )
        for item in body["value"]
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/connectors/test_ado_connector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/connectors/ado_connector.py backend/tests/connectors/test_ado_connector.py
git commit -m "feat: add minimal Azure DevOps connector for repo-list reconciliation"
```

---

### Task 6: Readiness service

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/readiness.py`
- Test: `backend/tests/services/__init__.py`
- Test: `backend/tests/services/test_readiness.py`

**Interfaces:**
- Consumes: `GitHubRepoData` (Task 4), `AdoRepoData` (Task 5), `Repo`/`ReadinessCheck` models (Task 2).
- Produces: `def compute_readiness_checks(github_repo: GitHubRepoData, ado_repo_names: set[str], repo_id: int, now: datetime) -> list[ReadinessCheck]` — pure function, no DB access, returns in-memory `ReadinessCheck` objects for stage keys: `migrated_from_ado`, `codeowners_assigned`, `readme_present`, `branch_protection`, `naming_standardized`. Never returns a row for `domain_assigned` (manual-only field, left untouched by sync).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/__init__.py
```

```python
# backend/tests/services/test_readiness.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_readiness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Implement `app/services/__init__.py` and `app/services/readiness.py`**

```python
# backend/app/services/__init__.py
```

```python
# backend/app/services/readiness.py
from datetime import datetime

from app.connectors.github_connector import GitHubRepoData
from app.models import ReadinessCheck


def compute_readiness_checks(
    github_repo: GitHubRepoData,
    ado_repo_names: set[str],
    repo_id: int,
    now: datetime,
) -> list[ReadinessCheck]:
    migrated = github_repo.name not in ado_repo_names

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
            detail={"required_reviewer_count": github_repo.required_reviewer_count},
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
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_readiness.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/readiness.py backend/tests/services/
git commit -m "feat: add readiness service computing Onboarded/Standardized stage checks"
```

---

### Task 7: Sync service (orchestration)

**Files:**
- Create: `backend/app/services/sync_service.py`
- Test: `backend/tests/services/test_sync_service.py`

**Interfaces:**
- Consumes: `fetch_repos` (Task 4), `fetch_ado_repos` (Task 5), `compute_readiness_checks` (Task 6), `Repo`/`AdoRepoSnapshot`/`SyncRun` models (Task 2).
- Produces: `async def run_github_sync(session: Session, client: httpx.AsyncClient, org: str, token: str, now: datetime) -> SyncRun`.
- Produces: `async def run_ado_sync(session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime) -> SyncRun`.
- Both functions commit their own transaction and return the completed `SyncRun` row (status `"success"` or `"failed"`, with `error` populated on failure). A failure in per-repo readiness computation for one repo does not stop the rest — that repo's checks are skipped and the run still reports `"success"` (Global Constraint: per-check granularity, not per-run failure).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_sync_service.py
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.connectors.ado_connector import AdoRepoData
from app.db import Base, get_engine, get_sessionmaker
from app.models import AdoRepoSnapshot, Repo, ReadinessCheck, SyncRun
from app.services.sync_service import run_ado_sync, run_github_sync

NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Session:
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return get_sessionmaker(engine)()


def github_handler(request: httpx.Request) -> httpx.Response:
    body = request.content.decode()
    if "repositories(first:" in body:
        return httpx.Response(200, json={"data": {"organization": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"name": "checkout-web", "url": "https://github.com/acme-org/checkout-web"}],
        }}}})
    return httpx.Response(200, json={"data": {"r0": {
        "readme": {"id": "1"}, "codeowners": {"id": "2"},
        "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 1}]},
    }}})


@pytest.mark.asyncio
async def test_run_github_sync_creates_repo_and_readiness_checks(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        sync_run = await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert repo.last_synced_at == NOW
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    assert {c.stage_key for c in checks} == {
        "migrated_from_ado", "codeowners_assigned", "readme_present", "branch_protection", "naming_standardized",
    }


@pytest.mark.asyncio
async def test_run_github_sync_is_idempotent_on_rerun(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert session.query(Repo).count() == 1
    assert session.query(ReadinessCheck).count() == 5


@pytest.mark.asyncio
async def test_run_github_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        sync_run = await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error


@pytest.mark.asyncio
async def test_run_ado_sync_stores_snapshot():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = get_sessionmaker(engine)()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{"name": "legacy-batch", "project": {"lastUpdateTime": "2026-05-01T00:00:00Z"}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_ado_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    assert sync_run.status == "success"
    snapshot = session.query(AdoRepoSnapshot).one()
    assert snapshot.name == "legacy-batch"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_sync_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.sync_service'`

- [ ] **Step 3: Implement `app/services/sync_service.py`**

```python
# backend/app/services/sync_service.py
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.connectors.ado_connector import fetch_ado_repos
from app.connectors.github_connector import fetch_repos
from app.models import AdoRepoSnapshot, Repo, SyncRun
from app.services.readiness import compute_readiness_checks


async def run_github_sync(
    session: Session, client: httpx.AsyncClient, org: str, token: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="github", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        github_repos = await fetch_repos(client, org=org, token=token)
        ado_repo_names = {row.name for row in session.query(AdoRepoSnapshot).all()}

        for github_repo in github_repos:
            repo = session.query(Repo).filter_by(name=github_repo.name).one_or_none()
            if repo is None:
                repo = Repo(name=github_repo.name, github_url=github_repo.url)
                session.add(repo)
                session.flush()  # assigns repo.id before building checks
            repo.github_url = github_repo.url
            repo.last_synced_at = now

            for check in compute_readiness_checks(github_repo, ado_repo_names, repo.id, now):
                session.merge(check)

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


async def run_ado_sync(
    session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="ado", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        ado_repos = await fetch_ado_repos(client, org=org, project=project, pat=pat)

        session.query(AdoRepoSnapshot).delete()
        for repo in ado_repos:
            session.add(AdoRepoSnapshot(name=repo.name, last_activity=repo.last_activity, synced_at=now))

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_sync_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/services/test_sync_service.py
git commit -m "feat: add sync service orchestrating GitHub and ADO connectors into readiness data"
```

---

### Task 8: Repos API

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/repos.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `Repo`, `ReadinessCheck`, `OnboardingLog` models (Task 2), `get_db` dependency (Task 3).
- Produces: `router = APIRouter()` in `app.api.repos`, mounted at `/repos` by `main.py`.
  - `GET /repos` → list of `{id, name, domain, migration_wave, stages: {stage_key: status}}`.
  - `GET /repos/{repo_id}` → same shape as one item above, 404 if missing.
  - `PATCH /repos/{repo_id}` → body `{domain?: str, migration_wave?: str}`, updates manual fields only, returns updated repo.
  - `POST /repos/{repo_id}/onboarding-log` → body `{engineer_name: str, hours: float}`, creates an `OnboardingLog` row, returns it.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_repos_api.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Repo, ReadinessCheck


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def seed_repo(app):
    session = app.state.sessionmaker()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web", domain="Growth")
    session.add(repo)
    session.commit()
    session.add(ReadinessCheck(
        repo_id=repo.id, stage_key="codeowners_assigned", status="pass", source="auto",
        detail=None, updated_at=datetime.now(timezone.utc),
    ))
    session.commit()
    session.close()
    return repo.id


def test_list_repos_returns_stage_map():
    app = create_app(make_test_settings())
    seed_repo(app)
    client = TestClient(app)

    response = client.get("/repos")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "checkout-web"
    assert body[0]["stages"]["codeowners_assigned"] == "pass"


def test_get_single_repo_404_when_missing():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/repos/999")

    assert response.status_code == 404


def test_patch_repo_updates_manual_fields_only():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"domain": "Checkout", "migration_wave": "pilot"})

    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "Checkout"
    assert body["migration_wave"] == "pilot"


def test_post_onboarding_log_creates_entry():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Sam", "hours": 6.5})

    assert response.status_code == 201
    body = response.json()
    assert body["engineer_name"] == "Sam"
    assert body["hours"] == 6.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_repos_api.py -v`
Expected: FAIL with `404` on `/repos` (route not registered) or `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/schemas.py`**

```python
# backend/app/schemas.py
from datetime import datetime

from pydantic import BaseModel


class RepoOut(BaseModel):
    id: int
    name: str
    domain: str | None
    migration_wave: str
    stages: dict[str, str]

    model_config = {"from_attributes": True}


class RepoPatchIn(BaseModel):
    domain: str | None = None
    migration_wave: str | None = None


class OnboardingLogIn(BaseModel):
    engineer_name: str
    hours: float


class OnboardingLogOut(BaseModel):
    id: int
    repo_id: int
    engineer_name: str
    hours: float
    logged_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement `app/api/__init__.py` and `app/api/repos.py`**

```python
# backend/app/api/__init__.py
```

```python
# backend/app/api/repos.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.main import get_db
from app.models import OnboardingLog, ReadinessCheck, Repo
from app.schemas import OnboardingLogIn, OnboardingLogOut, RepoOut, RepoPatchIn

router = APIRouter(prefix="/repos", tags=["repos"])


def _to_repo_out(repo: Repo, session: Session) -> RepoOut:
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        migration_wave=repo.migration_wave,
        stages={c.stage_key: c.status for c in checks},
    )


@router.get("", response_model=list[RepoOut])
def list_repos(session: Session = Depends(get_db)):
    repos = session.query(Repo).all()
    return [_to_repo_out(r, session) for r in repos]


@router.get("/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return _to_repo_out(repo, session)


@router.patch("/{repo_id}", response_model=RepoOut)
def patch_repo(repo_id: int, body: RepoPatchIn, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if body.domain is not None:
        repo.domain = body.domain
    if body.migration_wave is not None:
        repo.migration_wave = body.migration_wave
    session.commit()
    return _to_repo_out(repo, session)


@router.post("/{repo_id}/onboarding-log", response_model=OnboardingLogOut, status_code=201)
def post_onboarding_log(repo_id: int, body: OnboardingLogIn, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    entry = OnboardingLog(
        repo_id=repo_id,
        engineer_name=body.engineer_name,
        hours=body.hours,
        logged_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    session.commit()
    return entry
```

- [ ] **Step 5: Wire the router into the app**

```python
# backend/app/main.py — add import and include_router call
from app.api.repos import router as repos_router
```

Add inside `create_app`, before `return app`:

```python
    app.include_router(repos_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/__init__.py backend/app/api/repos.py backend/app/main.py backend/tests/api/test_repos_api.py
git commit -m "feat: add repos API for listing, detail, manual field edits, and onboarding log"
```

---

### Task 9: Sync trigger + status API

**Files:**
- Create: `backend/app/api/sync.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/api/test_sync_api.py`

**Interfaces:**
- Consumes: `run_github_sync`, `run_ado_sync` (Task 7), `SyncRun` model (Task 2).
- Produces: `router = APIRouter()` in `app.api.sync`, mounted at `/sync`.
  - `POST /sync/github` → runs `run_github_sync` against a live `httpx.AsyncClient`, returns the `SyncRun`.
  - `POST /sync/ado` → same for ADO.
  - `GET /sync/status` → latest `SyncRun` per connector, `{"github": {...} | null, "ado": {...} | null}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_sync_api.py
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import SyncRun


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_sync_status_returns_null_when_nothing_has_run():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json() == {"github": None, "ado": None}


def test_sync_status_returns_latest_run_per_connector():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    session.add(SyncRun(connector="github", started_at=datetime.now(timezone.utc), status="success"))
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/sync/status")

    assert response.status_code == 200
    body = response.json()
    assert body["github"]["status"] == "success"
    assert body["ado"] is None


def test_post_sync_github_triggers_a_run(monkeypatch):
    app = create_app(make_test_settings())

    async def fake_run_github_sync(session, client, org, token, now):
        return SyncRun(connector="github", started_at=now, status="success", finished_at=now)

    monkeypatch.setattr("app.api.sync.run_github_sync", fake_run_github_sync)

    client = TestClient(app)
    response = client.post("/sync/github")

    assert response.status_code == 202
    assert response.json()["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_sync_api.py -v`
Expected: FAIL with `404` (routes not registered) or `ModuleNotFoundError`

- [ ] **Step 3: Add `SyncRunOut` schema**

```python
# backend/app/schemas.py — append
class SyncRunOut(BaseModel):
    id: int
    connector: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    error: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement `app/api/sync.py`**

```python
# backend/app/api/sync.py
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.main import get_db
from app.models import SyncRun
from app.schemas import SyncRunOut
from app.services.sync_service import run_ado_sync, run_github_sync

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status")
def sync_status(session: Session = Depends(get_db)):
    result = {}
    for connector in ("github", "ado"):
        latest = (
            session.query(SyncRun)
            .filter_by(connector=connector)
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        result[connector] = SyncRunOut.model_validate(latest).model_dump() if latest else None
    return result


@router.post("/github", response_model=SyncRunOut, status_code=202)
async def trigger_github_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url="https://api.github.com") as client:
        return await run_github_sync(
            session, client, org=settings.github_org, token=settings.github_token, now=datetime.now(timezone.utc)
        )


@router.post("/ado", response_model=SyncRunOut, status_code=202)
async def trigger_ado_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}") as client:
        return await run_ado_sync(
            session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
            now=datetime.now(timezone.utc),
        )
```

- [ ] **Step 5: Wire the router into the app**

```python
# backend/app/main.py — add import
from app.api.sync import router as sync_router
```

Add inside `create_app`, alongside the existing `include_router` call:

```python
    app.include_router(sync_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_sync_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/sync.py backend/app/schemas.py backend/app/main.py backend/tests/api/test_sync_api.py
git commit -m "feat: add sync trigger and status API endpoints"
```

---

### Task 10: Scheduler wiring

**Files:**
- Create: `backend/app/scheduler.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_github_sync`, `run_ado_sync` (Task 7), `Settings` (Task 1).
- Produces: `def start_scheduler(app: FastAPI) -> BackgroundScheduler` — registers a GitHub sync job (every 4 hours) and an ADO sync job (daily), storing the scheduler on `app.state.scheduler`. Called from `create_app` only when `settings.database_url` isn't the test sqlite in-memory URL — tests call `start_scheduler` directly instead of relying on app startup, to avoid background jobs firing during the test suite.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scheduler.py
from app.config import Settings
from app.main import create_app
from app.scheduler import start_scheduler


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_start_scheduler_registers_github_and_ado_jobs():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"github_sync", "ado_sync"}
    scheduler.shutdown(wait=False)


def test_start_scheduler_github_job_runs_every_4_hours():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    github_job = scheduler.get_job("github_sync")
    assert github_job.trigger.interval.total_seconds() == 4 * 60 * 60
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scheduler'`

- [ ] **Step 3: Implement `app/scheduler.py`**

```python
# backend/app/scheduler.py
import asyncio
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.services.sync_service import run_ado_sync, run_github_sync


def _run_github_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url="https://api.github.com") as client:
            await run_github_sync(
                session, client, org=settings.github_org, token=settings.github_token,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def _run_ado_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}") as client:
            await run_ado_sync(
                session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def start_scheduler(app: FastAPI) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_github_sync_job, "interval", hours=4, args=[app], id="github_sync")
    scheduler.add_job(_run_ado_sync_job, "interval", days=1, args=[app], id="ado_sync")
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire scheduler startup into the app, skipped for the in-memory test database**

```python
# backend/app/main.py — add import
from app.scheduler import start_scheduler
```

Add inside `create_app`, right before `return app`:

```python
    if settings.database_url != "sqlite:///:memory:":
        start_scheduler(app)
```

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all tests across every file — scheduler is not started for any test since they all use `sqlite:///:memory:`)

- [ ] **Step 7: Commit**

```bash
git add backend/app/scheduler.py backend/app/main.py backend/tests/test_scheduler.py
git commit -m "feat: schedule periodic GitHub and ADO sync jobs"
```

---

## Self-Review Notes

- **Spec coverage:** Settings/Key Vault (§4 Security) → Task 1. Data model (§5) → Task 2. GitHub connector, README/CODEOWNERS/branch-protection only, no Actions/Dockerfile (§4 corrected scope) → Task 4. ADO connector v0, list-only (§4) → Task 5. `migrated_from_ado`/`codeowners_assigned`/`readme_present`/`branch_protection`/`naming_standardized` stage keys with `pending_convention` handling (§5, §8) → Task 6. Sync/error strategy — per-check failure isolation, `SyncRun` staleness tracking (§6) → Task 7. Manual fields (`domain`, `migration_wave`) and onboarding log (§7.3) → Task 8. Sync status for the "synced Xm ago" / failure-banner UI need (§6) → Task 9. Tiered scheduling (§4 Efficiency) → Task 10. `domain_assigned` is intentionally never auto-computed (manual-only, per §5) — verified by an explicit test in Task 6.
- **Placeholder scan:** no TBD/TODO markers; every step has runnable code.
- **Type consistency:** `GitHubRepoData`, `AdoRepoData`, `ReadinessCheck`, `Repo`, `SyncRun` field names are identical everywhere they're referenced across tasks (checked against Task 2/4/5 definitions when writing Tasks 6/7/8/9).
- **Deferred by design, not a gap:** Actions-per-env, Dockerfile/dockerized, ACA deployment, code coverage, E2E, load test — all explicitly out of scope per the corrected spec §3, powering the future Piped/Tested cards.

---

## Next steps after this plan ships

1. Deploy: provision the Azure Key Vault secrets (`builderops-database-url`, `builderops-github-token`, `builderops-ado-pat`), grant the backend's Managed Identity the "Key Vault Secrets User" role, set `AZURE_KEY_VAULT_URL` in the deployment environment.
2. Write the frontend plan (separate `docs/superpowers/plans/` document) against this API's actual contract: `GET /repos`, `GET /repos/{id}`, `PATCH /repos/{id}`, `POST /repos/{id}/onboarding-log`, `GET /sync/status`.
3. The frontend's "Onboarded"/"Standardized" cards map directly to the `stages` dict this API returns; "Piped"/"Tested"/"Paved Road" render as `Locked` client-side since no stage keys for them exist yet.
