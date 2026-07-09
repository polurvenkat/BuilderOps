# BuilderOps Platform — Inventory Tab & GitHub Repo Rename Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-09, ready for implementation planning
**Scope:** A new "Inventory" view on the Fleet landing page showing a dense matrix (app count, technology, complexity) across all real repos, plus a way to rename a repo's underlying GitHub repository directly from that matrix. Built against the real, live BuilderOps backend/frontend (all three pillars already shipped, per `docs/superpowers/specs/2026-07-*`) — not a new pillar, a cross-cutting addition to the existing Repo Fleet experience.

**Explicitly out of scope:** any cascading fix-up of dependencies *outside* BuilderOps (other repos' READMEs, Terraform state, Slack integrations, hardcoded CI scripts elsewhere, non-GitHub-App-based/Classic ADO pipeline definitions that hardcode the repo by name). BuilderOps cannot detect or fix those; renaming here does not cascade to them. This was discussed explicitly and accepted — see §5.

## 1. Navigation: in-page tabs on the Fleet page

The Fleet page (`/`) gains a **Board / Inventory** tab switcher directly under its header, replacing the single always-visible `StationBoard`. `Board` shows exactly what's there today (`StatStrip`, `Legend`, `StuckPanel`, `StationBoard`). `Inventory` shows the new matrix (§3). This is a same-URL, client-side view switch (`useState`), not a new route — the Repos table (`/repos`) and Journey page (`/repos/:id`) are unaffected and remain reached the way they are today. No persistent global nav is introduced in this pass.

## 2. Data model (`backend/app/models.py`, `Repo`)

Three new nullable columns, all additive (same safe pattern as prior schema changes this session — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` against the real DB, no backfill needed since these are genuinely new, previously-untracked facts):

- `app_count: int | None` — manual. How many deployable applications/services live in this repo. Editable inline in the Inventory matrix and via `RepoFieldsForm` (mirrors the existing `e2e_test_plan_id` numeric-field pattern).
- `primary_language: str | None` — auto. GitHub's own primary-language classification for the repo, from GraphQL `primaryLanguage.name`.
- `total_code_bytes: int | None` — auto. Sum of `languages.edges.size` (bytes per language) from GraphQL. Used only to *derive* complexity (§4) — never shown directly in the UI.

`primary_language` and `total_code_bytes` are populated by the existing `run_github_sync` (`backend/app/services/sync_service.py`) — one additional field on the GraphQL query already fetched per repo in `_checks_query` (`backend/app/connectors/github_connector.py`), zero new API round trips. `app_count` is never touched by any sync; it's pure manual data, same lifecycle as `domain`/`team`.

## 3. Complexity is computed, not stored

No `complexity` column. `GET /repos` computes it live: sort every repo in the database with a non-null `total_code_bytes` ascending by byte count (stable sort — ties keep their query order), and bucket by index into real tertiles using integer division on the count `n`: indices `[0, n//3)` → `"low"`, `[n//3, 2*(n//3))` → `"medium"` (rounding remainder into the high bucket), `[2*(n//3), n)` → `"high"`. A repo with `total_code_bytes is None` (never synced, or GitHub reported zero languages) gets `complexity: null`, displayed as "—" not a fabricated bucket.

**Complexity is always computed against the full, unfiltered repo set — never the `?domain=`/`?stage=`-filtered result set.** Otherwise a repo's complexity bucket would shift depending on which filter happens to be active (its peer group shrinks or grows), which is confusing and not a real property of the repo. `list_repos` computes the complexity map from a separate, unfiltered query before applying `domain`/`stage` filtering to the response.

This mirrors the existing pattern of computing `current_stage`/`is_stuck`/`dwell_days` live from stored facts rather than storing a derived value (`backend/app/services/stage.py`) — it self-calibrates as the real repo set changes instead of going stale. A new pure function `compute_complexity_buckets(byte_counts: dict[int, int | None]) -> dict[int, Literal["low","medium","high"] | None]` in a new `backend/app/services/complexity.py`, unit-testable in isolation (tertile edge cases: fewer than 3 repos with real byte counts, ties, all-None).

## 4. API changes

`RepoOut` (`backend/app/schemas.py`) gains: `app_count: int | None`, `primary_language: str | None`, `complexity: Literal["low", "medium", "high"] | None`. Populated in `_to_repo_out` (`backend/app/api/repos.py`) using the complexity map computed once per `GET /repos` call (not per-repo — same batch-first discipline as the readiness-check N+1 fix earlier this session; complexity must be computed from the *whole* result set in one pass, not recomputed or mismatched per row).

`RepoPatchIn` gains two new optional fields:
- `app_count: int | None` — plain field update, same as any other manual field in `patch_repo` today.
- `new_name: str | None` — triggers the GitHub rename flow (§5). Mutually independent of `app_count`; a single PATCH request may set either, both, or neither, following the existing "only touch what's present" convention already used for every other `RepoPatchIn` field.

## 5. GitHub rename: real, live, and safe against our own sync

When `body.new_name is not None` in `patch_repo`:

1. Call GitHub's real rename API (`PATCH /repos/{owner}/{repo}` REST endpoint, `{"name": new_name}`) using the existing `settings.github_token`/`settings.github_org`, via a new `rename_repo(client, org, token, current_name, new_name) -> RenamedRepoData` in `backend/app/connectors/github_connector.py` (returns the real `name` and `html_url` GitHub reports back — never assume the request body's `new_name` was applied verbatim; GitHub may normalize it).
2. On success: update `repo.name` and `repo.github_url` on **the same existing row**, in the same request, using GitHub's returned values. This is the one non-negotiable correctness requirement of this feature: `run_github_sync` matches incoming repos by `Repo.name` (`backend/app/services/sync_service.py`). If the rename doesn't update this row atomically, the next `github` sync will fail to find a match on the new name and **create a duplicate `Repo` row**, orphaning every readiness check, onboarding log, domain/team assignment, and `app_count`/pipeline link tied to the old row's ID. All of that data is keyed by `repo.id`, which is untouched by this flow — so as long as the update lands on the existing row, nothing is lost.
3. On GitHub API failure: `HTTPException(502, "Couldn't reach GitHub")`, matching the existing `ado_pipeline_id`/`pipeline-status` failure pattern — no partial state (the row is never updated if the GitHub call itself failed).
4. **Pipeline links are not actively re-matched by this endpoint.** A `PipelineLink` with `source == "manual"` is keyed by ADO pipeline ID, not name — entirely unaffected by a repo rename. A `PipelineLink` with `source == "auto"` will be re-evaluated on the next `POST /sync/ado-pipelines` run using the new `repo.name`; if ADO's GitHub service-connection tracks the repo by an internal ID (typical for the GitHub App integration), it self-heals automatically. If it doesn't (e.g. a Classic-editor pipeline hardcoding the old name), the repo will show "not connected" until manually re-linked via the existing reconnect flow (`RepoFieldsForm`'s `ado_pipeline_id` field, built earlier this session) — this is a real, accepted residual risk, not something this feature can eliminate, and the UI is explicit about it (§6).

## 6. Frontend: Inventory matrix (`frontend/src/pages/FleetPage.tsx` + new `frontend/src/components/fleet/InventoryTable.tsx`)

Per the approved mockup: a dense table, one row per repo — Name (with inline rename control), Apps (editable number), Technology (read-only badge, `primary_language` or "—"), Complexity (read-only badge, `complexity` or "—", color-coded low=track2/medium=gold/high=track3 matching the existing palette's severity convention).

**Rename control** (inline under the repo name, exactly as mocked): the current name (dim, static) → an editable text input, defaulting to the kebab-case transform of the current name (`toKebabCase(repo.name)`, a small pure function: lowercase, replace runs of non-alphanumeric characters with a single hyphen, trim leading/trailing hyphens) → an "Apply" button. Apply is disabled when the input's trimmed value equals the current name (nothing to do). Clicking Apply shows a native `window.confirm` ("Rename the real GitHub repository from "X" to "Y"? This is a live, hard-to-reverse action.") before calling `patchRepo(id, { new_name })` — this is a real, external, hard-to-reverse action, and the confirm step is a deliberate addition beyond the approved mockup's bare button, consistent with how this session treats every other risky action. On success, the row updates in place (new name becomes the static label, input resets to the new kebab-case default) and a small inline note appears: "Pipeline links re-check on the next sync." On failure (502), an inline error message under that row, matching `RepoFieldsForm`'s existing `error` state pattern.

**Apps** input: same optimistic-PATCH-on-blur-or-Enter pattern as a plain number field, calling `patchRepo(id, { app_count })`.

`frontend/src/api/types.ts`: `RepoOut` gains `app_count: number | null`, `primary_language: string | null`, `complexity: "low" | "medium" | "high" | null`. `RepoPatchIn` gains `app_count?: number`, `new_name?: string`.

## 7. Testing

Backend: `compute_complexity_buckets` unit tests (tertile boundaries, <3 repos, all-None, ties) in isolation; `run_github_sync` test extended to assert `primary_language`/`total_code_bytes` populate from a GraphQL fixture that includes those fields; `patch_repo` tests for `app_count` (plain field, mirrors existing `e2e_test_plan_id` test) and `new_name` (success path asserts same-row update via a mocked `rename_repo`, 502 path via a failing mock, **and a regression test asserting a subsequent `run_github_sync` against the new name does NOT create a second `Repo` row** — this is the one test that directly guards the correctness requirement in §5.2).

Frontend: `InventoryTable` tests for the kebab-case default, Apply-disabled-when-unchanged, the confirm-then-PATCH flow (mocking `window.confirm`), and the inline success/error states. Existing `FleetPage` tests extended to cover the Board/Inventory tab switch.

## 8. Out of scope

- Auto-detecting `app_count` from repo structure (e.g. counting Dockerfiles or deployable manifests) — stays manual, per §2, no signal decided for this yet.
- Overriding computed `complexity` manually — stays purely computed for this pass.
- Any cascading fix of external, non-BuilderOps dependencies on the old repo name (see "Explicitly out of scope" above).
- Bulk/multi-repo rename — one row, one rename, one confirm, at a time.
