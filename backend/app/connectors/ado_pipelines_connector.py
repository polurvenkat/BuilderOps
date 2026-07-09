from dataclasses import dataclass

import httpx

from app.connectors.ado_connector import _basic_auth_header


@dataclass
class PipelineLinkData:
    pipeline_id: int
    pipeline_name: str
    repository_name: str
    is_yaml: bool


@dataclass
class ReleaseDefinitionData:
    definition_id: int
    name: str


@dataclass
class PipelineDetailData:
    pipeline_id: int
    pipeline_name: str
    is_yaml: bool


async def fetch_azure_git_repos(client: httpx.AsyncClient, org: str, project: str, pat: str) -> dict[str, str]:
    """Map Azure Repos Git repository GUID -> repository name for this project.

    ADO pipeline configurations backed by Azure Repos Git identify their repository by an
    opaque GUID (configuration.repository.id), not a URL or name -- this resolves that GUID
    so pipelines can be matched against a tracked repo's name.
    """
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(f"/{project}/_apis/git/repositories", params={"api-version": "7.1"}, headers=headers)
    resp.raise_for_status()
    return {item["id"]: item["name"] for item in resp.json()["value"]}


async def fetch_pipeline_links(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[PipelineLinkData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    list_resp = await client.get(f"/{project}/_apis/pipelines", params={"api-version": "7.1"}, headers=headers)
    list_resp.raise_for_status()
    pipelines = list_resp.json()["value"]

    azure_git_repo_names = await fetch_azure_git_repos(client, org=org, project=project, pat=pat)

    results: list[PipelineLinkData] = []
    for pipeline in pipelines:
        detail_resp = await client.get(
            f"/{project}/_apis/pipelines/{pipeline['id']}", params={"api-version": "7.1"}, headers=headers,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
        configuration = detail.get("configuration") or {}
        repository = configuration.get("repository") or {}
        repository_type = repository.get("type", "")

        # ADO never returns a plain "url" for either repository type: a gitHub-backed
        # pipeline's repository identifies itself via "fullName" (org/repo), and an
        # azureReposGit-backed pipeline via an opaque "id" GUID resolved above.
        if repository_type in ("gitHub", "gitHubEnterprise"):
            full_name = repository.get("fullName", "")
            repository_name = full_name.rsplit("/", 1)[-1] if full_name else ""
        elif repository_type == "azureReposGit":
            repository_name = azure_git_repo_names.get(repository.get("id", ""), "")
        else:
            repository_name = ""

        results.append(
            PipelineLinkData(
                pipeline_id=detail["id"],
                pipeline_name=detail["name"],
                repository_name=repository_name,
                is_yaml=configuration.get("type") == "yaml",
            )
        )
    return results


async def fetch_pipeline_detail(
    client: httpx.AsyncClient, org: str, project: str, pat: str, pipeline_id: int
) -> PipelineDetailData:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/pipelines/{pipeline_id}", params={"api-version": "7.1"}, headers=headers,
    )
    resp.raise_for_status()
    detail = resp.json()
    configuration = detail.get("configuration") or {}
    return PipelineDetailData(
        pipeline_id=detail["id"],
        pipeline_name=detail["name"],
        is_yaml=configuration.get("type") == "yaml",
    )


async def fetch_release_definitions(
    client: httpx.AsyncClient, org: str, project: str, pat: str
) -> list[ReleaseDefinitionData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(f"/{project}/_apis/release/definitions", params={"api-version": "7.1"}, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return [ReleaseDefinitionData(definition_id=item["id"], name=item["name"]) for item in body["value"]]


async def fetch_environment_checks(
    client: httpx.AsyncClient, org: str, project: str, pat: str, environment_names: list[str]
) -> dict[str, bool]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(
        f"/{project}/_apis/pipelines/environments", params={"api-version": "7.1-preview.1"}, headers=headers,
    )
    resp.raise_for_status()
    environments = resp.json()["value"]

    result: dict[str, bool] = {}
    for target_name in environment_names:
        match = next((e for e in environments if target_name.lower() in e["name"].lower()), None)
        if match is None:
            continue
        checks_resp = await client.get(
            f"/{project}/_apis/pipelines/checks/configurations",
            params={"api-version": "7.1-preview.1", "resourceType": "environment", "resourceId": match["id"]},
            headers=headers,
        )
        checks_resp.raise_for_status()
        result[target_name] = len(checks_resp.json()["value"]) > 0
    return result


@dataclass
class PipelineStageStatus:
    name: str
    status: str
    pending_approval_description: str | None = None


async def fetch_pipeline_run_status(
    client: httpx.AsyncClient, org: str, project: str, pat: str, pipeline_id: int
) -> list[PipelineStageStatus]:
    headers = {"Authorization": _basic_auth_header(pat)}
    runs_resp = await client.get(
        f"/{project}/_apis/pipelines/{pipeline_id}/runs", params={"api-version": "7.1"}, headers=headers,
    )
    runs_resp.raise_for_status()
    runs = runs_resp.json()["value"]
    if not runs:
        return []
    latest_run = max(runs, key=lambda r: r["createdDate"])

    timeline_resp = await client.get(
        f"/{project}/_apis/build/builds/{latest_run['id']}/timeline", params={"api-version": "7.1"}, headers=headers,
    )
    timeline_resp.raise_for_status()
    records = timeline_resp.json()["records"]
    stage_records = sorted((r for r in records if r["type"] == "Stage"), key=lambda r: r.get("order", 0))

    stages: list[PipelineStageStatus] = []
    for record in stage_records:
        pending_approvals = (record.get("checkpoint") or {}).get("pendingApprovals") or []
        if pending_approvals:
            stages.append(PipelineStageStatus(
                name=record["name"], status="waiting_approval",
                pending_approval_description=pending_approvals[0]["description"],
            ))
        elif record["state"] == "completed" and record["result"] == "succeeded":
            stages.append(PipelineStageStatus(name=record["name"], status="succeeded"))
        elif record["state"] == "completed" and record["result"] == "failed":
            stages.append(PipelineStageStatus(name=record["name"], status="failed"))
        elif record["state"] == "inProgress":
            stages.append(PipelineStageStatus(name=record["name"], status="in_progress"))
        else:
            stages.append(PipelineStageStatus(name=record["name"], status="not_started"))
    return stages
