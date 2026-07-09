import json

import httpx
import pytest

from app.connectors.github_connector import GitHubRepoData, RenamedRepoData, fetch_repos, rename_repo

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
            "dockerfile": {"id": "dockerfile-1"},
            "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 2}]},
            "primaryLanguage": {"name": "TypeScript"},
            "languages": {"totalSize": 50000},
        },
        "r1": {
            "readme": None,
            "codeowners": None,
            "dockerfile": None,
            "branchProtectionRules": {"nodes": []},
            "primaryLanguage": None,
            "languages": {"totalSize": 0},
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
        dockerfile_present=True,
        branch_protection_enabled=True,
        required_reviewer_count=2,
        primary_language="TypeScript",
        total_code_bytes=50000,
    )
    assert repos[1] == GitHubRepoData(
        name="payments-api",
        url="https://github.com/acme-org/payments-api",
        has_readme=False,
        has_codeowners=False,
        dockerfile_present=False,
        branch_protection_enabled=False,
        required_reviewer_count=0,
        primary_language=None,
        total_code_bytes=0,
    )


@pytest.mark.asyncio
async def test_fetch_repos_raises_clear_error_when_graphql_returns_errors():
    graphql_error_response = {
        "data": {"organization": None},
        "errors": [
            {
                "type": "NOT_FOUND",
                "path": ["organization"],
                "message": "Could not resolve to an Organization with the login of 'wrong-org'.",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=graphql_error_response)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        with pytest.raises(RuntimeError, match="Could not resolve to an Organization with the login of 'wrong-org'"):
            await fetch_repos(client, org="wrong-org", token="gh-token")


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


@pytest.mark.asyncio
async def test_rename_repo_calls_the_real_rest_endpoint_and_returns_updated_name_and_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = str(request.url.path)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={
            "name": "checkout-web-v2",
            "html_url": "https://github.com/acme-org/checkout-web-v2",
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        result = await rename_repo(client, org="acme-org", token="gh-token", current_name="checkout-web", new_name="checkout-web-v2")

    assert seen["method"] == "PATCH"
    assert seen["path"] == "/repos/acme-org/checkout-web"
    assert seen["body"] == {"name": "checkout-web-v2"}
    assert result == RenamedRepoData(name="checkout-web-v2", url="https://github.com/acme-org/checkout-web-v2")


@pytest.mark.asyncio
async def test_rename_repo_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Validation Failed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await rename_repo(client, org="acme-org", token="gh-token", current_name="checkout-web", new_name="bad name")
