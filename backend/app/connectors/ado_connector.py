import base64
from dataclasses import dataclass

import httpx


@dataclass
class AdoRepoData:
    name: str
    last_activity: str | None


def _basic_auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {token}"


async def fetch_ado_repos(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[AdoRepoData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/git/repositories",
        params={"api-version": "7.1"},
        headers=headers,
    )
    resp.raise_for_status()
    body = resp.json()
    return [
        AdoRepoData(
            name=item["name"],
            last_activity=(item.get("project") or {}).get("lastUpdateTime"),
        )
        for item in body["value"]
    ]
