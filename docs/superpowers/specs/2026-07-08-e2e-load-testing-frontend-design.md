# BuilderOps Platform — E2E & Load Testing Frontend Design

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-08, ready for implementation planning
**Scope:** Frontend for the E2E & Load Testing Phase 0 backend (merged to `main`, commit `47855af`). Implements §8 of `docs/superpowers/specs/2026-07-08-e2e-load-testing-phase0-design.md` — the Tested `StationCard` going live, `RepoFieldsForm`'s `e2e_test_plan_id` field, and Fleet/Repos-table updates — against the frontend codebase as it actually exists today, including the Piped frontend work already merged (`b3a97bd`), which this pass reuses directly. This doc resolves two gaps between that prose and reality (documented below) and is the Track 3 counterpart to the CI/CD Piped frontend design.

**Notably smaller than the Piped frontend pass:** no live endpoint exists for this pillar, so there is no new panel, no new hook, and no new `StationCard` capability — the checklist-rendering mode built for Piped is reused as-is.

## 1. Two resolved gaps between the backend spec's prose and reality

1. **`e2e_test_plan_id` is write-only, same gap `dockerize_eligible` had.** `RepoOut` never exposes `e2e_test_plan_id` — it's `PATCH`-able but not readable via `GET`. Same fix as before: a small, isolated backend patch exposing it on `RepoOut`, wired in `_to_repo_out`.
2. **`ConvergenceDiagram`/`testingProgress` is never mentioned in the backend spec at all.** `JourneyPage.tsx` currently passes `testingProgress={0}` hardcoded. Decision: wire it to `e2e_covered` alone — `1` if it passes, else `0` — excluding `unit_tested`/`integration_tested`/`load_tested` since none of those three can reach `"pass"` this phase (they'd otherwise permanently cap progress below 100%), the same reasoning that already excludes `naming_standardized` from `standardsProgress`.

## 2. Backend — expose `e2e_test_plan_id` on `RepoOut`

Identical shape to the `dockerize_eligible` fix: add `e2e_test_plan_id: int | None` to `RepoOut`, populate it in `_to_repo_out` from `repo.e2e_test_plan_id`.

## 3. Data layer

`frontend/src/api/types.ts`:
- `RepoOut` gains `e2e_test_plan_id?: number | null` (optional, same rationale as `dockerize_eligible` — no other existing test fixture needs to change).
- `RepoPatchIn` gains `e2e_test_plan_id?: number`.

No new API client function — there is no live endpoint for this pillar.

## 4. Tested `StationCard` (`JourneyPage.tsx`)

- Badge: `Locked` (copy: "Not live yet — unlocks once an E2E Test Plan is mapped.") when `stages.e2e_covered?.status === "pending_convention"` or the check is entirely absent. `Cleared` when `stages.e2e_covered?.status === "pass"`. `You are here` otherwise (covers `"fail"` and `"unknown"`).
- Description copy corrected from the generic "Load testing, end-to-end testing, and code coverage all clear." to something reflecting the real E2E-only signal, e.g. "End-to-end tests are passing on the latest Azure Test Plans run."
- `checks` prop (reusing `StationCard`'s existing checklist mode, no new component work): `e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`, in that order — the latter three render their placeholder statuses (`pending_convention`/`unknown`) honestly, same treatment the Piped card's `deployed_aca` row already gets.
- `ConvergenceDiagram`'s `testingProgress` becomes `repo.stages.e2e_covered?.status === "pass" ? 1 : 0`, replacing the hardcoded `0`.

## 5. `RepoFieldsForm.tsx`

- New `e2e_test_plan_id` control: a plain numeric `<input type="number">`, pre-filled from `repo.e2e_test_plan_id` (empty when `null`/`undefined`). Omitted from the `PATCH` body entirely when left blank — same omit-if-unset convention `dockerize_eligible` already established, verified the same way (inspecting the real serialized PATCH body, not just UI state).

## 6. Fleet & Repos-table pages

- `frontend/src/components/fleet/StationBoard.tsx`: Tested becomes a real `RealColumn` (`stageKey="tested"`, filtering `current_stage === "tested"`), same as Onboarded/Standardized/Piped. Paved road remains `EmptyColumn` (no Track 4 exists). The file's explanatory comment is updated to reflect Tested joining the real columns.
- `frontend/src/pages/RepoTablePage.tsx`: `CHECK_COLUMNS` gains `e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`.
- `frontend/src/lib/format.ts`: `STAGE_LABELS` gains `tested: "Tested"`.

## 7. Out of scope

No live endpoint, no new panel, no new `StationCard` capability (reuses Piped's checklist mode as-is). Paved Road stays untouched — there is no Track 4 backend to make it real.
