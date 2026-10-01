export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

DOCKER_HUB_NAMESPACE ?= derekpedersen
HELM_RELEASE_NAME ?= jupyter-hub
HELM_NAMESPACE ?= jupyter-hub
HELM_CHART ?= jupyterhub/jupyterhub
HELM_CHART_VERSION ?= 4.4.2
HELM_VALUES_FILE ?= ./values.yaml
NOTEBOOK_IMAGE_REPO ?= docker.io/${DOCKER_HUB_NAMESPACE}/jupyter-datascience-notebook
NOTEBOOK_IMAGE_TAG ?= ${GIT_COMMIT_SHA}

.PHONY: helm-repo helm-repo-init validate deploy helm-upgrade helm-upgrade-init delete-kubernetes kubernetes

helm-repo:
	helm repo add jupyterhub https://hub.jupyter.org/helm-chart/ >/dev/null 2>&1 || true
	helm repo update >/dev/null

helm-repo-init: helm-repo

validate: helm-repo
	@tmpdir="$$(mktemp -d)"; \
	helm pull ${HELM_CHART} --version ${HELM_CHART_VERSION} --untar --untardir "$$tmpdir" >/dev/null; \
	helm lint "$$tmpdir/jupyterhub" --values ${HELM_VALUES_FILE}; \
	helm template ${HELM_RELEASE_NAME} ${HELM_CHART} \
		--version ${HELM_CHART_VERSION} \
		--namespace ${HELM_NAMESPACE} \
		--values ${HELM_VALUES_FILE} \
		--set singleuser.image.name=${NOTEBOOK_IMAGE_REPO} \
		--set singleuser.image.tag=${NOTEBOOK_IMAGE_TAG} >/dev/null; \
	rm -rf "$$tmpdir"

deploy: helm-repo
	helm upgrade --install ${HELM_RELEASE_NAME} ${HELM_CHART} \
		--version ${HELM_CHART_VERSION} \
		--namespace ${HELM_NAMESPACE} \
		--create-namespace \
		--values ${HELM_VALUES_FILE} \
		--set singleuser.image.name=${NOTEBOOK_IMAGE_REPO} \
		--set singleuser.image.tag=${NOTEBOOK_IMAGE_TAG}

helm-upgrade: deploy

helm-upgrade-init: helm-upgrade

delete-kubernetes:
	helm uninstall ${HELM_RELEASE_NAME} --namespace ${HELM_NAMESPACE}

kubernetes: deploy