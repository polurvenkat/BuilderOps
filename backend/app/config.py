import os
from typing import Protocol

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from pydantic_settings import BaseSettings


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...


class EnvSecretProvider:
    def get(self, name: str) -> str:
        if name not in os.environ:
            raise KeyError(f"Secret '{name}' not found in environment")
        return os.environ[name]


class KeyVaultSecretProvider:
    def __init__(self, vault_url: str):
        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    def get(self, name: str) -> str:
        return self._client.get_secret(name).value


class Settings(BaseSettings):
    database_url: str
    github_token: str
    github_org: str
    ado_org: str
    ado_project: str
    ado_pat: str
    azure_key_vault_url: str | None = None


_ENV_TO_KEY_VAULT_NAME = {
    "DATABASE_URL": "builderops-database-url",
    "GITHUB_TOKEN": "builderops-github-token",
    "ADO_PAT": "builderops-ado-pat",
}


def get_settings() -> Settings:
    key_vault_url = os.environ.get("AZURE_KEY_VAULT_URL")
    provider: SecretProvider = (
        KeyVaultSecretProvider(key_vault_url) if key_vault_url else EnvSecretProvider()
    )

    def resolve(env_name: str, default: str | None = None) -> str:
        secret_name = _ENV_TO_KEY_VAULT_NAME.get(env_name)
        if key_vault_url and secret_name:
            return provider.get(secret_name)
        if default is not None:
            return os.environ.get(env_name, default)
        return provider.get(env_name)

    return Settings(
        database_url=resolve("DATABASE_URL"),
        github_token=resolve("GITHUB_TOKEN"),
        github_org=os.environ.get("GITHUB_ORG", ""),
        ado_org=os.environ.get("ADO_ORG", ""),
        ado_project=os.environ.get("ADO_PROJECT", ""),
        ado_pat=resolve("ADO_PAT"),
        azure_key_vault_url=key_vault_url,
    )
