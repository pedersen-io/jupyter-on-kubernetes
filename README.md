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
