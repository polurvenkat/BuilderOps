import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FleetPage } from "../../src/pages/FleetPage";
import { JourneyPage } from "../../src/pages/JourneyPage";
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

    await waitFor(() => expect(screen.getByText("Repo fleet")).toBeInTheDocument());
    expect(screen.getByText("CI/CD & environments")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

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

    await waitFor(() => expect(screen.getByTestId("stuck-row-name")).toBeInTheDocument());
    expect(container.querySelector('[data-testid="stuck-panel"]')).toHaveAttribute("hidden");

    await user.click(screen.getByRole("button", { name: /stuck/i }));

    expect(container.querySelector('[data-testid="stuck-panel"]')).not.toHaveAttribute("hidden");
  });

  it("shows an error state instead of silently rendering 0 stats when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    render(
      <MemoryRouter>
        <FleetPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
    expect(screen.queryByText("Repos tracked")).not.toBeInTheDocument();
    expect(screen.queryByText("Repo fleet")).not.toBeInTheDocument();
  });

  it("navigates from the fleet board to a repo's Journey page on click", async () => {
    const user = userEvent.setup();
    const repo: RepoOut = {
      id: 7,
      name: "checkout-web",
      domain: "Growth",
      team: "Growth",
      migration_wave: "not_started",
      github_url: "https://github.com/acme/checkout-web",
      last_synced_at: null,
      stages: {
        migrated_from_ado: { status: "pass", source: "auto", detail: null, updated_at: null },
      },
      current_stage: "standardized",
      is_stuck: false,
      dwell_days: 3,
      stuck_reason: null,
    };

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/onboarding-log")) {
          return Promise.resolve({ ok: true, json: async () => ({ entries: [], median_hours: null }) });
        }
        if (url.includes("/repos/7")) {
          return Promise.resolve({ ok: true, json: async () => repo });
        }
        return Promise.resolve({ ok: true, json: async () => [repo] });
      })
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<FleetPage />} />
          <Route path="/repos/:id" element={<JourneyPage />} />
        </Routes>
      </MemoryRouter>
    );

    const repoLink = await screen.findByRole("link", { name: /checkout-web/i });
    await user.click(repoLink);

    await waitFor(() => expect(screen.getByTestId("journey-page")).toBeInTheDocument());
    expect(screen.getByText("checkout-web")).toBeInTheDocument();
  });

  it("shows Board content by default and switches to Inventory on tab click", async () => {
    const user = userEvent.setup();
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
        app_count: 2,
        primary_language: "TypeScript",
        complexity: "medium",
      },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => repos }));

    render(
      <MemoryRouter>
        <FleetPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Repo fleet")).toBeInTheDocument());
    expect(screen.getByText("CI/CD & environments")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /inventory/i }));

    expect(screen.queryByText("CI/CD & environments")).not.toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
  });
});
