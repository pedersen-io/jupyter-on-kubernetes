# Contributing

## Local Prerequisites

- Docker
- kubectl
- gcloud CLI authenticated to your project
- Access to the target GKE cluster

## Environment Variables

Set these before running publish or deploy commands:

- `GCLOUD_PROJECT_ID`
- `OAUTH_CALLBACK_URL` (used by JupyterHub config templating)

GitHub OAuth values are provided through Kubernetes secrets:

- `oauth_client_id`
- `oauth_client_secret`

## Local Workflow

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

Deploy JupyterHub manifests:

```bash
make -C jupyter-hub deploy
```

End-to-end orchestration:

```bash
make gke-jupyter
```

## CI/CD Expectations

- Jenkins runs build and test stages for all branches.
- Deploy is limited to `main` and requires manual approval.
- Keep Dockerfiles and Kubernetes manifests change-scoped and reviewable.
