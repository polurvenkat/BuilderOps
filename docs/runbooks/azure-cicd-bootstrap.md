# Azure CI/CD Bootstrap Runbook

One-time manual setup for `build-and-test.yml` and `deploy.yml`. Run these
`az` commands yourself (needs Azure AD / Entra ID admin rights the workflows
don't have); everything after this is automated by the pipeline itself —
`deploy.yml`'s `ensure-infra` job creates the resource group, registry, and
Container Apps Environment on its own first real run. Don't pre-create them
by hand; the whole point of the check-then-create logic is that the
pipeline is the one source of truth for provisioning.

## Current deployment target (BuilderOps / Innovation Sandbox)

| | |
|---|---|
| Azure subscription | `Innovation Sandbox` — `48e3acd2-a4f7-4c11-a2fb-934d6149f545` |
| Azure AD tenant | `ea4d58b6-6980-4312-be9a-ab68edfa574c` (arrivia.com) |
| GitHub repo | `polurvenkat/BuilderOps` |
| Resource group | `rg-builderops-wus3` |
| Location | `westus3` |
| ACR | `builderopsacrwus3` |
| Container Apps Environment | `cae-builderops-wus3` |
| Backend Container App | `builderops-backend-wus3` |
| Frontend Container App | `builderops-frontend-wus3` |

This subscription enforces a policy requiring `env`, `business`, `iac`,
`createdby`, and `availability` tags on every resource group — that's why
`ensure-infra` passes `--tags ${{ vars.AZURE_RG_TAGS }}` when creating one
(see the variables table below). If you deploy this to a subscription
without that policy, just leave `AZURE_RG_TAGS` unset.

## 1. Create the Azure AD App Registration and federated credential

This step needs Entra ID directory permissions (e.g. Application
Administrator or Global Administrator) — plain subscription Contributor/Owner
is not enough, and `az ad app create` / `az ad sp create-for-rbac` will both
fail with "Insufficient privileges" without it.

```bash
APP_ID=$(az ad app create --display-name "builderops-gh-actions" --query appId -o tsv)
az ad sp create --id "$APP_ID"

az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "builderops-main-branch",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:polurvenkat/BuilderOps:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

Grant the service principal rights on the target resource group. `deploy.yml`
does more than manage resources — it also runs `az role assignment create`
to grant each Container App's managed identity `AcrPull` on the registry, so
plain `Contributor` is **not enough** (Contributor explicitly excludes
`Microsoft.Authorization/roleAssignments/write`). Grant both `Contributor`
and `User Access Administrator` scoped to just the resource group (avoid
`Owner` at subscription scope — this keeps the CI identity's blast radius
limited to the one resource group it manages):

```bash
for ROLE in Contributor "User Access Administrator"; do
  az role assignment create \
    --assignee "$APP_ID" \
    --role "$ROLE" \
    --scope "/subscriptions/48e3acd2-a4f7-4c11-a2fb-934d6149f545/resourceGroups/rg-builderops-wus3"
done
```

Note: the resource group itself must exist before this role assignment can
be scoped to it. If it doesn't exist yet, create it first with the same
tags `ensure-infra` would use (see `AZURE_RG_TAGS` below) — `deploy.yml`'s
own `az group create` call is safe to run again afterwards, it's a no-op
against an existing group.

## 2. GitHub repo secrets (`Settings -> Secrets and variables -> Actions -> Secrets`)

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | `$APP_ID` from step 1 |
| `AZURE_TENANT_ID` | `ea4d58b6-6980-4312-be9a-ab68edfa574c` |
| `AZURE_SUBSCRIPTION_ID` | `48e3acd2-a4f7-4c11-a2fb-934d6149f545` |
| `DATABASE_URL` | The backend's Postgres connection string (from `backend/.env`, gitignored — never commit it) |
| `GITHUB_TOKEN` | The backend's GitHub PAT (from `backend/.env`) |
| `ADO_PAT` | The backend's Azure DevOps PAT (from `backend/.env`) |

These three app secrets are passed to the backend Container App as native
Container App secrets (`--secrets` / `secretref:`), not via Key Vault — this
deployment has no Key Vault provisioned, and `backend/app/config.py` already
falls back to reading them straight from the environment when
`AZURE_KEY_VAULT_URL` isn't set.

## 3. GitHub repo variables (`Settings -> Secrets and variables -> Actions -> Variables`)

| Variable | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | `rg-builderops-wus3` |
| `AZURE_LOCATION` | `westus3` |
| `AZURE_RG_TAGS` | `env=dev business=us iac=github-actions createdby=venkat.polur availability=24/7` |
| `ACR_NAME` | `builderopsacrwus3` |
| `ACA_ENV_NAME` | `cae-builderops-wus3` |
| `ACA_FRONTEND_APP` | `builderops-frontend-wus3` |
| `ACA_BACKEND_APP` | `builderops-backend-wus3` |
| `GITHUB_ORG` | `arriviainc-softeng` |
| `ADO_ORG` | `arrivia` |
| `ADO_PROJECT` | `SoftEng` |
| `VITE_API_BASE_URL` | *(blank until step 4)* |

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
