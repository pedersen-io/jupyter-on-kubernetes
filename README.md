# GKE Jupyter Hub 

This is the repository that holds the deployment configuration for a jupyter-hub to gke

## Local Commands

Build images:

```bash
make -C jupyter-datascience-notebook docker
make -C jupyter-hub docker
```

Publish images:

```bash
make -C jupyter-datascience-notebook publish
make -C jupyter-hub publish
```

Deploy manifests:

```bash
make -C jupyter-hub deploy
```

Run full orchestration:

```bash
make gke-jupyter
```

Run full orchestration with baseball data refresh:

```bash
make gke-jupyter-with-data
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
- `make mlb-data-pipeline-test`

These are thin passthrough targets to the module-local Makefile. They exist for convenience only; the module-local `mlb-data-pipeline/Makefile` remains the source of truth for pipeline options and arguments.

Recommended usage:

- Use the explicit Make targets for local-only runs versus upload-enabled runs.
- Do not add an interactive installer or prompt-driven wrapper unless the workflow becomes genuinely hard to operate non-interactively; today the Make targets and environment variables are simpler and easier to automate.

DigitalOcean Spaces credentials are supplied through a Kubernetes secret named `do-spaces-baseball`.

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

Required CI environment variables:

- `GCLOUD_PROJECT_ID`

Tooling expected on Jenkins agents:

- Docker CLI
- gcloud CLI
- kubectl

## Dependency Updates

Dependabot configuration is in `.github/dependabot.yml` and tracks Docker base-image updates for:

- `jupyter-hub/Dockerfile`
- `jupyter-datascience-notebook/Dockerfile`
- `mlb-data-pipeline/Dockerfile`
