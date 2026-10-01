# DOKS Jupyter Hub 

This is the repository that holds the deployment configuration for a jupyter-hub on DOKS

## Local Commands

Build images:

```bash
make -C jupyter-datascience-notebook docker
```

Publish images:

```bash
make -C jupyter-datascience-notebook publish
```

Validate the Helm release:

```bash
make -C jupyter-hub validate
```

Deploy JupyterHub with Helm:

```bash
make -C jupyter-hub deploy
```

Jenkins-style Helm aliases are also available for consistency with your Jenkins repo:

```bash
make -C jupyter-hub helm-repo-init
make -C jupyter-hub helm-upgrade
make -C jupyter-hub helm-upgrade-init
```

Run full orchestration:

```bash
make doks-jupyter
```

Run full orchestration with baseball data refresh:

```bash
make doks-jupyter-with-data
```

## Baseball Data Pipeline

The top-level `mlb-data-pipeline/` module builds detail and aggregate Parquet datasets and publishes snapshot versions to DigitalOcean Spaces.

Key outputs:

- Detail Parquet partitioned by `season` and `month`
- `player_season_metrics.parquet`
- `player_career_metrics.parquet`
- `manifest.json` and `latest.json` snapshot metadata

Typical workflow:

```bash
make -C mlb-data-pipeline docker
make -C mlb-data-pipeline publish IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
make -C mlb-data-pipeline run-job IMAGE_REPO=docker.io/<dockerhub-user>/mlb-data-pipeline
```

Local pipeline test workflow:

```bash
make mlb-data-pipeline-local-install
make mlb-data-pipeline-local-run START_SEASON=2024 END_SEASON=2024 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

Top-level MLB pipeline shortcuts:

- `make mlb-data-pipeline-local-install`
- `make mlb-data-pipeline-local-run ...`
- `make mlb-data-pipeline-local-run-upload ...`
- `make mlb-data-pipeline-local-bootstrap ...`
- `make mlb-data-pipeline-local-bootstrap-upload ...`
- `make mlb-data-pipeline-local-wizard`
- `make mlb-data-pipeline-bootstrap-estimate`
- `make mlb-data-pipeline-test`

These are thin passthrough targets to the module-local Makefile. They exist for convenience only; the module-local `mlb-data-pipeline/Makefile` remains the source of truth for pipeline options and arguments.

Recommended usage:

- Use the explicit Make targets for scripts, CI, and repeatable runs.
- Use `make mlb-data-pipeline-local-wizard` when you want the terminal to walk you through a one-off local pipeline run.

DigitalOcean Spaces credentials are supplied through a Kubernetes secret named `do-spaces-baseball`.

Create that secret in the JupyterHub namespace by filling in the real values below:

```bash
NAMESPACE=jupyter-hub
SPACES_ACCESS_KEY_ID="replace-me"
SPACES_SECRET_ACCESS_KEY="replace-me"
SPACES_BUCKET="replace-me"
SPACES_REGION="replace-me"
SPACES_ENDPOINT_URL="replace-me"

kubectl create secret generic do-spaces-baseball \
	--namespace "$NAMESPACE" \
	--from-literal=SPACES_ACCESS_KEY_ID="$SPACES_ACCESS_KEY_ID" \
	--from-literal=SPACES_SECRET_ACCESS_KEY="$SPACES_SECRET_ACCESS_KEY" \
	--from-literal=SPACES_BUCKET="$SPACES_BUCKET" \
	--from-literal=SPACES_REGION="$SPACES_REGION" \
	--from-literal=SPACES_ENDPOINT_URL="$SPACES_ENDPOINT_URL" \
	--dry-run=client -o yaml | kubectl apply -f -
```

## Shared Notebook Template

The notebook image now includes a shared starter notebook for MLB analysis:

- Template source: `jupyter-datascience-notebook/templates/MLB_Data_Starter.ipynb`
- Auto-copied on startup to each user workspace when missing:
	- `/home/jovyan/work/MLB_Data_Starter.ipynb`
	- `/home/jovyan/assignments/MLB_Data_Starter.ipynb`

This provides a common starting point for querying latest pipeline snapshots.

## CI/CD

- `Jenkinsfile` defines build, test, and deploy stages.
- Build and test run for all branches in a multibranch Jenkins pipeline.
- Deploy runs only on `main` and requires manual approval in Jenkins.
- JupyterHub deploys through the official `jupyterhub` Helm chart using `jupyter-hub/values.yaml` overrides.

Required CI environment variables:

Docker Hub credentials for publishing images are configured in the Jenkins credentials store.

JupyterHub secret prerequisites:

- A Kubernetes secret named `jupyter-hub-config` must exist with keys `oauth_client_id` and `oauth_client_secret`.
- DNS for `jupyter.pedersen.io` should point at the nginx ingress controller.
- cert-manager should expose the `letsencrypt-prod` cluster issuer.

Create the JupyterHub OAuth secret in the JupyterHub namespace by filling in the real values below:

```bash
NAMESPACE=jupyter-hub
OAUTH_CLIENT_ID="replace-me"
OAUTH_CLIENT_SECRET="replace-me"

kubectl create secret generic jupyter-hub-config \
	--namespace "$NAMESPACE" \
	--from-literal=oauth_client_id="$OAUTH_CLIENT_ID" \
	--from-literal=oauth_client_secret="$OAUTH_CLIENT_SECRET" \
	--dry-run=client -o yaml | kubectl apply -f -
```

Tooling expected on Jenkins agents:

- Docker CLI
- Helm CLI
- kubectl

## Dependency Updates

Dependabot configuration is in `.github/dependabot.yml` and tracks Docker base-image updates for:

- `jupyter-hub/Dockerfile`
- `jupyter-datascience-notebook/Dockerfile`
- `mlb-data-pipeline/Dockerfile`
