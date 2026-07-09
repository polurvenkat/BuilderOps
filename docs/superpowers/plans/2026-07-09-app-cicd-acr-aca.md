# App CI/CD to ACR + ACA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build GitHub Actions CI/CD for the BuilderOps app itself — test both apps on every PR, build+tag+push Docker images to ACR on `main`, and deploy both to Azure Container Apps — per `docs/superpowers/specs/2026-07-09-app-cicd-acr-aca-design.md`.

**Architecture:** Two workflows (`build-and-test.yml`, `deploy.yml`) sharing two composite actions (`ensure-acr`, `compute-tag`) so the ACR-existence-check and the `major.minor.buildid` tag math live in exactly one place each. `deploy.yml` recomputes the same tag from the triggering commit instead of passing artifacts between workflows.

**Tech Stack:** GitHub Actions, Docker, Azure CLI (`az`, `containerapp` extension), `azure/login@v2` (OIDC), nginx (frontend static serving), uvicorn `--factory` (backend ASGI entrypoint).

## Global Constraints

- Image tag format: `{major}.{minor}.{buildid}` — major/minor from each app's own version field (`frontend/package.json`, `backend/pyproject.toml`), buildid = the triggering `build-and-test.yml` run's `github.run_number` (spec §3).
- Frontend and backend are separate images (`builderops-frontend`, `builderops-backend`) and separate Container Apps — never combined (spec §2, product decision already made).
- PRs run tests only — no image build, no push, no Azure calls (spec §2.1).
- All Azure auth is OIDC via `azure/login@v2` — no client secret stored in GitHub (spec §5).
- Every Azure resource check (ACR, Container Apps Environment, each Container App) uses check-then-create-or-update — never a blind `create` that fails on "already exists" (spec §8).
- No new secrets in application code or Dockerfiles — `backend/.env` is real, already-gitignored, and must never be read, copied, or referenced by anything this plan creates.
- Backend's existing `app/config.py` already supports `AZURE_KEY_VAULT_URL` + `DefaultAzureCredential`; this plan wires ACA's managed identity to use that existing mechanism, it does not change `config.py`.

---

## File Structure

```
backend/
  Dockerfile                              # NEW: python:3.12-slim, uvicorn --factory entrypoint
  .dockerignore                           # NEW
frontend/
  Dockerfile                              # NEW: node build -> nginx serve, VITE_API_BASE_URL build-arg
  nginx.conf                              # NEW: SPA fallback routing
  .dockerignore                           # NEW
.github/
  actions/
    ensure-acr/action.yml                 # NEW: composite — check/create ACR, output login-server
    compute-tag/action.yml                # NEW: composite — major.minor.buildid from a version file
  workflows/
    build-and-test.yml                    # NEW: test jobs (Task 4) + build-push jobs (Task 5)
    deploy.yml                            # NEW: ensure-infra (Task 6) + deploy-frontend/backend (Task 7)
docs/
  runbooks/
    azure-cicd-bootstrap.md               # NEW: one-time OIDC setup + repo vars/secrets + bootstrap sequence
```

---

### Task 1: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: `backend/pyproject.toml`, `backend/app/` (existing, unmodified). `create_app()` factory in `backend/app/main.py` (existing) — no module-level `app` object exists, so the container must invoke uvicorn with `--factory`.
- Produces: a runnable image exposing `/health` on port 8000. Later tasks (compute-tag, deploy-backend) assume this image name is `builderops-backend` and this port is `8000`.

- [ ] **Step 1: Write `backend/.dockerignore`**

```
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.env
*.db
tests/
```

- [ ] **Step 2: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build the image locally**

Run: `docker build -t builderops-backend:local backend/`
Expected: build succeeds, final line is `naming to docker.io/library/builderops-backend:local`

- [ ] **Step 4: Smoke test against the local dev Postgres**

The repo already runs a local Postgres container (`backend-db-1`, db/user/password all `qapulse`) for backend dev. Reuse it — no new credentials needed:

```bash
docker run --rm -d --name builderops-backend-smoke -p 8001:8000 \
  -e DATABASE_URL="postgresql+psycopg://qapulse:qapulse@host.docker.internal:5432/qapulse" \
  -e GITHUB_TOKEN=smoke-test -e GITHUB_ORG=smoke-test \
  -e ADO_ORG=smoke-test -e ADO_PROJECT=smoke-test -e ADO_PAT=smoke-test \
  builderops-backend:local
sleep 2
curl -sf http://localhost:8001/health
docker stop builderops-backend-smoke
```

Expected: `curl` prints `{"status":"ok"}`, then the container stops cleanly.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "build: add backend Dockerfile"
```

---

### Task 2: Frontend Dockerfile + nginx config

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `frontend/.dockerignore`

**Interfaces:**
- Consumes: `frontend/package.json`, `frontend/src/` (existing, unmodified). `frontend/src/api/client.ts:11` already reads `import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"` — the build-arg below feeds exactly that existing read, no frontend code changes.
- Produces: a runnable image serving the built SPA on port 80. Later tasks assume image name `builderops-frontend` and port `80`.

- [ ] **Step 1: Write `frontend/.dockerignore`**

```
node_modules/
dist/
tests/
*.local
```

- [ ] **Step 2: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Write `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

- [ ] **Step 4: Build the image locally**

Run: `docker build -t builderops-frontend:local --build-arg VITE_API_BASE_URL=http://localhost:8001 frontend/`
Expected: build succeeds, final line is `naming to docker.io/library/builderops-frontend:local`

- [ ] **Step 5: Smoke test and confirm the build-arg was baked in**

```bash
docker run --rm -d --name builderops-frontend-smoke -p 8080:80 builderops-frontend:local
sleep 1
curl -sf http://localhost:8080/ | grep -o '<div id="root">'
docker exec builderops-frontend-smoke grep -o 'http://localhost:8001' /usr/share/nginx/html/assets/*.js
docker stop builderops-frontend-smoke
```

Expected: first command prints `<div id="root">`; second command prints `http://localhost:8001` (confirming Vite baked the build-arg into the bundled JS, not just left it as a runtime-unresolved reference).

- [ ] **Step 6: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore
git commit -m "build: add frontend Dockerfile"
```

---

### Task 3: Shared composite actions — `ensure-acr` and `compute-tag`

**Files:**
- Create: `.github/actions/ensure-acr/action.yml`
- Create: `.github/actions/compute-tag/action.yml`

**Interfaces:**
- Consumes: an already-authenticated `az` session (the calling job must run `azure/login@v2` before using either action — neither action logs in itself).
- Produces:
  - `ensure-acr`: output `login-server` (e.g. `builderopsacr.azurecr.io`). Used by Tasks 5 and 7.
  - `compute-tag`: output `tag` (e.g. `0.1.42`). Used by Tasks 5 and 7. Inputs: `version-file` (path relative to repo root), `file-type` (`npm` or `pyproject`), `run-number`.

- [ ] **Step 1: Write `.github/actions/ensure-acr/action.yml`**

```yaml
name: Ensure ACR exists
description: Checks whether the given Azure Container Registry exists and creates it (Basic SKU) if not. Requires an already-authenticated az session.
inputs:
  acr-name:
    required: true
    description: Name of the Azure Container Registry
  resource-group:
    required: true
    description: Resource group the registry lives in (or should be created in)
  location:
    required: true
    description: Azure region to create the registry in, if it doesn't exist
outputs:
  login-server:
    description: The registry's login server hostname
    value: ${{ steps.ensure.outputs.login-server }}
runs:
  using: composite
  steps:
    - id: ensure
      shell: bash
      run: |
        set -euo pipefail
        if ! az acr show --name "${{ inputs.acr-name }}" --resource-group "${{ inputs.resource-group }}" >/dev/null 2>&1; then
          echo "ACR '${{ inputs.acr-name }}' not found in '${{ inputs.resource-group }}', creating..."
          az acr create \
            --name "${{ inputs.acr-name }}" \
            --resource-group "${{ inputs.resource-group }}" \
            --location "${{ inputs.location }}" \
            --sku Basic >/dev/null
        else
          echo "ACR '${{ inputs.acr-name }}' already exists."
        fi
        LOGIN_SERVER=$(az acr show --name "${{ inputs.acr-name }}" --query loginServer -o tsv)
        echo "login-server=${LOGIN_SERVER}" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Write `.github/actions/compute-tag/action.yml`**

```yaml
name: Compute image tag
description: Computes a major.minor.buildid image tag from a package.json or pyproject.toml version field
inputs:
  version-file:
    required: true
    description: Path (relative to repo root) to the package.json or pyproject.toml containing the version
  file-type:
    required: true
    description: "npm or pyproject"
  run-number:
    required: true
    description: Build id to append, e.g. the triggering workflow's github.run_number
outputs:
  tag:
    description: Computed image tag, e.g. 0.1.42
    value: ${{ steps.compute.outputs.tag }}
runs:
  using: composite
  steps:
    - id: compute
      shell: bash
      run: |
        set -euo pipefail
        if [ "${{ inputs.file-type }}" = "npm" ]; then
          VERSION=$(node -p "require('./${{ inputs.version-file }}').version")
        else
          VERSION=$(grep -E '^version\s*=' "${{ inputs.version-file }}" | head -1 | sed -E 's/version\s*=\s*"([^"]+)".*/\1/')
        fi
        MAJOR_MINOR=$(echo "$VERSION" | cut -d. -f1,2)
        TAG="${MAJOR_MINOR}.${{ inputs.run-number }}"
        echo "Computed tag: $TAG (from $VERSION)"
        echo "tag=${TAG}" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 3: Validate both files are well-formed YAML**

Run: `python3 -c "import yaml, sys; [yaml.safe_load(open(f)) for f in ['.github/actions/ensure-acr/action.yml', '.github/actions/compute-tag/action.yml']]; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Verify the `compute-tag` bash logic locally against the repo's real version files**

The `az`/`node`-in-composite-action machinery can't run standalone, but the tag math itself can be verified directly:

```bash
VERSION=$(node -p "require('./frontend/package.json').version")
echo "${VERSION}" | cut -d. -f1,2
```

Expected: `0.1` (from `frontend/package.json`'s `"version": "0.1.0"`)

```bash
VERSION=$(grep -E '^version\s*=' backend/pyproject.toml | head -1 | sed -E 's/version\s*=\s*"([^"]+)".*/\1/')
echo "${VERSION}" | cut -d. -f1,2
```

Expected: `0.1` (from `backend/pyproject.toml`'s `version = "0.1.0"`)

- [ ] **Step 5: Commit**

```bash
git add .github/actions/ensure-acr/action.yml .github/actions/compute-tag/action.yml
git commit -m "ci: add shared ensure-acr and compute-tag composite actions"
```

---

### Task 4: `build-and-test.yml` — test jobs

**Files:**
- Create: `.github/workflows/build-and-test.yml` (initial version — test jobs only; Task 5 extends this same file)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a workflow named `Build and Test` (this exact name is referenced by `deploy.yml`'s `workflow_run` trigger in Task 6 — must match exactly).

- [ ] **Step 1: Write `.github/workflows/build-and-test.yml`**

```yaml
name: Build and Test

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  frontend-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run test -- --run
      - run: npm run build

  backend-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install .[dev]
      - run: pytest -q
```

- [ ] **Step 2: Validate the YAML is well-formed**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build-and-test.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Verify the underlying commands succeed locally (same commands the workflow runs)**

```bash
cd frontend && npm ci && npm run test -- --run && npm run build
```
Expected: `npm run test` reports all test files passing (baseline: 15 files, 101 tests), `npm run build` completes without error.

```bash
cd backend && .venv/bin/pip install .[dev] && .venv/bin/pytest -q
```
Expected: all tests pass (baseline: 151 passed).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/build-and-test.yml
git commit -m "ci: add build-and-test workflow with frontend/backend test jobs"
```

---

### Task 5: `build-and-test.yml` — build-and-push jobs

**Files:**
- Modify: `.github/workflows/build-and-test.yml` (add two jobs after `backend-test`)

**Interfaces:**
- Consumes: `ensure-acr` and `compute-tag` composite actions (Task 3), `backend/Dockerfile` (Task 1), `frontend/Dockerfile` (Task 2).
- Produces: on every push to `main`, images `builderops-frontend:{tag}` and `builderops-backend:{tag}` pushed to the ACR named by the `ACR_NAME` repo variable. `deploy.yml` (Task 7) assumes these exact image repository names.

- [ ] **Step 1: Append the two build-push jobs to `.github/workflows/build-and-test.yml`**

```yaml
  frontend-build-push:
    needs: frontend-test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - id: acr
        uses: ./.github/actions/ensure-acr
        with:
          acr-name: ${{ vars.ACR_NAME }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          location: ${{ vars.AZURE_LOCATION }}
      - id: tag
        uses: ./.github/actions/compute-tag
        with:
          version-file: frontend/package.json
          file-type: npm
          run-number: ${{ github.run_number }}
      - run: az acr login --name ${{ vars.ACR_NAME }}
      - run: |
          docker build \
            --build-arg VITE_API_BASE_URL=${{ vars.VITE_API_BASE_URL }} \
            -t ${{ steps.acr.outputs.login-server }}/builderops-frontend:${{ steps.tag.outputs.tag }} \
            frontend/
      - run: docker push ${{ steps.acr.outputs.login-server }}/builderops-frontend:${{ steps.tag.outputs.tag }}

  backend-build-push:
    needs: backend-test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - id: acr
        uses: ./.github/actions/ensure-acr
        with:
          acr-name: ${{ vars.ACR_NAME }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          location: ${{ vars.AZURE_LOCATION }}
      - id: tag
        uses: ./.github/actions/compute-tag
        with:
          version-file: backend/pyproject.toml
          file-type: pyproject
          run-number: ${{ github.run_number }}
      - run: az acr login --name ${{ vars.ACR_NAME }}
      - run: |
          docker build \
            -t ${{ steps.acr.outputs.login-server }}/builderops-backend:${{ steps.tag.outputs.tag }} \
            backend/
      - run: docker push ${{ steps.acr.outputs.login-server }}/builderops-backend:${{ steps.tag.outputs.tag }}
```

- [ ] **Step 2: Validate the full workflow file is well-formed YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build-and-test.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Confirm the new jobs are gated correctly by reading the `if` conditions back**

Run: `grep -A1 "frontend-build-push:\|backend-build-push:" .github/workflows/build-and-test.yml | grep "if:"`
Expected: two lines, both `if: github.ref == 'refs/heads/main' && github.event_name == 'push'` — confirms PRs never trigger a build/push (spec §2.1).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/build-and-test.yml
git commit -m "ci: push tagged frontend/backend images to ACR on main"
```

---

### Task 6: `deploy.yml` — `ensure-infra` job

**Files:**
- Create: `.github/workflows/deploy.yml` (initial version — `ensure-infra` job only; Task 7 adds the deploy jobs)

**Interfaces:**
- Consumes: `ensure-acr` composite action (Task 3).
- Produces: a workflow triggered by `build-and-test.yml` completing on `main`, or manually. Job `ensure-infra` — later tasks' jobs declare `needs: ensure-infra`.

- [ ] **Step 1: Write `.github/workflows/deploy.yml`**

```yaml
name: Deploy to ACA

on:
  workflow_run:
    workflows: ["Build and Test"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      frontend_tag:
        description: "Frontend image tag to deploy (leave blank to recompute the current one)"
        required: false
      backend_tag:
        description: "Backend image tag to deploy (leave blank to recompute the current one)"
        required: false

permissions:
  contents: read
  id-token: write

jobs:
  ensure-infra:
    if: github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Ensure resource group exists
        run: az group create --name ${{ vars.AZURE_RESOURCE_GROUP }} --location ${{ vars.AZURE_LOCATION }} >/dev/null
      - uses: ./.github/actions/ensure-acr
        with:
          acr-name: ${{ vars.ACR_NAME }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          location: ${{ vars.AZURE_LOCATION }}
      - name: Ensure Container Apps Environment exists
        run: |
          set -euo pipefail
          az extension add --name containerapp --upgrade -y >/dev/null 2>&1 || true
          az provider register --namespace Microsoft.App --wait
          az provider register --namespace Microsoft.OperationalInsights --wait
          if ! az containerapp env show --name ${{ vars.ACA_ENV_NAME }} --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} >/dev/null 2>&1; then
            echo "Container Apps Environment '${{ vars.ACA_ENV_NAME }}' not found, creating..."
            az containerapp env create \
              --name ${{ vars.ACA_ENV_NAME }} \
              --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} \
              --location ${{ vars.AZURE_LOCATION }}
          else
            echo "Container Apps Environment '${{ vars.ACA_ENV_NAME }}' already exists."
          fi
```

- [ ] **Step 2: Validate the YAML is well-formed**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Confirm the trigger references the exact workflow name from Task 4**

Run: `grep -A1 "workflow_run:" .github/workflows/deploy.yml`
Expected: shows `workflows: ["Build and Test"]`, matching the `name:` field at the top of `build-and-test.yml` exactly (GitHub matches `workflow_run` by the triggering workflow's declared `name`, not its filename).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add deploy workflow with infra bootstrap job"
```

---

### Task 7: `deploy.yml` — `deploy-backend` and `deploy-frontend` jobs

**Files:**
- Modify: `.github/workflows/deploy.yml` (add two jobs after `ensure-infra`)

**Interfaces:**
- Consumes: `ensure-acr` and `compute-tag` composite actions (Task 3); `ensure-infra` job (Task 6); repo variables `ACA_BACKEND_APP`, `ACA_FRONTEND_APP`, `ACA_ENV_NAME`, `AZURE_KEY_VAULT_URL`, `AZURE_KEY_VAULT_NAME`, `GITHUB_ORG`, `ADO_ORG`, `ADO_PROJECT` (documented in Task 8).
- Produces: two live (or updated) Container Apps. No further task depends on this one's outputs.

- [ ] **Step 1: Append `deploy-backend` to `.github/workflows/deploy.yml`**

The backend needs a system-assigned identity with Key Vault read access — wired only on first create, since the identity persists across later `update` calls:

```yaml
  deploy-backend:
    needs: ensure-infra
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha || github.sha }}
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - id: acr
        uses: ./.github/actions/ensure-acr
        with:
          acr-name: ${{ vars.ACR_NAME }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          location: ${{ vars.AZURE_LOCATION }}
      - id: tag
        if: github.event_name != 'workflow_dispatch' || github.event.inputs.backend_tag == ''
        uses: ./.github/actions/compute-tag
        with:
          version-file: backend/pyproject.toml
          file-type: pyproject
          run-number: ${{ github.event.workflow_run.run_number || github.run_number }}
      - id: resolve
        run: echo "tag=${{ github.event.inputs.backend_tag || steps.tag.outputs.tag }}" >> "$GITHUB_OUTPUT"
      - name: Deploy or update backend Container App
        run: |
          set -euo pipefail
          IMAGE="${{ steps.acr.outputs.login-server }}/builderops-backend:${{ steps.resolve.outputs.tag }}"
          if az containerapp show --name ${{ vars.ACA_BACKEND_APP }} --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} >/dev/null 2>&1; then
            echo "Updating existing backend Container App with $IMAGE"
            az containerapp update \
              --name ${{ vars.ACA_BACKEND_APP }} \
              --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} \
              --image "$IMAGE"
          else
            echo "Creating backend Container App with $IMAGE"
            az containerapp create \
              --name ${{ vars.ACA_BACKEND_APP }} \
              --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} \
              --environment ${{ vars.ACA_ENV_NAME }} \
              --image "$IMAGE" \
              --target-port 8000 \
              --ingress external \
              --system-assigned \
              --env-vars AZURE_KEY_VAULT_URL=${{ vars.AZURE_KEY_VAULT_URL }} GITHUB_ORG=${{ vars.GITHUB_ORG }} ADO_ORG=${{ vars.ADO_ORG }} ADO_PROJECT=${{ vars.ADO_PROJECT }}
            PRINCIPAL_ID=$(az containerapp show --name ${{ vars.ACA_BACKEND_APP }} --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} --query identity.principalId -o tsv)
            az keyvault set-policy \
              --name ${{ vars.AZURE_KEY_VAULT_NAME }} \
              --object-id "$PRINCIPAL_ID" \
              --secret-permissions get list
          fi
      - name: Report backend URL
        run: |
          FQDN=$(az containerapp show --name ${{ vars.ACA_BACKEND_APP }} --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} --query properties.configuration.ingress.fqdn -o tsv)
          echo "Backend URL: https://${FQDN}" >> "$GITHUB_STEP_SUMMARY"
          echo "If this is the first-ever deploy, set the VITE_API_BASE_URL repo variable to https://${FQDN} and re-run build-and-test so the frontend bakes in the real URL." >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Append `deploy-frontend` to `.github/workflows/deploy.yml`**

```yaml
  deploy-frontend:
    needs: ensure-infra
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha || github.sha }}
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - id: acr
        uses: ./.github/actions/ensure-acr
        with:
          acr-name: ${{ vars.ACR_NAME }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          location: ${{ vars.AZURE_LOCATION }}
      - id: tag
        if: github.event_name != 'workflow_dispatch' || github.event.inputs.frontend_tag == ''
        uses: ./.github/actions/compute-tag
        with:
          version-file: frontend/package.json
          file-type: npm
          run-number: ${{ github.event.workflow_run.run_number || github.run_number }}
      - id: resolve
        run: echo "tag=${{ github.event.inputs.frontend_tag || steps.tag.outputs.tag }}" >> "$GITHUB_OUTPUT"
      - name: Deploy or update frontend Container App
        run: |
          set -euo pipefail
          IMAGE="${{ steps.acr.outputs.login-server }}/builderops-frontend:${{ steps.resolve.outputs.tag }}"
          if az containerapp show --name ${{ vars.ACA_FRONTEND_APP }} --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} >/dev/null 2>&1; then
            echo "Updating existing frontend Container App with $IMAGE"
            az containerapp update \
              --name ${{ vars.ACA_FRONTEND_APP }} \
              --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} \
              --image "$IMAGE"
          else
            echo "Creating frontend Container App with $IMAGE"
            az containerapp create \
              --name ${{ vars.ACA_FRONTEND_APP }} \
              --resource-group ${{ vars.AZURE_RESOURCE_GROUP }} \
              --environment ${{ vars.ACA_ENV_NAME }} \
              --image "$IMAGE" \
              --target-port 80 \
              --ingress external
          fi
```

- [ ] **Step 3: Validate the full workflow file is well-formed YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Confirm both deploy jobs depend only on `ensure-infra` (so they run in parallel, and both skip together if infra bootstrap fails)**

Run: `grep -A1 "deploy-backend:\|deploy-frontend:" .github/workflows/deploy.yml | grep "needs:"`
Expected: two lines, both `needs: ensure-infra`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: deploy backend and frontend Container Apps"
```

---

### Task 8: Bootstrap runbook — OIDC setup, repo config, first-deploy sequence

**Files:**
- Create: `docs/runbooks/azure-cicd-bootstrap.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: the one-time manual steps a human with Azure AD admin rights must run before either workflow can succeed — referenced by spec §5 and §6 as "not automated in this scope."

- [ ] **Step 1: Write `docs/runbooks/azure-cicd-bootstrap.md`**

```markdown
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
   pushes both images; `deploy.yml` then runs `ensure-infra` and
   `deploy-backend` and `deploy-frontend` in parallel. On this first run,
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/azure-cicd-bootstrap.md
git commit -m "docs: add Azure CI/CD bootstrap runbook"
```

---

## Post-plan verification (not a task — requires the real Azure/GitHub environment)

Every task above verifies what's verifiable offline (Docker builds, YAML syntax, the exact test/build commands, the tag math). The workflows' actual Azure behavior (OIDC login succeeding, ACR/ACA creation, live deploys) can only be confirmed once:
1. Task 8's runbook has been run once against a real Azure subscription, and
2. A PR is opened (confirms `frontend-test`/`backend-test` run and pass) and then merged to `main` (confirms `build-and-test.yml`'s push jobs and `deploy.yml`'s full chain run end-to-end).

This is expected for infrastructure work — flag it to the user rather than claiming full verification from this plan alone.
