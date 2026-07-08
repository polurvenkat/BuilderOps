# Frontend Core (Repo Fleet + Repo Journey) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the read-only core of the BuilderOps frontend — the Repo Fleet landing page (design spec §7.1) and the per-repo Repo Journey page (§7.2) — wired to the real, now-complete backend API, with routing between them.

**Architecture:** React + TypeScript SPA built with Vite, styled with Tailwind (design tokens matching the approved dark palette from the HTML reference builds), routed with `react-router-dom`. No state-management library — plain `fetch` behind a small typed API client, data-fetching via small custom hooks (`useState`/`useEffect`), matching this project's established preference for minimal dependencies. No test-mocking library beyond Vitest's built-in `vi.fn()` — no MSW.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS 3, react-router-dom 6, Vitest + React Testing Library + jsdom.

## Global Constraints

- **Scope for this plan:** read-only display only. No PATCH forms, no onboarding-log editing UI, no searchable table (§7.3/§7.4 deferred to a follow-up plan). The Fleet page's "View all N repos →" affordance is an in-place client-side expand, not a route to a not-yet-built page.
- **Design tokens must match the approved reference builds exactly** (`repo-journey-5cards.html`, `repo-fleet-landing.html`): background `#0E1116`, card `#171B21`, locked card `#12151A`, rail/border `#262B33`/`#20242C`, chalk text `#ECEAE3`/`#8B8D93`/`#4E525B`, track colors Standards `#A79AE8`, Pipeline `#3FBBA0`, Testing `#E7975C`, Paved `#EFC24B`. Single-theme dark — no light mode (a deliberate, committed aesthetic per the design spec, not an omission).
- **`current_stage` is clamped server-side to `"onboarded"`/`"standardized"` only** (Phase 0 has no real Piped/Tested data). The frontend must never invent a `"piped"`/`"tested"`/`"paved_road"` grouping from data — those three columns/stages always render the empty/locked state, hardcoded as always-empty in this phase, not computed from what happens to be in the API response.
- **Every displayed string comes from real API data** (`stages`, `current_stage`, `is_stuck`, `dwell_days`, `stuck_reason`, `team`, `domain`) — no hardcoded sample data in shipped components (sample data is fine only inside tests).
- SQLite/Postgres/backend testing concerns from prior plans do not apply here — this plan has no backend code.

---

## File Structure

```
frontend/
  package.json
  vite.config.ts
  tailwind.config.js
  postcss.config.js
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    api/
      types.ts                    # TypeScript interfaces matching backend schemas exactly
      client.ts                   # listRepos, getRepo — typed fetch wrapper
    hooks/
      useRepos.ts                 # data-fetching hook for repo lists
      useRepo.ts                  # data-fetching hook for a single repo
    lib/
      format.ts                   # formatDwell, stage label/color lookups shared by both pages
    components/
      journey/
        ConvergenceDiagram.tsx
        StationCard.tsx
        DetailsToggle.tsx
      fleet/
        StatStrip.tsx
        Legend.tsx
        StuckPanel.tsx
        StationBoard.tsx
        RepoCard.tsx
    pages/
      FleetPage.tsx
      JourneyPage.tsx
  tests/
    lib/
      format.test.ts
    api/
      client.test.ts
    components/
      journey/
        ConvergenceDiagram.test.tsx
        StationCard.test.tsx
      fleet/
        StatStrip.test.tsx
        StuckPanel.test.tsx
        StationBoard.test.tsx
    pages/
      FleetPage.test.tsx
      JourneyPage.test.tsx
    App.test.tsx
```

---

### Task 1: Project scaffolding, Tailwind design tokens, test infrastructure

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`
- Create: `frontend/tests/App.test.tsx`
- Create: `frontend/.gitignore`

**Interfaces:**
- Produces: a working Vite dev server (`npm run dev`) and test runner (`npm test`), Tailwind classes available using the custom color tokens below, and an `App` component that renders without crashing (the only thing this task's test checks — real routes come in Task 3).

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "builderops-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.45",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.4",
    "vite": "^5.4.2",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Write `vite.config.ts`**

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
  },
});
```

Create `frontend/tests/setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: Write `tailwind.config.js` with the approved design tokens**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0E1116",
        "bg-card": "#171B21",
        "bg-card-locked": "#12151A",
        rail: "#262B33",
        "card-border": "#20242C",
        chalk: "#ECEAE3",
        "chalk-dim": "#8B8D93",
        "chalk-dimmer": "#4E525B",
        track1: "#A79AE8",
        track2: "#3FBBA0",
        track3: "#E7975C",
        gold: "#EFC24B",
      },
      fontFamily: {
        display: ["Sora", "ui-rounded", "system-ui", "sans-serif"],
        body: ["Inter", "-apple-system", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SF Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Write `postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Write `tsconfig.json` and `tsconfig.node.json`**

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

```json
// frontend/tsconfig.node.json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler"
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Write `index.html`, `src/index.css`, `src/main.tsx`, `src/App.tsx`**

```html
<!-- frontend/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>BuilderOps — Repo Fleet</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  </head>
  <body class="bg-bg text-chalk font-body">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```css
/* frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```typescript
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

```tsx
// frontend/src/App.tsx
export function App() {
  return <div className="min-h-screen bg-bg" />;
}
```

- [ ] **Step 7: Write the failing test**

```tsx
// frontend/tests/App.test.tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../src/App";

describe("App", () => {
  it("renders without crashing", () => {
    const { container } = render(<App />);
    expect(container).toBeInTheDocument();
  });
});
```

- [ ] **Step 8: Install dependencies and run the test**

Run: `cd frontend && npm install`
Run: `npm test`
Expected: PASS (1 test)

- [ ] **Step 9: Write `.gitignore`**

```
node_modules/
dist/
*.local
```

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vite/React/TypeScript/Tailwind frontend with design tokens"
```

---

### Task 2: API types and client

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/tests/api/client.test.ts`

**Interfaces:**
- Produces (`types.ts`): `interface StageCheckOut { status: string; source: string; detail: Record<string, unknown> | null; updated_at: string | null }`, `interface RepoOut { id: number; name: string; domain: string | null; team: string | null; migration_wave: "not_started" | "pilot" | "rolling_out" | "migrated"; github_url: string; last_synced_at: string | null; stages: Record<string, StageCheckOut>; current_stage: string; is_stuck: boolean; dwell_days: number | null; stuck_reason: string | null }`, `interface ListReposParams { stage?: string; domain?: string; sort?: "dwell_desc" }`.
- Produces (`client.ts`): `async function listRepos(params?: ListReposParams): Promise<RepoOut[]>`, `async function getRepo(id: number): Promise<RepoOut>` — both throw `Error` with a descriptive message on a non-OK response. Used by Task 4's `useRepos`/`useRepo` hooks.

- [ ] **Step 1: Write `types.ts`**

```typescript
// frontend/src/api/types.ts
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
  migration_wave: "not_started" | "pilot" | "rolling_out" | "migrated";
  github_url: string;
  last_synced_at: string | null;
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
```

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/tests/api/client.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepo, listRepos } from "../../src/api/client";
import type { RepoOut } from "../../src/api/types";

const SAMPLE_REPO: RepoOut = {
  id: 1,
  name: "checkout-web",
  domain: "Growth",
  team: "Growth",
  migration_wave: "not_started",
  github_url: "https://github.com/acme/checkout-web",
  last_synced_at: "2026-07-08T00:00:00Z",
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listRepos", () => {
  it("fetches /repos with no query string when no params given", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [SAMPLE_REPO],
    });
    vi.stubGlobal("fetch", fetchMock);

    const repos = await listRepos();

    expect(repos).toEqual([SAMPLE_REPO]);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toMatch(/\/repos$/);
  });

  it("builds a query string from stage/domain/sort params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    await listRepos({ stage: "onboarded", domain: "Growth", sort: "dwell_desc" });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("stage=onboarded");
    expect(calledUrl).toContain("domain=Growth");
    expect(calledUrl).toContain("sort=dwell_desc");
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(listRepos()).rejects.toThrow(/500/);
  });
});

describe("getRepo", () => {
  it("fetches /repos/{id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => SAMPLE_REPO });
    vi.stubGlobal("fetch", fetchMock);

    const repo = await getRepo(1);

    expect(repo).toEqual(SAMPLE_REPO);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1$/);
  });

  it("throws a descriptive error on a 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    await expect(getRepo(999)).rejects.toThrow(/404/);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test -- client.test.ts`
Expected: FAIL with `Cannot find module '../../src/api/client'`

- [ ] **Step 4: Implement `client.ts`**

```typescript
// frontend/src/api/client.ts
import type { ListReposParams, RepoOut } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function listRepos(params: ListReposParams = {}): Promise<RepoOut[]> {
  const search = new URLSearchParams();
  if (params.stage) search.set("stage", params.stage);
  if (params.domain) search.set("domain", params.domain);
  if (params.sort) search.set("sort", params.sort);
  const query = search.toString();

  const response = await fetch(`${BASE_URL}/repos${query ? `?${query}` : ""}`);
  if (!response.ok) {
    throw new Error(`Failed to list repos: HTTP ${response.status}`);
  }
  return response.json();
}

export async function getRepo(id: number): Promise<RepoOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to get repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- client.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/ frontend/tests/api/
git commit -m "feat: add typed API client for repos endpoints"
```

---

### Task 3: Data-fetching hooks, shared formatting helpers, routing skeleton

**Files:**
- Create: `frontend/src/hooks/useRepos.ts`
- Create: `frontend/src/hooks/useRepo.ts`
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/tests/lib/format.test.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/FleetPage.tsx` (placeholder shell, filled in by Tasks 6-8)
- Create: `frontend/src/pages/JourneyPage.tsx` (placeholder shell, filled in by Tasks 4-5)
- Modify: `frontend/tests/App.test.tsx`
- Modify: `frontend/package.json` (react-router-dom is already listed in Task 1's dependencies)

**Interfaces:**
- Produces: `function useRepos(params?: ListReposParams): { repos: RepoOut[]; loading: boolean; error: string | null }`.
- Produces: `function useRepo(id: number): { repo: RepoOut | null; loading: boolean; error: string | null }`.
- Produces: `function formatDwell(days: number | null): string` — `null` → `""`, `0` → `"<1d here"`, `1` → `"1d here"`, `N` → `"Nd here"`.
- Produces: `const STAGE_LABELS: Record<string, string>` — `{ onboarded: "Onboarded", standardized: "Standardized" }` (only the two real Phase 0 stages; Fleet page's other three columns are hardcoded separately in Task 7, not derived from this map).
- Produces: routes `"/"` → `FleetPage`, `"/repos/:id"` → `JourneyPage`, wired in `App.tsx` via `react-router-dom`.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/tests/lib/format.test.ts
import { describe, expect, it } from "vitest";
import { formatDwell, STAGE_LABELS } from "../../src/lib/format";

describe("formatDwell", () => {
  it("returns empty string for null", () => {
    expect(formatDwell(null)).toBe("");
  });

  it("returns '<1d here' for 0 days", () => {
    expect(formatDwell(0)).toBe("<1d here");
  });

  it("returns 'Nd here' for N days", () => {
    expect(formatDwell(28)).toBe("28d here");
  });
});

describe("STAGE_LABELS", () => {
  it("labels the two real Phase 0 stages", () => {
    expect(STAGE_LABELS.onboarded).toBe("Onboarded");
    expect(STAGE_LABELS.standardized).toBe("Standardized");
  });
});
```

```tsx
// frontend/tests/App.test.tsx — replace the existing file
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";

describe("App routing", () => {
  it("renders the Fleet page at /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App useMemoryRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("fleet-page")).toBeInTheDocument();
  });

  it("renders the Journey page at /repos/:id", () => {
    render(
      <MemoryRouter initialEntries={["/repos/42"]}>
        <App useMemoryRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("journey-page")).toBeInTheDocument();
  });
});
```

Note: `App` needs a way to avoid nesting two routers when tests wrap it in their own `MemoryRouter` for route-based testing. Implement `App` to accept an optional prop that lets tests supply routes without `BrowserRouter`, per Step 3 below.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- format.test.ts App.test.tsx`
Expected: FAIL — `format.ts` doesn't exist; `App.test.tsx` fails because `FleetPage`/`JourneyPage` don't have the expected test ids yet and `App` doesn't accept the `useMemoryRouter` prop

- [ ] **Step 3: Implement `lib/format.ts`**

```typescript
// frontend/src/lib/format.ts
export function formatDwell(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "<1d here";
  return `${days}d here`;
}

export const STAGE_LABELS: Record<string, string> = {
  onboarded: "Onboarded",
  standardized: "Standardized",
};
```

- [ ] **Step 4: Implement the hooks**

```typescript
// frontend/src/hooks/useRepos.ts
import { useEffect, useState } from "react";
import { listRepos } from "../api/client";
import type { ListReposParams, RepoOut } from "../api/types";

export function useRepos(params?: ListReposParams) {
  const [repos, setRepos] = useState<RepoOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    listRepos(params)
      .then((data) => {
        if (!cancelled) setRepos(data);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.stage, params?.domain, params?.sort]);

  return { repos, loading, error };
}
```

```typescript
// frontend/src/hooks/useRepo.ts
import { useEffect, useState } from "react";
import { getRepo } from "../api/client";
import type { RepoOut } from "../api/types";

export function useRepo(id: number) {
  const [repo, setRepo] = useState<RepoOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getRepo(id)
      .then((data) => {
        if (!cancelled) setRepo(data);
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
  }, [id]);

  return { repo, loading, error };
}
```

- [ ] **Step 5: Implement placeholder pages with test ids**

```tsx
// frontend/src/pages/FleetPage.tsx
export function FleetPage() {
  return <div data-testid="fleet-page" />;
}
```

```tsx
// frontend/src/pages/JourneyPage.tsx
import { useParams } from "react-router-dom";

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  return <div data-testid="journey-page">{id}</div>;
}
```

- [ ] **Step 6: Implement `App.tsx` with routing**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { FleetPage } from "./pages/FleetPage";
import { JourneyPage } from "./pages/JourneyPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<FleetPage />} />
      <Route path="/repos/:id" element={<JourneyPage />} />
    </Routes>
  );
}

export function App({ useMemoryRouter = false }: { useMemoryRouter?: boolean }) {
  if (useMemoryRouter) {
    // Tests supply their own MemoryRouter wrapper around <App useMemoryRouter />
    return <AppRoutes />;
  }
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests: Task 1's App smoke test replaced by the two routing tests, plus format tests)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hooks/ frontend/src/lib/ frontend/src/App.tsx frontend/src/pages/ frontend/tests/lib/ frontend/tests/App.test.tsx
git commit -m "feat: add data-fetching hooks, formatting helpers, and page routing"
```

---

### Task 4: Repo Journey page — convergence diagram

**Files:**
- Create: `frontend/src/components/journey/ConvergenceDiagram.tsx`
- Create: `frontend/tests/components/journey/ConvergenceDiagram.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond React itself — a presentational component.
- Produces: `function ConvergenceDiagram({ standardsProgress, pipelineProgress, testingProgress }: { standardsProgress: number; pipelineProgress: number; testingProgress: number }): JSX.Element` — each `*Progress` prop is a 0–1 fraction. Renders the three-line SVG convergence diagram from the approved reference build (`repo-journey-5cards.html`), with each line's traveled portion sized via `stroke-dasharray` driven by the prop (not DOM measurement — this is a deliberate simplification from the reference build's `getPointAtLength` approach, since the exact curve shape is decorative and the dasharray-percentage technique already used in the reference build's own CSS achieves the same visual result reliably in React without ref-timing complexity).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/components/journey/ConvergenceDiagram.test.tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConvergenceDiagram } from "../../../src/components/journey/ConvergenceDiagram";

describe("ConvergenceDiagram", () => {
  it("renders three progress paths with dasharray reflecting their progress props", () => {
    const { container } = render(
      <ConvergenceDiagram standardsProgress={1} pipelineProgress={0.5} testingProgress={0} />
    );

    const paths = container.querySelectorAll("path[data-line]");
    expect(paths).toHaveLength(3);

    const standards = container.querySelector('path[data-line="standards"]');
    const pipeline = container.querySelector('path[data-line="pipeline"]');
    const testing = container.querySelector('path[data-line="testing"]');

    expect(standards?.getAttribute("stroke-dasharray")).toBe("100 100");
    expect(pipeline?.getAttribute("stroke-dasharray")).toBe("50 100");
    expect(testing?.getAttribute("stroke-dasharray")).toBe("0 100");
  });

  it("uses the approved track colors", () => {
    const { container } = render(
      <ConvergenceDiagram standardsProgress={1} pipelineProgress={1} testingProgress={1} />
    );

    expect(container.querySelector('path[data-line="standards"]')?.getAttribute("stroke")).toBe("#A79AE8");
    expect(container.querySelector('path[data-line="pipeline"]')?.getAttribute("stroke")).toBe("#3FBBA0");
    expect(container.querySelector('path[data-line="testing"]')?.getAttribute("stroke")).toBe("#E7975C");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- ConvergenceDiagram.test.tsx`
Expected: FAIL with `Cannot find module '../../../src/components/journey/ConvergenceDiagram'`

- [ ] **Step 3: Implement `ConvergenceDiagram.tsx`**

```tsx
// frontend/src/components/journey/ConvergenceDiagram.tsx
interface ConvergenceDiagramProps {
  standardsProgress: number;
  pipelineProgress: number;
  testingProgress: number;
}

function toDasharray(progress: number): string {
  return `${Math.round(progress * 100)} 100`;
}

export function ConvergenceDiagram({
  standardsProgress,
  pipelineProgress,
  testingProgress,
}: ConvergenceDiagramProps) {
  const allArrived = standardsProgress >= 1 && pipelineProgress >= 1 && testingProgress >= 1;

  return (
    <div className="bg-bg-card border border-card-border rounded-[14px] p-6">
      <svg viewBox="0 0 720 160" className="w-full h-auto">
        <path d="M20,30 C 260,30 420,95 660,95" fill="none" stroke="#A79AE8" strokeWidth="3" opacity="0.18" />
        <path d="M20,80 C 260,80 420,95 660,95" fill="none" stroke="#3FBBA0" strokeWidth="3" opacity="0.18" />
        <path d="M20,130 C 260,130 420,95 660,95" fill="none" stroke="#E7975C" strokeWidth="3" opacity="0.18" />

        <path
          data-line="standards"
          pathLength={100}
          d="M20,30 C 260,30 420,95 660,95"
          fill="none"
          stroke="#A79AE8"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(standardsProgress)}
        />
        <path
          data-line="pipeline"
          pathLength={100}
          d="M20,80 C 260,80 420,95 660,95"
          fill="none"
          stroke="#3FBBA0"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(pipelineProgress)}
        />
        <path
          data-line="testing"
          pathLength={100}
          d="M20,130 C 260,130 420,95 660,95"
          fill="none"
          stroke="#E7975C"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(testingProgress)}
        />

        <circle
          cx="660"
          cy="95"
          r="9"
          fill={allArrived ? "#EFC24B" : "none"}
          stroke="#EFC24B"
          strokeWidth="2"
          opacity={allArrived ? 1 : 0.6}
        />
        <circle cx="660" cy="95" r="15" fill="none" stroke="#EFC24B" strokeWidth="1" opacity="0.3" />

        <text x="30" y="22" fill="#A79AE8" fontSize="9.5" fontFamily="ui-monospace, monospace">
          STANDARDS
        </text>
        <text x="30" y="72" fill="#3FBBA0" fontSize="9.5" fontFamily="ui-monospace, monospace">
          PIPELINE
        </text>
        <text x="30" y="146" fill="#E7975C" fontSize="9.5" fontFamily="ui-monospace, monospace">
          TESTING
        </text>
      </svg>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- ConvergenceDiagram.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/journey/ConvergenceDiagram.tsx frontend/tests/components/journey/ConvergenceDiagram.test.tsx
git commit -m "feat: add Repo Journey convergence diagram component"
```

---

### Task 5: Repo Journey page — station cards, details toggle, full page assembly

**Files:**
- Create: `frontend/src/components/journey/DetailsToggle.tsx`
- Create: `frontend/src/components/journey/StationCard.tsx`
- Create: `frontend/tests/components/journey/StationCard.test.tsx`
- Modify: `frontend/src/pages/JourneyPage.tsx`
- Create: `frontend/tests/pages/JourneyPage.test.tsx`

**Interfaces:**
- Consumes: `RepoOut`, `StageCheckOut` (Task 2), `useRepo` (Task 3), `ConvergenceDiagram` (Task 4).
- Produces: `function DetailsToggle({ children }: { children: React.ReactNode }): JSX.Element` — a real `<button>` with `aria-expanded`/`aria-controls`, toggling a details panel.
- Produces: `function StationCard(props: { code: string; title: string; description: string; badge: "Cleared" | "You are here" | "Locked"; trackColor: string; check?: StageCheckOut; lockedNote?: string }): JSX.Element` — one card in the route list. Badge text is exactly one of the three allowed values, per the design spec — no other text is invented.
- Produces: `JourneyPage` assembled: fetches the repo via `useRepo`, shows a loading state, an error state, and on success renders `ConvergenceDiagram` (progress computed from `stages`) plus five `StationCard`s — Onboarded and Standardized driven by real data (`current_stage`, `is_stuck`, `stages`), Piped/Tested/Paved Road always `"Locked"` with a fixed note ("Not live yet — unlocks once the CI/CD connector ships" / "...E2E/load connector ships" / "...once Piped and Tested both ship").

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/tests/components/journey/StationCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { StationCard } from "../../../src/components/journey/StationCard";

describe("StationCard", () => {
  it("renders the badge, title, and description", () => {
    render(
      <StationCard
        code="ST-01"
        title="Standardized"
        description="Repo hygiene, ownership, and access controls are in place."
        badge="Cleared"
        trackColor="#A79AE8"
      />
    );

    expect(screen.getByText("Cleared")).toBeInTheDocument();
    expect(screen.getByText("Standardized")).toBeInTheDocument();
  });

  it("shows the locked note instead of a details toggle when locked", () => {
    render(
      <StationCard
        code="PI-01"
        title="Piped"
        description="GitHub Actions are wired up for every environment."
        badge="Locked"
        trackColor="#3FBBA0"
        lockedNote="Not live yet — unlocks once the CI/CD connector ships."
      />
    );

    expect(screen.getByText(/Not live yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /details/i })).not.toBeInTheDocument();
  });

  it("toggles the details panel via a real accessible button", async () => {
    const user = userEvent.setup();
    render(
      <StationCard
        code="ON-01"
        title="Onboarded"
        description="Migrated from Azure DevOps."
        badge="Cleared"
        trackColor="#A79AE8"
        check={{ status: "pass", source: "auto", detail: null, updated_at: "2026-07-08T00:00:00Z" }}
      />
    );

    const button = screen.getByRole("button", { name: /details/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});
```

```tsx
// frontend/tests/pages/JourneyPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JourneyPage } from "../../src/pages/JourneyPage";
import type { RepoOut } from "../../src/api/types";

const STUCK_REPO: RepoOut = {
  id: 1,
  name: "checkout-web",
  domain: "Growth",
  team: "Growth",
  migration_wave: "not_started",
  github_url: "https://github.com/acme/checkout-web",
  last_synced_at: "2026-07-08T00:00:00Z",
  stages: {
    migrated_from_ado: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    codeowners_assigned: { status: "fail", source: "auto", detail: null, updated_at: "2026-06-01T00:00:00Z" },
    domain_assigned: { status: "pass", source: "manual", detail: null, updated_at: "2026-07-02T00:00:00Z" },
    branch_protection: { status: "pass", source: "auto", detail: { required_reviewer_count: 2 }, updated_at: "2026-07-01T00:00:00Z" },
    readme_present: { status: "pass", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
    naming_standardized: { status: "pending_convention", source: "auto", detail: null, updated_at: "2026-07-01T00:00:00Z" },
  },
  current_stage: "standardized",
  is_stuck: true,
  dwell_days: 41,
  stuck_reason: "No CODEOWNERS assigned — waiting on Growth team",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderAtRepo(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/repos/${id}`]}>
      <Routes>
        <Route path="/repos/:id" element={<JourneyPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("JourneyPage", () => {
  it("shows a loading state, then the repo's name and stuck reason once loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => STUCK_REPO }));

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    expect(screen.getByText(/No CODEOWNERS assigned/)).toBeInTheDocument();
  });

  it("always renders Piped/Tested/Paved Road as Locked regardless of data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => STUCK_REPO }));

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    const lockedBadges = screen.getAllByText("Locked");
    expect(lockedBadges.length).toBe(3); // Piped, Tested, Paved Road
  });

  it("shows an error state when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    renderAtRepo("999");

    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StationCard.test.tsx JourneyPage.test.tsx`
Expected: FAIL — `StationCard`/`DetailsToggle` don't exist; `JourneyPage` is still the Task 3 placeholder

- [ ] **Step 3: Implement `DetailsToggle.tsx`**

```tsx
// frontend/src/components/journey/DetailsToggle.tsx
import { useId, useState } from "react";

export function DetailsToggle({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((prev) => !prev)}
        className="text-chalk-dim text-[12.5px] font-semibold flex items-center gap-1.5 py-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
      >
        <span className={`text-[10px] transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
        Details
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows] duration-200"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `StationCard.tsx`**

```tsx
// frontend/src/components/journey/StationCard.tsx
import type { StageCheckOut } from "../../api/types";
import { DetailsToggle } from "./DetailsToggle";

interface StationCardProps {
  code: string;
  title: string;
  description: string;
  badge: "Cleared" | "You are here" | "Locked";
  trackColor: string;
  check?: StageCheckOut;
  lockedNote?: string;
}

const BADGE_STYLES: Record<StationCardProps["badge"], string> = {
  Cleared: "bg-white/[0.08] text-chalk-dim",
  "You are here": "bg-gold/15 text-gold",
  Locked: "bg-chalk-dimmer/20 text-chalk-dimmer",
};

export function StationCard({ code, title, description, badge, trackColor, check, lockedNote }: StationCardProps) {
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
          {check ? (
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

- [ ] **Step 5: Implement `JourneyPage.tsx`**

```tsx
// frontend/src/pages/JourneyPage.tsx
import { useParams } from "react-router-dom";
import { useRepo } from "../hooks/useRepo";
import { ConvergenceDiagram } from "../components/journey/ConvergenceDiagram";
import { StationCard } from "../components/journey/StationCard";

const STANDARDIZED_KEYS = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];

function fractionPassing(stages: Record<string, { status: string }>, keys: string[]): number {
  if (keys.length === 0) return 0;
  const passing = keys.filter((k) => stages[k]?.status === "pass").length;
  return passing / keys.length;
}

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  const { repo, loading, error } = useRepo(Number(id));

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

  return (
    <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk max-w-[760px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Status
      </div>
      <h1 className="font-display text-[clamp(36px,7vw,56px)] font-extrabold tracking-tight mb-8">
        {repo.name}
      </h1>

      <ConvergenceDiagram standardsProgress={standardsProgress} pipelineProgress={0} testingProgress={0} />

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
          check={repo.stages.codeowners_assigned}
          lockedNote={repo.current_stage === "onboarded" ? "Not started. Unlocks once Onboarded clears." : undefined}
        />
        <StationCard
          code="PI-01"
          title="Piped"
          description="GitHub Actions are wired up for every environment and verified working."
          badge="Locked"
          trackColor="#3FBBA0"
          lockedNote="Not live yet — unlocks once the CI/CD connector ships."
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
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/journey/ frontend/src/pages/JourneyPage.tsx frontend/tests/components/journey/StationCard.test.tsx frontend/tests/pages/
git commit -m "feat: assemble Repo Journey page with station cards and details toggle"
```

---

### Task 6: Repo Fleet page — hero, stat strip, legend

**Files:**
- Create: `frontend/src/components/fleet/StatStrip.tsx`
- Create: `frontend/tests/components/fleet/StatStrip.test.tsx`
- Create: `frontend/src/components/fleet/Legend.tsx`
- Modify: `frontend/src/pages/FleetPage.tsx`
- Create: `frontend/tests/pages/FleetPage.test.tsx`

**Interfaces:**
- Consumes: `RepoOut[]` (Task 2), `useRepos` (Task 3).
- Produces: `function StatStrip(props: { repos: RepoOut[]; onToggleStuck: () => void; stuckExpanded: boolean }): JSX.Element` — computes "Repos tracked" (`repos.length`), "Paved" (count where... in Phase 0 this is always 0, since `current_stage` never reports `paved_road` — compute it generically as `repos.filter(r => r.current_stage === "paved_road").length` so the code is correct once a future phase adds that stage, even though it's always 0 today), "Stuck >14 days" (`repos.filter(r => r.is_stuck && (r.dwell_days ?? 0) > 14).length`, as a clickable button toggling the stuck panel), "Most crowded" (the `current_stage` value with the highest count, mapped through `STAGE_LABELS`).
- Produces: `function Legend(): JSX.Element` — the four static chips, function-named per the design spec, never "Track 1/2/3".
- Produces: `FleetPage` assembled so far: hero (eyebrow/h1/tagline), `StatStrip`, `Legend`. The stuck panel and station board come in Tasks 7-8.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/tests/components/fleet/StatStrip.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StatStrip } from "../../../src/components/fleet/StatStrip";
import type { RepoOut } from "../../../src/api/types";

function makeRepo(overrides: Partial<RepoOut>): RepoOut {
  return {
    id: 1,
    name: "repo",
    domain: null,
    team: null,
    migration_wave: "not_started",
    github_url: "https://github.com/acme/repo",
    last_synced_at: null,
    stages: {},
    current_stage: "standardized",
    is_stuck: false,
    dwell_days: null,
    stuck_reason: null,
    ...overrides,
  };
}

describe("StatStrip", () => {
  it("shows total repo count and stuck-over-14-days count", () => {
    const repos = [
      makeRepo({ id: 1, is_stuck: true, dwell_days: 20 }),
      makeRepo({ id: 2, is_stuck: true, dwell_days: 5 }),
      makeRepo({ id: 3, is_stuck: false }),
    ];

    render(<StatStrip repos={repos} onToggleStuck={vi.fn()} stuckExpanded={false} />);

    expect(screen.getByText("3")).toBeInTheDocument(); // repos tracked
    expect(screen.getByText("1")).toBeInTheDocument(); // stuck >14 days (only the 20-day one)
  });

  it("calls onToggleStuck when the stuck stat is clicked", async () => {
    const user = userEvent.setup();
    const onToggleStuck = vi.fn();
    render(<StatStrip repos={[]} onToggleStuck={onToggleStuck} stuckExpanded={false} />);

    await user.click(screen.getByRole("button", { name: /stuck/i }));

    expect(onToggleStuck).toHaveBeenCalledOnce();
  });

  it("sets aria-expanded on the stuck toggle to match stuckExpanded", () => {
    render(<StatStrip repos={[]} onToggleStuck={vi.fn()} stuckExpanded={true} />);

    expect(screen.getByRole("button", { name: /stuck/i })).toHaveAttribute("aria-expanded", "true");
  });

  it("shows the most crowded stage by real label", () => {
    const repos = [
      makeRepo({ id: 1, current_stage: "onboarded" }),
      makeRepo({ id: 2, current_stage: "standardized" }),
      makeRepo({ id: 3, current_stage: "standardized" }),
    ];

    render(<StatStrip repos={repos} onToggleStuck={vi.fn()} stuckExpanded={false} />);

    expect(screen.getByText("Standardized")).toBeInTheDocument();
  });
});
```

```tsx
// frontend/tests/pages/FleetPage.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FleetPage } from "../../src/pages/FleetPage";
import type { RepoOut } from "../../src/api/types";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("FleetPage", () => {
  it("renders the hero, legend, and stat strip once repos load", async () => {
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
      },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => repos }));

    render(
      <MemoryRouter>
        <FleetPage />
      </MemoryRouter>
    );

    expect(screen.getByText("Repo fleet")).toBeInTheDocument();
    expect(screen.getByText("CI/CD & environments")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StatStrip.test.tsx FleetPage.test.tsx`
Expected: FAIL — `StatStrip`/`Legend` don't exist; `FleetPage` is still the Task 3 placeholder

- [ ] **Step 3: Implement `StatStrip.tsx`**

```tsx
// frontend/src/components/fleet/StatStrip.tsx
import type { RepoOut } from "../../api/types";
import { STAGE_LABELS } from "../../lib/format";

interface StatStripProps {
  repos: RepoOut[];
  onToggleStuck: () => void;
  stuckExpanded: boolean;
}

function mostCrowdedStage(repos: RepoOut[]): string | null {
  const counts = new Map<string, number>();
  for (const repo of repos) {
    counts.set(repo.current_stage, (counts.get(repo.current_stage) ?? 0) + 1);
  }
  let top: string | null = null;
  let topCount = 0;
  for (const [stage, count] of counts) {
    if (count > topCount) {
      top = stage;
      topCount = count;
    }
  }
  return top;
}

export function StatStrip({ repos, onToggleStuck, stuckExpanded }: StatStripProps) {
  const paved = repos.filter((r) => r.current_stage === "paved_road").length;
  const stuckOver14 = repos.filter((r) => r.is_stuck && (r.dwell_days ?? 0) > 14).length;
  const crowded = mostCrowdedStage(repos);

  return (
    <div className="grid gap-px bg-card-border border border-card-border rounded-xl overflow-hidden mb-6">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-px bg-card-border">
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Repos tracked</span>
          <span className="font-display text-[26px] font-extrabold text-gold tabular-nums">{repos.length}</span>
        </div>
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Paved</span>
          <span className="font-display text-[26px] font-extrabold text-gold tabular-nums">{paved}</span>
        </div>
        <button
          type="button"
          aria-expanded={stuckExpanded}
          onClick={onToggleStuck}
          className="bg-bg-card p-4 flex flex-col gap-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
        >
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Stuck &gt;14 days</span>
          <span className="font-display text-[26px] font-extrabold text-track3 tabular-nums">{stuckOver14}</span>
        </button>
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Most crowded</span>
          <span className="font-display text-[20px] font-extrabold text-gold">
            {crowded ? (STAGE_LABELS[crowded] ?? crowded) : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `Legend.tsx`**

```tsx
// frontend/src/components/fleet/Legend.tsx
const ENTRIES: { color: string; label: string }[] = [
  { color: "#A79AE8", label: "Repo standards" },
  { color: "#3FBBA0", label: "CI/CD & environments" },
  { color: "#E7975C", label: "E2E & load testing" },
  { color: "#EFC24B", label: "Paved — ready to ship" },
];

export function Legend() {
  return (
    <div className="flex flex-wrap gap-2.5 mb-6">
      {ENTRIES.map((entry) => (
        <div
          key={entry.label}
          className="flex items-center gap-1.5 bg-bg-card border border-card-border rounded-full py-1 pl-2 pr-3 font-mono text-[11px] text-chalk-dim"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
          {entry.label}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Implement `FleetPage.tsx` (hero + stat strip + legend so far)**

```tsx
// frontend/src/pages/FleetPage.tsx
import { useState } from "react";
import { useRepos } from "../hooks/useRepos";
import { StatStrip } from "../components/fleet/StatStrip";
import { Legend } from "../components/fleet/Legend";

export function FleetPage() {
  const { repos } = useRepos();
  const [stuckExpanded, setStuckExpanded] = useState(false);

  return (
    <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Fleet
      </div>
      <h1 className="font-display text-[clamp(32px,6vw,48px)] font-extrabold tracking-tight mb-2">Repo fleet</h1>
      <p className="text-chalk-dim text-[15px] mb-8 max-w-[60ch]">
        Where every repo sits right now, and what's stuck. Click any repo for its full journey.
      </p>

      <StatStrip repos={repos} onToggleStuck={() => setStuckExpanded((prev) => !prev)} stuckExpanded={stuckExpanded} />
      <Legend />
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/fleet/StatStrip.tsx frontend/src/components/fleet/Legend.tsx frontend/src/pages/FleetPage.tsx frontend/tests/components/fleet/StatStrip.test.tsx frontend/tests/pages/FleetPage.test.tsx
git commit -m "feat: add Repo Fleet hero, stat strip, and legend"
```

---

### Task 7: Repo Fleet page — station board with repo cards

**Files:**
- Create: `frontend/src/components/fleet/RepoCard.tsx`
- Create: `frontend/src/components/fleet/StationBoard.tsx`
- Create: `frontend/tests/components/fleet/StationBoard.test.tsx`
- Modify: `frontend/src/pages/FleetPage.tsx`

**Interfaces:**
- Consumes: `RepoOut` (Task 2), `formatDwell` (Task 3).
- Produces: `function RepoCard({ repo }: { repo: RepoOut }): JSX.Element` — links to `/repos/{id}` (a real `<Link>`, not a styled div), shows name, team, dwell time, and (if `is_stuck`) a bordered flag with `stuck_reason`.
- Produces: `function StationBoard({ repos }: { repos: RepoOut[] }): JSX.Element` — five columns: Onboarded and Standardized grouped from `repos` by `current_stage` (capped at 4 visible cards with a "Show all N" client-side expand toggle — no route, per this plan's deferred-table decision); Piped, Tested, Paved Road always render the empty-state pattern with fixed explanatory text, regardless of `repos` content, since Phase 0 never produces those `current_stage` values.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/components/fleet/StationBoard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { StationBoard } from "../../../src/components/fleet/StationBoard";
import type { RepoOut } from "../../../src/api/types";

function makeRepo(overrides: Partial<RepoOut>): RepoOut {
  return {
    id: 1,
    name: "repo",
    domain: null,
    team: "Growth",
    migration_wave: "not_started",
    github_url: "https://github.com/acme/repo",
    last_synced_at: null,
    stages: {},
    current_stage: "standardized",
    is_stuck: false,
    dwell_days: null,
    stuck_reason: null,
    ...overrides,
  };
}

function renderBoard(repos: RepoOut[]) {
  return render(
    <MemoryRouter>
      <StationBoard repos={repos} />
    </MemoryRouter>
  );
}

describe("StationBoard", () => {
  it("groups repos into their current_stage column", () => {
    renderBoard([
      makeRepo({ id: 1, name: "onboarding-repo", current_stage: "onboarded" }),
      makeRepo({ id: 2, name: "standardized-repo", current_stage: "standardized" }),
    ]);

    expect(screen.getByText("onboarding-repo")).toBeInTheDocument();
    expect(screen.getByText("standardized-repo")).toBeInTheDocument();
  });

  it("always shows Piped/Tested/Paved Road as empty with explanatory text", () => {
    renderBoard([makeRepo({ id: 1, current_stage: "standardized" })]);

    expect(screen.getByText(/unlocks once the CI\/CD connector ships/i)).toBeInTheDocument();
    expect(screen.getByText(/unlocks once the E2E\/load connector ships/i)).toBeInTheDocument();
    expect(screen.getByText(/unlocks once Piped and Tested both ship/i)).toBeInTheDocument();
  });

  it("shows a stuck flag with the plain-language reason on a stuck repo's card", () => {
    renderBoard([
      makeRepo({
        id: 1,
        name: "legacy-batch-importer",
        current_stage: "standardized",
        is_stuck: true,
        dwell_days: 41,
        stuck_reason: "No CODEOWNERS assigned — waiting on Platform team",
      }),
    ]);

    expect(screen.getByText(/No CODEOWNERS assigned/)).toBeInTheDocument();
    expect(screen.getByText("41d here")).toBeInTheDocument();
  });

  it("caps a column at 4 cards with a Show all expand toggle", async () => {
    const user = userEvent.setup();
    const repos = Array.from({ length: 6 }, (_, i) =>
      makeRepo({ id: i + 1, name: `repo-${i + 1}`, current_stage: "standardized" })
    );
    renderBoard(repos);

    expect(screen.queryByText("repo-5")).not.toBeInTheDocument();
    const showAll = screen.getByRole("button", { name: /show all 6/i });

    await user.click(showAll);

    expect(screen.getByText("repo-5")).toBeInTheDocument();
  });

  it("links each repo card to its Journey page", () => {
    renderBoard([makeRepo({ id: 42, name: "checkout-web", current_stage: "standardized" })]);

    expect(screen.getByRole("link", { name: /checkout-web/i })).toHaveAttribute("href", "/repos/42");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- StationBoard.test.tsx`
Expected: FAIL with `Cannot find module '../../../src/components/fleet/StationBoard'`

- [ ] **Step 3: Implement `RepoCard.tsx`**

```tsx
// frontend/src/components/fleet/RepoCard.tsx
import { Link } from "react-router-dom";
import type { RepoOut } from "../../api/types";
import { formatDwell } from "../../lib/format";

export function RepoCard({ repo }: { repo: RepoOut }) {
  return (
    <Link
      to={`/repos/${repo.id}`}
      className="block bg-bg-card border border-card-border rounded-[9px] p-3 no-underline text-inherit hover:-translate-y-0.5 transition-transform focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
    >
      <div className="font-display font-bold text-[14.5px] mb-1.5">{repo.name}</div>
      <div className="flex justify-between font-mono text-[10.5px] text-chalk-dim">
        <span>{repo.team ?? "Unassigned"}</span>
        <span>{formatDwell(repo.dwell_days)}</span>
      </div>
      {repo.is_stuck && repo.stuck_reason ? (
        <div className="mt-2 pt-2 border-t border-dashed border-card-border flex gap-1.5 text-[12px] text-chalk-dim">
          <span className="w-1.5 h-1.5 rounded-full bg-track3 mt-1 flex-shrink-0" />
          {repo.stuck_reason}
        </div>
      ) : null}
    </Link>
  );
}
```

- [ ] **Step 4: Implement `StationBoard.tsx`**

```tsx
// frontend/src/components/fleet/StationBoard.tsx
import { useState } from "react";
import type { RepoOut } from "../../api/types";
import { RepoCard } from "./RepoCard";

const CAP = 4;

interface RealColumnProps {
  code: string;
  title: string;
  color: string;
  repos: RepoOut[];
}

function RealColumn({ code, title, color, repos }: RealColumnProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? repos : repos.slice(0, CAP);

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
        {repos.length > CAP && !expanded ? (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="text-center border border-dashed border-card-border rounded-[9px] p-2.5 font-mono text-[11.5px] text-chalk-dim hover:text-chalk hover:border-chalk-dim focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
          >
            Show all {repos.length}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function EmptyColumn({ code, title, color, message }: { code: string; title: string; color: string; message: string }) {
  return (
    <div className="bg-bg-card-locked rounded-xl flex-1 min-w-[220px] flex flex-col">
      <div className="p-3.5 pb-2.5 rounded-t-xl" style={{ borderTop: `3px solid ${color}` }}>
        <div className="font-mono text-[10.5px] text-chalk-dimmer">{code}</div>
        <div className="font-display font-bold text-[17px] my-0.5">{title}</div>
        <div className="font-mono text-[11px] text-chalk-dim">0 repos</div>
      </div>
      <div className="px-3 pb-3.5">
        <div className="border border-dashed border-card-border rounded-[9px] p-5 text-center">
          <p className="font-mono text-[11px] text-chalk-dimmer leading-relaxed">{message}</p>
        </div>
      </div>
    </div>
  );
}

export function StationBoard({ repos }: { repos: RepoOut[] }) {
  const onboarded = repos.filter((r) => r.current_stage === "onboarded");
  const standardized = repos.filter((r) => r.current_stage === "standardized");

  return (
    <div className="flex gap-4 overflow-x-auto pb-3 mb-5">
      <RealColumn code="ON" title="Onboarded" color="#A79AE8" repos={onboarded} />
      <RealColumn code="ST" title="Standardized" color="#A79AE8" repos={standardized} />
      <EmptyColumn
        code="PI"
        title="Piped"
        color="#3FBBA0"
        message="Not live yet — unlocks once the CI/CD connector ships."
      />
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

- [ ] **Step 5: Wire `StationBoard` into `FleetPage`**

```tsx
// frontend/src/pages/FleetPage.tsx — add the import and render call
import { StationBoard } from "../components/fleet/StationBoard";
```

Add `<StationBoard repos={repos} />` immediately after `<Legend />` in the JSX.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/fleet/RepoCard.tsx frontend/src/components/fleet/StationBoard.tsx frontend/src/pages/FleetPage.tsx frontend/tests/components/fleet/StationBoard.test.tsx
git commit -m "feat: add Repo Fleet station board with repo cards and capped columns"
```

---

### Task 8: Repo Fleet page — stuck-now panel (final task)

**Files:**
- Create: `frontend/src/components/fleet/StuckPanel.tsx`
- Create: `frontend/tests/components/fleet/StuckPanel.test.tsx`
- Modify: `frontend/src/pages/FleetPage.tsx`
- Modify: `frontend/tests/pages/FleetPage.test.tsx`

**Interfaces:**
- Consumes: `RepoOut` (Task 2), `formatDwell` (Task 3).
- Produces: `function StuckPanel({ repos, expanded }: { repos: RepoOut[]; expanded: boolean }): JSX.Element` — hidden via the native `hidden` attribute (not just CSS) when `expanded` is `false`, so it's out of the accessibility tree when closed, per the design spec. Shows every stuck repo sorted by dwell time descending (longest first), each a full-width link to its Journey page.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/components/fleet/StuckPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { StuckPanel } from "../../../src/components/fleet/StuckPanel";
import type { RepoOut } from "../../../src/api/types";

function makeRepo(overrides: Partial<RepoOut>): RepoOut {
  return {
    id: 1,
    name: "repo",
    domain: null,
    team: null,
    migration_wave: "not_started",
    github_url: "https://github.com/acme/repo",
    last_synced_at: null,
    stages: {},
    current_stage: "standardized",
    is_stuck: true,
    dwell_days: 10,
    stuck_reason: "reason",
    ...overrides,
  };
}

function renderPanel(repos: RepoOut[], expanded: boolean) {
  return render(
    <MemoryRouter>
      <StuckPanel repos={repos} expanded={expanded} />
    </MemoryRouter>
  );
}

describe("StuckPanel", () => {
  it("is hidden via the native hidden attribute when not expanded", () => {
    const { container } = renderPanel([makeRepo({})], false);
    expect(container.querySelector('[data-testid="stuck-panel"]')).toHaveAttribute("hidden");
  });

  it("is visible (no hidden attribute) when expanded", () => {
    const { container } = renderPanel([makeRepo({})], true);
    expect(container.querySelector('[data-testid="stuck-panel"]')).not.toHaveAttribute("hidden");
  });

  it("sorts stuck repos by dwell time descending, worst first", () => {
    renderPanel(
      [
        makeRepo({ id: 1, name: "short-stuck", dwell_days: 5 }),
        makeRepo({ id: 2, name: "long-stuck", dwell_days: 41 }),
      ],
      true
    );

    const names = screen.getAllByTestId("stuck-row-name").map((el) => el.textContent);
    expect(names).toEqual(["long-stuck", "short-stuck"]);
  });

  it("excludes non-stuck repos even if present in the list", () => {
    renderPanel([makeRepo({ id: 1, name: "not-stuck", is_stuck: false, dwell_days: null })], true);

    expect(screen.queryByText("not-stuck")).not.toBeInTheDocument();
  });

  it("links each row to the repo's Journey page", () => {
    renderPanel([makeRepo({ id: 42, name: "checkout-web" })], true);

    expect(screen.getByRole("link", { name: /checkout-web/i })).toHaveAttribute("href", "/repos/42");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- StuckPanel.test.tsx`
Expected: FAIL with `Cannot find module '../../../src/components/fleet/StuckPanel'`

- [ ] **Step 3: Implement `StuckPanel.tsx`**

```tsx
// frontend/src/components/fleet/StuckPanel.tsx
import { Link } from "react-router-dom";
import type { RepoOut } from "../../api/types";
import { formatDwell } from "../../lib/format";

export function StuckPanel({ repos, expanded }: { repos: RepoOut[]; expanded: boolean }) {
  const stuckSorted = repos
    .filter((r) => r.is_stuck)
    .sort((a, b) => (b.dwell_days ?? 0) - (a.dwell_days ?? 0));

  return (
    <div
      data-testid="stuck-panel"
      hidden={!expanded}
      className="bg-bg-card border border-track3/35 rounded-xl p-4 mb-7"
    >
      <div className="font-mono text-[11px] uppercase tracking-wide text-track3 mb-3">Stuck now — worst first</div>
      {stuckSorted.map((repo, index) => (
        <Link
          key={repo.id}
          to={`/repos/${repo.id}`}
          className={`flex items-center gap-3 py-2.5 no-underline text-inherit ${index > 0 ? "border-t border-card-border" : ""}`}
        >
          <span data-testid="stuck-row-name" className="font-display font-bold text-[14px] flex-shrink-0 min-w-[170px]">
            {repo.name}
          </span>
          <span className="text-chalk-dim text-[13px] flex-1">{repo.stuck_reason}</span>
          <span className="font-mono font-bold text-track3 text-[13px] whitespace-nowrap tabular-nums">
            {formatDwell(repo.dwell_days)}
          </span>
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Wire `StuckPanel` into `FleetPage`**

```tsx
// frontend/src/pages/FleetPage.tsx — add the import and render call
import { StuckPanel } from "../components/fleet/StuckPanel";
```

Insert `<StuckPanel repos={repos} expanded={stuckExpanded} />` between `<Legend />` and `<StationBoard repos={repos} />` in the JSX.

- [ ] **Step 5: Update `FleetPage.test.tsx` to cover the stuck-toggle round trip**

Add to the existing test file:

```tsx
it("toggles the stuck panel's hidden attribute when the stat tile is clicked", async () => {
  const user = userEvent.setup();
  const repos: RepoOut[] = [
    {
      id: 1,
      name: "stuck-repo",
      domain: null,
      team: null,
      migration_wave: "not_started",
      github_url: "https://github.com/acme/stuck-repo",
      last_synced_at: null,
      stages: {},
      current_stage: "standardized",
      is_stuck: true,
      dwell_days: 20,
      stuck_reason: "reason",
    },
  ];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => repos }));

  const { container } = render(
    <MemoryRouter>
      <FleetPage />
    </MemoryRouter>
  );

  await waitFor(() => expect(screen.getByText("stuck-repo")).toBeInTheDocument());
  expect(container.querySelector('[data-testid="stuck-panel"]')).toHaveAttribute("hidden");

  await user.click(screen.getByRole("button", { name: /stuck/i }));

  expect(container.querySelector('[data-testid="stuck-panel"]')).not.toHaveAttribute("hidden");
});
```

Add `import userEvent from "@testing-library/user-event";` to the top of the file if not already present.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests — this is the last task, so confirm every test in the whole frontend suite passes, output pristine)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/fleet/StuckPanel.tsx frontend/src/pages/FleetPage.tsx frontend/tests/components/fleet/StuckPanel.test.tsx frontend/tests/pages/FleetPage.test.tsx
git commit -m "feat: add Repo Fleet stuck-now panel wired to the stat strip toggle"
```

---

## Self-Review Notes

- **Spec coverage:** Design tokens (§7.1/§7.2 shared palette) → Task 1. API contract (real backend shapes including `current_stage`/`is_stuck`/`dwell_days`/`stuck_reason`/`team`) → Task 2. Routing between the two primary screens → Task 3. Convergence diagram → Task 4. Station route list with exactly the three allowed badge states and Piped/Tested/Paved Road always Locked → Task 5. Hero/stat strip/legend (function-named, no track numbers) → Task 6. Station board with capped columns and the always-empty three columns → Task 7. Stuck-now panel with native `hidden`, sorted worst-first → Task 8.
- **Placeholder scan:** no TBD/TODO; every step has runnable code.
- **Type consistency:** `RepoOut`/`StageCheckOut` field names match the actual, already-shipped backend schema exactly (verified against `backend/app/schemas.py` — `current_stage`, `is_stuck`, `dwell_days`, `stuck_reason`, `team`, `github_url`, `last_synced_at` all present as of the backend-api-extensions merge).
- **Deferred by design, not a gap:** PATCH-based editing (domain/team/migration_wave), onboarding-log form, and the searchable/filterable table (§7.3/§7.4) are explicitly out of scope for this plan — the Fleet page's "View all" is a client-side expand, not a route, so no dead link is shipped.

---

## Next steps after this plan ships

1. Manually verify in a browser: run the backend (`uvicorn app.main:create_app --factory`) and `npm run dev` in `frontend/`, confirm the Fleet page loads real repo data and the Journey page renders correctly for a real repo id.
2. Write a follow-up plan for §7.3 (manual field editing, onboarding log UI) and §7.4 (searchable/filterable table) once this core is confirmed working end-to-end.
