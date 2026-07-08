import type { ListReposParams, RepoOut } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function listRepos(params: ListReposParams = {}): Promise<RepoOut[]> {
  const search = new URLSearchParams();
  if (params.stage) search.set("stage", params.stage);
  if (params.domain) search.set("domain", params.domain);
  if (params.sort) search.set("sort", params.sort);
  const query = search.toString();

  const response = await fetch(`${BASE_URL}/repos${query ? `?${query}` : ""}`);
  if (!response.ok) {
    throw new Error(`Failed to list repos: HTTP ${response.status}`);
  }
  return response.json();
}

export async function getRepo(id: number): Promise<RepoOut> {
  const response = await fetch(`${BASE_URL}/repos/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to get repo ${id}: HTTP ${response.status}`);
  }
  return response.json();
}
