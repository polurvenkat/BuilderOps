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
