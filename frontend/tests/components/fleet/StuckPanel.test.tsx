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
