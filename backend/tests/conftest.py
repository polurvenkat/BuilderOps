import pytest


@pytest.fixture(autouse=True)
def clear_key_vault_env(monkeypatch):
    monkeypatch.delenv("AZURE_KEY_VAULT_URL", raising=False)
