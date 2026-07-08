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
