# BuilderOps Platform — Phase 0: CI/CD & Lower Environments Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-08, ready for implementation planning
**Scope:** Second sub-project of the BuilderOps platform. Covers the CI/CD & Lower Environments pillar's first phase: pipeline inventory, gate *visibility* (not policy/enforcement), Dockerized detection, and the **Piped** journey stage going live end-to-end. Self-service environment provisioning — the pillar's one write/execute component — is deferred to a distinct future Phase 2; gate *policy*/enforcement and pipeline-template rollout are also future work, not yet assigned a phase number (see [Future Phases](#10-future-phases)).

## 1. Vision

Repos now live on GitHub, but their build/deploy pipelines live on Azure DevOps — teams are actively converting from classic Release pipelines to YAML build-and-release pipelines defined in-repo. This phase answers, for any repo, "is it piped to Azure DevOps yet, and where is its latest run right now?" — extending the same journey the Repo Standardization pillar already ships, without introducing any new internal terminology. The **Piped** stage (already present in the UI as a permanently-locked placeholder) goes live for the first time.

## 2. Team & program context

- CI/CD & Lower Environments is owned by Luke's group. It depends on Repo Standardization (standardized repos are easier to pipeline) and itself feeds into E2E & Load Testing (owned by Jiju + 2-3 engineers) for gate data — a planned sequencing fact, not slippage.
- End state (full pillar, not this phase): standardized pipeline templates with built-in gates (security scans, test thresholds, approvals), self-service on-demand QA/UAT provisioning, and a clear dev→qa→uat→prod promotion path with gate visibility.
- This phase builds only the read-only inventory + live status layer. The write/execute self-service provisioning component is a distinct future phase with its own permission boundary — never bundled into this one.

## 3. Scope for this spec

**In scope:**
- A new Azure Pipelines connector (scheduled sync) that discovers each repo's linked ADO pipeline and its classic-vs-YAML migration status.
- Gate *visibility*: a scheduled-sync check that observes whether each environment (specifically UAT and Prod) has an approval/check configured in ADO — observation only, no policy definition or enforcement.
- Dockerized detection: auto file-presence check (extends the existing GitHub connector) plus a manual eligibility flag, combined into one derived readiness check.
- ACA deployment detection is modeled in the data now (so no future schema change is needed) but ships honestly as `unknown` — the repo↔ACA-resource mapping method is still undecided (see [Open Questions](#9-open-questions-carried-over-still-unresolved-not-blocking-this-phase)).
- Auto-detected readiness checks (`pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca`) that power the **Piped** stage in both the Fleet page and the Repos table, using the exact same `ReadinessCheck` model Track 1 already uses — no schema redesign.
- A live-query endpoint, called only from the Repo Journey detail page, that fetches the latest pipeline run's stage-by-stage status (Build → DEV → QA → UAT → Prod) plus any pending approval, directly from ADO — never persisted.
- Journey page UI: the Piped `StationCard` goes live, a new stage-breakdown panel renders the live data, the convergence diagram's pipeline line gets real progress, and the stale "GitHub Actions" copy is corrected to reflect the actual Azure Pipelines flow.

**Explicitly out of scope (future work, see [Future Phases](#10-future-phases)):**
- Self-service QA/UAT environment provisioning — the platform's one write/execute, high-blast-radius component, explicitly deferred to **Phase 2**, with its own permission boundary when it's built (per the original program-management note). This is the only piece of the pillar's end state pushed to a distinct, named later phase.
- Gate *policy* — defining what gates *should* exist, enforcing thresholds. This phase only *observes* whatever ADO already reports; it does not evaluate that against a standard. Not yet assigned a phase number.
- Pipeline template standardization and the rollout tooling that migrates teams onto it. Not yet assigned a phase number.
- Environment/approval detection for repos whose pipeline doesn't follow the golden-path stage-naming shape — these degrade gracefully to `unknown`, they aren't specially handled.

**Deliberate design choice:** exactly like Track 1's Piped/Tested placeholders before this phase, repos whose pipeline shape doesn't match the detected pattern, or whose ACA mapping can't be resolved, don't error or hide — they render `pending_convention`/`unknown` the same way `naming_standardized` does today, distinguished from `fail` everywhere in the UI.

## 4. Architecture

### Two data-freshness tiers

This phase deliberately splits data into scheduled-sync (cheap, changes rarely) and live-query (freshness matters, fetched on demand) — carrying forward the freshness/architecture direction already set for this pillar, now made concrete:

- **Scheduled sync** (extends the existing Track 1 sync job): discovers the repo↔pipeline *link* and the classic-vs-YAML *migration status*. Both change infrequently, so they're synced on the same cadence as other structural checks and stored in Postgres. This is what powers the Fleet page and the Repos table — neither page pays any ADO API latency at page-load time.
- **Live query** (new, on-demand): the current run's stage-by-stage status and any pending approval. This changes constantly and staleness would be actively misleading, so it is fetched fresh, exactly when — and only when — a user opens that one repo's Journey page. The Fleet page and Repos table, which can render hundreds of repos in one view, never trigger a live ADO call; only the single-repo detail view does, so there is no batching/rate-limit exposure to design around.

### New connector

`backend/app/connectors/ado_pipelines_connector.py`, reusing the existing `ado_org` / `ado_project` / `ado_pat` config from Key Vault (same credential, same pattern as `ado_connector.py` — no new secret, no new auth code path):

- `fetch_pipeline_links(client, org, project, pat)` — lists pipelines in the project via the ADO Pipelines API; for each, reads `configuration.repository.url` and `configuration.type` (`"yaml"` for YAML pipelines). Returns one record per pipeline: `(pipeline_id, pipeline_name, repository_url, is_yaml)`.
- `fetch_release_definitions(client, org, project, pat)` — lists classic Release definitions via the separate Release Management API. Classic release pipelines are not a flag on the same object as YAML pipelines — they live in an entirely different API — so this call is what lets the sync distinguish "no pipeline at all" from "pipeline exists but hasn't migrated to YAML yet."
- `fetch_pipeline_run_status(client, org, project, pat, pipeline_id)` — hits the Timeline API for the pipeline's latest run, returning an ordered list of stages with `name`, `status` (`succeeded` / `in_progress` / `waiting_approval` / `not_started` / `failed`), and, when applicable, a pending-approval description. Used only by the live-query endpoint, never by the scheduled sync.
- `fetch_environment_checks(client, org, project, pat, environment_names)` — for each named ADO Environment (matched from the pipeline's stage names, e.g. a "UAT Deployment" stage implies an environment named/related to "uat"), calls the Environments Checks API and returns whether at least one check/approval is configured. Used by the scheduled sync (gate configuration changes rarely, unlike run status) to populate `environment_gates_configured`.

### GitHub connector extension

The existing GitHub connector's batched file-presence query (already used for `readme_present`/`codeowners_assigned`) gains one more aliased path per repo: `Dockerfile` at the repo root. This is a one-line addition to an existing batched GraphQL query, not a new connector or new API call pattern — it populates `dockerfile_present`.

### Azure Resource Graph connector — still not built

Per the deliberate "ships as unknown" decision for `deployed_aca`, no Resource Graph query is implemented in this phase. Building it without a resolved repo↔ACA mapping method would mean guessing at a detection method Track 1's spec already flagged as an open question — building the connector is deferred until that mapping decision is made, not until some later "phase" per se; it can be added the moment the mapping question resolves, independent of Phase 2's provisioning work.

### Repo ↔ pipeline matching

The sync matches each `Repo.github_url` against the `repository_url` returned by `fetch_pipeline_links`. A match creates/updates a `PipelineLink` row. No match means the repo has no row — read as "not linked" everywhere downstream, the same absence-means-not-yet-true convention `ReadinessCheck` already uses.

## 5. Data model

- **PipelineLink** (new table): `repo_id`, `ado_pipeline_id`, `ado_pipeline_name`, `is_yaml`, `last_synced_at`. One row per repo with a matched pipeline; repos without a match have no row.
- **Repo** (existing table, one new manually-set field): `dockerize_eligible` (nullable bool, manual, `PATCH`-able — defaults to unset/`null`, meaning "not yet assessed," distinct from `false` meaning "assessed, not eligible").
- **ReadinessCheck** (existing table, five new `stage_key` values under the Piped card — no schema change):
  - `pipeline_linked` — `pass` if a `PipelineLink` row exists for the repo, else `fail`.
  - `pipeline_is_yaml` — `pass` if the linked pipeline's `is_yaml` is true; `fail` if a classic Release definition was found instead; `unknown` if neither a YAML pipeline nor a classic definition could be matched (shouldn't happen if `pipeline_linked` passed, but modeled defensively).
  - `environment_gates_configured` — `pass` if both the UAT and Prod environments (matched from stage names) have at least one check/approval configured; `fail` if either is missing one; `unknown` if the UAT/Prod stages themselves couldn't be matched (e.g. non-standard pipeline shape). `detail` carries the full per-environment breakdown, e.g. `{"dev": false, "qa": false, "uat": true, "prod": true}`, so the UI can show which specific environment is ungated even though dev/qa don't affect pass/fail.
  - `dockerized` — derived, not a raw signal: `pass` if `dockerize_eligible` is `false` or `null` (not applicable / not yet assessed), or if `dockerize_eligible` is `true` and a Dockerfile was found; `fail` only when `dockerize_eligible` is `true` and no Dockerfile exists. `detail` carries both raw inputs: `{"eligible": true, "dockerfile_present": false}`.
  - `deployed_aca` — ships as `unknown` for every repo in this phase (see [Open Questions](#9-open-questions-carried-over-still-unresolved-not-blocking-this-phase)). Modeled now so the eventual Resource Graph connector needs no schema change, only a code path that starts producing real `pass`/`fail` values.
- **Current stage (derived, extends the existing rule):** Phase 0 clamped stage derivation at Standardized because Piped had zero real `ReadinessCheck` rows. This phase removes that clamp one stage further: a repo that clears every Standardized check and every *blocking* Piped check (`pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized` — `deployed_aca` is non-blocking, same `pending_convention`-style treatment as `naming_standardized`) now derives to `"piped"` as a real, non-fictitious stage. Tested and Paved Road remain clamped — still no real data behind them.
- **No new table for live run status.** It is fetched and returned directly by the API layer; it is never written to Postgres, per the live-query design above.

### Stage keys, Piped card (supersedes the "future phase" placeholder row in the Track 1 spec)

| Card | `stage_key` values | Source |
|---|---|---|
| **Piped** | `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized` (blocking), `deployed_aca` (non-blocking, ships as `unknown` this phase) | Auto (Azure Pipelines + GitHub connectors, scheduled sync); `dockerized` additionally depends on the manual `dockerize_eligible` flag; `deployed_aca` pending the ACA↔repo mapping decision |
| **Piped — live run status** *(not a `ReadinessCheck`, not stored)* | per-stage status for Build/DEV/QA/UAT/Prod + pending approval | Auto (Azure Pipelines connector, live query, Journey page only) |

## 6. API surface (new)

- `GET /repos/{id}/pipeline-status` — live, on-demand. Calls `fetch_pipeline_run_status` against the repo's linked pipeline (404/empty response if `pipeline_linked` is `fail`) and returns the current run's stage breakdown. Not cached, not persisted — every call hits ADO fresh. Only ever invoked by the Journey page, one repo at a time.
- `PATCH /repos/{id}` gains one more optional field: `dockerize_eligible` (bool), alongside the existing `domain`/`team`/`migration_wave` fields it already supports — same endpoint, same manual-field-editing form on the Journey page (§8.1), no new endpoint needed.
- No other change to `GET /repos` response shape beyond the five new entries appearing in each repo's `stages` dict, and `current_stage` now being able to return `"piped"`.

## 7. Error handling & sync strategy

Follows the same pattern already established for Track 1's sync (see that spec's §6), extended to the new connector:

- The pipeline-link/migration-status sync runs as part of the existing scheduled `SyncRun` job; a failure leaves the previous run's `PipelineLink`/`ReadinessCheck` data intact and stale-but-served, with the same "ADO Pipelines sync failing since Xh ago" staleness banner pattern.
- The live-query endpoint has no fallback-to-stale-data option by design — if the ADO call fails or times out, the Journey page's pipeline panel shows an explicit error state ("Couldn't reach Azure DevOps — try again"), never silently stale data, since the entire reason this path is live rather than synced is that staleness here would be actively misleading.
- Same known v1 limitation as Track 1's connector: no fine-grained per-repo failure isolation within one sync batch. Accepted for the same reason (batched-query architecture), revisit together if ever addressed.

## 8. UI design

All under the existing "journey" framing — no new internal terminology introduced by this phase.

### 8.1 Repo Journey page changes

- **Piped `StationCard`** stops being permanently `Locked`. Once `pipeline_linked` passes, its badge reflects real state (`You are here` while mid-flight, waiting on approval, or blocked by a failing Piped check; `Cleared` once fully through Prod with every blocking check passing; `Locked` still shown — with the existing "Not live yet" copy — only for repos with no pipeline link at all). Its description copy changes from the stale *"GitHub Actions are wired up for every environment and verified working"* to accurately describe the Azure Pipelines YAML flow. Its mini checklist shows all five sub-checks (`pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca`) exactly like Standardized's checklist shows its sub-checks today — `deployed_aca` renders with the same pending/unknown treatment `naming_standardized` already uses, so it reads as "not yet knowable," never as a failure.
- **`RepoFieldsForm` gains a `dockerize_eligible` control** (a checkbox/toggle, since it's a tri-state-adjacent bool: unset/true/false) alongside the existing domain/team/migration_wave fields — same form, same `PATCH /repos/{id}` call, no new component.
- **New live stage-breakdown panel**, positioned the same way `OnboardingLog` sits below `RepoFieldsForm` today: renders `GET /repos/{id}/pipeline-status` as an ordered row of stages (Build → DEV → QA → UAT → Prod) with per-stage status, and a called-out banner when a stage is waiting on an approval — directly modeled on the real ADO run view. Rendered only when `pipeline_linked` passes; otherwise this panel doesn't render at all (nothing to show yet).
- **`ConvergenceDiagram`'s `pipelineProgress` prop** (currently hardcoded `0` in `JourneyPage.tsx`) is wired to real data: fraction of the live run's environments (DEV/QA/UAT/Prod) currently `succeeded`, giving the teal Pipeline line real forward motion for the first time.

### 8.2 Fleet page & Repos table changes

No structural UI change — both already render whatever `stages` and `current_stage` the API returns. Their behavior simply changes because the data does:
- The Piped column in the Fleet page's station board stops being a permanent empty-state placeholder once any repo actually derives to `current_stage: "piped"`.
- The Repos table gains five more check-status columns (`pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca`), consistent with how the existing six Standardized-card checks are already rendered there.
- Neither page issues any live ADO call — they only ever read the synced `stages` data, per the architecture split in §4.

## 9. Open questions (carried over, still unresolved — not blocking this phase)

1. **ACA ↔ repo mapping** — naming convention or resource tag? Deliberately left unresolved this phase; `deployed_aca` ships as `unknown` until this is decided, at which point only the Resource Graph connector needs building — no further schema or spec change (see §5).
2. **Repo naming convention** — still not defined by BuilderOps. Unrelated to this phase's checks, but still blocks `naming_standardized` on the Standardized card.
3. **Golden-path pipeline shape's universality** — confirmed as of this spec that the "Build → DEV/QA/UAT/Prod Deployment" stage-naming + ADO Environment approvals shape is the standard across (most) repos being migrated. If that turns out to be less universal once implementation starts surfacing real data, the stage-name-matching logic in `fetch_pipeline_run_status` and `fetch_environment_checks` may need to become more tolerant — flagged here so a future revision isn't a surprise.

## 10. Future phases

- **Phase 2 — Self-service QA/UAT provisioning** (own spec): the pillar's write/execute, high-blast-radius component — on-demand environment creation, needs its own permission boundary/allowlisting before any design work starts. This is the only major piece of the CI/CD & Lower Environments pillar not covered by this phase.
- **Gate *policy* & enforcement**: defining what gates *should* exist per environment (security scans, test thresholds, approvals) and surfacing compliance against that policy — this phase only observes whatever gates already exist (`environment_gates_configured`), it doesn't evaluate them against a standard or enforce anything.
- **Pipeline template standardization & rollout**: migrating teams from ad hoc YAML onto a shared template, mirroring how Repo Standardization's golden-path doc drives that pillar.
- **E2E & Load Testing** (own spec, separate pillar): powers the **Tested** card; once built, its results are expected to annotate onto this pillar's environment-gate nodes (e.g., the QA stage showing "gated by: E2E pass rate 94%") rather than appending as a separate linear stage after Piped — a cross-cutting fact carried over from the original brainstorm, not yet designed in detail.
