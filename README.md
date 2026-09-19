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
make -C mlb-data-pipeline local-install
make -C mlb-data-pipeline local-run START_SEASON=2024 END_SEASON=2024 OUTPUT_DIR=$(pwd)/mlb-data-pipeline/output
```

DigitalOcean Spaces credentials are supplied through a Kubernetes secret named `do-spaces-baseball`.

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
