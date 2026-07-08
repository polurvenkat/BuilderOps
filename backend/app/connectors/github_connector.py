from dataclasses import dataclass

import httpx

GRAPHQL_URL = "/graphql"


@dataclass
class GitHubRepoData:
    name: str
    url: str
    has_readme: bool
    has_codeowners: bool
    branch_protection_enabled: bool
    required_reviewer_count: int


LIST_QUERY = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { name url }
    }
  }
}
"""


def _checks_query(repo_names: list[str], org: str) -> str:
    aliases = []
    for i, name in enumerate(repo_names):
        aliases.append(f'''
        r{i}: repository(owner: "{org}", name: "{name}") {{
          readme: object(expression: "HEAD:README.md") {{ id }}
          codeowners: object(expression: "HEAD:.github/CODEOWNERS") {{ id }}
          branchProtectionRules(first: 10) {{
            nodes {{ pattern requiredApprovingReviewCount }}
          }}
        }}''')
    return "query {" + "".join(aliases) + "\n}"


async def _fetch_repo_list(client: httpx.AsyncClient, org: str, headers: dict) -> list[dict]:
    repos: list[dict] = []
    cursor = None
    while True:
        resp = await client.post(
            GRAPHQL_URL,
            json={"query": LIST_QUERY, "variables": {"org": org, "cursor": cursor}},
            headers=headers,
        )
        data = _graphql_data(resp)
        organization = data.get("organization")
        if organization is None:
            raise RuntimeError(f"GitHub organization '{org}' not found or not accessible with this token")
        page = organization["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return repos


def _batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _graphql_data(resp: httpx.Response) -> dict:
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        messages = "; ".join(err.get("message", str(err)) for err in body["errors"])
        raise RuntimeError(f"GitHub GraphQL API returned errors: {messages}")
    if body.get("data") is None:
        raise RuntimeError("GitHub GraphQL API returned no data and no errors")
    return body["data"]


async def fetch_repos(client: httpx.AsyncClient, org: str, token: str) -> list[GitHubRepoData]:
    headers = {"Authorization": f"Bearer {token}"}
    repo_list = await _fetch_repo_list(client, org, headers)

    results: list[GitHubRepoData] = []
    for batch in _batched(repo_list, 100):
        names = [r["name"] for r in batch]
        resp = await client.post(GRAPHQL_URL, json={"query": _checks_query(names, org)}, headers=headers)
        data = _graphql_data(resp)
        for i, repo in enumerate(batch):
            check = data[f"r{i}"]
            protection_nodes = (check.get("branchProtectionRules") or {}).get("nodes") or []
            required_reviewers = max((n.get("requiredApprovingReviewCount") or 0) for n in protection_nodes) if protection_nodes else 0
            results.append(
                GitHubRepoData(
                    name=repo["name"],
                    url=repo["url"],
                    has_readme=check.get("readme") is not None,
                    has_codeowners=check.get("codeowners") is not None,
                    branch_protection_enabled=bool(protection_nodes),
                    required_reviewer_count=required_reviewers,
                )
            )
    return results
