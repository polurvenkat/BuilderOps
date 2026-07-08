# BuilderOps Platform — CI/CD & Lower Environments Frontend Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-08, ready for implementation planning
**Scope:** Frontend for the CI/CD & Lower Environments Phase 0 backend (merged to `main`, commit `75cb2fb`). Implements §8 of `docs/superpowers/specs/2026-07-08-cicd-lower-envs-phase0-design.md` — the Piped `StationCard` going live, the live pipeline-status panel, `ConvergenceDiagram` wiring, and Fleet/Repos-table updates — against the frontend codebase as it actually exists today (`frontend/src/`), not the backend spec's prose alone. This doc resolves three gaps between that prose and the real frontend (documented below) and is the frontend counterpart to Track 1's `frontend-core`/`frontend-track1-wrapup` plans.

**Explicitly out of scope:** the **Tested** card/column stay hardcoded `Locked`/`EmptyColumn` placeholders in this pass, even though the E2E & Load Testing (Track 3) backend already shipped in the same session and can produce real `current_stage: "tested"` data. This is a deliberate, acknowledged truth-gap accepted to keep this pass scoped to Track 2 — a Track 3 frontend pass should follow immediately after and is expected to close it quickly.

## 1. Three resolved gaps between the backend spec's prose and the real frontend

1. **Piped's Locked/live state must key off the `pipeline_linked` check directly, not `current_stage`.** Onboarded and Standardized today derive their badge from `current_stage`/`is_stuck` (`JourneyPage.tsx`), which only reaches `"piped"` once Standardized has fully cleared. But `pipeline_linked` (and the other Piped-card checks) are computed and stored independently of stage progression — a repo can have a real, linked pipeline before its Standardized checks are all green. Per the backend spec's intent ("badge reflects real state... Locked... only for repos with no pipeline link at all"), Piped must read `repo.stages.pipeline_linked?.status` directly, not gate on `current_stage`.
2. **"Mini checklist shows all five sub-checks" was never actually built.** `StationCard.tsx` only ever renders one primary `StageCheckOut` via `DetailsToggle` (Standardized picks one representative failing check via `primaryStandardizedCheck` in `JourneyPage.tsx`, same for Onboarded). The backend spec's §8.1 prose describes a fuller checklist that doesn't exist in code. Decision: build it now, as a new optional capability on `StationCard`, with Piped as its first consumer — not a re-interpretation of the spec down to what already exists.
3. **The live panel's fetch trigger isn't specified.** Decision: auto-fetch on page load whenever `pipeline_linked` passes, with a loading state and an explicit error banner on failure (no silent stale fallback, matching the backend's own no-stale-fallback contract for this endpoint).

## 2. Data layer

`frontend/src/api/types.ts`:
- `RepoOut` gains `dockerize_eligible: boolean | null`.
- `RepoPatchIn` gains `dockerize_eligible?: boolean`.
- New: `PipelineStageStatusOut { name: string; status: string; pending_approval_description: string | null }`.
- New: `PipelineStatusOut { stages: PipelineStageStatusOut[] }`.

`frontend/src/api/client.ts`:
- New `getPipelineStatus(id: number): Promise<PipelineStatusOut>` — `GET /repos/{id}/pipeline-status`. Callers must distinguish a 404 (no pipeline linked — shouldn't be called in that case, but tolerate it) from a 502 (ADO unreachable) from a network-level failure; all three surface as a thrown `Error` with the response status embedded in the message, same pattern every other `client.ts` function already uses.

## 3. `StationCard` gains a checklist mode

Extend `StationCardProps` with an optional `checks?: { label: string; check?: StageCheckOut }[]`. When `checks` is provided, the `DetailsToggle` body renders one row per entry (label + status + updated date, same row shape the existing single-`check` rendering already uses) instead of the single-check row. When `checks` is absent, behavior is byte-identical to today — Onboarded and Standardized are unaffected. Piped is the first and only consumer of `checks` in this pass.

## 4. Piped `StationCard` (`JourneyPage.tsx`)

- Badge: `Locked` (copy: "Not live yet — unlocks once a pipeline is linked in Azure DevOps.") when `stages.pipeline_linked?.status !== "pass"`. Otherwise `Cleared` when `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, and `dockerized` all pass; otherwise `You are here` (covers both mid-flight and stuck-with-a-failing-check, same conflation Onboarded/Standardized already use).
- Description copy corrected from the stale "GitHub Actions are wired up..." to reflect the real Azure Pipelines/YAML flow, e.g. "Azure Pipelines is wired up and the YAML pipeline deploys cleanly through every environment."
- `checks` prop: `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca` — all five, in that order. `deployed_aca` is display-only here; it never affects the badge (non-blocking, matches the backend's stage-derivation treatment).

## 5. Live pipeline-status panel (new: `frontend/src/components/journey/PipelineStatusPanel.tsx`)

- Renders only when `stages.pipeline_linked?.status === "pass"` — otherwise nothing (no empty state, no placeholder).
- On mount, calls `getPipelineStatus(repo.id)`. Shows a loading state, then either the ordered stage row (Build → DEV → QA → UAT → Prod, per `PipelineStatusOut.stages` order) with a per-stage status pill, or — if any stage carries `pending_approval_description` — a callout banner surfacing that text. On fetch failure, renders "Couldn't reach Azure DevOps — try again" with no fallback to stale data.
- Positioned on `JourneyPage` the same way `OnboardingLog` sits below `RepoFieldsForm` today.

## 6. `ConvergenceDiagram` wiring

- New small hook `frontend/src/hooks/usePipelineStatus.ts` (mirrors the shape of the existing `useRepo`/`useRepos` hooks): fetches `getPipelineStatus(repoId)` when `enabled` (i.e. `pipeline_linked` passes), exposes `{ stages, loading, error }`.
- `JourneyPage` calls this hook once and passes `stages` to both `PipelineStatusPanel` (as the already-fetched data, avoiding a duplicate call) and a `pipelineProgress` calculation: fraction of `["DEV", "QA", "UAT", "Prod"]`-named stages whose `status === "succeeded"`, replacing the hardcoded `0` currently passed to `ConvergenceDiagram`.

## 7. `RepoFieldsForm.tsx`

- New `dockerize_eligible` control: a `<select>` with three options — "Not yet assessed" (maps to omitting the field / `null`), "Eligible" (`true`), "Not eligible" (`false`) — same visual/structural pattern as the existing `WAVE_OPTIONS` select, not a native tri-state checkbox (no such native control exists, and a select keeps this consistent with the form's existing style).

## 8. Fleet & Repos-table pages

- `frontend/src/components/fleet/StationBoard.tsx`: Piped becomes a real `RealColumn` (`stageKey="piped"`, filtering `repos.filter(r => r.current_stage === "piped")`), same as the existing Onboarded/Standardized columns. The file's explanatory comment ("only onboarded/standardized are real columns today...") is updated to reflect Piped joining them. Tested and Paved road remain `EmptyColumn` (explicit scope boundary, §0 above).
- `frontend/src/pages/RepoTablePage.tsx`: `CHECK_COLUMNS` gains `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca`.
- `frontend/src/lib/format.ts`: `STAGE_LABELS` gains `piped: "Piped"`.

## 9. Out of scope (unchanged from the backend spec)

Self-service environment provisioning, gate policy/enforcement, pipeline template rollout, and E2E-gate annotation remain future work per the backend spec's §10 — none of it is frontend-visible in this pass.
