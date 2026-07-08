# CI/CD Piped Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `docs/superpowers/specs/2026-07-08-cicd-lower-envs-frontend-design.md` — the Piped `StationCard` going live, a new live pipeline-status panel, `ConvergenceDiagram` wiring, `dockerize_eligible` field editing, and Fleet/Repos-table updates. Tested stays a hardcoded `Locked`/`EmptyColumn` placeholder (deliberate, see the design doc's scope note).

**Architecture:** Almost entirely frontend (`frontend/src/`), following the exact component/hook/page patterns Track 1's frontend already established. Task 1 is a small, isolated backend patch (expose `dockerize_eligible` on `RepoOut` — currently write-only via `PATCH`, discovered during design review; without it `RepoFieldsForm` cannot honestly pre-fill the field's real saved value). Every other task is frontend-only.

**Tech Stack:** Backend: Python/FastAPI/Pydantic (Task 1 only). Frontend: React, TypeScript, Vite, Tailwind, Vitest, `@testing-library/react`/`user-event`.

## Global Constraints

- `dockerize_eligible` is typed as **optional** in the frontend `RepoOut` interface (`dockerize_eligible?: boolean | null`), not required — this means existing test fixtures across the frontend that construct `RepoOut` literals do NOT need to be touched; only the one file that actually reads the field (`RepoFieldsForm` and its test) needs to set it.
- Piped's `Locked`/`You are here`/`Cleared` badge state is driven by `repo.stages.pipeline_linked`/other Piped check statuses directly, never by `current_stage` — a repo can have a real pipeline link before Standardized has cleared (see design doc §1.1).
- Tested and Paved Road stay untouched hardcoded placeholders in every file this plan modifies — do not flip them to real, even though the Track 3 backend already exists (explicit, deliberate scope boundary, see design doc's header).
- The live pipeline-status panel auto-fetches on mount whenever `pipeline_linked` passes, shows a loading state, then either real data or an explicit "Couldn't reach Azure DevOps — try again" error — no silent stale fallback.
- `StationCard`'s existing single-`check` prop and its consumers (Onboarded, Standardized) must keep working byte-identically — the new `checks` (plural) prop is strictly additive.
- Match existing code style exactly: Tailwind utility classes copied from neighboring components, `useId()` for form label wiring, the `bg-bg-card border border-card-border rounded-xl p-4` card shell used by `RepoFieldsForm`/`OnboardingLog`.
- Frontend tests live under `frontend/tests/`, mirroring `frontend/src/`'s structure — not colocated with source files.
- Run `cd frontend && npm run build` (which runs `tsc` then `vite build`) at the end of every frontend task, not just `npm test` — this codebase has a documented recurring bug class of `npm test` passing while `tsc` fails silently on type errors `vitest`/esbuild don't check.

---

## File Structure

```
backend/
  app/
    schemas.py                                   # MODIFY: RepoOut gains dockerize_eligible
    api/repos.py                                 # MODIFY: _to_repo_out wires it through
  tests/api/test_repos_api.py                    # MODIFY: new assertion

frontend/
  src/
    api/
      types.ts                                   # MODIFY: dockerize_eligible?, PipelineStageStatusOut, PipelineStatusOut
      client.ts                                  # MODIFY: getPipelineStatus
    components/journey/
      StationCard.tsx                            # MODIFY: new `checks` prop
      PipelineStatusPanel.tsx                    # NEW
      RepoFieldsForm.tsx                         # MODIFY: dockerize_eligible select
    hooks/
      usePipelineStatus.ts                       # NEW
    pages/
      JourneyPage.tsx                            # MODIFY: real Piped badge/checklist, panel, pipelineProgress
    components/fleet/
      StationBoard.tsx                           # MODIFY: Piped becomes a RealColumn
    pages/
      RepoTablePage.tsx                          # MODIFY: CHECK_COLUMNS gains 5 keys
    lib/
      format.ts                                  # MODIFY: STAGE_LABELS gains "piped"
  tests/
    components/journey/
      StationCard.test.tsx                       # MODIFY: checklist-mode tests
      PipelineStatusPanel.test.tsx                # NEW
      RepoFieldsForm.test.tsx                     # MODIFY: dockerize_eligible tests
    pages/
      JourneyPage.test.tsx                       # MODIFY: real-Piped tests
      RepoTablePage.test.tsx                     # MODIFY: new-column test
    components/fleet/
      StationBoard.test.tsx                      # MODIFY: Piped-real-column tests, fix empty-columns test
```

---

### Task 1: Backend — expose `dockerize_eligible` on `RepoOut`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Produces: `RepoOut.dockerize_eligible: bool | None`, populated in `_to_repo_out` from `repo.dockerize_eligible`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_repos_api.py`:

```python
def test_repo_out_exposes_dockerize_eligible():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    client.patch(f"/repos/{repo_id}", json={"dockerize_eligible": True})
    body = client.get(f"/repos/{repo_id}").json()

    assert body["dockerize_eligible"] is True


def test_repo_out_dockerize_eligible_defaults_to_none():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["dockerize_eligible"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k dockerize_eligible`
Expected: FAIL — `KeyError: 'dockerize_eligible'` (the key doesn't exist in the response body yet)

- [ ] **Step 3: Update `app/schemas.py`**

```python
class RepoOut(BaseModel):
    id: int
    name: str
    domain: str | None
    team: str | None
    migration_wave: str
    github_url: str
    last_synced_at: datetime | None
    dockerize_eligible: bool | None
    stages: dict[str, StageCheckOut]
    current_stage: str
    is_stuck: bool
    dwell_days: int | None
    stuck_reason: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update `_to_repo_out` in `app/api/repos.py`**

```python
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        team=repo.team,
        migration_wave=repo.migration_wave,
        github_url=repo.github_url,
        last_synced_at=repo.last_synced_at,
        dockerize_eligible=repo.dockerize_eligible,
        stages=stages,
        current_stage=stage_info.current_stage,
        is_stuck=stage_info.is_stuck,
        dwell_days=stage_info.dwell_days,
        stuck_reason=stage_info.stuck_reason,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full backend suite and commit**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all tests pass (122+)

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: expose dockerize_eligible on RepoOut"
```

---

### Task 2: Frontend data layer — types and API client

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/tests/api/client.test.ts`

**Interfaces:**
- Consumes: Task 1's `dockerize_eligible` field (backend now returns it, but the TS type makes it optional so no other fixture needs updating).
- Produces: `RepoOut.dockerize_eligible?: boolean | null`, `RepoPatchIn.dockerize_eligible?: boolean`, `PipelineStageStatusOut { name, status, pending_approval_description }`, `PipelineStatusOut { stages: PipelineStageStatusOut[] }`, `getPipelineStatus(id: number): Promise<PipelineStatusOut>`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/api/client.test.ts`:

```typescript
import { getPipelineStatus } from "../../src/api/client";
```

(add to the existing import line from `"../../src/api/client"` — it currently imports `getOnboardingLog, getRepo, listRepos, patchRepo, postOnboardingLog`; add `getPipelineStatus` to that list)

```typescript
describe("getPipelineStatus", () => {
  it("fetches the live pipeline status for a repo", async () => {
    const status = { stages: [{ name: "Build", status: "succeeded", pending_approval_description: null }] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => status });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getPipelineStatus(1);

    expect(result).toEqual(status);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1\/pipeline-status$/);
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));

    await expect(getPipelineStatus(1)).rejects.toThrow(/502/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- client.test.ts`
Expected: FAIL — `getPipelineStatus is not a function` / TypeScript error (not exported yet)

- [ ] **Step 3: Update `src/api/types.ts`**

```typescript
export interface StageCheckOut {
  status: string;
  source: string;
  detail: Record<string, unknown> | null;
  updated_at: string | null;
}

export interface RepoOut {
  id: number;
  name: string;
  domain: string | null;
  team: string | null;
  migration_wave: string;
  github_url: string;
  last_synced_at: string | null;
  dockerize_eligible?: boolean | null;
  stages: Record<string, StageCheckOut>;
  current_stage: string;
  is_stuck: boolean;
  dwell_days: number | null;
  stuck_reason: string | null;
}

export interface ListReposParams {
  stage?: string;
  domain?: string;
  sort?: "dwell_desc";
}

export interface RepoPatchIn {
  domain?: string;
  team?: string;
  migration_wave?: "not_started" | "pilot" | "rolling_out" | "migrated";
  dockerize_eligible?: boolean;
}

export interface OnboardingLogIn {
  engineer_name: string;
  hours: number;
}

export interface OnboardingLogOut {
  id: number;
  repo_id: number;
  engineer_name: string;
  hours: number;
  logged_at: string;
}

export interface OnboardingSummaryOut {
  entries: OnboardingLogOut[];
  median_hours: number | null;
}

export interface PipelineStageStatusOut {
  name: string;
  status: string;
  pending_approval_description: string | null;
}

export interface PipelineStatusOut {
  stages: PipelineStageStatusOut[];
}
```

- [ ] **Step 4: Update `src/api/client.ts`**

Add to the import from `"./types"`: `PipelineStatusOut` (alongside the existing `ListReposParams, OnboardingLogIn, OnboardingLogOut, OnboardingSummaryOut, RepoOut, RepoPatchIn`).

Add at the end of the file:

```typescript
export async function getPipelineStatus(id: number): Promise<PipelineStatusOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}/pipeline-status`);
  if (!response.ok) {
    throw new Error(`Failed to get pipeline status for repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- client.test.ts`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: `tsc`/`vite build` clean, all tests pass

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/tests/api/client.test.ts
git commit -m "feat: add pipeline-status types and API client function"
```

---

### Task 3: `StationCard` gains a checklist-rendering mode

**Files:**
- Modify: `frontend/src/components/journey/StationCard.tsx`
- Modify: `frontend/tests/components/journey/StationCard.test.tsx`

**Interfaces:**
- Consumes: nothing new (uses existing `StageCheckOut` type).
- Produces: `StationCardProps.checks?: { label: string; check?: StageCheckOut }[]`. When provided, renders one row per entry inside the existing `DetailsToggle`. When absent, behavior is byte-identical to today (the existing `check` prop still works for Onboarded/Standardized). Task 5 (`JourneyPage`) is the first consumer of `checks`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/components/journey/StationCard.test.tsx`:

```tsx
it("renders a checklist of multiple sub-checks when the checks prop is provided", async () => {
  const user = userEvent.setup();
  render(
    <StationCard
      code="PI-01"
      title="Piped"
      description="Azure Pipelines is wired up."
      badge="You are here"
      trackColor="#3FBBA0"
      checks={[
        { label: "Pipeline linked", check: { status: "pass", source: "auto", detail: null, updated_at: null } },
        { label: "Dockerized", check: { status: "fail", source: "auto", detail: null, updated_at: null } },
      ]}
    />
  );

  await user.click(screen.getByRole("button", { name: /details/i }));

  expect(screen.getByText("Pipeline linked")).toBeInTheDocument();
  expect(screen.getByText("pass")).toBeInTheDocument();
  expect(screen.getByText("Dockerized")).toBeInTheDocument();
  expect(screen.getByText("fail")).toBeInTheDocument();
});

it("renders 'unknown' for a checklist entry with no check data yet", async () => {
  const user = userEvent.setup();
  render(
    <StationCard
      code="PI-01"
      title="Piped"
      description="Azure Pipelines is wired up."
      badge="You are here"
      trackColor="#3FBBA0"
      checks={[{ label: "Deployed to ACA" }]}
    />
  );

  await user.click(screen.getByRole("button", { name: /details/i }));

  expect(screen.getByText("Deployed to ACA")).toBeInTheDocument();
  expect(screen.getByText("unknown")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- StationCard.test.tsx`
Expected: FAIL — TypeScript error (`checks` doesn't exist on `StationCardProps`) or the rows simply don't render

- [ ] **Step 3: Update `src/components/journey/StationCard.tsx`**

```tsx
import type { StageCheckOut } from "../../api/types";
import { DetailsToggle } from "./DetailsToggle";

interface StationCardProps {
  code: string;
  title: string;
  description: string;
  badge: "Cleared" | "You are here" | "Locked";
  trackColor: string;
  check?: StageCheckOut;
  checks?: { label: string; check?: StageCheckOut }[];
  lockedNote?: string;
}

const BADGE_STYLES: Record<StationCardProps["badge"], string> = {
  Cleared: "bg-white/[0.08] text-chalk-dim",
  "You are here": "bg-gold/15 text-gold",
  Locked: "bg-chalk-dimmer/20 text-chalk-dimmer",
};

export function StationCard({ code, title, description, badge, trackColor, check, checks, lockedNote }: StationCardProps) {
  const isLocked = badge === "Locked";

  return (
    <div
      className={`rounded-xl border border-card-border p-4 ${isLocked ? "bg-bg-card-locked" : "bg-bg-card"}`}
      style={{ borderTopWidth: 3, borderTopColor: trackColor }}
    >
      <div className="flex justify-between items-center mb-2">
        <span className="font-mono text-[11px] text-chalk-dimmer">{code}</span>
        <span className={`font-mono text-[10.5px] font-semibold px-2 py-0.5 rounded ${BADGE_STYLES[badge]}`}>
          {badge}
        </span>
      </div>
      <h3 className={`font-display text-[21px] font-bold mb-1.5 ${isLocked ? "text-chalk-dim" : ""}`}>{title}</h3>
      <p className={`text-[14.5px] mb-2.5 ${isLocked ? "opacity-60" : "opacity-90"}`}>{description}</p>

      {isLocked ? (
        <p className="text-[13px] text-chalk-dim pt-2">{lockedNote}</p>
      ) : (
        <DetailsToggle>
          {checks ? (
            <div className="flex flex-col gap-1.5 py-2 border-t border-card-border">
              {checks.map(({ label, check: c }) => (
                <div key={label} className="flex justify-between text-[13px]">
                  <span className="opacity-85">{label}</span>
                  <span className="font-mono text-[11px] text-chalk-dimmer">{c?.status ?? "unknown"}</span>
                </div>
              ))}
            </div>
          ) : check ? (
            <div className="flex justify-between text-[13px] py-2 border-t border-card-border">
              <span className="opacity-85">Status: {check.status}</span>
              <span className="font-mono text-[11px] text-chalk-dimmer">
                {check.updated_at ? new Date(check.updated_at).toLocaleDateString() : "—"}
              </span>
            </div>
          ) : null}
        </DetailsToggle>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- StationCard.test.tsx`
Expected: PASS (all tests, including the 3 pre-existing ones — confirm they still pass unchanged)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/components/journey/StationCard.tsx frontend/tests/components/journey/StationCard.test.tsx
git commit -m "feat: add a checklist-rendering mode to StationCard"
```

---

### Task 4: Live pipeline-status hook and panel

**Files:**
- Create: `frontend/src/hooks/usePipelineStatus.ts`
- Create: `frontend/src/components/journey/PipelineStatusPanel.tsx`
- Create: `frontend/tests/components/journey/PipelineStatusPanel.test.tsx`

**Interfaces:**
- Consumes: `getPipelineStatus` (Task 2).
- Produces: `usePipelineStatus(repoId: number, enabled: boolean): { stages: PipelineStageStatusOut[] | null; loading: boolean; error: string | null }` — fetches only when `enabled` is true, resets to idle state when `enabled` is false. `PipelineStatusPanel({ stages, loading, error })` — pure presentational component, no fetching of its own (the hook's consumer, Task 5's `JourneyPage`, owns the fetch and passes the result down as props so the same data can also feed `ConvergenceDiagram` without a duplicate call).

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/components/journey/PipelineStatusPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineStatusPanel } from "../../../src/components/journey/PipelineStatusPanel";

describe("PipelineStatusPanel", () => {
  it("shows a loading state", () => {
    render(<PipelineStatusPanel stages={null} loading={true} error={null} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error banner on failure, with no stage data", () => {
    render(<PipelineStatusPanel stages={null} loading={false} error="HTTP 502" />);

    expect(screen.getByText(/Couldn't reach Azure DevOps/)).toBeInTheDocument();
  });

  it("renders each stage's name and status", () => {
    render(
      <PipelineStatusPanel
        stages={[
          { name: "Build", status: "succeeded", pending_approval_description: null },
          { name: "DEV", status: "succeeded", pending_approval_description: null },
          { name: "UAT", status: "waiting_approval", pending_approval_description: "Needs sign-off" },
        ]}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText("Build")).toBeInTheDocument();
    expect(screen.getAllByText("succeeded")).toHaveLength(2);
    expect(screen.getByText("waiting_approval")).toBeInTheDocument();
  });

  it("surfaces a pending-approval callout with its description", () => {
    render(
      <PipelineStatusPanel
        stages={[{ name: "UAT", status: "waiting_approval", pending_approval_description: "Needs sign-off" }]}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText(/Needs sign-off/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- PipelineStatusPanel.test.tsx`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create `src/hooks/usePipelineStatus.ts`**

```typescript
import { useEffect, useState } from "react";
import { getPipelineStatus } from "../api/client";
import type { PipelineStageStatusOut } from "../api/types";

export function usePipelineStatus(repoId: number, enabled: boolean) {
  const [stages, setStages] = useState<PipelineStageStatusOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setStages(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getPipelineStatus(repoId)
      .then((data) => {
        if (!cancelled) setStages(data.stages);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [repoId, enabled]);

  return { stages, loading, error };
}
```

- [ ] **Step 4: Create `src/components/journey/PipelineStatusPanel.tsx`**

```tsx
import type { PipelineStageStatusOut } from "../../api/types";

interface PipelineStatusPanelProps {
  stages: PipelineStageStatusOut[] | null;
  loading: boolean;
  error: string | null;
}

export function PipelineStatusPanel({ stages, loading, error }: PipelineStatusPanelProps) {
  const pendingApprovals = stages?.filter((s) => s.pending_approval_description) ?? [];

  return (
    <div className="bg-bg-card border border-card-border rounded-xl p-4 mt-4">
      <div className="font-mono text-[10.5px] text-chalk-dim uppercase mb-2">Live pipeline status</div>
      {loading ? <p className="text-[13px] text-chalk-dim">Loading…</p> : null}
      {error ? <p className="text-[13px] text-track3">Couldn't reach Azure DevOps — try again</p> : null}
      {!loading && !error && stages ? (
        <div className="flex flex-col gap-2">
          {stages.map((stage) => (
            <div key={stage.name} className="flex justify-between text-[13px]">
              <span>{stage.name}</span>
              <span className="font-mono text-[12px] text-chalk-dim">{stage.status}</span>
            </div>
          ))}
          {pendingApprovals.map((stage) => (
            <div
              key={`${stage.name}-approval`}
              className="mt-2 rounded-lg border border-gold/40 bg-gold/10 text-gold p-2 text-[12.5px]"
            >
              {stage.name}: {stage.pending_approval_description}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- PipelineStatusPanel.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/hooks/usePipelineStatus.ts frontend/src/components/journey/PipelineStatusPanel.tsx frontend/tests/components/journey/PipelineStatusPanel.test.tsx
git commit -m "feat: add usePipelineStatus hook and PipelineStatusPanel component"
```

---

### Task 5: `JourneyPage` — Piped goes live, panel + `ConvergenceDiagram` wiring

**Files:**
- Modify: `frontend/src/pages/JourneyPage.tsx`
- Modify: `frontend/tests/pages/JourneyPage.test.tsx`

**Interfaces:**
- Consumes: `checks` prop (Task 3), `usePipelineStatus`/`PipelineStatusPanel` (Task 4).
- Produces: Piped `StationCard` reflects real badge/checklist state; `ConvergenceDiagram`'s `pipelineProgress` reflects live data; `PipelineStatusPanel` renders below `RepoFieldsForm` when linked.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/pages/JourneyPage.test.tsx` (add `PipelineStatusOut` handling to the fetch-mock sequence — `JourneyPage` will now issue a third fetch call, to `pipeline-status`, whenever `pipeline_linked` passes):

```tsx
const PIPED_REPO: RepoOut = {
  ...STUCK_REPO,
  id: 2,
  name: "checkout-web-piped",
  stages: {
    ...STUCK_REPO.stages,
    codeowners_assigned: { status: "pass", source: "auto", detail: null, updated_at: "2026-06-01T00:00:00Z" },
    pipeline_linked: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    pipeline_is_yaml: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    environment_gates_configured: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    dockerized: { status: "fail", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    deployed_aca: { status: "unknown", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
  },
  current_stage: "piped",
  is_stuck: true,
  stuck_reason: "Dockerfile missing for a dockerize-eligible repo — waiting on Growth team",
};

it("shows Piped as 'You are here' with real sub-checks once pipeline_linked passes", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => PIPED_REPO })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ stages: [{ name: "DEV", status: "succeeded", pending_approval_description: null }] }),
    });
  vi.stubGlobal("fetch", fetchMock);

  renderAtRepo("2");

  await waitFor(() => expect(screen.getByText("checkout-web-piped")).toBeInTheDocument());
  const pipedCard = screen.getByText("PI-01").closest("div.rounded-xl") as HTMLElement;
  expect(within(pipedCard).getByText("You are here")).toBeInTheDocument();

  await clickDetails(pipedCard);
  expect(within(pipedCard).getByText("Dockerized")).toBeInTheDocument();
});

it("keeps Piped Locked when pipeline_linked has not been reached", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => STUCK_REPO })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
  vi.stubGlobal("fetch", fetchMock);

  renderAtRepo("1");

  await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
  const pipedCard = screen.getByText("PI-01").closest("div.rounded-xl") as HTMLElement;
  expect(within(pipedCard).getByText("Locked")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2); // repo + onboarding-log only, no pipeline-status call
});

it("shows Cleared when every blocking Piped check passes, and renders the live status panel", async () => {
  const clearedRepo: RepoOut = {
    ...PIPED_REPO,
    stages: { ...PIPED_REPO.stages, dockerized: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" } },
    current_stage: "tested",
    is_stuck: false,
    stuck_reason: null,
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => clearedRepo })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        stages: [
          { name: "DEV", status: "succeeded", pending_approval_description: null },
          { name: "QA", status: "succeeded", pending_approval_description: null },
          { name: "UAT", status: "waiting_approval", pending_approval_description: "Needs sign-off" },
          { name: "Prod", status: "not_started", pending_approval_description: null },
        ],
      }),
    });
  vi.stubGlobal("fetch", fetchMock);

  renderAtRepo("2");

  await waitFor(() => expect(screen.getByText("checkout-web-piped")).toBeInTheDocument());
  const pipedCard = screen.getByText("PI-01").closest("div.rounded-xl") as HTMLElement;
  expect(within(pipedCard).getByText("Cleared")).toBeInTheDocument();

  await waitFor(() => expect(screen.getByText(/Needs sign-off/)).toBeInTheDocument());
});
```

Add `import userEvent from "@testing-library/user-event";` to the top of the file's existing import block (alongside the `@testing-library/react`, `react-router-dom`, and `vitest` imports already there).

Add this small helper function right after `renderAtRepo`'s definition, since two of the new tests need to open a specific card's details toggle:

```tsx
async function clickDetails(cardElement: HTMLElement) {
  const user = userEvent.setup();
  await user.click(within(cardElement).getByRole("button", { name: /details/i }));
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- JourneyPage.test.tsx`
Expected: FAIL — Piped card still hardcoded `Locked` regardless of `PIPED_REPO`'s data; no third fetch call is made

- [ ] **Step 3: Update `src/pages/JourneyPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useRepo } from "../hooks/useRepo";
import { usePipelineStatus } from "../hooks/usePipelineStatus";
import { ConvergenceDiagram } from "../components/journey/ConvergenceDiagram";
import { StationCard } from "../components/journey/StationCard";
import { RepoFieldsForm } from "../components/journey/RepoFieldsForm";
import { PipelineStatusPanel } from "../components/journey/PipelineStatusPanel";
import { OnboardingLog } from "../components/journey/OnboardingLog";
import type { PipelineStageStatusOut, RepoOut } from "../api/types";

const STANDARDIZED_KEYS = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];
const STANDARDIZED_CHECK_ORDER = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];

const PIPED_CHECK_ORDER = ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized", "deployed_aca"];
const PIPED_CHECK_LABELS: Record<string, string> = {
  pipeline_linked: "Pipeline linked",
  pipeline_is_yaml: "YAML pipeline",
  environment_gates_configured: "Environment gates",
  dockerized: "Dockerized",
  deployed_aca: "Deployed to ACA",
};
const PIPED_BLOCKING_KEYS = ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized"];
const DEPLOY_STAGE_NAMES = ["DEV", "QA", "UAT", "Prod"];

function fractionPassing(stages: Record<string, { status: string }>, keys: string[]): number {
  if (keys.length === 0) return 0;
  const passing = keys.filter((k) => stages[k]?.status === "pass").length;
  return passing / keys.length;
}

// Picks the most relevant Standardized sub-check to show in the card's Details panel: when the
// repo is stuck at the Standardized stage, surface whichever sub-check is actually failing
// (in a fixed priority order) instead of always defaulting to codeowners_assigned, so the
// Details panel matches the badge's "You are here" state.
function primaryStandardizedCheck(repo: RepoOut) {
  if (repo.is_stuck && repo.current_stage === "standardized") {
    const failingKey = STANDARDIZED_CHECK_ORDER.find((key) => repo.stages[key]?.status === "fail");
    if (failingKey) return repo.stages[failingKey];
  }
  return repo.stages.codeowners_assigned;
}

function pipelineLinked(repo: RepoOut): boolean {
  return repo.stages.pipeline_linked?.status === "pass";
}

function pipedBadge(repo: RepoOut): "Cleared" | "You are here" | "Locked" {
  if (!pipelineLinked(repo)) return "Locked";
  const allBlockingPass = PIPED_BLOCKING_KEYS.every((key) => repo.stages[key]?.status === "pass");
  return allBlockingPass ? "Cleared" : "You are here";
}

function pipedChecks(repo: RepoOut) {
  return PIPED_CHECK_ORDER.map((key) => ({ label: PIPED_CHECK_LABELS[key], check: repo.stages[key] }));
}

function pipelineProgressFraction(stages: PipelineStageStatusOut[] | null): number {
  if (!stages) return 0;
  const relevant = stages.filter((s) => DEPLOY_STAGE_NAMES.includes(s.name));
  if (relevant.length === 0) return 0;
  return relevant.filter((s) => s.status === "succeeded").length / relevant.length;
}

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  const { repo: fetchedRepo, loading, error } = useRepo(Number(id));
  const [repo, setRepo] = useState<RepoOut | null>(null);

  useEffect(() => {
    if (fetchedRepo) setRepo(fetchedRepo);
  }, [fetchedRepo]);

  const linked = repo ? pipelineLinked(repo) : false;
  const { stages: pipelineStages, loading: pipelineLoading, error: pipelineError } = usePipelineStatus(
    repo?.id ?? 0,
    linked
  );

  if (loading) {
    return (
      <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk p-8">
        Loading…
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk p-8">
        {error ?? "Repo not found"}
      </div>
    );
  }

  const standardsProgress = fractionPassing(repo.stages, ["migrated_from_ado", ...STANDARDIZED_KEYS]);
  const pipelineProgress = pipelineProgressFraction(pipelineStages);

  return (
    <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk max-w-[760px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Status
      </div>
      <h1 className="font-display text-[clamp(36px,7vw,56px)] font-extrabold tracking-tight mb-8">
        {repo.name}
      </h1>

      <ConvergenceDiagram standardsProgress={standardsProgress} pipelineProgress={pipelineProgress} testingProgress={0} />

      <div className="mt-8 flex flex-col gap-4">
        <StationCard
          code="ON-01"
          title="Onboarded"
          description="The repo now lives on GitHub and no longer exists in Azure DevOps."
          badge={
            repo.current_stage === "onboarded"
              ? "You are here"
              : repo.stages.migrated_from_ado?.status === "pass"
                ? "Cleared"
                : "You are here"
          }
          trackColor="#A79AE8"
          check={repo.stages.migrated_from_ado}
        />
        <StationCard
          code="ST-01"
          title="Standardized"
          description="Repo hygiene, ownership, and access controls are in place."
          badge={
            repo.current_stage === "standardized" && repo.is_stuck
              ? "You are here"
              : repo.current_stage === "onboarded"
                ? "Locked"
                : "Cleared"
          }
          trackColor="#A79AE8"
          check={primaryStandardizedCheck(repo)}
          lockedNote={repo.current_stage === "onboarded" ? "Not started. Unlocks once Onboarded clears." : undefined}
        />
        <StationCard
          code="PI-01"
          title="Piped"
          description="Azure Pipelines is wired up and the YAML pipeline deploys cleanly through every environment."
          badge={pipedBadge(repo)}
          trackColor="#3FBBA0"
          checks={pipedChecks(repo)}
          lockedNote={!linked ? "Not live yet — unlocks once a pipeline is linked in Azure DevOps." : undefined}
        />
        <StationCard
          code="TS-01"
          title="Tested"
          description="Load testing, end-to-end testing, and code coverage all clear."
          badge="Locked"
          trackColor="#E7975C"
          lockedNote="Not live yet — unlocks once the E2E/load connector ships."
        />
        <StationCard
          code="PV-01"
          title="Paved Road"
          description="Every station cleared — this repo ships to prod with no manual gates."
          badge="Locked"
          trackColor="#EFC24B"
          lockedNote="Not started. Unlocks once Piped and Tested both ship."
        />
      </div>

      {repo.is_stuck && repo.stuck_reason ? (
        <div className="mt-6 rounded-lg border border-track3/40 bg-track3/10 text-track3 p-3 text-[13px]">
          {repo.stuck_reason}
        </div>
      ) : null}

      <div className="mt-8">
        <RepoFieldsForm repo={repo} onUpdated={setRepo} />
        {linked ? (
          <PipelineStatusPanel stages={pipelineStages} loading={pipelineLoading} error={pipelineError} />
        ) : null}
        <OnboardingLog repoId={repo.id} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- JourneyPage.test.tsx`
Expected: PASS (all tests, including the 4 pre-existing ones)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/pages/JourneyPage.tsx frontend/tests/pages/JourneyPage.test.tsx
git commit -m "feat: wire the Piped card, live pipeline panel, and ConvergenceDiagram to real data"
```

---

### Task 6: `RepoFieldsForm` — `dockerize_eligible` field

**Files:**
- Modify: `frontend/src/components/journey/RepoFieldsForm.tsx`
- Modify: `frontend/tests/components/journey/RepoFieldsForm.test.tsx`

**Interfaces:**
- Consumes: `RepoOut.dockerize_eligible`/`RepoPatchIn.dockerize_eligible` (Task 2, backed by Task 1's real data).
- Produces: a `dockerize_eligible` `<select>` control, pre-filled from `repo.dockerize_eligible`, submitted only when the user has explicitly picked "Eligible" or "Not eligible" (never re-submitted while left at "Not yet assessed" — same omit-if-unset convention the backend's `PATCH` already uses for every other field).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/components/journey/RepoFieldsForm.test.tsx`:

```tsx
it("pre-fills the dockerize-eligible select from the repo's current value", () => {
  render(<RepoFieldsForm repo={{ ...REPO, dockerize_eligible: true }} onUpdated={vi.fn()} />);

  expect(screen.getByLabelText(/dockerize eligible/i)).toHaveValue("true");
});

it("defaults the dockerize-eligible select to 'not yet assessed' when the repo has no value", () => {
  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

  expect(screen.getByLabelText(/dockerize eligible/i)).toHaveValue("unset");
});

it("submits dockerize_eligible as a real boolean when changed from unset", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...REPO, dockerize_eligible: true }) });
  vi.stubGlobal("fetch", fetchMock);

  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText(/dockerize eligible/i), "true");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, options] = fetchMock.mock.calls[0];
  expect(JSON.parse(options.body)).toMatchObject({ dockerize_eligible: true });
});

it("omits dockerize_eligible from the PATCH body when left at not-yet-assessed", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPO });
  vi.stubGlobal("fetch", fetchMock);

  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, options] = fetchMock.mock.calls[0];
  expect(JSON.parse(options.body)).not.toHaveProperty("dockerize_eligible");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- RepoFieldsForm.test.tsx`
Expected: FAIL — no element found for label `/dockerize eligible/i`

- [ ] **Step 3: Update `src/components/journey/RepoFieldsForm.tsx`**

```tsx
import { useId, useState } from "react";
import { patchRepo } from "../../api/client";
import type { RepoOut, RepoPatchIn } from "../../api/types";

const WAVE_OPTIONS: { value: RepoOut["migration_wave"]; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "pilot", label: "Pilot" },
  { value: "rolling_out", label: "Rolling out" },
  { value: "migrated", label: "Migrated" },
];

const DOCKERIZE_OPTIONS: { value: "unset" | "true" | "false"; label: string }[] = [
  { value: "unset", label: "Not yet assessed" },
  { value: "true", label: "Eligible" },
  { value: "false", label: "Not eligible" },
];

function dockerizeEligibleToOption(value: boolean | null | undefined): "unset" | "true" | "false" {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unset";
}

export function RepoFieldsForm({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }) {
  const [domain, setDomain] = useState(repo.domain ?? "");
  const [team, setTeam] = useState(repo.team ?? "");
  const [wave, setWave] = useState(repo.migration_wave);
  const [dockerizeEligible, setDockerizeEligible] = useState(dockerizeEligibleToOption(repo.dockerize_eligible));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const domainId = useId();
  const teamId = useId();
  const waveId = useId();
  const dockerizeId = useId();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const body: RepoPatchIn = {
        domain,
        team,
        migration_wave: wave as RepoPatchIn["migration_wave"],
      };
      if (dockerizeEligible !== "unset") {
        body.dockerize_eligible = dockerizeEligible === "true";
      }
      const updated = await patchRepo(repo.id, body);
      onUpdated(updated);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-bg-card border border-card-border rounded-xl p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor={domainId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Domain
        </label>
        <input
          id={domainId}
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={teamId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Team
        </label>
        <input
          id={teamId}
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={waveId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Rollout wave
        </label>
        <select
          id={waveId}
          value={wave}
          onChange={(e) => setWave(e.target.value as RepoOut["migration_wave"])}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        >
          {WAVE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={dockerizeId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Dockerize eligible
        </label>
        <select
          id={dockerizeId}
          value={dockerizeEligible}
          onChange={(e) => setDockerizeEligible(e.target.value as "unset" | "true" | "false")}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        >
          {DOCKERIZE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="bg-gold text-bg font-semibold text-[12px] rounded px-3 py-1.5 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {saved ? <span className="text-[12px] text-track2">Saved</span> : null}
        {error ? <span className="text-[12px] text-track3">{error}</span> : null}
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- RepoFieldsForm.test.tsx`
Expected: PASS (all tests, including the 3 pre-existing ones)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/components/journey/RepoFieldsForm.tsx frontend/tests/components/journey/RepoFieldsForm.test.tsx
git commit -m "feat: add dockerize_eligible field editing to RepoFieldsForm"
```

---

### Task 7: `StationBoard` — Piped becomes a real column

**Files:**
- Modify: `frontend/src/components/fleet/StationBoard.tsx`
- Modify: `frontend/src/lib/format.ts`
- Modify: `frontend/tests/components/fleet/StationBoard.test.tsx`

**Interfaces:**
- Consumes: nothing new — `current_stage: "piped"` is already real backend data.
- Produces: `StationBoard` renders a real `RealColumn` for Piped (`stageKey="piped"`, filtering `current_stage === "piped"`), same as Onboarded/Standardized. Tested and Paved road remain `EmptyColumn`. `STAGE_LABELS` gains `piped: "Piped"` (used by the Repos table's "Clear stage filter" button and anywhere else that looks up a friendly stage name).

- [ ] **Step 1: Write the failing tests**

The existing test `"always shows Piped/Tested/Paved Road as empty with explanatory text"` in `frontend/tests/components/fleet/StationBoard.test.tsx` asserts Piped's `EmptyColumn` message — that assertion becomes false once Piped is real. Replace it with two tests: one confirming Piped groups repos like the other real columns, one confirming Tested/Paved road are still empty placeholders.

Replace:

```tsx
it("always shows Piped/Tested/Paved Road as empty with explanatory text", () => {
  renderBoard([makeRepo({ id: 1, current_stage: "standardized" })]);

  expect(screen.getByText(/unlocks once the CI\/CD connector ships/i)).toBeInTheDocument();
  expect(screen.getByText(/unlocks once the E2E\/load connector ships/i)).toBeInTheDocument();
  expect(screen.getByText(/unlocks once Piped and Tested both ship/i)).toBeInTheDocument();
});
```

with:

```tsx
it("groups a piped repo into a real Piped column", () => {
  renderBoard([makeRepo({ id: 1, name: "piped-repo", current_stage: "piped" })]);

  expect(screen.getByText("piped-repo")).toBeInTheDocument();
});

it("still shows Tested and Paved Road as empty with explanatory text", () => {
  renderBoard([makeRepo({ id: 1, current_stage: "standardized" })]);

  expect(screen.getByText(/unlocks once the E2E\/load connector ships/i)).toBeInTheDocument();
  expect(screen.getByText(/unlocks once Piped and Tested both ship/i)).toBeInTheDocument();
});

it("caps the Piped column at 4 cards and links 'Show all N' to the Repos table filtered by stage", () => {
  const repos = Array.from({ length: 6 }, (_, i) =>
    makeRepo({ id: i + 1, name: `piped-repo-${i + 1}`, current_stage: "piped" })
  );
  renderBoard(repos);

  expect(screen.queryByText("piped-repo-5")).not.toBeInTheDocument();
  const showAllLink = screen.getByRole("link", { name: /show all 6/i });
  expect(showAllLink).toHaveAttribute("href", "/repos?stage=piped");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: FAIL — `piped-repo` isn't rendered anywhere (Piped is still an `EmptyColumn` with a fixed message, not a repo list)

- [ ] **Step 3: Update `src/components/fleet/StationBoard.tsx`**

Replace the `StationBoard` function body:

```tsx
export function StationBoard({ repos }: { repos: RepoOut[] }) {
  // Onboarded/Standardized/Piped are real columns because the backend can produce those
  // current_stage values. Tested/Paved road remain empty placeholders until their own
  // connectors ship — a future phase adding a new stage must also update this component.
  const onboarded = repos.filter((r) => r.current_stage === "onboarded");
  const standardized = repos.filter((r) => r.current_stage === "standardized");
  const piped = repos.filter((r) => r.current_stage === "piped");

  return (
    <div className="flex gap-4 overflow-x-auto pb-3 mb-5">
      <RealColumn code="ON" title="Onboarded" color="#A79AE8" stageKey="onboarded" repos={onboarded} />
      <RealColumn code="ST" title="Standardized" color="#A79AE8" stageKey="standardized" repos={standardized} />
      <RealColumn code="PI" title="Piped" color="#3FBBA0" stageKey="piped" repos={piped} />
      <EmptyColumn
        code="TS"
        title="Tested"
        color="#E7975C"
        message="Not live yet — unlocks once the E2E/load connector ships."
      />
      <EmptyColumn
        code="PV"
        title="Paved road"
        color="#EFC24B"
        message="Not started. Unlocks once Piped and Tested both ship."
      />
    </div>
  );
}
```

- [ ] **Step 4: Update `src/lib/format.ts`**

```typescript
export const STAGE_LABELS: Record<string, string> = {
  onboarded: "Onboarded",
  standardized: "Standardized",
  piped: "Piped",
};
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: PASS (all tests, including the pre-existing ones not replaced above — the "groups repos" and dwell-sort tests use `current_stage: "standardized"`, unaffected)

- [ ] **Step 6: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/components/fleet/StationBoard.tsx frontend/src/lib/format.ts frontend/tests/components/fleet/StationBoard.test.tsx
git commit -m "feat: make Piped a real column on the Fleet station board"
```

---

### Task 8: `RepoTablePage` — Piped check columns

**Files:**
- Modify: `frontend/src/pages/RepoTablePage.tsx`
- Modify: `frontend/tests/pages/RepoTablePage.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CHECK_COLUMNS` gains `pipeline_linked`, `pipeline_is_yaml`, `environment_gates_configured`, `dockerized`, `deployed_aca`, rendered as additional table columns and CSV export columns, consistent with how the existing Standardized-card checks already render there.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/pages/RepoTablePage.test.tsx`:

```tsx
it("renders a column header for each Piped-card check", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({})] }));

  renderTable();

  await waitFor(() => expect(screen.getByText("repo")).toBeInTheDocument());
  ["pipe", "envi", "dock", "depl"].forEach((prefix) => {
    expect(screen.getAllByTitle(new RegExp(`^${prefix}`)).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx`
Expected: FAIL — no `title` attributes matching `pipeline_linked`/`environment_gates_configured`/`dockerized`/`deployed_aca` exist yet

- [ ] **Step 3: Update `src/pages/RepoTablePage.tsx`**

```typescript
const CHECK_COLUMNS = [
  "migrated_from_ado",
  "codeowners_assigned",
  "domain_assigned",
  "branch_protection",
  "readme_present",
  "naming_standardized",
  "pipeline_linked",
  "pipeline_is_yaml",
  "environment_gates_configured",
  "dockerized",
  "deployed_aca",
];
```

(This is the only change — `checkIcon`, the CSV export, and the table header/body rendering all already iterate `CHECK_COLUMNS` generically.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/pages/RepoTablePage.tsx frontend/tests/pages/RepoTablePage.test.tsx
git commit -m "feat: add Piped-card check columns to the Repos table"
```

---

## Self-Review Notes

- **Spec coverage:** Design doc §1 (three gaps) → Tasks 3/5 (checklist mode, panel fetch trigger), Task 5 (pipeline_linked-driven badge). §2 (data layer) → Tasks 1/2. §3 (StationCard) → Task 3. §4 (Piped card) → Task 5. §5 (panel) → Task 4. §6 (ConvergenceDiagram) → Task 5. §7 (RepoFieldsForm) → Task 6. §8 (Fleet/table) → Tasks 7/8. §0/§9 (Tested stays out of scope) — respected in every task, no task touches Tested's hardcoded rendering.
- **Placeholder scan:** no TBD/TODO; every step has runnable code and exact assertions.
- **Type consistency:** `PipelineStageStatusOut`/`PipelineStatusOut` field names checked identical across Tasks 2/4/5. `StationCardProps.checks` shape (`{ label: string; check?: StageCheckOut }[]`) matches exactly between Task 3's definition and Task 5's `pipedChecks()` construction. `usePipelineStatus`'s return shape matches what Task 5 destructures and what Task 4's own test exercises via `PipelineStatusPanel`'s props directly (the hook itself has no standalone test file, per this codebase's existing convention of testing hooks only through their consuming component — exercised end-to-end in Task 5's `JourneyPage` tests).
- **Cross-task ripple risk flagged for implementers:** Task 7's fix to the StationBoard "always empty" test is a deliberate, explained ripple (Piped stops being an `EmptyColumn`), not a mistake — same pattern the backend plans in this project have repeatedly hit when a new real stage/column is introduced. Task 5's `JourneyPage` tests add a third mocked fetch call only for repos where `pipeline_linked` passes; the pre-existing two-call tests (`STUCK_REPO`) are unaffected since that fixture has no `pipeline_linked` key at all (defaults to not-linked, so `usePipelineStatus`'s `enabled` flag stays false and no third call fires) — implementers should verify this explicitly rather than assume it.
