# BuilderOps Platform — Phase 0: Repo Standardization Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-07, ready for implementation planning
**Scope:** First sub-project of the BuilderOps platform. Covers the Repo Standardization pillar only. CI/CD & Lower Environments and E2E & Load Testing are separate, future specs (see [Future Phases](#future-phases)).

## 1. Vision

Give any app team or BuilderOps engineer a single page that answers "what state is my repo in, and what's blocking it from shipping cleanly to prod?" — without pinging BuilderOps. The platform reads state from GitHub (and, for one specific check, Azure DevOps and Azure), and presents it as a repo's **journey**, not a spreadsheet of flags.

Internally, the underlying requirements doc organizes work into three named tracks (Repo Standardization, CI/CD & Lower Environments, E2E & Load Testing). **That numbering is planning-doc language only and must never appear in the product.** The platform instead frames everything as one continuous journey a repo takes, in five stages: **Onboarded → Standardized → Piped → Tested → Paved Road**.

## 2. Team & program context

- Repo Standardization is owned by Naveen, Erik, +1 hire (team at capacity/hiring).
- End state: every app repo lives on GitHub with a consistent structure, containerized dependencies, one-script onboarding, and app teams self-driving compliance rather than BuilderOps babysitting every repo.
- CI/CD & Lower Environments (future spec) is owned by Luke's group; it depends on Repo Standardization (standardized repos are easier to pipeline) and itself depends on E2E & Load Testing (owned by Jiju + 2-3 engineers) for gate data. This dependency chain is a planned sequencing fact — it should read as "plan," not "slippage," anywhere program status is shown.
- Every track has a separate **build** phase (is the capability built) and **adoption** phase (are teams using it) — track these independently, never blend them into one number.

## 3. Scope for this spec

**In scope:** backend foundation (auth, Postgres, API), a GitHub connector covering only the Onboarded/Standardized checks (repo metadata, README, CODEOWNERS, branch protection/permissions), a minimal (list-only) Azure DevOps connector for migration reconciliation, the compliance/readiness data model (built generically enough to hold future Piped/Tested stage keys without a schema change), and the full 5-stage journey UI.

**Explicitly out of scope (future specs):** the Azure Resource Graph connector and GitHub Actions/workflow polling (both are Piped-card data sources, built in the CI/CD phase), the CI/CD pipeline-template and gate-policy engine, self-service QA/UAT environment provisioning (the platform's one write/execute, high-blast-radius component — needs its own permission boundary and approval gates when it's built), the E2E/load test generation and execution engine, RBAC/multi-tenant auth, GitHub webhooks (event-driven sync).

**Deliberate design choice:** the UI ships all 5 journey stages now, even though only the first two (Onboarded, Standardized) have real data behind them in this phase. Piped and Tested render using the same "Locked" treatment as any other not-yet-reached stage, with a note naming what unlocks them ("Unlocks once the CI/CD connector ships"). This avoids a UI redesign when the next two phases land, and previews the full journey so users understand the destination even before it's built.

## 4. Architecture

- **Backend:** Python (FastAPI) + Postgres. An Azure Postgres Flexible Server database named `builderOps` already exists at `quality-pulse-postgres.postgres.database.azure.com` — the backend connects to it rather than provisioning a new instance.
- **Background worker:** APScheduler-based, in-process or a small separate worker — no Celery/Redis needed at this scale. Scheduled connector syncs write only to Postgres; the API/UI never calls GitHub/ADO/Azure live. A manual "Refresh" button triggers an on-demand run of the same job.
- **Connectors** (read-only, isolated from any future write/execute component). Phase 0 only needs enough data to power the **Onboarded** and **Standardized** cards — connectors for **Piped** (GitHub Actions per env, Dockerfile, Azure Resource Graph) and **Tested** (test-framework/load-test feeds) are built in their own future phases, not here:
  - **GitHub connector** — GraphQL-based. Pulls repo metadata and file presence (README/CODEOWNERS), and branch protection + permissions. Does *not* pull Actions workflow/run status or Dockerfile presence in this phase — those are Piped-card concerns, deferred.
  - **ADO connector v0** — repo list only (name, last activity), used solely to compute "exists in ADO but not GitHub" for the Onboarded check. No pipeline/build data, no historical comparison. Full ADO connector remains out of scope until/unless needed later.
  - **Azure connector — deferred, not built in Phase 0.** Resource Graph query against Container Apps, to detect actual ACA deployments, is part of the future CI/CD phase that builds the Piped card. **Open question for that future phase:** how an ACA app maps back to a GitHub repo (naming convention vs. a tag on the resource).
- **Frontend:** React + Tailwind SPA.
- **Auth:** Azure AD (Entra ID) SSO via OIDC. All authenticated users see all repos — no RBAC/multi-tenant scoping in this phase.
- **Secrets:** Azure Key Vault only. The backend's Managed Identity is granted the "Key Vault Secrets User" RBAC role; secrets (DB password, GitHub App key, ADO PAT) are fetched via `azure-identity`'s `DefaultAzureCredential` + `azure-keyvault-secrets`'s `SecretClient`, cached in memory after first fetch. Local dev uses the developer's own `az login` session via the same `DefaultAzureCredential` fallback — no `.env` files with real secrets. No credential is ever stored in code, config, chat, or this document.

### Efficiency

- **GitHub GraphQL batching:** file-existence checks use aliased `object(expression: "HEAD:<path>")` queries, batching up to 100 repos per request — a handful of API calls per sync across hundreds of repos, not hundreds of calls.
- **Tiered sync cadence:** structural checks (CODEOWNERS, README, branch protection) sync every few hours; ADO reconciliation syncs daily. (Actions/pipeline status and Azure Resource Graph cadence will be defined in the future phase that builds those connectors.)
- **Async worker:** httpx async client with bounded concurrency (e.g. a semaphore of 10) so repos process in parallel up to the rate-limit budget.
- **DB writes:** batched upserts (`ON CONFLICT DO UPDATE`) per sync run inside one transaction, unique index on `(repo_id, stage_key)`.
- **Read path:** UI/API only ever reads Postgres — page loads never depend on GitHub/ADO latency or availability.
- **Deferred, documented as a v1.1 optimization, not built now:** GitHub webhooks (push / branch-protection-changed events) for near-real-time updates instead of polling. Needs a public ingress endpoint + GitHub App webhook registration — more infra than this phase needs.

## 5. Data model

- **Repo**: `id`, `name`, `github_url`, `domain` (nullable, manually set in-platform — no existing source of truth), `team`, `migration_wave` (enum: not_started/pilot/rolling_out/migrated — a BuilderOps engagement/rollout-program field, distinct from technical readiness), `created_at`, `last_synced_at`.
- **ReadinessCheck**: one row per repo per stage — a generic table, not fixed columns on `Repo`, so new checks can be added without schema migrations. Fields: `repo_id`, `stage_key`, `status` (pass/fail/unknown/pending_convention), `source` (auto/manual), `detail` (JSON, e.g. `{"dev": true, "qa": true, "uat": false}`), `updated_at`.
- **AdoRepoSnapshot**: raw list from the ADO connector v0 (`name`, `last_activity`) — used only to compute the migration-reconciliation diff.
- **OnboardingLog**: `repo_id`, `engineer_name`, `hours`, `logged_at` — manual entries; no automated telemetry source exists yet (would come from the setup-script itself, in a future phase).
- **SyncRun**: `connector`, `started_at`, `finished_at`, `status`, `error` — lets the UI show "GitHub sync failing since 2h ago" instead of silently serving stale data.
- **ReadinessCheck.status_changed_at** (addition, needed for the fleet landing page's dwell-time feature): a second timestamp, distinct from `updated_at`. `updated_at` is touched on every sync regardless of whether `status` changed; `status_changed_at` only updates when `status` actually differs from the prior value (set equal to `updated_at` on first creation). Dwell time = `now - status_changed_at` of the earliest currently-blocking check. Without this distinction, dwell time would incorrectly reset every sync cycle (every 4h) instead of reflecting how long a repo has actually been stuck.
- **Current stage (derived, not stored):** a repo's current station = the earliest stage in journey order (Onboarded → Standardized → Piped → Tested → Paved Road) where it has a check with `status="fail"` (a `pending_convention` status is treated as non-blocking, consistent with `naming_standardized` never gating Standardized). **Phase 0 clamps this derivation at Standardized** — since Piped/Tested have zero real `ReadinessCheck` rows in this phase (no connector produces them yet), a repo that clears every Standardized check is NOT advanced to a fictitious "Piped" or "Paved Road" state it can't be verified against. It simply stays shown as cleared-and-waiting at Standardized until a future phase's connector gives it real Piped data. This computation belongs server-side (on `RepoOut`, see below), not duplicated in frontend code.

### Stage keys, grouped into the 5 journey cards

| Card | `stage_key` values | Source |
|---|---|---|
| **Onboarded** | `migrated_from_ado` | Auto (ADO connector v0 reconciliation) |
| **Standardized** | `codeowners_assigned`, `domain_assigned`, `branch_protection` (incl. permission model), `readme_present`, `naming_standardized` | Auto except `domain_assigned` (manual) and `naming_standardized` (auto once a convention exists — ships as `pending_convention` until BuilderOps defines one) |
| **Piped** *(future phase — CI/CD connector)* | `actions_dev`, `actions_qa`, `actions_uat`, `actions_prod`, `dockerized`, `deployed_aca` | Auto (GitHub Actions API + file presence + Azure Resource Graph). `dockerized`'s eligibility is a manual flag; presence of a Dockerfile is auto-detected. |
| **Tested** *(future phase — E2E/load connector)* | `code_coverage`, `e2e_pass_rate`, `load_test_result` | Auto, pulled from the future test-framework/load-test result feeds |
| **Paved Road** | derived — true only when every applicable stage above is `pass` | Computed, not stored |

Naming-convention and environment/job-naming detection are both blocked on BuilderOps first defining the conventions (part of the golden-path doc milestone) — until then these render as `pending_convention`, shown distinctly from `fail` everywhere in the UI (never conflate "unknown because not yet standardized" with "failing").

## 6. Error handling & sync strategy

- Each connector run writes a `SyncRun` row. A failure partway through does not roll back already-processed repos **from prior runs** — the previous sync's data stays intact and is served as stale-but-valid until the next successful sync.
- Staleness is surfaced, not hidden: "synced 12m ago" always shown; if the last `SyncRun` for a connector failed, a banner reads "GitHub sync failing since 2h ago, data may be stale."
- Rate limits: connectors respect API rate-limit headers and back off/resume; this is why sync is scheduled rather than live-on-page-load.
- Retry: a failed sync is retried on the next scheduled run — no separate backoff-retry loop needed for v1.
- **Known v1 limitation (identified in the Phase 0 backend's final review, not yet fixed):** true per-repo/per-check failure isolation within a single sync run — "a failed API call for one repo flips only that repo's specific check to `unknown`, without failing the rest of that run" — is NOT implemented as of the initial backend build. The GitHub connector fetches checks in batches of up to 100 repos per GraphQL query; if a batch call fails, the exception propagates and the entire run rolls back and is marked `failed` (falling back to the previous run's data, per the point above — data is stale, not corrupted). The `unknown` status value is defined in the data model but not yet produced by any code path. This is an accepted v1 tradeoff given the batched-query architecture makes true per-repo isolation within a batch non-trivial; revisit if a future phase needs finer-grained partial-failure reporting (e.g. wrapping each batch, not each repo, in its own try/except and marking only that batch's repos `unknown`).

## 7. UI design

Three screens, all under the "journey" framing (no Track 1/2/3 language anywhere):

### 7.1 Repo Fleet (landing page — "repo-fleet-landing.html" reference build)
The fleet-wide overview, answering "where are all our repos right now, and what's stuck" — a kanban-style **station board**, one column per journey stage (Onboarded → Standardized → Piped → Tested → Paved Road), not a flat list. Repos sit in exactly one column: their current stage (see the "current stage" derivation rule in §5). Color coding for track ownership is identical to the Repo Journey page — same hex values, same meaning, no T1/T2/T3 text anywhere except the legend.

- **Hero**: eyebrow + h1 "Repo fleet" + one-line tagline.
- **Stat strip**: 4 tiles — Repos tracked (total), Paved (count at final stage), **Stuck >14 days** (a clickable toggle, not static text — reveals the stuck-now panel), Most crowded station (column with the highest count, with a qualifying hint when a spike is a known transient event so it isn't misread as chronic).
- **Legend**: 4 chips, function-named ("Repo standards," "CI/CD & environments," "E2E & load testing," "Paved — ready to ship") — never internal track numbers.
- **Stuck-now panel**: hidden by default (`hidden` attribute, not just `display:none`, so it's correctly out of the accessibility tree when closed); toggled via the stat tile (`aria-expanded`/`aria-controls`). Every stuck repo fleet-wide, sorted by dwell time descending (worst first) — a viewer shouldn't have to scan five columns to find the worst offender. Each row: colored dot for the stuck stage, repo name, plain-language reason + "waiting on [team]" (sourced from `Repo.team`, never free text), dwell time. Full-width link to that repo's Journey page.
- **Station board**: 5 columns, horizontally scrollable as a unit (`overflow-x: auto`, never wraps to a second row — a deliberate kanban convention). Column header: stage code, title, live count, 3px top border in the stage's track color.
- **Repo card**: name, meta row (owning team — never internal track names — + dwell time), and if stuck, a bordered-off flag with a specific plain-language reason (e.g. "Missing E2E coverage for checkout flow," never "in progress"). Entire card links to that repo's Journey page.
- **Capped columns**: columns over 5 repos show only the top 4 (sorted longest-dwelling-first, consistent with the stuck panel) plus a "View all N repos →" row linking to §7.4's searchable table, pre-filtered to that stage — never render hundreds of cards inline.
- **Empty column state**: dashed border, centered, honest mono text explaining why it's empty and what populates it. In Phase 0 specifically, **Piped and Tested will always render this empty state** (not because repos have "drained," but because those connectors don't exist yet) — text should say so plainly, e.g. "Not live yet — unlocks once the CI/CD connector ships," consistent with the "Locked" language used on the Repo Journey page.
- **Design tokens**: identical to §7.2's Repo Journey page (same hex values, same Sora/Inter/IBM Plex Mono type roles) — this page is wider (max-width 1180px vs. 760px) to fit five columns side by side, and single-theme dark like the Journey page (no light-mode variant — this is a deliberate, committed aesthetic, not an omission).
- **Accessibility**: color is never the only "stuck" signal — the flag section always includes explanatory text. All animation guarded by `prefers-reduced-motion`. Real `<button>`/`<a>` elements throughout, visible gold focus outline.
- **Resolved v1 decisions** (this design explicitly flagged these as needing a decision, not a guess): sort order for capped previews and the stuck panel is longest-dwelling-first; the stuck threshold is a single global 14-day placeholder for v1 (per-stage thresholds deferred); "waiting on [team]" reads from `Repo.team`; dwell-time freshness is bounded by the existing sync cadence (4h GitHub / 1d ADO) — acceptable for v1, revisit if a future phase needs near-real-time station movement.

### 7.2 Repo Journey (signature page — "repo-journey-5cards.html" reference build)
A per-repo page, styled as a transit map: three colored lines (Standards/purple, Pipeline/teal, Testing/orange) converge into a gold "Paved Road" terminus. Track names appear as text only in the legend and diagram line labels — everywhere else (roundels, badges, card borders), track ownership is color-only.

- **Convergence diagram**: each line is drawn with a solid "traveled" portion sized to that line's actual progress (via SVG `pathLength` + `stroke-dasharray`, with the exact tip position computed from real path geometry via `getPointAtLength`, not hand-coded coordinates) and a dim/dashed remainder. The terminus circle stays hollow until all three lines arrive together. A pulsing marker and short status label ("55% · blocked", "ready · holding") sit at each line's current position.
- **Route list**: one card per stage (Onboarded, Standardized, Piped, Tested, Paved Road), each with:
  - A roundel to its left: filled solid in the stage's track color when cleared/current, hollow (border only, ~45% opacity) when locked. The current stage's roundel pulses (disabled under `prefers-reduced-motion`).
  - A gold "traveled" bar overlaid on the dashed rail, its height computed at runtime from the current stage's actual DOM position (cards vary in height, so this is never a hardcoded percentage).
  - Card contents, top to bottom: mono stage code + status badge (exactly three states: `Cleared`, `You are here`, `Locked` — no other badge text is invented), title, one-line plain-language description, a mini checklist of the sub-checks that make up that stage (pass/fail/pending icon + label + value), a meta line (which pillar owns it, last updated), a blocker callout in the blocking area's color if current and blocked, and a **Details** toggle.
  - **Details toggle**: real `<button>` with `aria-expanded`/`aria-controls` (not a div with onclick), animated via the CSS grid `0fr → 1fr` trick. Expanded content includes both a dated log of what happened (past-tense, specific — e.g. "Branch protection enabled — Mar 15") and a metrics grid (numbers like code coverage %, E2E pass rate, load-test p95 latency vs. baseline) — not just a log list. Locked stages show one honest forward-looking sentence naming the unlock condition instead of an empty list.
- **Accessibility**: all animation wrapped in `@media (prefers-reduced-motion: no-preference)`; visible gold focus outline on every focusable element; card hover-lift guarded by `@media (hover: hover)`.
- **Design tokens**: background `#0E1116`, card `#171B21`, locked card `#12151A`, chalk text `#ECEAE3`/`#8B8D93`/`#4E525B`, track colors Standards `#A79AE8`, Pipeline `#3FBBA0`, Testing `#E7975C`, Paved `#EFC24B`. Display type Sora 700–800, body Inter 400–600, mono/utility IBM Plex Mono 500–600. Page max-width 760px. Card radius 12px (map card 14px), 3px top border per card in its track's accent color.

### 7.3 Manual fields & onboarding log
A small, separate section on the Repo Journey page (not part of the transit visualization itself) where BuilderOps edits the fields that aren't auto-derivable: `domain`, `team`, and `migration_wave` — the three fields the backend's `PATCH /repos/{id}` actually supports. (The Dockerization-eligibility flag described in an earlier draft of this section was never implemented as a backend field — it belongs to the future Piped card and is out of scope until that connector exists; don't build a control for a column that doesn't exist.) Also a form to log onboarding time entries (engineer, hours, date) with a running median shown alongside, backed by the already-shipped `POST`/`GET /repos/{id}/onboarding-log`. This is the same manual-entry pattern used everywhere a field has no data source yet — it's what feeds the future onboarding-time success metric.

### 7.4 Repos (searchable table)
The exhaustive fallback: filter by domain/wave, sort by earliest stuck stage (reusing the same stuck-first/longest-dwell-first ordering as the Fleet page's stuck panel), one column per stage status, a name search box, CSV export, row click opens the Repo Journey page for that repo. Also serves as the destination for the Repo Fleet page's "View all N repos →" rows, which navigate here pre-filtered to the stage the user clicked from (replacing the client-side in-column expand used as a placeholder in the first frontend build). **Implementation note:** filtering/sorting/search happen entirely client-side against the full `GET /repos` result (already fetched, no new params) — the backend has no `migration_wave` query param and doesn't need one at this repo count (~230); CSV export is generated client-side from the already-loaded data, no backend export endpoint.

### 7.5 What's hardcoded in the reference build vs. what becomes data-driven

| Element | Reference build | Production |
|---|---|---|
| Repo name, tagline | Hardcoded | `Repo` entity |
| Stage status (cleared/current/locked) | Hardcoded per row | Derived from that repo's `ReadinessCheck` rows |
| "Now approaching" banner | Hardcoded | Current stage's code + name |
| Details log entries | Hardcoded list | Repo's event/audit-log records, sorted by date |
| Blocker callout text | Hardcoded | The specific failing check's detail from `ReadinessCheck.detail` |
| Convergence-line progress % | Hardcoded per line | Fraction of that card's sub-checks passing |
| Traveled bar height | Computed from DOM at runtime | Same approach — no change needed |
| Repo Fleet: counts per column, repo cards | Hardcoded HTML | Queried from `/repos`, grouped by each repo's derived current-stage field |
| Repo Fleet: stuck flag + reason | Hardcoded text | Derived from the repo's blocking `ReadinessCheck.detail` |
| Repo Fleet: dwell time | Hardcoded string | `now - status_changed_at` of the earliest currently-failing check (see §5) |
| Repo Fleet: "most crowded station" stat | Hardcoded | Computed as the column with the highest live count |
| Repo Fleet: stuck-panel row order | Hardcoded | Sorted by dwell time descending from live data |
| Repo Fleet: "View all" link | `href="#"` placeholder | Routes to §7.4 filtered to that stage |

## 8. Open questions (must resolve before the dependent feature is built)

1. **ACA ↔ repo mapping** — naming convention or resource tag? Blocks the `deployed_aca` check.
2. **Repo naming convention** — not yet defined by BuilderOps (part of the golden-path doc milestone). Blocks `naming_standardized`.
3. **Environment/test-type detection method** — GitHub's native Environments feature vs. file/job naming convention. Not yet decided. Blocks `actions_dev/qa/uat/prod` granularity and `e2e_pass_rate`/`code_coverage` job attribution.

## 9. Future phases

- **CI/CD & Lower Environments** (own spec): pipeline/environment inventory, gate-policy design, self-service QA/UAT provisioning (isolated, high-blast-radius component), migration onto standardized pipelines. Powers the **Piped** card.
- **E2E & Load Testing** (own spec): critical-path identification, shared E2E/load infra, wiring results into CI/CD gates, product-by-product coverage expansion. Powers the **Tested** card.
- **Program Health view** (cross-cutting, after at least two tracks have real data): Build % vs. Adopt % per pillar, tracked separately; per-pillar success metrics (% repos on standard; deploy lead time + env provisioning time; % critical paths with E2E coverage + deploy failure rate caught pre-prod); explicit statement of the Piped→Tested dependency so it reads as planned sequencing, not slippage. Doubles as the leadership weekly email body.
