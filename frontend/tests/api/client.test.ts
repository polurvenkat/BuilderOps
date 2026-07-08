import { afterEach, describe, expect, it, vi } from "vitest";
import { getOnboardingLog, getPipelineStatus, getRepo, listRepos, patchRepo, postOnboardingLog } from "../../src/api/client";
import type { RepoOut } from "../../src/api/types";

const SAMPLE_REPO: RepoOut = {
  id: 1,
  name: "checkout-web",
  domain: "Growth",
  team: "Growth",
  migration_wave: "not_started",
  github_url: "https://github.com/acme/checkout-web",
  last_synced_at: "2026-07-08T00:00:00Z",
  stages: {},
  current_stage: "standardized",
  is_stuck: false,
  dwell_days: null,
  stuck_reason: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listRepos", () => {
  it("fetches /repos with no query string when no params given", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [SAMPLE_REPO],
    });
    vi.stubGlobal("fetch", fetchMock);

    const repos = await listRepos();

    expect(repos).toEqual([SAMPLE_REPO]);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toMatch(/\/repos$/);
  });

  it("builds a query string from stage/domain/sort params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    await listRepos({ stage: "onboarded", domain: "Growth", sort: "dwell_desc" });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("stage=onboarded");
    expect(calledUrl).toContain("domain=Growth");
    expect(calledUrl).toContain("sort=dwell_desc");
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(listRepos()).rejects.toThrow(/500/);
  });
});

describe("getRepo", () => {
  it("fetches /repos/{id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => SAMPLE_REPO });
    vi.stubGlobal("fetch", fetchMock);

    const repo = await getRepo(1);

    expect(repo).toEqual(SAMPLE_REPO);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1$/);
  });

  it("throws a descriptive error on a 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    await expect(getRepo(999)).rejects.toThrow(/404/);
  });
});

describe("patchRepo", () => {
  it("sends a PATCH with the body as JSON and returns the updated repo", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => SAMPLE_REPO });
    vi.stubGlobal("fetch", fetchMock);

    const repo = await patchRepo(1, { domain: "Growth", team: "Growth" });

    expect(repo).toEqual(SAMPLE_REPO);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/repos\/1$/);
    expect(options.method).toBe("PATCH");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ domain: "Growth", team: "Growth" });
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));

    await expect(patchRepo(1, { domain: "Growth" })).rejects.toThrow(/422/);
  });
});

describe("getOnboardingLog", () => {
  it("fetches the onboarding log summary for a repo", async () => {
    const summary = { entries: [], median_hours: null };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => summary });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getOnboardingLog(1);

    expect(result).toEqual(summary);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1\/onboarding-log$/);
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    await expect(getOnboardingLog(999)).rejects.toThrow(/404/);
  });
});

describe("postOnboardingLog", () => {
  it("sends a POST with the entry as JSON and returns the created entry", async () => {
    const entry = { id: 1, repo_id: 1, engineer_name: "Sam", hours: 4.5, logged_at: "2026-07-08T00:00:00Z" };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => entry });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOnboardingLog(1, { engineer_name: "Sam", hours: 4.5 });

    expect(result).toEqual(entry);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/repos\/1\/onboarding-log$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ engineer_name: "Sam", hours: 4.5 });
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(postOnboardingLog(1, { engineer_name: "Sam", hours: 4.5 })).rejects.toThrow(/500/);
  });
});

describe("getPipelineStatus", () => {
  it("fetches the live pipeline status for a repo", async () => {
    const status = { stages: [{ name: "Build", status: "succeeded", pending_approval_description: null }] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => status });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getPipelineStatus(1);

    expect(result).toEqual(status);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/repos\/1\/pipeline-status$/);
  });

  it("throws a descriptive error on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));

    await expect(getPipelineStatus(1)).rejects.toThrow(/502/);
  });
});
