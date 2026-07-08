from app.config import Settings
from app.main import create_app
from app.scheduler import _run_github_sync_job, start_scheduler


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_start_scheduler_registers_github_and_ado_jobs():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"github_sync", "ado_sync", "ado_pipelines_sync"}
    scheduler.shutdown(wait=False)


def test_start_scheduler_github_job_runs_every_4_hours():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    github_job = scheduler.get_job("github_sync")
    assert github_job.trigger.interval.total_seconds() == 4 * 60 * 60
    scheduler.shutdown(wait=False)


def test_github_sync_job_uses_a_generous_timeout(monkeypatch):
    app = create_app(make_test_settings())
    captured_clients = []

    async def fake_run_github_sync(session, client, org, token, now):
        captured_clients.append(client)

    monkeypatch.setattr("app.scheduler.run_github_sync", fake_run_github_sync)

    _run_github_sync_job(app)

    assert len(captured_clients) == 1
    # A real 100-repo batched GraphQL checks query takes ~9-10s against GitHub's API;
    # httpx's 5s default timeout is not enough. Guard against regressing to the default.
    assert captured_clients[0].timeout.read >= 30.0
