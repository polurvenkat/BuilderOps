import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
});
