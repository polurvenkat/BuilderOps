# BuilderOps App — GitHub Actions CI/CD to ACR + ACA

**Owner:** Venk Polur
**Status:** Approved by Venk 2026-07-09, ready for implementation planning
**Scope:** CI/CD for the BuilderOps application itself (this repo's `frontend/` and `backend/`) — build, test, containerize, push to Azure Container Registry, and deploy to Azure Container Apps. This is infrastructure for BuilderOps's own delivery pipeline, unrelated to the CI/CD & Lower Environments *feature* pillar (which tracks other teams' ADO pipelines).

## 1. Context

Neither app has a Dockerfile, and there are no GitHub Actions workflows, ACR, or ACA resources yet — this is a from-scratch bootstrap. The frontend (Vite/React) and backend (FastAPI) are independently versioned (`frontend/package.json`, `backend/pyproject.toml`) and deploy as two separate images and two separate Container Apps.

## 2. Workflows

### 2.1 `build-and-test.yml` (CI)

Triggers: `pull_request` (any branch), `push` to `main`.

Jobs:
- **`frontend-test`** (always runs): `npm ci`, `npm run test` (vitest), `npm run build` (tsc + vite build, validates the build itself succeeds).
- **`backend-test`** (always runs): install deps (`pip install .[dev]`), `pytest`.
- **`frontend-build-push`** (push to `main` only, `needs: frontend-test`): calls the `ensure-acr` composite action, computes the image tag, `docker build`/`push` to `<acr>.azurecr.io/builderops-frontend`.
- **`backend-build-push`** (push to `main` only, `needs: backend-test`): same pattern, pushes to `builderops-backend`.

PRs only run tests — no image build/push — to keep PR CI fast and avoid pushing untagged/throwaway images.

### 2.2 `deploy.yml` (CD)

Triggers:
- `workflow_run`: fires when `build-and-test.yml` completes on `main`; the job is gated on `github.event.workflow_run.conclusion == 'success'`.
- `workflow_dispatch`: manual run, for redeploying a specific existing tag without rebuilding.

Jobs:
- **`ensure-infra`**: `az group create` (idempotent — safe to call whether or not the RG exists), calls `ensure-acr`, then checks/creates the Container Apps Environment (`az containerapp env show` → `create` if missing).
- **`deploy-frontend`** / **`deploy-backend`** (`needs: ensure-infra`): `az containerapp show` → `update --image <tag>` if the app exists, else `create` with the full spec (image, ingress, target port, environment). The tag is recomputed the same deterministic way as in CI (see §3) from `github.event.workflow_run.head_sha` and `github.event.workflow_run.run_number` — no artifact download needed between the two workflows.

### 2.3 `.github/actions/ensure-acr` (composite action, shared)

Inputs: `acr_name`, `resource_group`, `location`. Logic: `az acr show -n <acr_name>` → on failure, `az acr create --sku Basic`. Outputs: `login_server`. Used by both workflows so the very first `build-and-test` push doesn't fail against a registry that doesn't exist yet, and so `deploy.yml` also works standalone (e.g., a fresh environment bootstrap via `workflow_dispatch`).

## 3. Image tag scheme

Format: `{major}.{minor}.{buildid}`, where:
- `major`/`minor` are read from each app's own version field — `frontend/package.json`'s `version` for the frontend image, `backend/pyproject.toml`'s `version` for the backend image — truncated to the first two dot-separated components (a `0.1.0` version produces `0.1`).
- `buildid` is `github.run_number` of the `build-and-test.yml` run. Both images from the same CI run share the same `buildid`, so `0.1.42` (frontend) and `1.0.42` (backend) are traceable back to the same commit even though their major.minor differ independently.

Bumping major/minor is a manual edit to `package.json`/`pyproject.toml` version — no automated semver bump logic in this scope.

## 4. Dockerfiles (new)

- **`frontend/Dockerfile`**: multi-stage — `node:20-alpine` stage runs `npm ci && npm run build`; final stage is `nginx:alpine` copying `dist/` in, with an SPA-fallback `nginx.conf` (`try_files $uri /index.html`). Accepts a `VITE_API_BASE_URL` build-arg (see §6). Listens on port 80.
- **`backend/Dockerfile`**: `python:3.12-slim`, `pip install .` (production deps only, no `[dev]` extra), `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

## 5. Azure auth

OIDC federated credentials via `azure/login@v2` — no long-lived secret stored in GitHub. Both workflows declare `permissions: id-token: write, contents: read`.

**One-time manual setup (outside CI, done once by a human with Azure AD permissions):** create an Azure AD App Registration and a federated credential scoped to this repo (subject `repo:<org>/<repo>:ref:refs/heads/main`, plus one for `pull_request` if PR workflows ever need Azure access — they don't in this design, since PRs only test). The exact `az ad app create` / `az ad app federated-credential create` commands will be included as a runbook in the implementation plan, not automated — this step needs Azure AD admin rights this workflow doesn't have.

## 6. Configuration

**Repo variables** (`Settings → Actions → Variables`): `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `ACR_NAME`, `ACA_ENV_NAME`, `ACA_FRONTEND_APP`, `ACA_BACKEND_APP`, `VITE_API_BASE_URL`.

**Repo secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.

### Frontend/backend URL bootstrapping (open issue, resolved with a manual step)

The Vite build bakes `VITE_API_BASE_URL` in at build time, but the backend's ACA-assigned FQDN doesn't exist until the backend is deployed at least once. Sequence for a first-ever deploy:
1. Deploy backend first (its Container App creation doesn't depend on the frontend URL).
2. Read the backend's FQDN from `az containerapp show`, set it as the `VITE_API_BASE_URL` repo variable.
3. Re-run (or let the next push trigger) the frontend build so it bakes in the real URL.

This is a one-time manual step after first bootstrap; subsequent deploys reuse the already-set variable and need no manual intervention, since the backend's FQDN doesn't change across redeploys (Container Apps ingress FQDN is stable across revisions).

## 7. Ingress & networking

Both Container Apps use external ingress (public HTTPS) — frontend serves the SPA directly to browsers; backend is called directly from the browser via `VITE_API_BASE_URL`, not proxied through the frontend's nginx. Target ports: 80 (frontend), 8000 (backend). No custom domain in this scope — both use the default `*.azurecontainerapps.io` FQDN.

## 8. Error handling

- `ensure-acr` and the ACA environment check use existence-check-then-create, never blind `create`, so re-runs are idempotent and don't fail on "already exists" errors.
- `deploy-frontend`/`deploy-backend` use `show`-then-`create`-or-`update` for the same reason — safe to re-run, safe for the very first run.
- If `build-and-test.yml` fails (tests or build), no image is pushed and `deploy.yml` never fires (`workflow_run` only triggers on completion, and the job itself checks `conclusion == 'success'`).
- No automatic rollback on a failed ACA deploy in this scope — a failed `containerapp update` leaves the previous revision serving traffic (Container Apps' default single-revision-mode behavior), which is an acceptable safety net without extra rollback logic.

## 9. Out of scope

- Azure AD app registration / federated credential creation (manual runbook, not automated — needs Azure AD admin rights).
- Backend runtime secrets/config beyond what's needed to boot (e.g., Key Vault-sourced ADO/GitHub tokens the app already reads at runtime) — assumed to already be wired via the backend's existing settings/Key Vault pattern, not newly introduced by this CI/CD work.
- Automated semver bumping, changelog generation, or release notes.
- Custom domains, WAF, or any networking beyond default ACA ingress.
- Staging/QA environments — this spec covers a single production-style deploy target only.
