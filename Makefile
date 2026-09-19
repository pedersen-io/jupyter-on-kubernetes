export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

notebook-build-publish-deploy:
	cd ./jupyter-datascience-notebook && make kubernetes

hub-build-publish-deploy:
	cd ./jupyter-hub && make kubernetes

mlb-data-pipeline-build-publish:
	cd ./mlb-data-pipeline && make docker publish

mlb-data-pipeline-refresh-job:
	cd ./mlb-data-pipeline && make run-job

mlb-data-pipeline-apply-cronjob:
	cd ./mlb-data-pipeline && make apply-cronjob

gke-jupyter: notebook-build-publish-deploy hub-build-publish-deploy

gke-jupyter-with-data: gke-jupyter mlb-data-pipeline-build-publish mlb-data-pipeline-refresh-job

delete-gke-jupyter:
	cd ./jupyter-hub && make delete-kubernetes