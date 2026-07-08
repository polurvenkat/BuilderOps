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
