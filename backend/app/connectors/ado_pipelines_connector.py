from dataclasses import dataclass

import httpx

from app.connectors.ado_connector import _basic_auth_header


@dataclass
class PipelineLinkData:
    pipeline_id: int
    pipeline_name: str
    repository_url: str
    is_yaml: bool


@dataclass
class ReleaseDefinitionData:
    definition_id: int
    name: str


async def fetch_pipeline_links(client: httpx.AsyncClient, org: str, project: str, pat: str) -> list[PipelineLinkData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    list_resp = await client.get(f"/{project}/_apis/pipelines", params={"api-version": "7.1"}, headers=headers)
    list_resp.raise_for_status()
    pipelines = list_resp.json()["value"]

    results: list[PipelineLinkData] = []
    for pipeline in pipelines:
        detail_resp = await client.get(
            f"/{project}/_apis/pipelines/{pipeline['id']}", params={"api-version": "7.1"}, headers=headers,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
        configuration = detail.get("configuration") or {}
        repository = configuration.get("repository") or {}
        results.append(
            PipelineLinkData(
                pipeline_id=detail["id"],
                pipeline_name=detail["name"],
                repository_url=repository.get("url", ""),
                is_yaml=configuration.get("type") == "yaml",
            )
        )
    return results


async def fetch_release_definitions(
    client: httpx.AsyncClient, org: str, project: str, pat: str
) -> list[ReleaseDefinitionData]:
    headers = {"Authorization": _basic_auth_header(pat)}
    resp = await client.get(f"/{project}/_apis/release/definitions", params={"api-version": "7.1"}, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return [ReleaseDefinitionData(definition_id=item["id"], name=item["name"]) for item in body["value"]]
