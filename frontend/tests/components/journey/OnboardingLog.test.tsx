import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OnboardingLog } from "../../../src/components/journey/OnboardingLog";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OnboardingLog", () => {
  it("shows a no-entries message when the summary is empty", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ entries: [], median_hours: null }) }));

    render(<OnboardingLog repoId={1} />);

    await waitFor(() => expect(screen.getByText(/no entries logged yet/i)).toBeInTheDocument());
  });

  it("shows the median and lists entries once loaded", async () => {
    const summary = {
      entries: [
        { id: 1, repo_id: 1, engineer_name: "Sam", hours: 4, logged_at: "2026-07-01T00:00:00Z" },
        { id: 2, repo_id: 1, engineer_name: "Alex", hours: 8, logged_at: "2026-07-02T00:00:00Z" },
      ],
      median_hours: 6,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => summary }));

    render(<OnboardingLog repoId={1} />);

    await waitFor(() => expect(screen.getByText(/6/)).toBeInTheDocument());
    expect(screen.getByText("Sam")).toBeInTheDocument();
    expect(screen.getByText("Alex")).toBeInTheDocument();
  });

  it("logs a new entry and refetches the summary", async () => {
    const user = userEvent.setup();
    const emptySummary = { entries: [], median_hours: null };
    const afterPostSummary = {
      entries: [{ id: 1, repo_id: 1, engineer_name: "Jo", hours: 5, logged_at: "2026-07-08T00:00:00Z" }],
      median_hours: 5,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => emptySummary }) // initial load
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 1, repo_id: 1, engineer_name: "Jo", hours: 5, logged_at: "2026-07-08T00:00:00Z" }) }) // POST
      .mockResolvedValueOnce({ ok: true, json: async () => afterPostSummary }); // refetch
    vi.stubGlobal("fetch", fetchMock);

    render(<OnboardingLog repoId={1} />);
    await waitFor(() => expect(screen.getByText(/no entries logged yet/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/engineer/i), "Jo");
    await user.type(screen.getByLabelText(/hours/i), "5");
    await user.click(screen.getByRole("button", { name: /log/i }));

    await waitFor(() => expect(screen.getByText("Jo")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
