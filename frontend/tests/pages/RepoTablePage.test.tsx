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
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderTable();
    await waitFor(() => expect(screen.getByText("checkout-web")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /export csv/i }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsText(blob);
    });
    expect(text).toContain("checkout-web");
    expect(text.split("\n")[0]).toContain("Name");
  });

  it("renders a column header for each Piped-card check", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [makeRepo({})] }));

    renderTable();

    await waitFor(() => expect(screen.getByText("repo")).toBeInTheDocument());
    ["pipe", "envi", "dock", "depl"].forEach((prefix) => {
      expect(screen.getAllByTitle(new RegExp(`^${prefix}`)).length).toBeGreaterThan(0);
    });
  });
});
