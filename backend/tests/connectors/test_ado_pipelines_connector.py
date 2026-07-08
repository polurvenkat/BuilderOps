import httpx
import pytest

from app.connectors.ado_pipelines_connector import (
    PipelineLinkData,
    ReleaseDefinitionData,
    fetch_pipeline_links,
    fetch_release_definitions,
    fetch_environment_checks,
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


ENVIRONMENTS_RESPONSE = {
    "value": [
        {"id": 10, "name": "Dev Deployment"},
        {"id": 11, "name": "QA Deployment"},
        {"id": 12, "name": "UAT Deployment"},
        {"id": 13, "name": "Prod Deployment"},
    ]
}


@pytest.mark.asyncio
async def test_fetch_environment_checks_reports_configured_gates():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines/environments"):
            return httpx.Response(200, json=ENVIRONMENTS_RESPONSE)
        env_id = int(request.url.params["resourceId"])
        has_check = env_id in (12, 13)  # UAT and Prod are gated; Dev and QA are not
        return httpx.Response(200, json={"value": [{"id": 1}] if has_check else []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        gates = await fetch_environment_checks(
            client, org="acme-ado", project="acme-project", pat="ado-pat",
            environment_names=["dev", "qa", "uat", "prod"],
        )

    assert gates == {"dev": False, "qa": False, "uat": True, "prod": True}


@pytest.mark.asyncio
async def test_fetch_environment_checks_omits_unmatched_environment_names():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines/environments"):
            return httpx.Response(200, json={"value": [{"id": 12, "name": "UAT Deployment"}]})
        return httpx.Response(200, json={"value": [{"id": 1}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        gates = await fetch_environment_checks(
            client, org="acme-ado", project="acme-project", pat="ado-pat",
            environment_names=["dev", "qa", "uat", "prod"],
        )

    assert gates == {"uat": True}
    assert "dev" not in gates and "qa" not in gates and "prod" not in gates
