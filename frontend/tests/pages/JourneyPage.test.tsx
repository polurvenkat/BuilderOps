import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

async function clickDetails(cardElement: HTMLElement) {
  const user = userEvent.setup();
  await user.click(within(cardElement).getByRole("button", { name: /details/i }));
}

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

describe("JourneyPage", () => {
  it("shows a loading state, then the repo's name and stuck reason once loaded", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => STUCK_REPO })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
    vi.stubGlobal("fetch", fetchMock);

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    expect(screen.getByText(/No CODEOWNERS assigned/)).toBeInTheDocument();
  });

  it("links back to the Fleet landing page", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => STUCK_REPO })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
    vi.stubGlobal("fetch", fetchMock);

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /BuilderOps · Repo Status/ })).toHaveAttribute("href", "/");
  });

  it("renders Piped and Tested as Locked when neither is mapped, and Paved Road as always Locked", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => STUCK_REPO })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
    vi.stubGlobal("fetch", fetchMock);

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());
    const lockedBadges = screen.getAllByText("Locked");
    expect(lockedBadges.length).toBe(3); // Piped, Tested, Paved Road
  });

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

  it("shows an error state when the fetch fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
    vi.stubGlobal("fetch", fetchMock);

    renderAtRepo("999");

    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });

  it("shows the actual failing sub-check (branch_protection), not codeowners_assigned, when stuck at standardized", async () => {
    const repo: RepoOut = {
      ...STUCK_REPO,
      stages: {
        ...STUCK_REPO.stages,
        codeowners_assigned: { status: "pass", source: "auto", detail: null, updated_at: "2026-06-01T00:00:00Z" },
        branch_protection: { status: "fail", source: "auto", detail: null, updated_at: "2026-07-03T00:00:00Z" },
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => repo })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
    vi.stubGlobal("fetch", fetchMock);

    renderAtRepo("1");

    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());

    const standardizedCard = screen.getByText("ST-01").closest("div.rounded-xl") as HTMLElement;
    expect(within(standardizedCard).getByText("Status: fail")).toBeInTheDocument();
    expect(within(standardizedCard).queryByText("Status: pass")).not.toBeInTheDocument();
  });

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

  it("counts pipeline stages toward progress via case-insensitive substring matching, not just exact names", async () => {
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
            { name: "Deploy to Dev", status: "succeeded", pending_approval_description: null },
            { name: "QA Environment", status: "succeeded", pending_approval_description: null },
            { name: "uat sign-off", status: "succeeded", pending_approval_description: null },
            { name: "Production", status: "succeeded", pending_approval_description: null },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderAtRepo("2");

    await waitFor(() => expect(screen.getByText("checkout-web-piped")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Deploy to Dev")).toBeInTheDocument());

    const pipelineLine = container.querySelector('[data-line="pipeline"]');
    expect(pipelineLine).toHaveAttribute("stroke-dasharray", "100 100");
  });
});
