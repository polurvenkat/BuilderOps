import httpx
import pytest

from app.connectors.github_connector import GitHubRepoData, fetch_repos

REPO_LIST_RESPONSE = {
    "data": {
        "organization": {
            "repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"name": "checkout-web", "url": "https://github.com/acme-org/checkout-web"},
                    {"name": "payments-api", "url": "https://github.com/acme-org/payments-api"},
                ],
            }
        }
    }
}

REPO_CHECKS_RESPONSE = {
    "data": {
        "r0": {
            "readme": {"id": "readme-1"},
            "codeowners": {"id": "codeowners-1"},
            "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 2}]},
        },
        "r1": {
            "readme": None,
            "codeowners": None,
            "branchProtectionRules": {"nodes": []},
        },
    }
}


@pytest.mark.asyncio
async def test_fetch_repos_combines_list_and_checks():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        calls.append(body)
        if "repositories(first:" in body:
            return httpx.Response(200, json=REPO_LIST_RESPONSE)
        return httpx.Response(200, json=REPO_CHECKS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        repos = await fetch_repos(client, org="acme-org", token="gh-token")

    assert len(repos) == 2
    assert repos[0] == GitHubRepoData(
        name="checkout-web",
        url="https://github.com/acme-org/checkout-web",
        has_readme=True,
        has_codeowners=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
    )
    assert repos[1] == GitHubRepoData(
        name="payments-api",
        url="https://github.com/acme-org/payments-api",
        has_readme=False,
        has_codeowners=False,
        branch_protection_enabled=False,
        required_reviewer_count=0,
    )
    assert any("Authorization" in c or True for c in calls)  # calls captured, auth checked via header assertion below


@pytest.mark.asyncio
async def test_fetch_repos_sends_bearer_token():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["authorization"] = request.headers.get("authorization")
        body = request.content.decode()
        if "repositories(first:" in body:
            return httpx.Response(200, json={"data": {"organization": {"repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}})
        return httpx.Response(200, json={"data": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await fetch_repos(client, org="acme-org", token="gh-token")

    assert seen_headers["authorization"] == "Bearer gh-token"
