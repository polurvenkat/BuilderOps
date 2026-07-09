import { render, screen } from "@testing-library/react";
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

  it("groups a piped repo into a real Piped column", () => {
    renderBoard([makeRepo({ id: 1, name: "piped-repo", current_stage: "piped" })]);

    expect(screen.getByText("piped-repo")).toBeInTheDocument();
  });

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

  it("caps the Piped column at 4 cards and links 'Show all N' to the Repos table filtered by stage", () => {
    const repos = Array.from({ length: 6 }, (_, i) =>
      makeRepo({ id: i + 1, name: `piped-repo-${i + 1}`, current_stage: "piped" })
    );
    renderBoard(repos);

    expect(screen.queryByText("piped-repo-5")).not.toBeInTheDocument();
    const showAllLink = screen.getByRole("link", { name: /show all 6/i });
    expect(showAllLink).toHaveAttribute("href", "/repos?stage=piped");
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

  it("links each repo card to its Journey page", () => {
    renderBoard([makeRepo({ id: 42, name: "checkout-web", current_stage: "standardized" })]);

    expect(screen.getByRole("link", { name: /checkout-web/i })).toHaveAttribute("href", "/repos/42");
  });

  it("shows all 5 repos uncapped when a column has exactly 5", () => {
    const repos = Array.from({ length: 5 }, (_, i) =>
      makeRepo({ id: i + 1, name: `repo-${i + 1}`, current_stage: "standardized" })
    );
    renderBoard(repos);

    for (let i = 1; i <= 5; i++) {
      expect(screen.getByText(`repo-${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /show all/i })).not.toBeInTheDocument();
  });

  it("shows the 4 longest-dwelling repos first when capped, not just array order", () => {
    const repos = [
      makeRepo({ id: 1, name: "repo-low-a", current_stage: "standardized", is_stuck: true, dwell_days: 2 }),
      makeRepo({ id: 2, name: "repo-high-a", current_stage: "standardized", is_stuck: true, dwell_days: 50 }),
      makeRepo({ id: 3, name: "repo-high-b", current_stage: "standardized", is_stuck: true, dwell_days: 40 }),
      makeRepo({ id: 4, name: "repo-low-b", current_stage: "standardized", is_stuck: true, dwell_days: 1 }),
      makeRepo({ id: 5, name: "repo-high-c", current_stage: "standardized", is_stuck: true, dwell_days: 30 }),
      makeRepo({ id: 6, name: "repo-high-d", current_stage: "standardized", is_stuck: true, dwell_days: 20 }),
    ];
    renderBoard(repos);

    expect(screen.getByText("repo-high-a")).toBeInTheDocument();
    expect(screen.getByText("repo-high-b")).toBeInTheDocument();
    expect(screen.getByText("repo-high-c")).toBeInTheDocument();
    expect(screen.getByText("repo-high-d")).toBeInTheDocument();
    expect(screen.queryByText("repo-low-a")).not.toBeInTheDocument();
    expect(screen.queryByText("repo-low-b")).not.toBeInTheDocument();
  });
});
