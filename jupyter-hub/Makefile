export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

DOCKER_HUB_NAMESPACE ?= derekpedersen

docker:
	cp ./jupyter-hub_config.template.py ./jupyter-hub_config.py
	docker build ./ -t jupyter-hub

publish:
	docker tag jupyter-hub docker.io/${DOCKER_HUB_NAMESPACE}/jupyter-hub:${GIT_COMMIT_SHA}
	docker push docker.io/${DOCKER_HUB_NAMESPACE}/jupyter-hub:${GIT_COMMIT_SHA}

deploy:
	sed -e 's/%GIT_COMMIT_SHA%/${GIT_COMMIT_SHA}/g' ./kubernetes-deployment.yaml > deployment.sed.yaml
	kubectl apply -f ./deployment.sed.yaml
	kubectl apply -f ./kubernetes-service.yaml

delete-kubernetes:
	kubectl delete deployment jupyter-hub-deployment

kubernetes: docker publish deploy