# Frontend Track 1 Wrap-Up (Manual Editing + Repos Table) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the Repo Standardization pillar's frontend (design spec §7.3 and §7.4) — manual field editing and the onboarding-time log on the Repo Journey page, and the searchable/filterable/exportable Repos table that the Fleet page's "View all" links route to.

**Architecture:** Pure frontend work — no backend changes needed. `PATCH /repos/{id}` (domain/team/migration_wave) and `GET`/`POST /repos/{id}/onboarding-log` already exist and are unused by the frontend today; this plan wires them up. The Repos table fetches the full `GET /repos` result once and does all filtering/sorting/search/CSV-export client-side (no new query params — the real repo count, ~230, makes this the simplest correct choice).

**Tech Stack:** Same as the existing frontend — React 18, TypeScript, Vite, Tailwind, react-router-dom, Vitest + React Testing Library.

## Global Constraints

- **No Dockerization-eligibility field.** An earlier spec draft mentioned it; it was never implemented as a backend column (it belongs to the future Piped card). The only editable fields are `domain`, `team`, `migration_wave` — exactly what `RepoPatchIn` supports.
- **Filtering/sorting/search on the Repos table is entirely client-side.** Fetch once via `useRepos()` with no params; never add new backend query params for this.
- **CSV export is generated client-side** from the currently filtered/sorted rows — no backend export endpoint exists or is needed.
- **The Fleet board's "View all N repos →" now navigates to `/repos?stage=X`**, replacing the client-side in-column expand from the first frontend build. The expand behavior and its test are being removed, not kept alongside.
- Every displayed string comes from real API data — no hardcoded sample data in shipped components.

---

## File Structure

```
frontend/src/
  api/
    types.ts                        # MODIFY: add RepoPatchIn, OnboardingLogIn, OnboardingLogOut, OnboardingSummaryOut
    client.ts                       # MODIFY: add patchRepo, getOnboardingLog, postOnboardingLog
  components/
    journey/
      RepoFieldsForm.tsx             # NEW: domain/team/migration_wave editing form
      OnboardingLog.tsx              # NEW: entries list + median + add-entry form
  pages/
    JourneyPage.tsx                  # MODIFY: render RepoFieldsForm + OnboardingLog below the stations
    RepoTablePage.tsx                # NEW: the searchable/filterable/exportable table
  components/fleet/
    StationBoard.tsx                 # MODIFY: "Show all N" becomes a Link to /repos?stage=X
  App.tsx                            # MODIFY: add the /repos route
frontend/tests/
  api/client.test.ts                 # MODIFY: add tests for the 3 new client functions
  components/journey/
    RepoFieldsForm.test.tsx          # NEW
    OnboardingLog.test.tsx           # NEW
  pages/
    JourneyPage.test.tsx             # MODIFY: cover the new sections
    RepoTablePage.test.tsx           # NEW
  components/fleet/
    StationBoard.test.tsx            # MODIFY: replace expand tests with navigation-link tests
```

---

### Task 1: API client and types for manual editing and onboarding log

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/tests/api/client.test.ts`

**Interfaces:**
- Produces (`types.ts`): `interface RepoPatchIn { domain?: string; team?: string; migration_wave?: "not_started" | "pilot" | "rolling_out" | "migrated" }`, `interface OnboardingLogIn { engineer_name: string; hours: number }`, `interface OnboardingLogOut { id: number; repo_id: number; engineer_name: string; hours: number; logged_at: string }`, `interface OnboardingSummaryOut { entries: OnboardingLogOut[]; median_hours: number | null }`.
- Produces (`client.ts`): `async function patchRepo(id: number, body: RepoPatchIn): Promise<RepoOut>`, `async function getOnboardingLog(id: number): Promise<OnboardingSummaryOut>`, `async function postOnboardingLog(id: number, body: OnboardingLogIn): Promise<OnboardingLogOut>` — all three throw a descriptive `Error` including the HTTP status on a non-OK response, matching the existing `listRepos`/`getRepo` pattern exactly.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/api/client.test.ts` (keep all existing tests):

```typescript
import { getOnboardingLog, getRepo, listRepos, patchRepo, postOnboardingLog } from "../../src/api/client";

// ... (existing SAMPLE_REPO and describe blocks stay as-is) ...

describe("patchRepo", () => {
  it("sends a PATCH with the body as JSON and returns the updated repo", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => SAMPLE_REPO });
    vi.stubGlobal("fetch", fetchMock);

    const repo = await patchRepo(1, { domain: "Growth", team: "Growth" });

    expect(repo).toEqual(SAMPLE_REPO);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/repos\/1$/);
    expect(options.method).toBe("PATCH");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ domain: "Growth", team: "Growth" });
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));

    await expect(patchRepo(1, { domain: "Growth" })).rejects.toThrow(/422/);
  });
});

describe("getOnboardingLog", () => {
  it("fetches the onboarding log summary for a repo", async () => {
    const summary = { entries: [], median_hours: null };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => summary });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getOnboardingLog(1);

    expect(result).toEqual(summary);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1\/onboarding-log$/);
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    await expect(getOnboardingLog(999)).rejects.toThrow(/404/);
  });
});

describe("postOnboardingLog", () => {
  it("sends a POST with the entry as JSON and returns the created entry", async () => {
    const entry = { id: 1, repo_id: 1, engineer_name: "Sam", hours: 4.5, logged_at: "2026-07-08T00:00:00Z" };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => entry });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOnboardingLog(1, { engineer_name: "Sam", hours: 4.5 });

    expect(result).toEqual(entry);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/repos\/1\/onboarding-log$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ engineer_name: "Sam", hours: 4.5 });
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(postOnboardingLog(1, { engineer_name: "Sam", hours: 4.5 })).rejects.toThrow(/500/);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- client.test.ts`
Expected: FAIL — `patchRepo`/`getOnboardingLog`/`postOnboardingLog` don't exist yet

- [ ] **Step 3: Add the types to `types.ts`**

```typescript
// frontend/src/api/types.ts — append
export interface RepoPatchIn {
  domain?: string;
  team?: string;
  migration_wave?: "not_started" | "pilot" | "rolling_out" | "migrated";
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
```

- [ ] **Step 4: Add the functions to `client.ts`**

```typescript
// frontend/src/api/client.ts — add import and functions
import type {
  ListReposParams,
  OnboardingLogIn,
  OnboardingLogOut,
  OnboardingSummaryOut,
  RepoOut,
  RepoPatchIn,
} from "./types";

export async function patchRepo(id: number, body: RepoPatchIn): Promise<RepoOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Failed to update repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}

export async function getOnboardingLog(id: number): Promise<OnboardingSummaryOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}/onboarding-log`);
  if (!response.ok) {
    throw new Error(`Failed to get onboarding log for repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}

export async function postOnboardingLog(id: number, body: OnboardingLogIn): Promise<OnboardingLogOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}/onboarding-log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Failed to log onboarding time for repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- client.test.ts`
Expected: PASS (all tests — prior 5 + 6 new)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/tests/api/client.test.ts
git commit -m "feat: add API client support for repo PATCH and onboarding log endpoints"
```

---

### Task 2: Manual fields editing form on the Journey page

**Files:**
- Create: `frontend/src/components/journey/RepoFieldsForm.tsx`
- Create: `frontend/tests/components/journey/RepoFieldsForm.test.tsx`
- Modify: `frontend/src/pages/JourneyPage.tsx`
- Modify: `frontend/tests/pages/JourneyPage.test.tsx`

**Interfaces:**
- Consumes: `RepoOut`, `RepoPatchIn`, `patchRepo` (Task 1).
- Produces: `function RepoFieldsForm({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }): JSX.Element` — a form with a text input for `domain`, a text input for `team`, and a `<select>` for `migration_wave` (options: Not started/Pilot/Rolling out/Migrated). On submit, calls `patchRepo(repo.id, { domain, team, migration_wave })`, and on success calls `onUpdated(updatedRepo)` and shows a brief "Saved" confirmation; on failure shows an inline error message without losing the user's edits.
- `JourneyPage` is modified to hold `repo` as local state (synced from `useRepo`'s result via `useEffect`) so `RepoFieldsForm`'s `onUpdated` callback can update what's displayed without a full page refetch.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/tests/components/journey/RepoFieldsForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RepoFieldsForm } from "../../../src/components/journey/RepoFieldsForm";
import type { RepoOut } from "../../../src/api/types";

const REPO: RepoOut = {
  id: 1,
  name: "checkout-web",
  domain: "Growth",
  team: "Growth",
  migration_wave: "pilot",
  github_url: "https://github.com/acme/checkout-web",
  last_synced_at: null,
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RepoFieldsForm", () => {
  it("pre-fills the form with the repo's current field values", () => {
    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/domain/i)).toHaveValue("Growth");
    expect(screen.getByLabelText(/team/i)).toHaveValue("Growth");
    expect(screen.getByLabelText(/wave/i)).toHaveValue("pilot");
  });

  it("submits the edited fields via patchRepo and calls onUpdated with the result", async () => {
    const user = userEvent.setup();
    const updatedRepo = { ...REPO, domain: "Checkout" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => updatedRepo }));
    const onUpdated = vi.fn();

    render(<RepoFieldsForm repo={REPO} onUpdated={onUpdated} />);
    await user.clear(screen.getByLabelText(/domain/i));
    await user.type(screen.getByLabelText(/domain/i), "Checkout");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepo));
    expect(screen.getByText(/saved/i)).toBeInTheDocument();
  });

  it("shows an inline error and preserves the edit if the save fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.clear(screen.getByLabelText(/domain/i));
    await user.type(screen.getByLabelText(/domain/i), "Checkout");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/422/)).toBeInTheDocument());
    expect(screen.getByLabelText(/domain/i)).toHaveValue("Checkout");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- RepoFieldsForm.test.tsx`
Expected: FAIL with `Cannot find module '../../../src/components/journey/RepoFieldsForm'`

- [ ] **Step 3: Implement `RepoFieldsForm.tsx`**

```tsx
// frontend/src/components/journey/RepoFieldsForm.tsx
import { useId, useState } from "react";
import { patchRepo } from "../../api/client";
import type { RepoOut } from "../../api/types";

const WAVE_OPTIONS: { value: RepoOut["migration_wave"]; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "pilot", label: "Pilot" },
  { value: "rolling_out", label: "Rolling out" },
  { value: "migrated", label: "Migrated" },
];

export function RepoFieldsForm({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }) {
  const [domain, setDomain] = useState(repo.domain ?? "");
  const [team, setTeam] = useState(repo.team ?? "");
  const [wave, setWave] = useState(repo.migration_wave);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const domainId = useId();
  const teamId = useId();
  const waveId = useId();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await patchRepo(repo.id, {
        domain,
        team,
        migration_wave: wave as RepoOut["migration_wave"],
      });
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

- [ ] **Step 4: Wire `RepoFieldsForm` into `JourneyPage.tsx`**

Replace the `useRepo` usage with local state that syncs from it:

```tsx
// frontend/src/pages/JourneyPage.tsx — add imports
import { useEffect, useState } from "react";
import { RepoFieldsForm } from "../components/journey/RepoFieldsForm";
```

Replace:
```tsx
  const { id } = useParams<{ id: string }>();
  const { repo, loading, error } = useRepo(Number(id));
```
with:
```tsx
  const { id } = useParams<{ id: string }>();
  const { repo: fetchedRepo, loading, error } = useRepo(Number(id));
  const [repo, setRepo] = useState<RepoOut | null>(null);

  useEffect(() => {
    if (fetchedRepo) setRepo(fetchedRepo);
  }, [fetchedRepo]);
```

Add, right after the closing `</div>` of the stuck-reason banner block (still inside the outermost page `<div>`):

```tsx
      <div className="mt-8">
        <RepoFieldsForm repo={repo} onUpdated={setRepo} />
      </div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — existing `JourneyPage.test.tsx` tests still pass unchanged (the form is additive; if any existing test's fixture data causes a TypeScript/runtime issue from the new `repo` local-state indirection, fix the test to still work with the same assertions, not different ones)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/journey/RepoFieldsForm.tsx frontend/src/pages/JourneyPage.tsx frontend/tests/components/journey/RepoFieldsForm.test.tsx frontend/tests/pages/JourneyPage.test.tsx
git commit -m "feat: add manual domain/team/migration_wave editing form to Repo Journey page"
```

---

### Task 3: Onboarding log section on the Journey page

**Files:**
- Create: `frontend/src/components/journey/OnboardingLog.tsx`
- Create: `frontend/tests/components/journey/OnboardingLog.test.tsx`
- Modify: `frontend/src/pages/JourneyPage.tsx`

**Interfaces:**
- Consumes: `OnboardingSummaryOut`, `OnboardingLogIn`, `getOnboardingLog`, `postOnboardingLog` (Task 1).
- Produces: `function OnboardingLog({ repoId }: { repoId: number }): JSX.Element` — fetches the summary on mount, shows the median (or "No entries logged yet" if `median_hours` is `null`), lists entries (engineer, hours, date), and a small form (engineer name text input + hours number input + "Log" button) that posts a new entry and refetches the summary on success.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/components/journey/OnboardingLog.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OnboardingLog } from "../../../src/components/journey/OnboardingLog";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OnboardingLog", () => {
  it("shows a no-entries message when the summary is empty", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ entries: [], median_hours: null }) }));

    render(<OnboardingLog repoId={1} />);

    await waitFor(() => expect(screen.getByText(/no entries logged yet/i)).toBeInTheDocument());
  });

  it("shows the median and lists entries once loaded", async () => {
    const summary = {
      entries: [
        { id: 1, repo_id: 1, engineer_name: "Sam", hours: 4, logged_at: "2026-07-01T00:00:00Z" },
        { id: 2, repo_id: 1, engineer_name: "Alex", hours: 8, logged_at: "2026-07-02T00:00:00Z" },
      ],
      median_hours: 6,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => summary }));

    render(<OnboardingLog repoId={1} />);

    await waitFor(() => expect(screen.getByText(/6/)).toBeInTheDocument());
    expect(screen.getByText("Sam")).toBeInTheDocument();
    expect(screen.getByText("Alex")).toBeInTheDocument();
  });

  it("logs a new entry and refetches the summary", async () => {
    const user = userEvent.setup();
    const emptySummary = { entries: [], median_hours: null };
    const afterPostSummary = {
      entries: [{ id: 1, repo_id: 1, engineer_name: "Jo", hours: 5, logged_at: "2026-07-08T00:00:00Z" }],
      median_hours: 5,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => emptySummary }) // initial load
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, repo_id: 1, engineer_name: "Jo", hours: 5, logged_at: "2026-07-08T00:00:00Z" }) }) // POST
      .mockResolvedValueOnce({ ok: true, json: async () => afterPostSummary }); // refetch
    vi.stubGlobal("fetch", fetchMock);

    render(<OnboardingLog repoId={1} />);
    await waitFor(() => expect(screen.getByText(/no entries logged yet/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/engineer/i), "Jo");
    await user.type(screen.getByLabelText(/hours/i), "5");
    await user.click(screen.getByRole("button", { name: /log/i }));

    await waitFor(() => expect(screen.getByText("Jo")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- OnboardingLog.test.tsx`
Expected: FAIL with `Cannot find module '../../../src/components/journey/OnboardingLog'`

- [ ] **Step 3: Implement `OnboardingLog.tsx`**

```tsx
// frontend/src/components/journey/OnboardingLog.tsx
import { useEffect, useId, useState } from "react";
import { getOnboardingLog, postOnboardingLog } from "../../api/client";
import type { OnboardingSummaryOut } from "../../api/types";

export function OnboardingLog({ repoId }: { repoId: number }) {
  const [summary, setSummary] = useState<OnboardingSummaryOut | null>(null);
  const [engineerName, setEngineerName] = useState("");
  const [hours, setHours] = useState("");
  const engineerId = useId();
  const hoursId = useId();

  function refetch() {
    getOnboardingLog(repoId).then(setSummary);
  }

  useEffect(() => {
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await postOnboardingLog(repoId, { engineer_name: engineerName, hours: Number(hours) });
    setEngineerName("");
    setHours("");
    refetch();
  }

  if (!summary) return null;

  return (
    <div className="bg-bg-card border border-card-border rounded-xl p-4 mt-4">
      <div className="font-mono text-[10.5px] text-chalk-dim uppercase mb-2">Onboarding time</div>
      {summary.median_hours === null ? (
        <p className="text-[13px] text-chalk-dim mb-3">No entries logged yet.</p>
      ) : (
        <p className="text-[13px] text-chalk mb-3">
          Median: <span className="font-mono">{summary.median_hours}</span> hrs ({summary.entries.length} entries)
        </p>
      )}
      <div className="flex flex-col gap-1 mb-3">
        {summary.entries.map((entry) => (
          <div key={entry.id} className="flex justify-between text-[12.5px] text-chalk-dim">
            <span>{entry.engineer_name}</span>
            <span className="font-mono">{entry.hours} hrs</span>
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={engineerId} className="font-mono text-[10px] text-chalk-dim">
            Engineer
          </label>
          <input
            id={engineerId}
            value={engineerName}
            onChange={(e) => setEngineerName(e.target.value)}
            className="bg-bg border border-card-border rounded px-2 py-1 text-[12px] text-chalk w-28"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={hoursId} className="font-mono text-[10px] text-chalk-dim">
            Hours
          </label>
          <input
            id={hoursId}
            type="number"
            step="0.5"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className="bg-bg border border-card-border rounded px-2 py-1 text-[12px] text-chalk w-16"
          />
        </div>
        <button type="submit" className="bg-gold text-bg font-semibold text-[12px] rounded px-3 py-1.5">
          Log
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Wire `OnboardingLog` into `JourneyPage.tsx`**

```tsx
// frontend/src/pages/JourneyPage.tsx — add import
import { OnboardingLog } from "../components/journey/OnboardingLog";
```

Add immediately after the `<RepoFieldsForm .../>` block added in Task 2:

```tsx
      <OnboardingLog repoId={repo.id} />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/journey/OnboardingLog.tsx frontend/src/pages/JourneyPage.tsx frontend/tests/components/journey/OnboardingLog.test.tsx
git commit -m "feat: add onboarding-time log section to Repo Journey page"
```

---

### Task 4: Repos table page — core structure, filters, search

**Files:**
- Create: `frontend/src/pages/RepoTablePage.tsx`
- Create: `frontend/tests/pages/RepoTablePage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `RepoOut`, `useRepos` (existing), `STAGE_LABELS` (existing, from `lib/format.ts`).
- Produces: `RepoTablePage` rendered at route `/repos`. Fetches all repos once via `useRepos()`. Client-side state: `domainFilter: string` ("" = all), `waveFilter: string` ("" = all), `search: string` (matches repo name, case-insensitive substring). Renders a table with columns: Name (a `Link` to `/repos/{id}`), Domain, Team, Wave, Current Stage (via `STAGE_LABELS`), Dwell, and one column per stage key (`migrated_from_ado`, `codeowners_assigned`, `domain_assigned`, `branch_protection`, `readme_present`, `naming_standardized`) showing `✓`/`✗`/`?` for pass/fail/anything else.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/tests/pages/RepoTablePage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RepoTablePage } from "../../src/pages/RepoTablePage";
import type { RepoOut } from "../../src/api/types";

function makeRepo(overrides: Partial<RepoOut>): RepoOut {
  return {
    id: 1,
    name: "repo",
    domain: "Growth",
    team: "Growth",
    migration_wave: "not_started",
    github_url: "https://github.com/acme/repo",
    last_synced_at: null,
    stages: {
      migrated_from_ado: { status: "pass", source: "auto", detail: null, updated_at: null },
      codeowners_assigned: { status: "fail", source: "auto", detail: null, updated_at: null },
    },
    current_stage: "standardized",
    is_stuck: true,
    dwell_days: 10,
    stuck_reason: "reason",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderTable(initialEntries = ["/repos"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <RepoTablePage />
    </MemoryRouter>
  );
}

describe("RepoTablePage", () => {
  it("renders one row per repo with a link to its Journey page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({ id: 42, name: "checkout-web" })] })
    );

    renderTable();

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /checkout-web/i })).toHaveAttribute("href", "/repos/42");
  });

  it("shows pass/fail icons for each stage check column", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({})] }));

    renderTable();

    await waitFor(() => expect(screen.getAllByText("✓").length).toBeGreaterThan(0));
    expect(screen.getAllByText("✗").length).toBeGreaterThan(0);
  });

  it("filters by domain", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          makeRepo({ id: 1, name: "growth-repo", domain: "Growth" }),
          makeRepo({ id: 2, name: "platform-repo", domain: "Platform" }),
        ],
      })
    );

    renderTable();
    await waitFor(() => expect(screen.getByText("growth-repo")).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText(/domain/i), "Platform");

    expect(screen.queryByText("growth-repo")).not.toBeInTheDocument();
    expect(screen.getByText("platform-repo")).toBeInTheDocument();
  });

  it("filters by name search", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [makeRepo({ id: 1, name: "checkout-web" }), makeRepo({ id: 2, name: "payments-api" })],
      })
    );

    renderTable();
    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());

    await user.type(screen.getByLabelText(/search/i), "checkout");

    expect(screen.getByText("checkout-web")).toBeInTheDocument();
    expect(screen.queryByText("payments-api")).not.toBeInTheDocument();
  });

  it("pre-selects the stage filter from the ?stage= URL param", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          makeRepo({ id: 1, name: "onboarded-repo", current_stage: "onboarded" }),
          makeRepo({ id: 2, name: "standardized-repo", current_stage: "standardized" }),
        ],
      })
    );

    renderTable(["/repos?stage=onboarded"]);

    await waitFor(() => expect(screen.getByText("onboarded-repo")).toBeInTheDocument());
    expect(screen.queryByText("standardized-repo")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx`
Expected: FAIL with `Cannot find module '../../src/pages/RepoTablePage'`

- [ ] **Step 3: Implement `RepoTablePage.tsx`**

```tsx
// frontend/src/pages/RepoTablePage.tsx
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRepos } from "../hooks/useRepos";
import { STAGE_LABELS, formatDwell } from "../lib/format";
import type { RepoOut } from "../api/types";

const CHECK_COLUMNS = [
  "migrated_from_ado",
  "codeowners_assigned",
  "domain_assigned",
  "branch_protection",
  "readme_present",
  "naming_standardized",
];

function checkIcon(status: string | undefined): string {
  if (status === "pass") return "✓";
  if (status === "fail") return "✗";
  return "?";
}

export function RepoTablePage() {
  const { repos } = useRepos();
  const [searchParams] = useSearchParams();
  const [stageFilter, setStageFilter] = useState(searchParams.get("stage") ?? "");
  const [domainFilter, setDomainFilter] = useState("");
  const [waveFilter, setWaveFilter] = useState("");
  const [search, setSearch] = useState("");

  const domains = useMemo(() => Array.from(new Set(repos.map((r) => r.domain).filter(Boolean))) as string[], [repos]);

  const filtered = repos.filter((r) => {
    if (stageFilter && r.current_stage !== stageFilter) return false;
    if (domainFilter && r.domain !== domainFilter) return false;
    if (waveFilter && r.migration_wave !== waveFilter) return false;
    if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <h1 className="font-display text-[28px] font-extrabold mb-6">Repos</h1>

      <div className="flex gap-3 mb-4">
        <div>
          <label htmlFor="domain-filter" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Domain
          </label>
          <select
            id="domain-filter"
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          >
            <option value="">All domains</option>
            {domains.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="wave-filter" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Wave
          </label>
          <select
            id="wave-filter"
            value={waveFilter}
            onChange={(e) => setWaveFilter(e.target.value)}
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          >
            <option value="">All waves</option>
            <option value="not_started">Not started</option>
            <option value="pilot">Pilot</option>
            <option value="rolling_out">Rolling out</option>
            <option value="migrated">Migrated</option>
          </select>
        </div>
        <div>
          <label htmlFor="name-search" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Search
          </label>
          <input
            id="name-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name…"
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          />
        </div>
      </div>

      {stageFilter ? (
        <button
          type="button"
          onClick={() => setStageFilter("")}
          className="mb-4 font-mono text-[11px] text-chalk-dim underline"
        >
          Clear stage filter: {STAGE_LABELS[stageFilter] ?? stageFilter} ×
        </button>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full text-[12px] border-collapse">
          <thead>
            <tr className="text-left text-chalk-dim font-mono text-[10.5px] uppercase border-b border-card-border">
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">Domain</th>
              <th className="py-2 pr-3">Team</th>
              <th className="py-2 pr-3">Wave</th>
              <th className="py-2 pr-3">Stage</th>
              <th className="py-2 pr-3">Dwell</th>
              {CHECK_COLUMNS.map((key) => (
                <th key={key} className="py-2 pr-3" title={key}>
                  {key.slice(0, 4)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((repo) => (
              <tr key={repo.id} className="border-b border-card-border">
                <td className="py-2 pr-3">
                  <Link to={`/repos/${repo.id}`} className="text-gold hover:underline">
                    {repo.name}
                  </Link>
                </td>
                <td className="py-2 pr-3">{repo.domain ?? "—"}</td>
                <td className="py-2 pr-3">{repo.team ?? "—"}</td>
                <td className="py-2 pr-3">{repo.migration_wave}</td>
                <td className="py-2 pr-3">{STAGE_LABELS[repo.current_stage] ?? repo.current_stage}</td>
                <td className="py-2 pr-3 font-mono">{formatDwell(repo.dwell_days)}</td>
                {CHECK_COLUMNS.map((key) => (
                  <td key={key} className="py-2 pr-3 text-center">
                    {checkIcon(repo.stages[key]?.status)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add the route to `App.tsx`**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { FleetPage } from "./pages/FleetPage";
import { JourneyPage } from "./pages/JourneyPage";
import { RepoTablePage } from "./pages/RepoTablePage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<FleetPage />} />
      <Route path="/repos" element={<RepoTablePage />} />
      <Route path="/repos/:id" element={<JourneyPage />} />
    </Routes>
  );
}
```

(Keep the rest of `App.tsx` — the `useMemoryRouter` prop logic — unchanged.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/RepoTablePage.tsx frontend/src/App.tsx frontend/tests/pages/RepoTablePage.test.tsx
git commit -m "feat: add searchable/filterable Repos table page"
```

---

### Task 5: Repos table — sort and CSV export

**Files:**
- Modify: `frontend/src/pages/RepoTablePage.tsx`
- Modify: `frontend/tests/pages/RepoTablePage.test.tsx`

**Interfaces:**
- Produces: the filtered table rows are sorted stuck-first/longest-dwell-first before rendering (same ordering rule as the Fleet page's stuck panel and station board columns — reused as a local function in this file, not shared as a module, matching this codebase's established "small local duplication over premature abstraction" pattern). Produces an "Export CSV" button that builds a CSV string from the currently filtered+sorted rows and triggers a browser download via a `Blob` + temporary `<a>` element.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/tests/pages/RepoTablePage.test.tsx — add these tests
it("sorts rows stuck-first, longest-dwelling-first", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        makeRepo({ id: 1, name: "short-stuck", is_stuck: true, dwell_days: 5 }),
        makeRepo({ id: 2, name: "long-stuck", is_stuck: true, dwell_days: 40 }),
        makeRepo({ id: 3, name: "not-stuck", is_stuck: false, dwell_days: null }),
      ],
    })
  );

  renderTable();
  await waitFor(() => expect(screen.getByText("short-stuck")).toBeInTheDocument());

  const rows = screen.getAllByRole("row").slice(1); // skip header row
  const names = rows.map((row) => row.textContent);
  const longIndex = names.findIndex((t) => t?.includes("long-stuck"));
  const shortIndex = names.findIndex((t) => t?.includes("short-stuck"));
  const notStuckIndex = names.findIndex((t) => t?.includes("not-stuck"));
  expect(longIndex).toBeLessThan(shortIndex);
  expect(shortIndex).toBeLessThan(notStuckIndex);
});

it("exports the currently filtered rows as a CSV download", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({ id: 1, name: "checkout-web" })] })
  );
  const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });

  renderTable();
  await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());

  await user.click(screen.getByRole("button", { name: /export csv/i }));

  expect(createObjectURL).toHaveBeenCalledTimes(1);
  const blob = createObjectURL.mock.calls[0][0] as Blob;
  const text = await blob.text();
  expect(text).toContain("checkout-web");
  expect(text.split("\n")[0]).toContain("Name");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx -t "sorts rows|exports"`
Expected: FAIL — no sort applied yet; no "Export CSV" button exists

- [ ] **Step 3: Add sorting to `RepoTablePage.tsx`**

```tsx
// frontend/src/pages/RepoTablePage.tsx — add above the component
function sortByDwellDesc(repos: RepoOut[]): RepoOut[] {
  return [...repos].sort((a, b) => {
    const aStuck = a.is_stuck ? 1 : 0;
    const bStuck = b.is_stuck ? 1 : 0;
    if (aStuck !== bStuck) return bStuck - aStuck;
    return (b.dwell_days ?? 0) - (a.dwell_days ?? 0);
  });
}
```

`RepoOut` is already imported at the top of the file from Task 4's Step 3 — no new import needed.

Change:
```tsx
  const filtered = repos.filter((r) => { ... });
```
to:
```tsx
  const filtered = sortByDwellDesc(repos.filter((r) => { ... }));
```

- [ ] **Step 4: Add CSV export**

```tsx
// frontend/src/pages/RepoTablePage.tsx — add function above the component
function toCsv(repos: RepoOut[]): string {
  const header = ["Name", "Domain", "Team", "Wave", "Stage", "Dwell Days", ...CHECK_COLUMNS];
  const rows = repos.map((r) => [
    r.name,
    r.domain ?? "",
    r.team ?? "",
    r.migration_wave,
    r.current_stage,
    String(r.dwell_days ?? ""),
    ...CHECK_COLUMNS.map((key) => r.stages[key]?.status ?? ""),
  ]);
  return [header, ...rows].map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\n");
}

function downloadCsv(repos: RepoOut[]) {
  const csv = toCsv(repos);
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "repos.csv";
  a.click();
  URL.revokeObjectURL(url);
}
```

Add a button in the JSX, next to the filters:

```tsx
        <button
          type="button"
          onClick={() => downloadCsv(filtered)}
          className="self-end bg-bg-card border border-card-border rounded px-3 py-1.5 text-[12px] text-chalk-dim hover:text-chalk"
        >
          Export CSV
        </button>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- RepoTablePage.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 6: Run the full suite**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/RepoTablePage.tsx frontend/tests/pages/RepoTablePage.test.tsx
git commit -m "feat: add stuck-first sort and CSV export to Repos table"
```

---

### Task 6: Wire the Fleet board's "View all" to navigate to the Repos table (final task)

**Files:**
- Modify: `frontend/src/components/fleet/StationBoard.tsx`
- Modify: `frontend/tests/components/fleet/StationBoard.test.tsx`

**Interfaces:**
- Produces: `RealColumn` gains a `stageKey: string` prop (`"onboarded"` or `"standardized"`). Its "Show all N" button (previously a client-side expand toggle) becomes a `Link to={`/repos?stage=${stageKey}`}`, styled identically. The `expanded`/`setExpanded` local state and the conditional "show top 4 vs. all" logic are removed — `RealColumn` now ALWAYS shows only the top 4 (sorted) inline, with the Link appearing whenever there are more than 5 total (matching Task 5's existing `RepoTablePage` cap-consistency threshold).

- [ ] **Step 1: Update the failing/changing tests**

In `frontend/tests/components/fleet/StationBoard.test.tsx`, REPLACE the existing "caps a column at 4 cards with a Show all expand toggle" test (which asserts the removed in-place expand behavior) with:

```tsx
it("caps a column at 4 cards and links 'Show all N' to the Repos table filtered by stage", () => {
  const repos = Array.from({ length: 6 }, (_, i) =>
    makeRepo({ id: i + 1, name: `repo-${i + 1}`, current_stage: "standardized" })
  );
  renderBoard(repos);

  expect(screen.queryByText("repo-5")).not.toBeInTheDocument();
  const showAllLink = screen.getByRole("link", { name: /show all 6/i });
  expect(showAllLink).toHaveAttribute("href", "/repos?stage=standardized");
});

it("does not show a 'Show all' link when a column has 5 or fewer repos", () => {
  const repos = Array.from({ length: 5 }, (_, i) =>
    makeRepo({ id: i + 1, name: `repo-${i + 1}`, current_stage: "onboarded" })
  );
  renderBoard(repos);

  expect(screen.getByText("repo-5")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /show all/i })).not.toBeInTheDocument();
});
```

(Keep every other existing test in this file unchanged — grouping, empty columns, stuck flags, repo-card links.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: FAIL — the "Show all" element is currently a `<button>`, not a `<link>` role, and has no `href`

- [ ] **Step 3: Update `StationBoard.tsx`**

Replace the entire `RealColumn` function:

```tsx
// frontend/src/components/fleet/StationBoard.tsx
import { Link } from "react-router-dom";

// ... keep sortByDwellDesc as-is ...

interface RealColumnProps {
  code: string;
  title: string;
  color: string;
  stageKey: string;
  repos: RepoOut[];
}

function RealColumn({ code, title, color, stageKey, repos }: RealColumnProps) {
  const sorted = sortByDwellDesc(repos);
  const isCapped = repos.length > 5;
  const visible = isCapped ? sorted.slice(0, CAP) : sorted;

  return (
    <div className="bg-bg-card-locked rounded-xl flex-1 min-w-[220px] flex flex-col">
      <div className="p-3.5 pb-2.5 rounded-t-xl" style={{ borderTop: `3px solid ${color}` }}>
        <div className="font-mono text-[10.5px] text-chalk-dimmer">{code}</div>
        <div className="font-display font-bold text-[17px] my-0.5">{title}</div>
        <div className="font-mono text-[11px] text-chalk-dim">{repos.length} repos</div>
      </div>
      <div className="px-3 pb-3.5 flex flex-col gap-2.5">
        {visible.map((repo) => (
          <RepoCard key={repo.id} repo={repo} />
        ))}
        {isCapped ? (
          <Link
            to={`/repos?stage=${stageKey}`}
            className="text-center border border-dashed border-card-border rounded-[9px] p-2.5 font-mono text-[11.5px] text-chalk-dim hover:text-chalk hover:border-chalk-dim focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
          >
            Show all {repos.length}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
```

Update the two `RealColumn` call sites in `StationBoard`'s export to pass `stageKey`:

```tsx
      <RealColumn code="ON" title="Onboarded" color="#A79AE8" stageKey="onboarded" repos={onboarded} />
      <RealColumn code="ST" title="Standardized" color="#A79AE8" stageKey="standardized" repos={standardized} />
```

Remove the now-unused `useState` import if `RealColumn` no longer uses it (check the top of the file — `EmptyColumn` and the rest of the module don't use `useState`, so the import should be removed entirely).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Run the FULL test suite one final time**

Run: `cd frontend && npm test`
Expected: PASS (every test in the frontend, output pristine)

- [ ] **Step 6: Run the production build**

Run: `cd frontend && npm run build`
Expected: succeeds with zero TypeScript errors (this plan adds new routes/components — confirm nothing broke the build, the same class of bug the previous plan's final review caught)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/fleet/StationBoard.tsx frontend/tests/components/fleet/StationBoard.test.tsx
git commit -m "feat: link Fleet board's Show-all to the Repos table instead of an in-place expand"
```

---

## Self-Review Notes

- **Spec coverage:** §7.3 manual fields (`domain`/`team`/`migration_wave`, Dockerization field correctly excluded) → Tasks 1-2. §7.3 onboarding log → Task 3. §7.4 searchable table (domain/wave filter, name search, per-stage-check columns, row → Journey link) → Task 4. §7.4 sort-by-earliest-stuck-stage (via stuck-first/dwell-desc) + CSV export → Task 5. §7.1's "View all N repos" linking to §7.4's table (the original design intent, deferred by the first frontend plan) → Task 6.
- **Placeholder scan:** no TBD/TODO; every step has runnable code.
- **Type consistency:** `RepoPatchIn`/`OnboardingLogIn`/`OnboardingLogOut`/`OnboardingSummaryOut` field names checked against the real, already-shipped backend schemas in `backend/app/schemas.py` (Task 1). `RepoOut`/`STAGE_LABELS`/`formatDwell` reused unchanged from the existing frontend-core build.
- **Cross-plan risk carried forward:** the prior plan's final review caught a production-build failure (`import.meta.env` typing) that `npm test` alone didn't catch — Task 6's final step explicitly re-runs `npm run build`, not just `npm test`, to guard against a repeat.
