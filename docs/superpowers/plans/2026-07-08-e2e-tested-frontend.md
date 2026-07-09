# E2E Tested Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `docs/superpowers/specs/2026-07-08-e2e-load-testing-frontend-design.md` — the Tested `StationCard` going live, `RepoFieldsForm`'s `e2e_test_plan_id` field, `ConvergenceDiagram`'s `testingProgress` wiring, and Fleet/Repos-table updates. Paved Road stays a hardcoded placeholder throughout (no Track 4 backend exists).

**Architecture:** Almost entirely frontend, following the exact pattern the CI/CD Piped frontend plan (merged, commit `b3a97bd`) already established — Task 1 is a small, isolated backend patch (expose `e2e_test_plan_id` on `RepoOut` — currently write-only via `PATCH`, the same gap `dockerize_eligible` had). Every other task is frontend-only. This plan is smaller than the Piped one: no live endpoint exists for this pillar, so there's no new hook, no new panel, and no new `StationCard` capability — the checklist-rendering mode built for Piped is reused as-is.

**Tech Stack:** Backend: Python/FastAPI/Pydantic (Task 1 only). Frontend: React, TypeScript, Vite, Tailwind, Vitest, `@testing-library/react`/`user-event`.

## Global Constraints

- `e2e_test_plan_id` is typed **optional** in the frontend `RepoOut` interface (`e2e_test_plan_id?: number | null`), not required — matching the `dockerize_eligible` precedent, so no other existing test fixture needs to change.
- Tested's badge is driven directly by `repo.stages.e2e_covered`, never by `current_stage` — same principle Piped's badge already established: `Locked` when `e2e_covered` is `"pending_convention"` or the check is entirely absent, `Cleared` when it's `"pass"`, `You are here` otherwise (covers `"fail"` and `"unknown"`).
- Paved Road stays an untouched hardcoded placeholder in every file this plan modifies — do not flip it to real (there is no Track 4 backend).
- No new live-query hook, panel, or `StationCard` capability — reuse the existing `checks` prop (built for Piped) as-is.
- `ConvergenceDiagram`'s `testingProgress` becomes `repo.stages.e2e_covered?.status === "pass" ? 1 : 0` — a single-key fraction, deliberately excluding `unit_tested`/`integration_tested`/`load_tested` since none of those three can reach `"pass"` this phase.
- Match existing code style exactly — this plan's tasks mirror the Piped plan's tasks almost line-for-line; follow the same Tailwind classes, `useId()` patterns, and omit-if-unset PATCH-body conventions already established.
- Run `cd frontend && npm run build` (tsc + vite build) at the end of every frontend task, not just `npm test`.

---

## File Structure

```
backend/
  app/
    schemas.py                                   # MODIFY: RepoOut gains e2e_test_plan_id
    api/repos.py                                 # MODIFY: _to_repo_out wires it through
  tests/api/test_repos_api.py                    # MODIFY: new assertions

frontend/
  src/
    api/types.ts                                 # MODIFY: e2e_test_plan_id on RepoOut/RepoPatchIn
    pages/JourneyPage.tsx                         # MODIFY: real Tested badge/checklist, testingProgress
    components/journey/RepoFieldsForm.tsx         # MODIFY: e2e_test_plan_id numeric input
    components/fleet/StationBoard.tsx             # MODIFY: Tested becomes a RealColumn
    pages/RepoTablePage.tsx                       # MODIFY: CHECK_COLUMNS gains 4 keys
    lib/format.ts                                 # MODIFY: STAGE_LABELS gains "tested"
  tests/
    pages/JourneyPage.test.tsx                    # MODIFY: real-Tested tests, fix ripple
    components/journey/RepoFieldsForm.test.tsx    # MODIFY: e2e_test_plan_id tests
    components/fleet/StationBoard.test.tsx        # MODIFY: Tested-real-column tests, fix ripple
    pages/RepoTablePage.test.tsx                  # MODIFY: new-column test
```

---

### Task 1: Backend — expose `e2e_test_plan_id` on `RepoOut`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/repos.py`
- Modify: `backend/tests/api/test_repos_api.py`

**Interfaces:**
- Produces: `RepoOut.e2e_test_plan_id: int | None`, populated in `_to_repo_out` from `repo.e2e_test_plan_id`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_repos_api.py`:

```python
def test_repo_out_exposes_e2e_test_plan_id():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    client.patch(f"/repos/{repo_id}", json={"e2e_test_plan_id": 42})
    body = client.get(f"/repos/{repo_id}").json()

    assert body["e2e_test_plan_id"] == 42


def test_repo_out_e2e_test_plan_id_defaults_to_none():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["e2e_test_plan_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v -k e2e_test_plan_id`
Expected: FAIL — `KeyError: 'e2e_test_plan_id'` (the key doesn't exist in the response body yet)

- [ ] **Step 3: Update `app/schemas.py`**

Add `e2e_test_plan_id: int | None` to `RepoOut`, immediately after the existing `dockerize_eligible: bool | None` field:

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
    e2e_test_plan_id: int | None
    stages: dict[str, StageCheckOut]
    current_stage: str
    is_stuck: bool
    dwell_days: int | None
    stuck_reason: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update `_to_repo_out` in `app/api/repos.py`**

Add `e2e_test_plan_id=repo.e2e_test_plan_id,` immediately after the existing `dockerize_eligible=repo.dockerize_eligible,` line in the `RepoOut(...)` construction.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/api/test_repos_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full backend suite and commit**

Run: `cd backend && .venv/bin/python -m pytest`
Expected: all tests pass (124+)

```bash
git add backend/app/schemas.py backend/app/api/repos.py backend/tests/api/test_repos_api.py
git commit -m "feat: expose e2e_test_plan_id on RepoOut"
```

---

### Task 2: Frontend types — `e2e_test_plan_id`

**Files:**
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes: Task 1's `e2e_test_plan_id` field.
- Produces: `RepoOut.e2e_test_plan_id?: number | null`, `RepoPatchIn.e2e_test_plan_id?: number`.

- [ ] **Step 1: Update `src/api/types.ts`**

Add `e2e_test_plan_id?: number | null;` to `RepoOut`, immediately after the existing `dockerize_eligible?: boolean | null;` line. Add `e2e_test_plan_id?: number;` to `RepoPatchIn`, immediately after the existing `dockerize_eligible?: boolean;` line.

This task has no test of its own — it's a pure type addition with no runtime behavior, consumed and exercised by Tasks 3/4/5/6.

- [ ] **Step 2: Run the full frontend build to verify nothing broke**

Run: `cd frontend && npm run build`
Expected: clean, zero errors (this is purely additive to two interfaces both already have optional fields on them)

- [ ] **Step 3: Run the full test suite and commit**

Run: `cd frontend && npm test`
Expected: all 79 tests still pass

```bash
git add frontend/src/api/types.ts
git commit -m "feat: add e2e_test_plan_id to RepoOut and RepoPatchIn types"
```

---

### Task 3: `JourneyPage` — Tested goes live, `ConvergenceDiagram` wiring

**Files:**
- Modify: `frontend/src/pages/JourneyPage.tsx`
- Modify: `frontend/tests/pages/JourneyPage.test.tsx`

**Interfaces:**
- Consumes: `StationCard`'s existing `checks` prop (built for Piped, no changes needed).
- Produces: Tested `StationCard` reflects real badge/checklist state; `ConvergenceDiagram`'s `testingProgress` reflects `e2e_covered`.

- [ ] **Step 1: Write the failing tests**

The existing test `"renders Tested/Paved Road as Locked, and Piped as Locked when the repo has no pipeline link"` still passes unchanged after this task (`STUCK_REPO` has no `e2e_covered` key, so Tested stays Locked by the same "absent → Locked" rule) — but rename it to stay accurate now that Tested is also data-driven, not hardcoded:

Replace:

```tsx
it("renders Tested/Paved Road as Locked, and Piped as Locked when the repo has no pipeline link", async () => {
```

with:

```tsx
it("renders Piped and Tested as Locked when neither is mapped, and Paved Road as always Locked", async () => {
```

(No other change to that test's body.)

Add two new tests:

```tsx
it("shows Tested as 'You are here' with real sub-checks once an E2E Test Plan is mapped but failing", async () => {
  const testedRepo: RepoOut = {
    ...PIPED_REPO,
    id: 3,
    name: "checkout-web-tested",
    stages: {
      ...PIPED_REPO.stages,
      e2e_covered: { status: "fail", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      unit_tested: { status: "pending_convention", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      integration_tested: { status: "pending_convention", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      load_tested: { status: "unknown", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    },
    current_stage: "tested",
    is_stuck: true,
    stuck_reason: "E2E tests failing on the latest run — waiting on Growth team",
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => testedRepo })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ stages: [{ name: "DEV", status: "succeeded", pending_approval_description: null }] }),
    });
  vi.stubGlobal("fetch", fetchMock);

  renderAtRepo("3");

  await waitFor(() => expect(screen.getByText("checkout-web-tested")).toBeInTheDocument());
  const testedCard = screen.getByText("TS-01").closest("div.rounded-xl") as HTMLElement;
  expect(within(testedCard).getByText("You are here")).toBeInTheDocument();

  await clickDetails(testedCard);
  expect(within(testedCard).getByText("Unit tests")).toBeInTheDocument();
});

it("shows Tested as Cleared and wires testingProgress to 1 when e2e_covered passes", async () => {
  const clearedTestedRepo: RepoOut = {
    ...PIPED_REPO,
    id: 4,
    name: "checkout-web-cleared-tested",
    stages: {
      ...PIPED_REPO.stages,
      e2e_covered: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      unit_tested: { status: "pending_convention", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      integration_tested: { status: "pending_convention", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
      load_tested: { status: "unknown", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    },
    current_stage: "tested",
    is_stuck: false,
    stuck_reason: null,
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => clearedTestedRepo })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ stages: [] }) });
  vi.stubGlobal("fetch", fetchMock);

  const { container } = renderAtRepo("4");

  await waitFor(() => expect(screen.getByText("checkout-web-cleared-tested")).toBeInTheDocument());
  const testedCard = screen.getByText("TS-01").closest("div.rounded-xl") as HTMLElement;
  expect(within(testedCard).getByText("Cleared")).toBeInTheDocument();

  const testingLine = container.querySelector('[data-line="testing"]');
  expect(testingLine).toHaveAttribute("stroke-dasharray", "100 100");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- JourneyPage.test.tsx`
Expected: FAIL — Tested card still hardcoded `Locked` regardless of `e2e_covered` data; `ConvergenceDiagram`'s testing line still shows `stroke-dasharray="0 100"`

- [ ] **Step 3: Update `src/pages/JourneyPage.tsx`**

Add these constants right after the existing `PIPED_BLOCKING_KEYS`/`DEPLOY_STAGE_NAMES` constants:

```tsx
const TESTED_CHECK_ORDER = ["e2e_covered", "unit_tested", "integration_tested", "load_tested"];
const TESTED_CHECK_LABELS: Record<string, string> = {
  e2e_covered: "E2E coverage",
  unit_tested: "Unit tests",
  integration_tested: "Integration tests",
  load_tested: "Load tests",
};
```

Add these functions right after the existing `pipelineProgressFraction`:

```tsx
function testedBadge(repo: RepoOut): "Cleared" | "You are here" | "Locked" {
  const status = repo.stages.e2e_covered?.status;
  if (status === "pass") return "Cleared";
  if (!status || status === "pending_convention") return "Locked";
  return "You are here";
}

function testedChecks(repo: RepoOut) {
  return TESTED_CHECK_ORDER.map((key) => ({ label: TESTED_CHECK_LABELS[key], check: repo.stages[key] }));
}
```

Inside the `JourneyPage` function body, right after the existing `const pipelineProgress = pipelineProgressFraction(pipelineStages);` line, add:

```tsx
  const testingProgress = repo.stages.e2e_covered?.status === "pass" ? 1 : 0;
```

Update the `ConvergenceDiagram` element's `testingProgress` prop from the hardcoded `0` to the new variable:

```tsx
      <ConvergenceDiagram standardsProgress={standardsProgress} pipelineProgress={pipelineProgress} testingProgress={testingProgress} />
```

Replace the hardcoded Tested `StationCard`:

```tsx
        <StationCard
          code="TS-01"
          title="Tested"
          description="Load testing, end-to-end testing, and code coverage all clear."
          badge="Locked"
          trackColor="#E7975C"
          lockedNote="Not live yet — unlocks once the E2E/load connector ships."
        />
```

with:

```tsx
        <StationCard
          code="TS-01"
          title="Tested"
          description="End-to-end tests are passing on the latest Azure Test Plans run."
          badge={testedBadge(repo)}
          trackColor="#E7975C"
          checks={testedChecks(repo)}
          lockedNote={testedBadge(repo) === "Locked" ? "Not live yet — unlocks once an E2E Test Plan is mapped." : undefined}
        />
```

Do NOT touch the Onboarded, Standardized, Piped, or Paved Road `StationCard`s, or their helper functions (`fractionPassing`, `primaryStandardizedCheck`, `pipelineLinked`, `pipedBadge`, `pipedChecks`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- JourneyPage.test.tsx`
Expected: PASS (all tests, including the renamed one and the 7 other pre-existing ones)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/pages/JourneyPage.tsx frontend/tests/pages/JourneyPage.test.tsx
git commit -m "feat: wire the Tested card and testingProgress to real e2e_covered data"
```

---

### Task 4: `RepoFieldsForm` — `e2e_test_plan_id` field

**Files:**
- Modify: `frontend/src/components/journey/RepoFieldsForm.tsx`
- Modify: `frontend/tests/components/journey/RepoFieldsForm.test.tsx`

**Interfaces:**
- Consumes: `RepoOut.e2e_test_plan_id`/`RepoPatchIn.e2e_test_plan_id` (Task 2, backed by Task 1's real data).
- Produces: a plain numeric `<input type="number">` control, pre-filled from `repo.e2e_test_plan_id`, submitted only when non-blank (omitted from the PATCH body entirely when left blank).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/components/journey/RepoFieldsForm.test.tsx`:

```tsx
it("pre-fills the E2E test plan ID from the repo's current value", () => {
  render(<RepoFieldsForm repo={{ ...REPO, e2e_test_plan_id: 42 }} onUpdated={vi.fn()} />);

  expect(screen.getByLabelText(/e2e test plan id/i)).toHaveValue(42);
});

it("leaves the E2E test plan ID input blank when the repo has no value", () => {
  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

  expect(screen.getByLabelText(/e2e test plan id/i)).toHaveValue(null);
});

it("submits e2e_test_plan_id as a real number when filled in", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...REPO, e2e_test_plan_id: 42 }) });
  vi.stubGlobal("fetch", fetchMock);

  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
  await user.type(screen.getByLabelText(/e2e test plan id/i), "42");
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, options] = fetchMock.mock.calls[0];
  expect(JSON.parse(options.body)).toMatchObject({ e2e_test_plan_id: 42 });
});

it("omits e2e_test_plan_id from the PATCH body when left blank", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPO });
  vi.stubGlobal("fetch", fetchMock);

  render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: /save/i }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, options] = fetchMock.mock.calls[0];
  expect(JSON.parse(options.body)).not.toHaveProperty("e2e_test_plan_id");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- RepoFieldsForm.test.tsx`
Expected: FAIL — no element found for label `/e2e test plan id/i`

- [ ] **Step 3: Update `src/components/journey/RepoFieldsForm.tsx`**

Add state, right after the existing `dockerizeEligible` state line:

```tsx
  const [e2eTestPlanId, setE2eTestPlanId] = useState(
    repo.e2e_test_plan_id != null ? String(repo.e2e_test_plan_id) : ""
  );
```

Add an id, right after the existing `dockerizeId` line:

```tsx
  const e2eTestPlanIdId = useId();
```

In `handleSubmit`, right after the existing `if (dockerizeEligible !== "unset") { ... }` block and before `const updated = await patchRepo(...)`, add:

```tsx
      if (e2eTestPlanId.trim() !== "") {
        const parsed = Number(e2eTestPlanId);
        if (!Number.isNaN(parsed)) {
          body.e2e_test_plan_id = parsed;
        }
      }
```

Add the new field's JSX, right after the existing "Dockerize eligible" `<div>` block and before the submit-button `<div>`:

```tsx
      <div className="flex flex-col gap-1">
        <label htmlFor={e2eTestPlanIdId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          E2E test plan ID
        </label>
        <input
          id={e2eTestPlanIdId}
          type="number"
          value={e2eTestPlanId}
          onChange={(e) => setE2eTestPlanId(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- RepoFieldsForm.test.tsx`
Expected: PASS (all tests, including the 7 pre-existing ones)

- [ ] **Step 5: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/components/journey/RepoFieldsForm.tsx frontend/tests/components/journey/RepoFieldsForm.test.tsx
git commit -m "feat: add e2e_test_plan_id field editing to RepoFieldsForm"
```

---

### Task 5: `StationBoard` — Tested becomes a real column

**Files:**
- Modify: `frontend/src/components/fleet/StationBoard.tsx`
- Modify: `frontend/src/lib/format.ts`
- Modify: `frontend/tests/components/fleet/StationBoard.test.tsx`

**Interfaces:**
- Consumes: nothing new — `current_stage: "tested"` is already real backend data.
- Produces: `StationBoard` renders a real `RealColumn` for Tested (`stageKey="tested"`, filtering `current_stage === "tested"`), same as Onboarded/Standardized/Piped. Paved road remains `EmptyColumn`. `STAGE_LABELS` gains `tested: "Tested"`.

- [ ] **Step 1: Write the failing tests**

Replace the existing test:

```tsx
it("still shows Tested and Paved Road as empty with explanatory text", () => {
  renderBoard([makeRepo({ id: 1, current_stage: "standardized" })]);

  expect(screen.getByText(/unlocks once the E2E\/load connector ships/i)).toBeInTheDocument();
  expect(screen.getByText(/unlocks once Piped and Tested both ship/i)).toBeInTheDocument();
});
```

with:

```tsx
it("groups a tested repo into a real Tested column", () => {
  renderBoard([makeRepo({ id: 1, name: "tested-repo", current_stage: "tested" })]);

  expect(screen.getByText("tested-repo")).toBeInTheDocument();
});

it("still shows Paved Road as empty with explanatory text", () => {
  renderBoard([makeRepo({ id: 1, current_stage: "standardized" })]);

  expect(screen.getByText(/unlocks once Piped and Tested both ship/i)).toBeInTheDocument();
});

it("caps the Tested column at 4 cards and links 'Show all N' to the Repos table filtered by stage", () => {
  const repos = Array.from({ length: 6 }, (_, i) =>
    makeRepo({ id: i + 1, name: `tested-repo-${i + 1}`, current_stage: "tested" })
  );
  renderBoard(repos);

  expect(screen.queryByText("tested-repo-5")).not.toBeInTheDocument();
  const showAllLink = screen.getByRole("link", { name: /show all 6/i });
  expect(showAllLink).toHaveAttribute("href", "/repos?stage=tested");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: FAIL — `tested-repo` isn't rendered anywhere (Tested is still an `EmptyColumn` with a fixed message)

- [ ] **Step 3: Update `src/components/fleet/StationBoard.tsx`**

Replace the `StationBoard` function body:

```tsx
export function StationBoard({ repos }: { repos: RepoOut[] }) {
  // Onboarded/Standardized/Piped/Tested are real columns because the backend can produce those
  // current_stage values. Paved road remains an empty placeholder — no Track 4 backend exists.
  const onboarded = repos.filter((r) => r.current_stage === "onboarded");
  const standardized = repos.filter((r) => r.current_stage === "standardized");
  const piped = repos.filter((r) => r.current_stage === "piped");
  const tested = repos.filter((r) => r.current_stage === "tested");

  return (
    <div className="flex gap-4 overflow-x-auto pb-3 mb-5">
      <RealColumn code="ON" title="Onboarded" color="#A79AE8" stageKey="onboarded" repos={onboarded} />
      <RealColumn code="ST" title="Standardized" color="#A79AE8" stageKey="standardized" repos={standardized} />
      <RealColumn code="PI" title="Piped" color="#3FBBA0" stageKey="piped" repos={piped} />
      <RealColumn code="TS" title="Tested" color="#E7975C" stageKey="tested" repos={tested} />
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
  tested: "Tested",
};
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: PASS (all tests, including the other pre-existing ones not replaced above)

- [ ] **Step 6: Run the full frontend build and test suite, then commit**

Run: `cd frontend && npm run build && npm test`
Expected: clean

```bash
git add frontend/src/components/fleet/StationBoard.tsx frontend/src/lib/format.ts frontend/tests/components/fleet/StationBoard.test.tsx
git commit -m "feat: make Tested a real column on the Fleet station board"
```

---

### Task 6: `RepoTablePage` — Tested check columns

**Files:**
- Modify: `frontend/src/pages/RepoTablePage.tsx`
- Modify: `frontend/tests/pages/RepoTablePage.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CHECK_COLUMNS` gains `e2e_covered`, `unit_tested`, `integration_tested`, `load_tested`, rendered as additional table columns and CSV export columns.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/pages/RepoTablePage.test.tsx`:

```tsx
it("renders a column header for each Tested-card check", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({})] }));

  renderTable();

  await waitFor(() => expect(screen.getByText("repo")).toBeInTheDocument());
  ["e2e_", "unit", "inte", "load"].forEach((prefix) => {
    expect(screen.getAllByTitle(new RegExp(`^${prefix}`)).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx`
Expected: FAIL — no `title` attributes matching `e2e_covered`/`unit_tested`/`integration_tested`/`load_tested` exist yet

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
  "e2e_covered",
  "unit_tested",
  "integration_tested",
  "load_tested",
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
git commit -m "feat: add Tested-card check columns to the Repos table"
```

---

## Self-Review Notes

- **Spec coverage:** Design doc §1 (two gaps) → Tasks 1/3. §2 (backend) → Task 1. §3 (data layer) → Task 2. §4 (Tested card) → Task 3. §5 (RepoFieldsForm) → Task 4. §6 (Fleet/table) → Tasks 5/6. §7 (out of scope: no live endpoint, no new panel, no new StationCard capability, Paved Road untouched) — respected in every task, none add a hook/panel/StationCard change.
- **Placeholder scan:** no TBD/TODO; every step has runnable code and exact assertions.
- **Type consistency:** `testedBadge`/`testedChecks` mirror `pipedBadge`/`pipedChecks`'s exact shape and signature pattern. `e2e_test_plan_id` typed identically across Task 1 (backend `int | None`) and Task 2 (frontend `number | null`, optional).
- **Cross-task ripple risk flagged for implementers:** Task 3's rename of the "always Locked" test mirrors the exact same ripple the Piped plan's Task 5 hit — implementers should verify the renamed test's body is untouched, only the title string changes. Task 5's `StationBoard` test replacement is the same class of ripple Task 7 of the Piped plan already handled once for Piped; do it again for Tested.
