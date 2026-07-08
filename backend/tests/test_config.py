import pytest
from app.config import EnvSecretProvider, KeyVaultSecretProvider, get_settings, Settings


def test_env_secret_provider_reads_from_environ(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "shh")
    provider = EnvSecretProvider()
    assert provider.get("MY_SECRET") == "shh"


def test_env_secret_provider_missing_raises(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    provider = EnvSecretProvider()
    with pytest.raises(KeyError):
        provider.get("DOES_NOT_EXIST")


def test_get_settings_uses_env_provider_when_no_key_vault_url(monkeypatch):
    monkeypatch.delenv("AZURE_KEY_VAULT_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_ORG", "acme-org")
    monkeypatch.setenv("ADO_ORG", "acme-ado")
    monkeypatch.setenv("ADO_PROJECT", "acme-project")
    monkeypatch.setenv("ADO_PAT", "ado-pat")

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.github_org == "acme-org"


def test_key_vault_secret_provider_calls_client(monkeypatch):
    class FakeSecret:
        def __init__(self, value):
            self.value = value

    class FakeSecretClient:
        def __init__(self, vault_url, credential):
            self.vault_url = vault_url

        def get_secret(self, name):
            return FakeSecret(f"value-for-{name}")

    monkeypatch.setattr("app.config.SecretClient", FakeSecretClient)
    monkeypatch.setattr("app.config.DefaultAzureCredential", lambda: object())

    provider = KeyVaultSecretProvider(vault_url="https://fake.vault.azure.net")
    assert provider.get("db-password") == "value-for-db-password"


def test_get_settings_uses_key_vault_when_url_set(monkeypatch):
    class FakeSecret:
        def __init__(self, value):
            self.value = value

    class FakeSecretClient:
        def __init__(self, vault_url, credential):
            self.vault_url = vault_url

        def get_secret(self, name):
            return FakeSecret(f"value-for-{name}")

    monkeypatch.setattr("app.config.SecretClient", FakeSecretClient)
    monkeypatch.setattr("app.config.DefaultAzureCredential", lambda: object())

    monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://test.vault.azure.net")
    monkeypatch.setenv("GITHUB_ORG", "acme-org")
    monkeypatch.setenv("ADO_ORG", "acme-ado")
    monkeypatch.setenv("ADO_PROJECT", "acme-project")

    settings = get_settings()

    assert isinstance(settings, Settings)
    assert settings.database_url == "value-for-builderops-database-url"
    assert settings.github_token == "value-for-builderops-github-token"
    assert settings.ado_pat == "value-for-builderops-ado-pat"
    assert settings.github_org == "acme-org"
    assert settings.ado_org == "acme-ado"
    assert settings.ado_project == "acme-project"
    assert settings.azure_key_vault_url == "https://test.vault.azure.net"
