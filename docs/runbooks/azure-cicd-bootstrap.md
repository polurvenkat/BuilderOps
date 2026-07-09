# Azure CI/CD Bootstrap Runbook

One-time manual setup for `build-and-test.yml` and `deploy.yml`. Run these
`az` commands yourself (needs Azure AD admin rights the workflows don't have);
everything after this is automated.

## 1. Create the Azure AD App Registration and federated credential

Replace `<org>/<repo>` with this repository's `owner/name`.

```bash
APP_ID=$(az ad app create --display-name "builderops-gh-actions" --query appId -o tsv)
az ad sp create --id "$APP_ID"

az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "builderops-main-branch",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<org>/<repo>:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

Grant the service principal `Contributor` on the target subscription or
resource group (whichever scope you want CI to manage):

```bash
az role assignment create \
  --assignee "$APP_ID" \
  --role "Contributor" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>"
```

## 2. GitHub repo secrets (`Settings -> Secrets and variables -> Actions -> Secrets`)

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | `$APP_ID` from step 1 |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |

## 3. GitHub repo variables (`Settings -> Secrets and variables -> Actions -> Variables`)

| Variable | Example | Notes |
|---|---|---|
| `AZURE_RESOURCE_GROUP` | `builderops-rg` | Created automatically if missing |
| `AZURE_LOCATION` | `eastus` | Used for ACR, ACA environment, and both apps |
| `ACR_NAME` | `builderopsacr` | Must be globally unique across Azure |
| `ACA_ENV_NAME` | `builderops-env` | Container Apps Environment name |
| `ACA_FRONTEND_APP` | `builderops-frontend` | Container App name |
| `ACA_BACKEND_APP` | `builderops-backend` | Container App name |
| `AZURE_KEY_VAULT_URL` | `https://builderops-kv.vault.azure.net/` | Passed to the backend as `AZURE_KEY_VAULT_URL` |
| `AZURE_KEY_VAULT_NAME` | `builderops-kv` | Used for the `az keyvault set-policy` call, not passed to the app |
| `GITHUB_ORG` | `arriviainc-softeng` | Passed through to the backend, non-secret |
| `ADO_ORG` | `arrivia` | Passed through to the backend, non-secret |
| `ADO_PROJECT` | `SoftEng` | Passed through to the backend, non-secret |
| `VITE_API_BASE_URL` | *(blank until step 4)* | Baked into the frontend build |

The Key Vault referenced above must already contain the secrets
`builderops-database-url`, `builderops-github-token`, and `builderops-ado-pat`
(see `backend/app/config.py`'s `_ENV_TO_KEY_VAULT_NAME` mapping) — this
runbook only wires the backend's managed identity to read them, it does not
create the Key Vault or populate its secrets.

## 4. First-ever deploy sequence

The frontend bakes `VITE_API_BASE_URL` in at Docker build time, but the
backend's Container Apps FQDN doesn't exist until it's deployed once:

1. Push to `main` (or merge a PR into it). `build-and-test.yml` builds and
   pushes both images; `deploy.yml` then runs `ensure-infra` first, followed
   by `deploy-backend` and `deploy-frontend` in parallel. On this first run,
   the frontend will be built with whatever `VITE_API_BASE_URL` was set to
   (blank, if you haven't done step 4 yet) — this is expected and corrected
   in the next step.
2. Open the `deploy-backend` job's summary in the Actions run — it prints
   `Backend URL: https://<something>.<region>.azurecontainerapps.io`.
3. Set the `VITE_API_BASE_URL` repo variable to that URL.
4. Push any commit to `main` (or re-run `build-and-test.yml` manually) so
   the frontend image gets rebuilt with the real backend URL baked in, and
   `deploy.yml` redeploys it.

Every deploy after this is fully automatic — the backend's FQDN doesn't
change across redeploys.

## 5. Manual redeploy of a specific tag

`deploy.yml` can also be triggered manually via `workflow_dispatch` — for
example, to roll back to a previous image or re-deploy after a failed run.
Manual dispatch now requires an explicit tag for whichever app you're
redeploying; there's no "leave blank to recompute the current one" fallback
(the recompute logic relies on `build-and-test.yml`'s run number, which
`workflow_dispatch` has no way to determine on its own).

1. Find existing tags in the registry:

   ```bash
   az acr repository show-tags --name <ACR_NAME> --repository builderops-backend --output table
   az acr repository show-tags --name <ACR_NAME> --repository builderops-frontend --output table
   ```

2. In the GitHub UI, go to the Actions tab → **Deploy to ACA** → **Run
   workflow**, and supply the desired `backend_tag` and/or `frontend_tag`.
