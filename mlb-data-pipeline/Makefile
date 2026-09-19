export GIT_COMMIT_SHA = $(shell git rev-parse HEAD)

IMAGE_REPO ?= us.gcr.io/${GCLOUD_PROJECT_ID}/mlb-data-pipeline
IMAGE_TAG ?= ${GIT_COMMIT_SHA}
IMAGE ?= ${IMAGE_REPO}:${IMAGE_TAG}
PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON ?= ${VENV_DIR}/bin/python
RUN_PYTHON ?= $(if $(wildcard ${VENV_PYTHON}),${VENV_PYTHON},${PYTHON})
START_SEASON ?= 2024
END_SEASON ?= 2024
OUTPUT_DIR ?= $(CURDIR)/output
SAMPLE_MODE ?= false
SAMPLE_START_DATE ?=
SAMPLE_END_DATE ?=
SAMPLE_MAX_ROWS ?= 20000
SAMPLE_MAX_WINDOWS ?= 2
SAMPLE_RANDOM_STATE ?= 42

.PHONY: render-job render-cronjob docker publish run-job apply-cronjob apply-spaces-secret-example clean local-install local-run local-run-docker local-run-sample local-run-sample-docker test

render-job:
	sed -e 's|%DATA_PIPELINE_IMAGE%|${IMAGE}|g' -e 's|%GIT_COMMIT_SHA%|${GIT_COMMIT_SHA}|g' ./kubernetes-job.yaml > ./kubernetes-job.rendered.yaml

render-cronjob:
	sed -e 's|%DATA_PIPELINE_IMAGE%|${IMAGE}|g' ./kubernetes-cronjob.yaml > ./kubernetes-cronjob.rendered.yaml

docker:
	docker build ./ -t mlb-data-pipeline

local-install:
	${PYTHON} -m venv ${VENV_DIR}
	${VENV_PYTHON} -m pip install --upgrade pip
	${VENV_PYTHON} -m pip install -r ./requirements.txt

local-run:
	mkdir -p "${OUTPUT_DIR}"
	START_SEASON=${START_SEASON} END_SEASON=${END_SEASON} OUTPUT_DIR="${OUTPUT_DIR}" \
	SAMPLE_MODE=${SAMPLE_MODE} SAMPLE_START_DATE=${SAMPLE_START_DATE} SAMPLE_END_DATE=${SAMPLE_END_DATE} \
	SAMPLE_MAX_ROWS=${SAMPLE_MAX_ROWS} SAMPLE_MAX_WINDOWS=${SAMPLE_MAX_WINDOWS} SAMPLE_RANDOM_STATE=${SAMPLE_RANDOM_STATE} \
	${RUN_PYTHON} ./download_and_convert.py

local-run-sample:
	mkdir -p "${OUTPUT_DIR}"
	START_SEASON=${START_SEASON} END_SEASON=${END_SEASON} OUTPUT_DIR="${OUTPUT_DIR}" \
	SAMPLE_MODE=true SAMPLE_MAX_ROWS=${SAMPLE_MAX_ROWS} SAMPLE_MAX_WINDOWS=${SAMPLE_MAX_WINDOWS} SAMPLE_RANDOM_STATE=${SAMPLE_RANDOM_STATE} \
	${RUN_PYTHON} ./download_and_convert.py

local-run-docker: docker
	mkdir -p "${OUTPUT_DIR}"
	docker run --rm \
		-e START_SEASON=${START_SEASON} \
		-e END_SEASON=${END_SEASON} \
		-e SAMPLE_MODE=${SAMPLE_MODE} \
		-e SAMPLE_START_DATE=${SAMPLE_START_DATE} \
		-e SAMPLE_END_DATE=${SAMPLE_END_DATE} \
		-e SAMPLE_MAX_ROWS=${SAMPLE_MAX_ROWS} \
		-e SAMPLE_MAX_WINDOWS=${SAMPLE_MAX_WINDOWS} \
		-e SAMPLE_RANDOM_STATE=${SAMPLE_RANDOM_STATE} \
		-e OUTPUT_DIR=/out \
		-v "${OUTPUT_DIR}":/out \
		mlb-data-pipeline

local-run-sample-docker: docker
	mkdir -p "${OUTPUT_DIR}"
	docker run --rm \
		-e START_SEASON=${START_SEASON} \
		-e END_SEASON=${END_SEASON} \
		-e SAMPLE_MODE=true \
		-e SAMPLE_MAX_ROWS=${SAMPLE_MAX_ROWS} \
		-e SAMPLE_MAX_WINDOWS=${SAMPLE_MAX_WINDOWS} \
		-e SAMPLE_RANDOM_STATE=${SAMPLE_RANDOM_STATE} \
		-e OUTPUT_DIR=/out \
		-v "${OUTPUT_DIR}":/out \
		mlb-data-pipeline

test:
	${RUN_PYTHON} -m unittest discover -s ./tests -p 'test_*.py'

publish:
	docker tag mlb-data-pipeline ${IMAGE}
	docker push ${IMAGE}

run-job: render-job
	kubectl apply -f ./kubernetes-job.rendered.yaml

apply-cronjob: render-cronjob
	kubectl apply -f ./kubernetes-cronjob.rendered.yaml

apply-spaces-secret-example:
	kubectl apply -f ./spaces-secret.example.yaml

clean:
	rm -f ./kubernetes-job.rendered.yaml ./kubernetes-cronjob.rendered.yaml
