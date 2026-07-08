from app.config import Settings
from app.main import create_app
from app.scheduler import start_scheduler


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
    assert job_ids == {"github_sync", "ado_sync"}
    scheduler.shutdown(wait=False)


def test_start_scheduler_github_job_runs_every_4_hours():
    app = create_app(make_test_settings())

    scheduler = start_scheduler(app)

    github_job = scheduler.get_job("github_sync")
    assert github_job.trigger.interval.total_seconds() == 4 * 60 * 60
    scheduler.shutdown(wait=False)
