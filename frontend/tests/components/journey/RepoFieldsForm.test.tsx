import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RepoFieldsForm } from "../../../src/components/journey/RepoFieldsForm";
import type { RepoOut } from "../../../src/api/types";

const REPO: RepoOut = {
  id: 1,
  name: "checkout-web",
  domain: "Growth",
  team: "Growth",
  migration_wave: "pilot",
  github_url: "https://github.com/acme/checkout-web",
  last_synced_at: null,
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RepoFieldsForm", () => {
  it("pre-fills the form with the repo's current field values", () => {
    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/domain/i)).toHaveValue("Growth");
    expect(screen.getByLabelText(/team/i)).toHaveValue("Growth");
    expect(screen.getByLabelText(/wave/i)).toHaveValue("pilot");
  });

  it("submits the edited fields via patchRepo and calls onUpdated with the result", async () => {
    const user = userEvent.setup();
    const updatedRepo = { ...REPO, domain: "Checkout" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => updatedRepo }));
    const onUpdated = vi.fn();

    render(<RepoFieldsForm repo={REPO} onUpdated={onUpdated} />);
    await user.clear(screen.getByLabelText(/domain/i));
    await user.type(screen.getByLabelText(/domain/i), "Checkout");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepo));
    expect(screen.getByText(/saved/i)).toBeInTheDocument();
  });

  it("shows an inline error and preserves the edit if the save fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.clear(screen.getByLabelText(/domain/i));
    await user.type(screen.getByLabelText(/domain/i), "Checkout");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/422/)).toBeInTheDocument());
    expect(screen.getByLabelText(/domain/i)).toHaveValue("Checkout");
  });
});
