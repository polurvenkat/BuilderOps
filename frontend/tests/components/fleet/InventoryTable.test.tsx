import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InventoryTable } from "../../../src/components/fleet/InventoryTable";
import type { RepoOut } from "../../../src/api/types";

const REPO: RepoOut = {
  id: 1,
  name: "Ovs.Core.Models",
  domain: "Growth",
  team: "Growth",
  migration_wave: "migrated",
  github_url: "https://github.com/acme/Ovs.Core.Models",
  last_synced_at: null,
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
  app_count: 3,
  primary_language: "C#",
  complexity: "high",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("InventoryTable", () => {
  it("renders one row per repo with technology and complexity badges", () => {
    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);

    expect(screen.getByText("Ovs.Core.Models")).toBeInTheDocument();
    expect(screen.getByText("C#")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("defaults the rename input to the kebab-case of the current name", () => {
    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/New name for Ovs.Core.Models/i)).toHaveValue("ovs-core-models");
  });

  it("disables Apply when the rename input already matches the current name", async () => {
    const user = userEvent.setup();
    const unchanged: RepoOut = { ...REPO, name: "already-kebab-case" };
    render(<InventoryTable repos={[unchanged]} onUpdated={vi.fn()} />);

    const input = screen.getByLabelText(/New name for already-kebab-case/i);
    await user.clear(input);
    await user.type(input, "already-kebab-case");

    expect(screen.getByRole("button", { name: /apply/i })).toBeDisabled();
  });

  it("confirms before renaming, then PATCHes and updates the row on confirm", async () => {
    const user = userEvent.setup();
    const renamedRepo = { ...REPO, name: "ovs-core-models" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => renamedRepo }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onUpdated = vi.fn();

    render(<InventoryTable repos={[REPO]} onUpdated={onUpdated} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(renamedRepo));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Ovs.Core.Models"));
    expect(screen.getByText(/pipeline links re-check/i)).toBeInTheDocument();
  });

  it("does not call patchRepo when the user cancels the confirm dialog", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows an inline error when the rename PATCH fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<InventoryTable repos={[REPO]} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => expect(screen.getByText(/502/)).toBeInTheDocument());
  });

  it("commits the app count on blur", async () => {
    const user = userEvent.setup();
    const updatedRepo = { ...REPO, app_count: 5 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => updatedRepo }));
    const onUpdated = vi.fn();

    render(<InventoryTable repos={[REPO]} onUpdated={onUpdated} />);
    const appsInput = screen.getByLabelText(/App count for Ovs.Core.Models/i);
    await user.clear(appsInput);
    await user.type(appsInput, "5");
    await user.tab();

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepo));
  });
});
