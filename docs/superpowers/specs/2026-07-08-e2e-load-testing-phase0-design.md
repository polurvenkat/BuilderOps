# BuilderOps Platform — Phase 0: E2E & Load Testing Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-08, ready for implementation planning
**Scope:** Third sub-project of the BuilderOps platform. Covers the E2E & Load Testing pillar's first phase: a manual mapping from each app repo to the Azure Test Plan representing its E2E coverage, a scheduled connector that reads the latest test-run outcome from that plan, and the **Tested** journey stage going live for the one signal that's real and standardized today — E2E coverage. Unit/integration test tracking and load testing are modeled in the data now but ship as honestly unresolved (`pending_convention`/`unknown`) this phase; on-platform load-test execution and gate-annotation into Track 2 are future work, not yet assigned a phase number (see [Future Phases](#9-future-phases)).

## 1. Vision

Repo Standardization and CI/CD & Lower Environments both now report real, live data. This phase answers, for any repo, "is it covered by end-to-end tests, and are they passing?" — extending the same journey those two pillars already ship, without introducing any new internal terminology. The **Tested** stage (already present in the UI as a permanently-locked placeholder) goes live for the first time.

Load testing infrastructure doesn't officially exist as an org-wide practice yet — teams lean on Azure Load Testing directly today, and a future phase may add on-platform load-test execution. E2E testing is further along: teams are standing up dedicated E2E test repos (commonly one E2E repo covering several app repos) and tracking results in Azure Test Plans. This phase builds only what that real infrastructure supports.

## 2. Team & program context

- E2E & Load Testing is owned by Jiju's group (lead + 2-3 engineers). It depends on Repo Standardization and CI/CD & Lower Environments (an app needs to exist and be pipelined before its tests mean much), and its results are meant to feed into Track 2's CI/CD gates as annotations — a planned sequencing fact, not slippage.
- End state (full pillar, not this phase): centralized E2E test suites covering critical user journeys across products, load testing baked into the release cycle rather than a pre-launch scramble, and results plugging directly into Track 2's gate visibility.
- This phase builds only the read-only E2E-coverage inventory layer. Load-test execution and any write/execute component are distinct future phases with their own permission boundary, never bundled into this one.

## 3. Scope for this spec

**In scope:**
- A manual mapping from an app repo to the Azure Test Plan that represents its E2E coverage: `Repo.e2e_test_plan_id`. Manual because one E2E repo commonly covers many app repos and no auto-derivable link exists yet — the same "no existing source of truth" rationale that made `domain` a manual field in Track 1.
- A new Azure Test Plans connector (scheduled sync) that fetches the latest completed test run for a mapped Test Plan and reports its pass/fail counts.
- An `e2e_covered` readiness check, computed from that connector data: `pending_convention` when no Test Plan is mapped (the common case today), `unknown` when mapped but no completed run exists yet, `pass`/`fail` based on the latest run's outcome once real data exists.
- `unit_tested` and `integration_tested` readiness checks, modeled now so no future schema change is needed, shipping unconditionally as `pending_convention` this phase — confirmed that no standard location for either exists yet (varies by team), the same "can't auto-detect what hasn't been standardized" situation Track 1 hit with naming and environment/quality-gate detection.
- A `load_tested` readiness check, shipping unconditionally as `unknown` this phase — Azure Load Testing is a real tool teams use, but results aren't organized in any repo-queryable way yet, and no connector to it is built this phase (mirrors Track 2's deliberate `deployed_aca`-ships-as-unknown decision).
- The **Tested** stage becoming reachable: blocked only by `e2e_covered` (the one resolved signal); `unit_tested`/`integration_tested`/`load_tested` are non-blocking, the same treatment `naming_standardized` and `deployed_aca` already get.

**Explicitly out of scope (future work, see [Future Phases](#9-future-phases)):**
- On-platform load-test execution — the pillar's one write/execute, high-blast-radius component, explicitly deferred, mirroring how Track 2 deferred self-service QA/UAT provisioning.
- Any unit/integration test connector — blocked on BuilderOps and teams standardizing where those results live, not a platform gap.
- Any Azure Load Testing connector — blocked on load-test results being organized in a way that maps to a repo at all.
- Release-level correlation between a specific pipeline run/deployment and a specific test run — confirmed unresolved in Azure Test Plans today. This phase reports the Test Plan's latest completed run, not a per-deployment join.
- Wiring `e2e_covered` (or any of the other three checks) into Track 2's environment-gate nodes as a "gated by: E2E pass rate 94%" annotation — cross-cutting future work once both pillars have enough real data to connect meaningfully.
- Auto-deriving the E2E-repo↔app-repo mapping (e.g. from a manifest file committed in the E2E repo) instead of a manual assignment.

**Deliberate design choice:** exactly like `naming_standardized` and `deployed_aca` before it, a repo with no Test Plan mapped yet doesn't error or read as a compliance failure — it renders `pending_convention`, distinguished from `fail` everywhere in the UI. Most repos will be in this state at launch, since E2E coverage is being rolled out incrementally (Track 3's own first milestone is identifying which critical paths to cover first) rather than expected everywhere on day one.

## 4. Architecture

### Single data-freshness tier this phase

Unlike Track 2, this phase needs no live-query tier: Azure Test Plans test-run freshness doesn't demand on-demand querying the way an in-flight pipeline run's stage status did. Everything here is scheduled-sync, stored in Postgres, same tier as Track 1's checks and most of Track 2's.

### New connector

`backend/app/connectors/ado_test_plans_connector.py`, reusing the existing `ado_org`/`ado_project`/`ado_pat` config from Key Vault — same credential, same pattern as `ado_connector.py`/`ado_pipelines_connector.py`, no new secret:

- `fetch_test_plan_latest_run(client, org, project, pat, test_plan_id)` — lists test runs for the given plan via the Azure Test Results API, picks the most recently completed run, and returns its pass/fail/total counts and completion date. Returns `None` if the plan has no completed runs yet.

### No new table

Unlike `PipelineLink` (which exists because Track 2's connector *auto-discovers* the repo↔pipeline link and a live endpoint needs a fast lookup by `repo_id`), the app-repo↔Test-Plan link here is manually asserted and there's no live endpoint needing a fast join. It's therefore just one new nullable column on the existing `Repo` table, and the fetched result is stored the same way `branch_protection`'s reviewer count and `environment_gates_configured`'s per-environment breakdown already are — as `detail` JSON on the `ReadinessCheck` row itself. No new table, no schema redesign beyond one column.

## 5. Data model

- **Repo** (existing table, one new manually-set field): `e2e_test_plan_id` (nullable int, manual, `PATCH`-able — defaults to unset/`null`, meaning "no Test Plan mapped yet," distinct from a real plan ID meaning "this is the plan that represents this repo's E2E coverage").
- **ReadinessCheck** (existing table, four new `stage_key` values under the Tested card — no schema change):
  - `e2e_covered` — `pending_convention` if `e2e_test_plan_id` is unset; `unknown` if set but the connector finds no completed run yet; `pass` if the latest completed run has zero failures; `fail` if it has one or more. `detail` carries `{"test_plan_id": ..., "passed_count": ..., "failed_count": ..., "total_count": ..., "completed_date": ...}` once a run exists, else `null`.
  - `unit_tested` — ships as `pending_convention` for every repo this phase (no standard test-plan/location convention exists yet for unit tests).
  - `integration_tested` — ships as `pending_convention` for every repo this phase (same reason, confirmed to vary by team).
  - `load_tested` — ships as `unknown` for every repo this phase (see [Open Questions](#8-open-questions-carried-over-not-blocking-this-phase)). Modeled now so a future Azure Load Testing connector needs no schema change, only a code path that starts producing real `pass`/`fail` values.
- **Current stage (derived, extends the existing rule):** `STAGE_ORDER` gains a fourth entry, `("tested", ["e2e_covered"])`, appended after `"piped"`. Only `e2e_covered` is a blocking key; `unit_tested`/`integration_tested`/`load_tested` are deliberately excluded, the same non-blocking treatment `naming_standardized`/`deployed_aca` already get. The existing generalized clamp (`STAGE_ORDER[-1][0]`, introduced in Track 2) needs no further change — a repo clearing every check now derives all the way to `"tested"` automatically.

### Stage keys, Tested card (supersedes the "future phase" placeholder row in the Track 1/Track 2 specs)

| Card | `stage_key` values | Source |
|---|---|---|
| **Tested** | `e2e_covered` (blocking), `unit_tested`, `integration_tested`, `load_tested` (all non-blocking, ship as `pending_convention`/`unknown` this phase) | `e2e_covered`: Auto (Azure Test Plans connector, scheduled sync), depends on the manual `e2e_test_plan_id` mapping; the other three: pending future connectors/conventions |

## 6. API surface (new)

- `PATCH /repos/{id}` gains one more optional field: `e2e_test_plan_id` (int), alongside the existing `domain`/`team`/`migration_wave`/`dockerize_eligible` fields it already supports — same endpoint, same manual-field-editing form on the Journey page, no new endpoint needed. Writes straight through with no immediate readiness-check recompute (the check refreshes on the next scheduled sync, same latency-acceptance already established for `dockerize_eligible`).
- `POST /sync/test-plans` — new trigger endpoint, same synchronous-v1-simplification pattern as `/sync/github`, `/sync/ado`, and `/sync/ado-pipelines`.
- `GET /sync/status` gains a fourth key, `"test_plans"`, alongside `"github"`/`"ado"`/`"ado_pipelines"`.
- No other change to `GET /repos` response shape beyond the four new entries appearing in each repo's `stages` dict, and `current_stage` now being able to return `"tested"`.

## 7. Error handling & sync strategy

Follows the same pattern already established for Track 1's and Track 2's syncs:

- The Test Plans sync runs as part of the existing scheduled job pattern, on the same 4-hour cadence as `github_sync`/`ado_pipelines_sync`; a failure leaves the previous run's `e2e_covered` (and other Tested-card) `ReadinessCheck` data intact and stale-but-served, with the same staleness-banner pattern the other two connectors already use.
- No live-query endpoint exists this phase, so there's no "hard-fail, never stale" path to design for here — unlike Track 2's pipeline-status endpoint, everything on the Tested card degrades gracefully to stale-but-served on a sync failure, same as Track 1's checks.
- Same known v1 limitation as the other two connectors: no fine-grained per-repo failure isolation within one sync batch. Accepted for the same reason (batched architecture), revisit together if ever addressed.

## 8. UI design

All under the existing "journey" framing — no new internal terminology introduced by this phase.

### 8.1 Repo Journey page changes

- **Tested `StationCard`** stops being permanently `Locked`. Once `e2e_test_plan_id` is set, its badge reflects real state (`You are here` while failing, `Cleared` once the latest run passes with zero failures; `Locked` — with "Not live yet" copy — still shown only for repos with no Test Plan mapped at all). Its mini checklist shows all four sub-checks (`e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`) exactly like Piped's checklist shows its five — the three unresolved ones render with the same "not yet knowable" pending/unknown treatment `naming_standardized`/`deployed_aca` already use.
- **`RepoFieldsForm` gains an `e2e_test_plan_id` control** (a numeric input) alongside the existing domain/team/migration_wave/dockerize_eligible fields — same form, same `PATCH /repos/{id}` call, no new component.
- No new live-data panel this phase (unlike Piped) — there's no live-query endpoint to render.

### 8.2 Fleet page & Repos table changes

No structural UI change — both already render whatever `stages` and `current_stage` the API returns, exactly as every prior phase has been:
- The Tested column in the Fleet page's station board stops being a permanent empty-state placeholder once any repo actually derives to `current_stage: "tested"`.
- The Repos table gains four more check-status columns (`e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`), consistent with how the Standardized and Piped cards' checks are already rendered there.

## 9. Open questions (carried over, not blocking this phase)

1. **Unit/integration test location convention** — confirmed unresolved, varies by team. `unit_tested`/`integration_tested` ship as `pending_convention` until BuilderOps and teams settle on where those results should live.
2. **Build↔test-run correlation** — confirmed not established in Azure Test Plans today. `e2e_covered` reports the mapped plan's latest completed run rather than a specific deployment's results; revisit if Azure Test Plans (or org process) ever supports this join.
3. **Should the E2E-repo↔app-repo mapping become auto-derivable?** Currently manual (e.g. a manifest file committed in the E2E repo is one option raised, not committed to). Revisit once enough mappings exist to judge whether the manual burden is worth automating.
4. **How could Azure Load Testing results eventually be organized/queried per repo?** Unresolved; `load_tested` ships as `unknown` until this is decided, at which point only a new connector needs building — no further schema change (see §5).

## 10. Future phases

- **On-platform load-test execution** (own spec, own phase number): the pillar's write/execute, high-blast-radius component — needs its own permission boundary/allowlisting before any design work starts, mirroring Track 2's deferred self-service provisioning phase.
- **Unit/integration test connector**: once a standard location/convention is settled, mirroring how Repo Standardization's golden-path doc unblocked naming/environment detection.
- **Azure Load Testing connector**: once load-test results are organized in a way that maps to a repo, per Open Question 4.
- **Gate annotation into Track 2**: `e2e_covered` (and eventually the other three checks) annotated onto Track 2's environment-gate nodes as "gated by: E2E pass rate 94%" rather than appended as a separate linear stage after Piped — a cross-cutting fact carried over from the original brainstorm, not yet designed in detail.
