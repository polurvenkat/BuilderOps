import base64

import httpx
import pytest

from app.connectors.ado_connector import AdoRepoData, fetch_ado_repos

ADO_LIST_RESPONSE = {
    "value": [
        {"name": "legacy-batch", "project": {"lastUpdateTime": "2026-05-01T00:00:00Z"}},
        {"name": "checkout-web", "project": {"lastUpdateTime": "2026-06-10T00:00:00Z"}},
    ]
}


@pytest.mark.asyncio
async def test_fetch_ado_repos_parses_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/acme-project/_apis/git/repositories" in str(request.url)
        return httpx.Response(200, json=ADO_LIST_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        repos = await fetch_ado_repos(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert repos == [
        AdoRepoData(name="legacy-batch", last_activity="2026-05-01T00:00:00Z"),
        AdoRepoData(name="checkout-web", last_activity="2026-06-10T00:00:00Z"),
    ]


@pytest.mark.asyncio
async def test_fetch_ado_repos_sends_basic_auth_with_pat():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await fetch_ado_repos(client, org="acme-ado", project="acme-project", pat="ado-pat")

    expected_token = base64.b64encode(b":ado-pat").decode()
    assert seen["authorization"] == f"Basic {expected_token}"
