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
  dockerize_eligible: null,
  e2e_test_plan_id: null,
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

  it("pre-fills the dockerize-eligible select from the repo's current value", () => {
    render(<RepoFieldsForm repo={{ ...REPO, dockerize_eligible: true }} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/dockerize eligible/i)).toHaveValue("true");
  });

  it("defaults the dockerize-eligible select to 'not yet assessed' when the repo has no value", () => {
    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/dockerize eligible/i)).toHaveValue("unset");
  });

  it("submits dockerize_eligible as a real boolean when changed from unset", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...REPO, dockerize_eligible: true }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.selectOptions(screen.getByLabelText(/dockerize eligible/i), "true");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toMatchObject({ dockerize_eligible: true });
  });

  it("omits dockerize_eligible from the PATCH body when left at not-yet-assessed", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPO });
    vi.stubGlobal("fetch", fetchMock);

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).not.toHaveProperty("dockerize_eligible");
  });

  it("pre-fills the E2E test plan ID from the repo's current value", () => {
    render(<RepoFieldsForm repo={{ ...REPO, e2e_test_plan_id: 42 }} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/e2e test plan id/i)).toHaveValue(42);
  });

  it("leaves the E2E test plan ID input blank when the repo has no value", () => {
    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);

    expect(screen.getByLabelText(/e2e test plan id/i)).toHaveValue(null);
  });

  it("submits e2e_test_plan_id as a real number when filled in", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...REPO, e2e_test_plan_id: 42 }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.type(screen.getByLabelText(/e2e test plan id/i), "42");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).toMatchObject({ e2e_test_plan_id: 42 });
  });

  it("omits e2e_test_plan_id from the PATCH body when left blank", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPO });
    vi.stubGlobal("fetch", fetchMock);

    render(<RepoFieldsForm repo={REPO} onUpdated={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body)).not.toHaveProperty("e2e_test_plan_id");
  });
});
