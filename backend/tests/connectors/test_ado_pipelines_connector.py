import httpx
import pytest

from app.connectors.ado_pipelines_connector import (
    PipelineDetailData,
    PipelineLinkData,
    PipelineStageStatus,
    ReleaseDefinitionData,
    fetch_azure_git_repos,
    fetch_pipeline_detail,
    fetch_pipeline_links,
    fetch_release_definitions,
    fetch_environment_checks,
    fetch_pipeline_run_status,
)

PIPELINES_LIST_RESPONSE = {"value": [{"id": 7, "name": "checkout-web-ci"}]}

# Real ADO pipeline configurations never return a "url" field for either repository type:
# a gitHub-backed pipeline identifies its repo via "fullName" (org/repo), and an
# azureReposGit-backed pipeline via an opaque "id" GUID (resolved separately, see
# fetch_azure_git_repos).
PIPELINE_DETAIL_RESPONSE = {
    "id": 7,
    "name": "checkout-web-ci",
    "configuration": {
        "type": "yaml",
        "repository": {"type": "gitHub", "fullName": "acme-org/checkout-web"},
    },
}

RELEASE_DEFINITIONS_RESPONSE = {"value": [{"id": 3, "name": "legacy-batch-classic-release"}]}

GIT_REPOS_RESPONSE = {"value": []}


def _pipelines_handler_returning(detail_response):
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        if path.endswith("/_apis/git/repositories"):
            return httpx.Response(200, json=GIT_REPOS_RESPONSE)
        return httpx.Response(200, json=detail_response)

    return handler


@pytest.mark.asyncio
async def test_fetch_pipeline_links_resolves_github_backed_pipeline_by_full_name():
    transport = httpx.MockTransport(_pipelines_handler_returning(PIPELINE_DETAIL_RESPONSE))
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links == [
        PipelineLinkData(
            pipeline_id=7,
            pipeline_name="checkout-web-ci",
            repository_name="checkout-web",
            is_yaml=True,
        )
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_links_resolves_azure_repos_git_pipeline_via_guid():
    detail_response = {
        "id": 7, "name": "checkout-web-ci",
        "configuration": {"type": "yaml", "repository": {"type": "azureReposGit", "id": "guid-123"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_RESPONSE)
        if path.endswith("/_apis/git/repositories"):
            return httpx.Response(200, json={"value": [{"id": "guid-123", "name": "checkout-web"}]})
        return httpx.Response(200, json=detail_response)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links == [
        PipelineLinkData(pipeline_id=7, pipeline_name="checkout-web-ci", repository_name="checkout-web", is_yaml=True)
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_links_leaves_repository_name_empty_when_unresolvable():
    detail_response = {
        "id": 7, "name": "checkout-web-ci",
        "configuration": {"type": "yaml", "repository": {"type": "azureReposGit", "id": "unknown-guid"}},
    }
    transport = httpx.MockTransport(_pipelines_handler_returning(detail_response))
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        links = await fetch_pipeline_links(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert links[0].repository_name == ""


@pytest.mark.asyncio
async def test_fetch_azure_git_repos_maps_guid_to_name():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url.path).endswith("/_apis/git/repositories")
        return httpx.Response(200, json={"value": [{"id": "guid-123", "name": "checkout-web"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        result = await fetch_azure_git_repos(client, org="acme-ado", project="acme-project", pat="ado-pat")

    assert result == {"guid-123": "checkout-web"}


@pytest.mark.asyncio
async def test_fetch_pipeline_detail_returns_name_and_yaml_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url.path).endswith("/_apis/pipelines/7")
        return httpx.Response(200, json=PIPELINE_DETAIL_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        detail = await fetch_pipeline_detail(client, org="acme-ado", project="acme-project", pat="ado-pat", pipeline_id=7)

    assert detail == PipelineDetailData(pipeline_id=7, pipeline_name="checkout-web-ci", is_yaml=True)


@pytest.mark.asyncio
async def test_fetch_pipeline_links_flags_classic_pipelines_as_not_yaml():
    detail_response = {
        "id": 7, "name": "checkout-web-ci",
        "configuration": {"type": "designerJson", "repository": {"type": "gitHub", "fullName": "acme-org/checkout-web"}},
    }
    transport = httpx.MockTransport(_pipelines_handler_returning(detail_response))
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


RUNS_RESPONSE = {"value": [{"id": 555, "createdDate": "2026-07-08T10:00:00Z"}]}

TIMELINE_RESPONSE = {
    "records": [
        {"name": "Build", "type": "Stage", "order": 1, "state": "completed", "result": "succeeded"},
        {"name": "DEV", "type": "Stage", "order": 2, "state": "completed", "result": "succeeded"},
        {"name": "QA", "type": "Stage", "order": 3, "state": "inProgress", "result": None},
        {
            "name": "UAT", "type": "Stage", "order": 4, "state": "pending", "result": None,
            "checkpoint": {"pendingApprovals": [{"description": "Waiting on release manager sign-off"}]},
        },
        {"name": "Prod", "type": "Stage", "order": 5, "state": "pending", "result": None},
        {"name": "Publish artifacts", "type": "Job", "order": 6, "state": "completed", "result": "succeeded"},
    ]
}


@pytest.mark.asyncio
async def test_fetch_pipeline_run_status_maps_stages_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/runs"):
            return httpx.Response(200, json=RUNS_RESPONSE)
        return httpx.Response(200, json=TIMELINE_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        stages = await fetch_pipeline_run_status(client, org="acme-ado", project="acme-project", pat="ado-pat", pipeline_id=7)

    assert stages == [
        PipelineStageStatus(name="Build", status="succeeded"),
        PipelineStageStatus(name="DEV", status="succeeded"),
        PipelineStageStatus(name="QA", status="in_progress"),
        PipelineStageStatus(name="UAT", status="waiting_approval", pending_approval_description="Waiting on release manager sign-off"),
        PipelineStageStatus(name="Prod", status="not_started"),
    ]


@pytest.mark.asyncio
async def test_fetch_pipeline_run_status_returns_empty_list_when_no_runs_exist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        stages = await fetch_pipeline_run_status(client, org="acme-ado", project="acme-project", pat="ado-pat", pipeline_id=7)

    assert stages == []
