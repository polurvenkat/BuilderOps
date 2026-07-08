import httpx
import pytest

from app.connectors.ado_test_plans_connector import TestPlanRunResult, fetch_test_plan_latest_run

RUNS_RESPONSE = {"value": [
    {"id": 501, "state": "InProgress", "completedDate": None, "totalTests": 10, "passedTests": 0},
    {"id": 500, "state": "Completed", "completedDate": "2026-07-01T00:00:00Z", "totalTests": 20, "passedTests": 20},
    {"id": 502, "state": "Completed", "completedDate": "2026-07-08T00:00:00Z", "totalTests": 15, "passedTests": 13},
]}


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_picks_most_recent_completed_run():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url.path).endswith("/_apis/test/runs")
        assert request.url.params["planId"] == "42"
        return httpx.Response(200, json=RUNS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result == TestPlanRunResult(
        passed_count=13, failed_count=2, total_count=15, completed_date="2026-07-08T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_ignores_incomplete_runs():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [
            {"id": 501, "state": "InProgress", "completedDate": None, "totalTests": 10, "passedTests": 0},
        ]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_returns_none_when_no_runs_exist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_test_plan_latest_run(
            client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42,
        )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_test_plan_latest_run_sends_basic_auth_with_pat():
    import base64

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await fetch_test_plan_latest_run(client, org="acme-ado", project="acme-project", pat="ado-pat", test_plan_id=42)

    expected_token = base64.b64encode(b":ado-pat").decode()
    assert seen["authorization"] == f"Basic {expected_token}"
