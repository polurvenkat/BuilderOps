from dataclasses import dataclass

import httpx

from app.connectors.ado_connector import _basic_auth_header


@dataclass
class TestPlanRunResult:
    passed_count: int
    failed_count: int
    total_count: int
    completed_date: str


async def fetch_test_plan_latest_run(
    client: httpx.AsyncClient, org: str, project: str, pat: str, test_plan_id: int
) -> TestPlanRunResult | None:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/test/runs",
        params={"api-version": "7.1", "planId": test_plan_id},
        headers=headers,
    )
    resp.raise_for_status()
    runs = resp.json()["value"]

    completed_runs = [r for r in runs if r.get("state") == "Completed"]
    if not completed_runs:
        return None

    latest_run = max(completed_runs, key=lambda r: r["completedDate"])
    total_count = latest_run["totalTests"]
    passed_count = latest_run["passedTests"]
    return TestPlanRunResult(
        passed_count=passed_count,
        failed_count=total_count - passed_count,
        total_count=total_count,
        completed_date=latest_run["completedDate"],
    )
