import httpx
import pytest

from app.connectors.ado_pipelines_connector import (
    PipelineLinkData,
    ReleaseDefinitionData,
    fetch_pipeline_links,
    fetch_release_definitions,
)

PIPELINES_LIST_RESPONSE = {"value": [{"id": 7, "name": "checkout-web-ci"}]}

PIPELINE_DETAIL_RESPONSE = {
    "id": 7,
    "name": "checkout-web-ci",
    "configuration": {
        "type": "yaml",
        "repository": {"url": "https://github.com/acme-org/checkout-web"},
    },
}

RELEASE_DEFINITIONS_RESPONSE = {"value": [{"id": 3, "name": "legacy-batch-classic-release"}]}


@pytest.mark.asyncio
async def test_fetch_pipeline_links_combines_list_and_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        return httpx.Response(200, json=PIPELINE_DETAIL_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links == [
        PipelineLinkData(
            pipeline_id=7,
            pipeline_name="checkout-web-ci",
            repository_url="https://github.com/acme-org/checkout-web",
            is_yaml=True,
        )
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_links_flags_classic_pipelines_as_not_yaml():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url.path).endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        return httpx.Response(200, json={
            "id": 7, "name": "checkout-web-ci",
            "configuration": {"type": "designerJson", "repository": {"url": "https://github.com/acme-org/checkout-web"}},
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links[0].is_yaml is False


@pytest.mark.asyncio
async def test_fetch_release_definitions_parses_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RELEASE_DEFINITIONS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://vsrm.dev.azure.com/acme-ado") as client:
        defs = await fetch_release_definitions(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert defs == [ReleaseDefinitionData(definition_id=3, name="legacy-batch-classic-release")]
