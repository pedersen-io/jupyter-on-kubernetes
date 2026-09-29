# Contributing

## Local Prerequisites

- Docker
- kubectl
- Access to the target DOKS cluster
- Docker Hub access for publishing images

## Environment Variables

Set these before running publish or deploy commands:

- `DOCKER_HUB_NAMESPACE` (optional; defaults to `derekpedersen`)
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

The publish targets tag and push to Docker Hub using `DOCKER_HUB_NAMESPACE`.

Deploy JupyterHub manifests:

```bash
make -C jupyter-hub deploy
```

End-to-end orchestration:

```bash
make doks-jupyter
```

## CI/CD Expectations

- Jenkins runs build and test stages for all branches.
- Deploy is limited to `main` and requires manual approval.
- Keep Dockerfiles and Kubernetes manifests change-scoped and reviewable.
