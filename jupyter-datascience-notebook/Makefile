export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

DOCKER_HUB_NAMESPACE ?= derekpedersen

secret:
	cat jupyter-datascience-notebook_config.py | base64 >> jupyter-datascience-notebook_config.txt

docker:
	docker build ./ -t jupyter-datascience-notebook

publish:
	docker tag jupyter-datascience-notebook docker.io/${DOCKER_HUB_NAMESPACE}/jupyter-datascience-notebook:${GIT_COMMIT_SHA}
	docker push docker.io/${DOCKER_HUB_NAMESPACE}/jupyter-datascience-notebook:${GIT_COMMIT_SHA}

kubernetes: docker publish