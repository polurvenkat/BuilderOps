# Inventory Tab & GitHub Repo Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Board/Inventory tab switcher to the Fleet landing page, where Inventory shows a matrix of app count (manual), technology (auto-detected), and complexity (computed) per repo, plus an inline control to rename a repo's real GitHub repository.

**Architecture:** Backend: three new nullable `Repo` columns (`app_count` manual, `primary_language`/`total_code_bytes` auto-filled by the existing GitHub GraphQL sync with zero new API calls); complexity is computed live per request as tertiles across the full, unfiltered repo set (never stored, never filter-dependent); rename calls GitHub's real REST API and updates the *same* `Repo` row atomically to prevent the next sync from creating a duplicate. Frontend: an in-page tab switch on `FleetPage` (no new route), a new `InventoryTable` component with an inline kebab-case-defaulted rename control gated by a native confirm.

**Tech Stack:** FastAPI/SQLAlchemy/Postgres backend, React/TypeScript/Tailwind frontend — same stack as the rest of BuilderOps.

## Global Constraints

- All new `Repo` columns are nullable with no backfill required (genuinely new, previously-untracked facts) — additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` against the real DB, applied after merge (not part of any task; the app has no migration system, `Base.metadata.create_all` only creates missing tables).
- Complexity tertiles: sort every repo with a non-null `total_code_bytes` ascending by byte count (stable sort, ties keep query/insertion order), bucket by index using integer division on count `n`: `[0, n//3)` → `"low"`, `[n//3, 2*(n//3))` → `"medium"`, `[2*(n//3), n)` → `"high"`. A repo with `total_code_bytes is None` gets `complexity: null`.
- Complexity is **always** computed against the full, unfiltered repo set, never the `?domain=`/`?stage=`-filtered result — a repo's complexity must not change depending on which filter is active.
- The GitHub rename flow **must** update `repo.name`/`repo.github_url` on the same existing row in the same request as the GitHub API call. `run_github_sync` matches incoming repos by `Repo.name` — if this row isn't updated atomically, the next sync creates a duplicate `Repo` row and orphans every readiness check/onboarding log/domain/team assignment tied to the old row's id. This is the one non-negotiable correctness requirement in this plan (see Task 5).
- GraphQL field names verified against the real GitHub API before writing this plan: `primaryLanguage { name }` and `languages { totalSize }` (no `first:` argument needed — confirmed live against a real repo, returns e.g. `{"primaryLanguage": {"name": "TypeScript"}, "languages": {"totalSize": 642232}}`).
- Rename REST endpoint: `PATCH /repos/{org}/{repo}` with body `{"name": new_name}`, same `https://api.github.com` base URL already used for GraphQL calls in this codebase. Response body's `name`/`html_url` are the source of truth for the updated row (GitHub may normalize the requested name — never assume the request body's value was applied verbatim).
- Frontend `patchRepo` (`frontend/src/api/client.ts`) already accepts arbitrary `RepoPatchIn` fields — no changes needed to `client.ts` in this plan.

---

### Task 1: Backend — `Repo` schema columns + GitHub connector auto-detected fields

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/connectors/github_connector.py`
- Test: `backend/tests/connectors/test_github_connector.py`

**Interfaces:**
- Produces: `Repo.app_count: int | None`, `Repo.primary_language: str | None`, `Repo.total_code_bytes: int | None`. `GitHubRepoData` gains `primary_language: str | None = None` and `total_code_bytes: int = 0` (defaulted so the existing `make_github_repo()` helper in `tests/services/test_readiness.py` keeps working unmodified — out of this task's file scope).

- [ ] **Step 1: Add the three new columns to `Repo`**

In `backend/app/models.py`, add after the existing `e2e_test_plan_id` line inside `class Repo`:

```python
    app_count: Mapped[int | None] = mapped_column(nullable=True, default=None)
    primary_language: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    total_code_bytes: Mapped[int | None] = mapped_column(nullable=True, default=None)
```

- [ ] **Step 2: Write the failing test for the connector fields**

In `backend/tests/connectors/test_github_connector.py`, replace `REPO_CHECKS_RESPONSE` with:

```python
REPO_CHECKS_RESPONSE = {
    "data": {
        "r0": {
            "readme": {"id": "readme-1"},
            "codeowners": {"id": "codeowners-1"},
            "dockerfile": {"id": "dockerfile-1"},
            "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 2}]},
            "primaryLanguage": {"name": "TypeScript"},
            "languages": {"totalSize": 50000},
        },
        "r1": {
            "readme": None,
            "codeowners": None,
            "dockerfile": None,
            "branchProtectionRules": {"nodes": []},
            "primaryLanguage": None,
            "languages": {"totalSize": 0},
        },
    }
}
```

Then update the two assertions in `test_fetch_repos_combines_list_and_checks`:

```python
    assert repos[0] == GitHubRepoData(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        dockerfile_present=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
        primary_language="TypeScript",
        total_code_bytes=50000,
    )
    assert repos[1] == GitHubRepoData(
        name="payments-api",
        url="https://github.com/acme-org/payments-api",
        has_readme=False,
        has_codeowners=False,
        dockerfile_present=False,
        branch_protection_enabled=False,
        required_reviewer_count=0,
        primary_language=None,
        total_code_bytes=0,
    )
```

- [ ] **Step 2b: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/connectors/test_github_connector.py -v`
Expected: FAIL — `GitHubRepoData.__init__()` doesn't accept `primary_language`/`total_code_bytes` yet.

- [ ] **Step 3: Extend `GitHubRepoData`, the GraphQL query, and the parsing**

In `backend/app/connectors/github_connector.py`, change the dataclass to:

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
    primary_language: str | None = None
    total_code_bytes: int = 0
```

Change `_checks_query` — add two fields to each aliased repository block:

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
          primaryLanguage {{ name }}
          languages {{ totalSize }}
        }}''')
    return "query {" + "".join(aliases) + "\n}"
```

Change the parsing loop inside `fetch_repos`:

```python
        for i, repo in enumerate(batch):
            check = data[f"r{i}"]
            protection_nodes = (check.get("branchProtectionRules") or {}).get("nodes") or []
            required_reviewers = max((n.get("requiredApprovingReviewCount") or 0) for n in protection_nodes) if protection_nodes else 0
            primary_language = (check.get("primaryLanguage") or {}).get("name")
            total_code_bytes = (check.get("languages") or {}).get("totalSize") or 0
            results.append(
                GitHubRepoData(
                    name=repo["name"],
                    url=repo["url"],
                    has_readme=check.get("readme") is not None,
                    has_codeowners=check.get("codeowners") is not None,
                    dockerfile_present=check.get("dockerfile") is not None,
                    branch_protection_enabled=bool(protection_nodes),
                    required_reviewer_count=required_reviewers,
                    primary_language=primary_language,
                    total_code_bytes=total_code_bytes,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/connectors/test_github_connector.py tests/services/test_readiness.py -v`
Expected: all PASS (the `test_readiness.py` file is untouched and unaffected because the two new fields default).

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/connectors/github_connector.py backend/tests/connectors/test_github_connector.py
git commit -m "feat: add app_count/primary_language/total_code_bytes to Repo and the GitHub connector"
```

---

### Task 2: Backend — wire the new connector fields into `run_github_sync`

**Files:**
- Modify: `backend/app/services/sync_service.py`
- Test: `backend/tests/services/test_sync_service.py`

**Interfaces:**
- Consumes: `GitHubRepoData.primary_language`, `GitHubRepoData.total_code_bytes` (Task 1).
- Produces: `Repo.primary_language`/`Repo.total_code_bytes` populated on every `run_github_sync` call.

- [ ] **Step 1: Write the failing test**

In `backend/tests/services/test_sync_service.py`, update the shared `github_handler` fixture (used by several existing tests) to include the new fields in its checks-response branch:

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
        "primaryLanguage": {"name": "TypeScript"}, "languages": {"totalSize": 12345},
    }}})
```

Then add a new test right after `test_run_github_sync_creates_repo_and_readiness_checks`:

```python
@pytest.mark.asyncio
async def test_run_github_sync_populates_primary_language_and_code_size(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert repo.primary_language == "TypeScript"
    assert repo.total_code_bytes == 12345
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/services/test_sync_service.py -v -k populates_primary_language`
Expected: FAIL — `repo.primary_language` is `None`.

- [ ] **Step 3: Wire the fields in `run_github_sync`**

In `backend/app/services/sync_service.py`, inside the `for github_repo in github_repos:` loop, after `repo.last_synced_at = now`, add:

```python
            repo.primary_language = github_repo.primary_language
            repo.total_code_bytes = github_repo.total_code_bytes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/test_sync_service.py -v`
Expected: all PASS, including the existing `github_handler`-based tests (unaffected by the added fixture fields).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/services/test_sync_service.py
git commit -m "feat: populate Repo.primary_language/total_code_bytes from the GitHub sync"
```

---

### Task 3: Backend — complexity tertile computation

**Files:**
- Create: `backend/app/services/complexity.py`
- Test: `backend/tests/services/test_complexity.py`

**Interfaces:**
- Produces: `compute_complexity_buckets(byte_counts: dict[int, int | None]) -> dict[int, Literal["low", "medium", "high"] | None]` — a pure function, no DB/session dependency, consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_complexity.py`:

```python
from app.services.complexity import compute_complexity_buckets


def test_buckets_split_into_real_tertiles_for_nine_repos():
    byte_counts = {i: (i + 1) * 1000 for i in range(9)}  # repo 0 smallest ... repo 8 largest
    result = compute_complexity_buckets(byte_counts)

    assert [result[i] for i in range(3)] == ["low", "low", "low"]
    assert [result[i] for i in range(3, 6)] == ["medium", "medium", "medium"]
    assert [result[i] for i in range(6, 9)] == ["high", "high", "high"]


def test_repo_with_no_byte_count_gets_none_not_a_fabricated_bucket():
    byte_counts = {1: 1000, 2: 2000, 3: None}
    result = compute_complexity_buckets(byte_counts)

    assert result[3] is None
    assert result[1] in ("low", "medium", "high")


def test_fewer_than_three_repos_all_land_in_high():
    byte_counts = {1: 500, 2: 1500}
    result = compute_complexity_buckets(byte_counts)

    assert result[1] == "high"
    assert result[2] == "high"


def test_single_repo_lands_in_high():
    result = compute_complexity_buckets({1: 500})
    assert result[1] == "high"


def test_ties_are_broken_by_stable_input_order():
    byte_counts = {1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000, 6: 1000}
    result = compute_complexity_buckets(byte_counts)

    assert [result[i] for i in range(1, 7)] == ["low", "low", "medium", "medium", "high", "high"]


def test_empty_input_returns_empty_dict():
    assert compute_complexity_buckets({}) == {}


def test_all_none_byte_counts_all_map_to_none():
    result = compute_complexity_buckets({1: None, 2: None})
    assert result == {1: None, 2: None}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/test_complexity.py -v`
Expected: FAIL — `app.services.complexity` doesn't exist yet.

- [ ] **Step 3: Implement `compute_complexity_buckets`**

Create `backend/app/services/complexity.py`:

```python
from typing import Literal

ComplexityBucket = Literal["low", "medium", "high"]


def compute_complexity_buckets(byte_counts: dict[int, int | None]) -> dict[int, ComplexityBucket | None]:
    """Bucket repos into complexity tertiles by real total code size (bytes).

    Repos with no byte count (never synced, or GitHub reports zero languages) get None --
    never a fabricated bucket. Tertiles are computed only over repos with a real byte count,
    sorted ascending (stable -- ties keep dict iteration order), split by index using integer
    division so every repo lands in exactly one bucket.
    """
    result: dict[int, ComplexityBucket | None] = {repo_id: None for repo_id in byte_counts}

    ranked = sorted(
        (repo_id for repo_id, size in byte_counts.items() if size is not None),
        key=lambda repo_id: byte_counts[repo_id],
    )
    n = len(ranked)
    low_end = n // 3
    medium_end = 2 * (n // 3)
    for index, repo_id in enumerate(ranked):
        if index < low_end:
            result[repo_id] = "low"
        elif index < medium_end:
            result[repo_id] = "medium"
        else:
            result[repo_id] = "high"
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/test_complexity.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/complexity.py backend/tests/services/test_complexity.py
git commit -m "feat: add compute_complexity_buckets pure function for real-tertile complexity"
```

---

### Task 4: Backend — expose `app_count`/`primary_language`/`complexity` on `GET /repos`, `app_count` on `PATCH`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Test: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Consumes: `compute_complexity_buckets` (Task 3).
- Produces: `RepoOut.app_count`/`primary_language`/`complexity`; `RepoPatchIn.app_count`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/api/test_repos_api.py`, add these tests (near the other `test_patch_repo_*`/`test_list_repos_*` tests):

```python
def test_patch_repo_updates_app_count():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"app_count": 4})

    assert response.status_code == 200
    assert response.json()["app_count"] == 4
    session = app.state.sessionmaker()
    repo = session.get(Repo, repo_id)
    assert repo.app_count == 4
    session.close()


def test_list_repos_exposes_primary_language_and_complexity():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    repo = Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web",
        primary_language="TypeScript", total_code_bytes=5000,
    )
    session.add(repo)
    session.commit()
    session.close()

    client = TestClient(app)
    body = client.get("/repos").json()

    assert body[0]["primary_language"] == "TypeScript"
    assert body[0]["complexity"] == "high"  # only repo with a real byte count -> lands in high


def test_list_repos_computes_complexity_against_the_full_unfiltered_repo_set():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    session.add_all([
        Repo(name="small-repo", github_url="https://github.com/acme-org/small-repo", domain="Growth", total_code_bytes=1000),
        Repo(name="medium-repo", github_url="https://github.com/acme-org/medium-repo", domain="Growth", total_code_bytes=5000),
        Repo(name="large-repo", github_url="https://github.com/acme-org/large-repo", domain="Payments", total_code_bytes=50000),
    ])
    session.commit()
    session.close()

    client = TestClient(app)
    # "large-repo" is alone in the Payments domain -- filtering must not make its complexity
    # look different than it is against the whole org.
    unfiltered = {r["name"]: r["complexity"] for r in client.get("/repos").json()}
    filtered = {r["name"]: r["complexity"] for r in client.get("/repos", params={"domain": "Payments"}).json()}

    assert filtered["large-repo"] == unfiltered["large-repo"]


def test_get_single_repo_includes_complexity():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web", total_code_bytes=5000)
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()

    client = TestClient(app)
    body = client.get(f"/repos/{repo_id}").json()

    assert body["complexity"] == "high"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/api/test_repos_api.py -v -k "app_count or complexity"`
Expected: FAIL — `RepoOut`/`RepoPatchIn` don't have these fields yet.

- [ ] **Step 3: Extend `RepoOut` and `RepoPatchIn`**

In `backend/app/schemas.py`, `RepoOut` gains three fields (insert after `e2e_test_plan_id: int | None`):

```python
    app_count: int | None
    primary_language: str | None
    complexity: Literal["low", "medium", "high"] | None
```

`RepoPatchIn` gains one field (append at the end):

```python
    app_count: int | None = None
```

- [ ] **Step 4: Wire complexity computation into `api/repos.py`**

Add the import at the top of `backend/app/api/repos.py`:

```python
from app.services.complexity import compute_complexity_buckets
```

Add a small helper right after `_aware`:

```python
def _compute_complexity_map(session: Session) -> dict[int, str | None]:
    byte_counts = dict(session.query(Repo.id, Repo.total_code_bytes).all())
    return compute_complexity_buckets(byte_counts)
```

Change `_to_repo_out`'s signature and body to accept and use a `complexity` argument:

```python
def _to_repo_out(
    repo: Repo, session: Session, checks: list[ReadinessCheck] | None = None, complexity: str | None = None,
) -> RepoOut:
```

...and in the `RepoOut(...)` construction, add (alongside the existing `dockerize_eligible`/`e2e_test_plan_id` lines):

```python
        app_count=repo.app_count,
        primary_language=repo.primary_language,
        complexity=complexity,
```

Change `list_repos` to compute the complexity map from the full, unfiltered table *before* applying the `domain` filter, and pass each repo's bucket through:

```python
@router.get("", response_model=list[RepoOut])
def list_repos(
    stage: str | None = None,
    domain: str | None = None,
    sort: str | None = None,
    session: Session = Depends(get_db),
):
    complexity_map = _compute_complexity_map(session)

    query = session.query(Repo)
    if domain is not None:
        query = query.filter(Repo.domain == domain)
    repo_rows = query.all()

    # Batch-fetch every repo's readiness checks in one query instead of one query per repo --
    # against a remote DB, N sequential round trips dominate response time (11s for 230 repos).
    checks_by_repo_id: dict[int, list[ReadinessCheck]] = defaultdict(list)
    repo_ids = [r.id for r in repo_rows]
    if repo_ids:
        for check in session.query(ReadinessCheck).filter(ReadinessCheck.repo_id.in_(repo_ids)).all():
            checks_by_repo_id[check.repo_id].append(check)

    repos = [
        _to_repo_out(r, session, checks_by_repo_id.get(r.id, []), complexity_map.get(r.id))
        for r in repo_rows
    ]

    if stage is not None:
        repos = [r for r in repos if r.current_stage == stage]

    if sort == "dwell_desc":
        repos.sort(key=lambda r: (not r.is_stuck, -(r.dwell_days or 0)))

    return repos
```

Change `get_repo`:

```python
@router.get("/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    complexity_map = _compute_complexity_map(session)
    return _to_repo_out(repo, session, complexity=complexity_map.get(repo_id))
```

In `patch_repo`, add the `app_count` handler alongside the other simple field assignments (after the `e2e_test_plan_id` block):

```python
    if body.app_count is not None:
        repo.app_count = body.app_count
```

And change the function's final two lines to include complexity in the response:

```python
    session.commit()
    complexity_map = _compute_complexity_map(session)
    return _to_repo_out(repo, session, complexity=complexity_map.get(repo_id))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: expose app_count/primary_language/complexity on GET /repos, app_count on PATCH"
```

---

### Task 5: Backend — GitHub repo rename (real, live, same-row-atomic)

**Files:**
- Modify: `backend/app/connectors/github_connector.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Test: `backend/tests/connectors/test_github_connector.py`
- Test: `backend/tests/api/test_repos_api.py`
- Test: `backend/tests/services/test_sync_service.py`

**Interfaces:**
- Produces: `rename_repo(client, org, token, current_name, new_name) -> RenamedRepoData` (in `github_connector.py`); `RepoPatchIn.new_name`; `PATCH /repos/{id}` with `new_name` set.

- [ ] **Step 1: Write the failing connector tests**

In `backend/tests/connectors/test_github_connector.py`, add `import json` near the top if not already present, then add:

```python
from app.connectors.github_connector import GitHubRepoData, RenamedRepoData, fetch_repos, rename_repo


@pytest.mark.asyncio
async def test_rename_repo_calls_the_real_rest_endpoint_and_returns_updated_name_and_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = str(request.url.path)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={
            "name": "checkout-web-v2",
            "html_url": "https://github.com/acme-org/checkout-web-v2",
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        result = await rename_repo(client, org="acme-org", token="gh-token", current_name="checkout-web", new_name="checkout-web-v2")

    assert seen["method"] == "PATCH"
    assert seen["path"] == "/repos/acme-org/checkout-web"
    assert seen["body"] == {"name": "checkout-web-v2"}
    assert result == RenamedRepoData(name="checkout-web-v2", url="https://github.com/acme-org/checkout-web-v2")


@pytest.mark.asyncio
async def test_rename_repo_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Validation Failed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await rename_repo(client, org="acme-org", token="gh-token", current_name="checkout-web", new_name="bad name")
```

Note: this replaces the existing `from app.connectors.github_connector import GitHubRepoData, fetch_repos` import line at the top of the file with the one shown above (adds `RenamedRepoData`, `rename_repo`).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/connectors/test_github_connector.py -v -k rename`
Expected: FAIL — `rename_repo`/`RenamedRepoData` don't exist yet.

- [ ] **Step 3: Implement `rename_repo`**

In `backend/app/connectors/github_connector.py`, add at the end of the file:

```python
@dataclass
class RenamedRepoData:
    name: str
    url: str


async def rename_repo(
    client: httpx.AsyncClient, org: str, token: str, current_name: str, new_name: str
) -> RenamedRepoData:
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.patch(f"/repos/{org}/{current_name}", json={"name": new_name}, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return RenamedRepoData(name=body["name"], url=body["html_url"])
```

- [ ] **Step 4: Run connector tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/connectors/test_github_connector.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing API tests**

In `backend/tests/api/test_repos_api.py`, add:

```python
def test_patch_repo_renames_the_real_github_repo_on_the_same_row(monkeypatch):
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)

    from app.connectors.github_connector import RenamedRepoData

    async def fake_rename_repo(client, org, token, current_name, new_name):
        assert current_name == "checkout-web"
        assert new_name == "checkout-web-v2"
        return RenamedRepoData(name="checkout-web-v2", url="https://github.com/acme-org/checkout-web-v2")

    monkeypatch.setattr("app.api.repos.rename_repo", fake_rename_repo)

    client = TestClient(app)
    response = client.patch(f"/repos/{repo_id}", json={"new_name": "checkout-web-v2"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "checkout-web-v2"
    assert body["id"] == repo_id  # same row, not a new repo

    session = app.state.sessionmaker()
    assert session.query(Repo).count() == 1  # no duplicate row created
    repo = session.get(Repo, repo_id)
    assert repo.name == "checkout-web-v2"
    assert repo.github_url == "https://github.com/acme-org/checkout-web-v2"
    session.close()


def test_patch_repo_502_when_github_rename_call_fails(monkeypatch):
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)

    async def failing_rename(client, org, token, current_name, new_name):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.api.repos.rename_repo", failing_rename)

    client = TestClient(app)
    response = client.patch(f"/repos/{repo_id}", json={"new_name": "checkout-web-v2"})

    assert response.status_code == 502
    session = app.state.sessionmaker()
    repo = session.get(Repo, repo_id)
    assert repo.name == "checkout-web"  # unchanged on failure
    session.close()
```

- [ ] **Step 6: Write the failing sync regression test**

In `backend/tests/services/test_sync_service.py`, add:

```python
@pytest.mark.asyncio
async def test_run_github_sync_does_not_duplicate_a_repo_that_was_renamed_via_patch(session):
    """Regression test for the rename flow's core correctness requirement: PATCH /repos/{id}
    with new_name updates Repo.name on the existing row directly (not via a sync). The next
    github sync must recognize the row by its NEW name and update it in place, not create
    a second Repo row and orphan the first one's history."""
    repo = Repo(name="checkout-web-v2", github_url="https://github.com/acme-org/checkout-web-v2")
    session.add(repo)
    session.commit()
    original_id = repo.id

    def renamed_handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "repositories(first:" in body:
            return httpx.Response(200, json={"data": {"organization": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"name": "checkout-web-v2", "url": "https://github.com/acme-org/checkout-web-v2"}],
            }}}})
        return httpx.Response(200, json={"data": {"r0": {
            "readme": {"id": "1"}, "codeowners": {"id": "2"}, "dockerfile": None,
            "branchProtectionRules": {"nodes": []},
            "primaryLanguage": {"name": "TypeScript"}, "languages": {"totalSize": 999},
        }}})

    transport = httpx.MockTransport(renamed_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert session.query(Repo).count() == 1
    repo = session.get(Repo, original_id)
    assert repo.name == "checkout-web-v2"
```

- [ ] **Step 7: Run to verify all three new tests fail**

Run: `.venv/bin/python -m pytest tests/api/test_repos_api.py tests/services/test_sync_service.py -v -k "rename or duplicate"`
Expected: FAIL — `RepoPatchIn.new_name` and `patch_repo`'s rename handling don't exist yet (the sync regression test will currently pass trivially since nothing renamed anything yet — re-check it after Step 8 too).

- [ ] **Step 8: Wire the rename flow into `RepoPatchIn` and `patch_repo`**

In `backend/app/schemas.py`, `RepoPatchIn` gains one more field (append at the end):

```python
    new_name: str | None = None
```

In `backend/app/api/repos.py`, add to the import from `app.connectors.github_connector`:

```python
from app.connectors.github_connector import rename_repo
```

In `patch_repo`, add this block after the `ado_pipeline_id` block and before `session.commit()`:

```python
    if body.new_name is not None:
        settings = request.app.state.settings
        try:
            async with httpx.AsyncClient(base_url="https://api.github.com", timeout=30.0) as client:
                renamed = await rename_repo(
                    client, org=settings.github_org, token=settings.github_token,
                    current_name=repo.name, new_name=body.new_name,
                )
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Couldn't reach GitHub")

        # Update the SAME row GitHub just renamed -- run_github_sync matches incoming repos by
        # Repo.name, so if this doesn't land on the existing row, the next sync creates a
        # duplicate Repo and orphans every readiness check/onboarding log/domain/team tied to
        # the old row's id.
        repo.name = renamed.name
        repo.github_url = renamed.url
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/api/test_repos_api.py tests/services/test_sync_service.py -v`
Expected: all PASS.

- [ ] **Step 10: Run the full backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/app/connectors/github_connector.py backend/app/schemas.py backend/app/api/repos.py backend/tests/connectors/test_github_connector.py backend/tests/api/test_repos_api.py backend/tests/services/test_sync_service.py
git commit -m "feat: rename a repo's real GitHub repository via PATCH /repos/{id}, same-row-atomic"
```

---

### Task 6: Frontend — data layer + kebab-case utility

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/lib/format.ts`
- Test: `frontend/tests/lib/format.test.ts`

**Interfaces:**
- Produces: `RepoOut.app_count?`/`primary_language?`/`complexity?`; `RepoPatchIn.app_count?`/`new_name?`; `toKebabCase(value: string): string`.

- [ ] **Step 1: Write the failing test for `toKebabCase`**

In `frontend/tests/lib/format.test.ts`, change the import line to:

```ts
import { formatDwell, STAGE_LABELS, toKebabCase } from "../../src/lib/format";
```

Then add at the end of the file:

```ts
describe("toKebabCase", () => {
  it("lowercases and hyphenates dot-separated names", () => {
    expect(toKebabCase("Ovs.Core.Models")).toBe("ovs-core-models");
  });

  it("leaves an already-kebab-case name unchanged", () => {
    expect(toKebabCase("membership-webjobs")).toBe("membership-webjobs");
  });

  it("collapses runs of non-alphanumeric characters into a single hyphen", () => {
    expect(toKebabCase("Front End__Applications")).toBe("front-end-applications");
  });

  it("trims leading and trailing hyphens", () => {
    expect(toKebabCase("--Checkout Web--")).toBe("checkout-web");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run tests/lib/format.test.ts`
Expected: FAIL — `toKebabCase` isn't exported yet.

- [ ] **Step 3: Implement `toKebabCase` and the type additions**

In `frontend/src/lib/format.ts`, add at the end of the file:

```ts
export function toKebabCase(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
```

In `frontend/src/api/types.ts`, `RepoOut` gains (after `e2e_test_plan_id?: number | null;`):

```ts
  app_count?: number | null;
  primary_language?: string | null;
  complexity?: "low" | "medium" | "high" | null;
```

`RepoPatchIn` gains (after `ado_pipeline_id?: number;`):

```ts
  app_count?: number;
  new_name?: string;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run tests/lib/format.test.ts`
Expected: all PASS.

- [ ] **Step 5: Type-check and run the full frontend suite**

Run: `npx tsc --noEmit && npx vitest run`
Expected: no type errors, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/lib/format.ts frontend/tests/lib/format.test.ts
git commit -m "feat: add app_count/primary_language/complexity types and toKebabCase util"
```

---

### Task 7: Frontend — `InventoryTable` component

**Files:**
- Create: `frontend/src/components/fleet/InventoryTable.tsx`
- Test: `frontend/tests/components/fleet/InventoryTable.test.tsx`

**Interfaces:**
- Consumes: `toKebabCase` (Task 6), `patchRepo` (`frontend/src/api/client.ts`, unchanged), `RepoOut`/`RepoPatchIn` (Task 6).
- Produces: `InventoryTable({ repos: RepoOut[]; onUpdated: (repo: RepoOut) => void })` — consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/components/fleet/InventoryTable.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InventoryTable } from "../../../src/components/fleet/InventoryTable";
import type { RepoOut } from "../../../src/api/types";

const REPO: RepoOut = {
  id: 1,
  name: "Ovs.Core.Models",
  domain: "Growth",
  team: "Growth",
  migration_wave: "migrated",
  github_url: "https://github.com/acme/Ovs.Core.Models",
  last_synced_at: null,
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
  app_count: 3,
  primary_language: "C#",
  complexity: "high",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("InventoryTable", () => {
  it("renders one row per repo with technology and complexity badges", () => {
    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);

    expect(screen.getByText("Ovs.Core.Models")).toBeInTheDocument();
    expect(screen.getByText("C#")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("defaults the rename input to the kebab-case of the current name", () => {
    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/New name for Ovs.Core.Models/i)).toHaveValue("ovs-core-models");
  });

  it("disables Apply when the rename input already matches the current name", async () => {
    const user = userEvent.setup();
    const unchanged: RepoOut = { ...REPO, name: "already-kebab-case" };
    render(<InventoryTable repos={[unchanged]} onUpdated={vi.fn()} />);

    const input = screen.getByLabelText(/New name for already-kebab-case/i);
    await user.clear(input);
    await user.type(input, "already-kebab-case");

    expect(screen.getByRole("button", { name: /apply/i })).toBeDisabled();
  });

  it("confirms before renaming, then PATCHes and updates the row on confirm", async () => {
    const user = userEvent.setup();
    const renamedRepo = { ...REPO, name: "ovs-core-models" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => renamedRepo }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onUpdated = vi.fn();

    render(<InventoryTable repos={[REPO]} onUpdated={onUpdated} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(renamedRepo));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Ovs.Core.Models"));
    expect(screen.getByText(/pipeline links re-check/i)).toBeInTheDocument();
  });

  it("does not call patchRepo when the user cancels the confirm dialog", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows an inline error when the rename PATCH fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => expect(screen.getByText(/502/)).toBeInTheDocument());
  });

  it("commits the app count on blur", async () => {
    const user = userEvent.setup();
    const updatedRepo = { ...REPO, app_count: 5 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => updatedRepo }));
    const onUpdated = vi.fn();

    render(<InventoryTable repos={[REPO]} onUpdated={onUpdated} />);
    const appsInput = screen.getByLabelText(/App count for Ovs.Core.Models/i);
    await user.clear(appsInput);
    await user.type(appsInput, "5");
    await user.tab();

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepo));
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run tests/components/fleet/InventoryTable.test.tsx`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement `InventoryTable`**

Create `frontend/src/components/fleet/InventoryTable.tsx`:

```tsx
import { useState } from "react";
import { patchRepo } from "../../api/client";
import { toKebabCase } from "../../lib/format";
import type { RepoOut } from "../../api/types";

const COMPLEXITY_COLOR: Record<string, string> = {
  low: "text-track2",
  medium: "text-gold",
  high: "text-track3",
};

function InventoryRow({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }) {
  const [newName, setNewName] = useState(toKebabCase(repo.name));
  const [appCount, setAppCount] = useState(repo.app_count != null ? String(repo.app_count) : "");
  const [renaming, setRenaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const trimmedNewName = newName.trim();
  const applyDisabled = renaming || trimmedNewName === "" || trimmedNewName === repo.name;

  async function handleRename() {
    if (applyDisabled) return;
    const confirmed = window.confirm(
      `Rename the real GitHub repository from "${repo.name}" to "${trimmedNewName}"? This is a live, hard-to-reverse action.`
    );
    if (!confirmed) return;

    setRenaming(true);
    setError(null);
    setNote(null);
    try {
      const updated = await patchRepo(repo.id, { new_name: trimmedNewName });
      onUpdated(updated);
      setNewName(toKebabCase(updated.name));
      setNote("Pipeline links re-check on the next sync.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRenaming(false);
    }
  }

  async function commitAppCount() {
    const trimmed = appCount.trim();
    if (trimmed === "") return;
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed) || parsed === repo.app_count) return;
    try {
      const updated = await patchRepo(repo.id, { app_count: parsed });
      onUpdated(updated);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <tr className="border-b border-card-border">
      <td className="p-2.5 align-top">
        <div className="text-chalk mb-1.5">{repo.name}</div>
        <div className="flex items-center gap-1.5">
          <span className="text-chalk-dimmer text-[11px]">{repo.name} →</span>
          <input
            aria-label={`New name for ${repo.name}`}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="bg-bg border border-card-border rounded px-1.5 py-0.5 text-[11px] text-chalk w-[150px]"
          />
          <button
            onClick={handleRename}
            disabled={applyDisabled}
            className="bg-gold text-bg font-semibold text-[11px] rounded px-2.5 py-0.5 disabled:opacity-40"
          >
            {renaming ? "Renaming…" : "Apply"}
          </button>
        </div>
        {note ? <div className="text-[11px] text-track2 mt-1">{note}</div> : null}
        {error ? <div className="text-[11px] text-track3 mt-1">{error}</div> : null}
      </td>
      <td className="p-2.5 align-top">
        <input
          aria-label={`App count for ${repo.name}`}
          type="number"
          value={appCount}
          onChange={(e) => setAppCount(e.target.value)}
          onBlur={commitAppCount}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          className="bg-bg border border-card-border rounded px-1.5 py-0.5 text-[13px] text-chalk w-[50px] text-center"
        />
      </td>
      <td className="p-2.5 align-top">
        <span className="bg-bg-card border border-card-border rounded px-2 py-0.5 text-[12px] text-chalk">
          {repo.primary_language ?? "—"}
        </span>
      </td>
      <td className="p-2.5 align-top">
        <span
          className={`bg-bg-card border border-card-border rounded px-2 py-0.5 text-[12px] capitalize ${
            repo.complexity ? COMPLEXITY_COLOR[repo.complexity] : "text-chalk-dimmer"
          }`}
        >
          {repo.complexity ?? "—"}
        </span>
      </td>
    </tr>
  );
}

export function InventoryTable({ repos, onUpdated }: { repos: RepoOut[]; onUpdated: (repo: RepoOut) => void }) {
  return (
    <table className="w-full border-collapse text-[12.5px]">
      <thead>
        <tr className="text-left text-chalk-dim uppercase text-[10px] tracking-wide">
          <th className="p-2.5 border-b border-card-border">Repo name</th>
          <th className="p-2.5 border-b border-card-border">Apps</th>
          <th className="p-2.5 border-b border-card-border">Technology</th>
          <th className="p-2.5 border-b border-card-border">Complexity</th>
        </tr>
      </thead>
      <tbody>
        {repos.map((repo) => (
          <InventoryRow key={repo.id} repo={repo} onUpdated={onUpdated} />
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run tests/components/fleet/InventoryTable.test.tsx`
Expected: all 7 tests PASS.

- [ ] **Step 5: Type-check**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/fleet/InventoryTable.tsx frontend/tests/components/fleet/InventoryTable.test.tsx
git commit -m "feat: add InventoryTable with inline kebab-case rename and app-count editing"
```

---

### Task 8: Frontend — Board/Inventory tab switch on `FleetPage`

**Files:**
- Modify: `frontend/src/pages/FleetPage.tsx`
- Test: `frontend/tests/pages/FleetPage.test.tsx`

**Interfaces:**
- Consumes: `InventoryTable` (Task 7).

- [ ] **Step 1: Write the failing test**

In `frontend/tests/pages/FleetPage.test.tsx`, add this test at the end of the `describe("FleetPage", ...)` block:

```tsx
  it("shows Board content by default and switches to Inventory on tab click", async () => {
    const user = userEvent.setup();
    const repos: RepoOut[] = [
      {
        id: 1,
        name: "checkout-web",
        domain: "Growth",
        team: "Growth",
        migration_wave: "not_started",
        github_url: "https://github.com/acme/checkout-web",
        last_synced_at: null,
        stages: {},
        current_stage: "standardized",
        is_stuck: false,
        dwell_days: null,
        stuck_reason: null,
        app_count: 2,
        primary_language: "TypeScript",
        complexity: "medium",
      },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => repos }));

    render(
      <MemoryRouter>
        <FleetPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Repo fleet")).toBeInTheDocument());
    expect(screen.getByText("CI/CD & environments")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /inventory/i }));

    expect(screen.queryByText("CI/CD & environments")).not.toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run tests/pages/FleetPage.test.tsx`
Expected: FAIL — no `role="tab"` elements exist yet.

- [ ] **Step 3: Implement the tab switch in `FleetPage`**

Replace the full contents of `frontend/src/pages/FleetPage.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { useRepos } from "../hooks/useRepos";
import { StatStrip } from "../components/fleet/StatStrip";
import { Legend } from "../components/fleet/Legend";
import { StuckPanel } from "../components/fleet/StuckPanel";
import { StationBoard } from "../components/fleet/StationBoard";
import { InventoryTable } from "../components/fleet/InventoryTable";
import type { RepoOut } from "../api/types";

export function FleetPage() {
  const { repos: fetchedRepos, loading, error } = useRepos();
  const [repos, setRepos] = useState<RepoOut[]>([]);
  const [stuckExpanded, setStuckExpanded] = useState(false);
  const [view, setView] = useState<"board" | "inventory">("board");

  useEffect(() => {
    setRepos(fetchedRepos);
  }, [fetchedRepos]);

  function handleRepoUpdated(updated: RepoOut) {
    setRepos((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  if (loading) {
    return (
      <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk p-8">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk p-8">
        {error}
      </div>
    );
  }

  return (
    <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Fleet
      </div>
      <h1 className="font-display text-[clamp(32px,6vw,48px)] font-extrabold tracking-tight mb-2">Repo fleet</h1>
      <p className="text-chalk-dim text-[15px] mb-8 max-w-[60ch]">
        Where every repo sits right now, and what's stuck. Click any repo for its full journey.
      </p>

      <div className="flex gap-1 border-b border-card-border mb-6" role="tablist">
        <button
          role="tab"
          aria-selected={view === "board"}
          onClick={() => setView("board")}
          className={`px-4 py-2 text-[12px] border-b-2 -mb-px ${
            view === "board" ? "border-gold text-gold" : "border-transparent text-chalk-dim"
          }`}
        >
          Board
        </button>
        <button
          role="tab"
          aria-selected={view === "inventory"}
          onClick={() => setView("inventory")}
          className={`px-4 py-2 text-[12px] border-b-2 -mb-px ${
            view === "inventory" ? "border-gold text-gold" : "border-transparent text-chalk-dim"
          }`}
        >
          Inventory
        </button>
      </div>

      {view === "board" ? (
        <>
          <StatStrip repos={repos} onToggleStuck={() => setStuckExpanded((prev) => !prev)} stuckExpanded={stuckExpanded} />
          <Legend />
          <StuckPanel repos={repos} expanded={stuckExpanded} />
          <StationBoard repos={repos} />
        </>
      ) : (
        <InventoryTable repos={repos} onUpdated={handleRepoUpdated} />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run tests/pages/FleetPage.test.tsx`
Expected: all PASS, including the pre-existing tests (Board is the default view, unaffected).

- [ ] **Step 5: Type-check and run the full frontend suite**

Run: `npx tsc --noEmit && npx vitest run`
Expected: no type errors, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/FleetPage.tsx frontend/tests/pages/FleetPage.test.tsx
git commit -m "feat: add Board/Inventory tab switch to the Fleet landing page"
```
