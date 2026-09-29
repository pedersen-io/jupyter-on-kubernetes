export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

.PHONY: notebook-build-publish-deploy hub-build-publish-deploy mlb-data-pipeline-build-publish mlb-data-pipeline-refresh-job mlb-data-pipeline-apply-cronjob mlb-data-pipeline-local-install mlb-data-pipeline-local-run mlb-data-pipeline-local-run-upload mlb-data-pipeline-local-bootstrap mlb-data-pipeline-local-bootstrap-upload mlb-data-pipeline-local-wizard mlb-data-pipeline-bootstrap-estimate mlb-data-pipeline-test doks-jupyter doks-jupyter-with-data delete-doks-jupyter

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

mlb-data-pipeline-local-install:
	cd ./mlb-data-pipeline && make local-install

mlb-data-pipeline-local-run:
	cd ./mlb-data-pipeline && make local-run

mlb-data-pipeline-local-run-upload:
	cd ./mlb-data-pipeline && make local-run-upload

mlb-data-pipeline-local-bootstrap:
	cd ./mlb-data-pipeline && make local-bootstrap

mlb-data-pipeline-local-bootstrap-upload:
	cd ./mlb-data-pipeline && make local-bootstrap-upload

mlb-data-pipeline-local-wizard:
	cd ./mlb-data-pipeline && make local-wizard

mlb-data-pipeline-bootstrap-estimate:
	cd ./mlb-data-pipeline && make bootstrap-estimate

mlb-data-pipeline-test:
	cd ./mlb-data-pipeline && make test

doks-jupyter: notebook-build-publish-deploy hub-build-publish-deploy

doks-jupyter-with-data: doks-jupyter mlb-data-pipeline-build-publish mlb-data-pipeline-refresh-job

delete-doks-jupyter:
	cd ./jupyter-hub && make delete-kubernetes