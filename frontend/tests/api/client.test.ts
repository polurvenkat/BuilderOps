import { afterEach, describe, expect, it, vi } from "vitest";
import { getRepo, listRepos } from "../../src/api/client";
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
