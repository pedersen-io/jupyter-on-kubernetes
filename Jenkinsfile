pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  environment {
    GIT_COMMIT_SHA = "${env.GIT_COMMIT}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        sh 'git rev-parse HEAD'
      }
    }

    stage('Validate Environment') {
      steps {
        sh '''
          set -eu

          [ -n "${GCLOUD_PROJECT_ID:-}" ] || { echo "GCLOUD_PROJECT_ID is required"; exit 1; }
          command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
          command -v gcloud >/dev/null 2>&1 || { echo "gcloud is required"; exit 1; }
          command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required"; exit 1; }
        '''
      }
    }

    stage('Build') {
      parallel {
        stage('Build Notebook Image') {
          steps {
            sh 'make -C jupyter-datascience-notebook docker'
          }
        }

        stage('Build Hub Image') {
          steps {
            sh 'make -C jupyter-hub docker'
          }
        }

        stage('Build MLB Data Pipeline Image') {
          steps {
            sh 'make -C mlb-data-pipeline docker'
          }
        }
      }
    }

    stage('Test') {
      steps {
        sh '''
          set -eu

          sed -e "s/%GCLOUD_PROJECT_ID%/${GCLOUD_PROJECT_ID}/g" \
              -e "s/%GIT_COMMIT_SHA%/${GIT_COMMIT_SHA}/g" \
              ./jupyter-hub/kubernetes-deployment.yaml > ./jupyter-hub/deployment.ci.yaml

          kubectl apply --dry-run=client -f ./jupyter-hub/deployment.ci.yaml
          kubectl apply --dry-run=client -f ./jupyter-hub/kubernetes-service.yaml

          rm -f ./jupyter-hub/deployment.ci.yaml
        '''
      }
    }

    stage('Deploy') {
      when {
        branch 'main'
      }
      steps {
        input message: 'Deploy to Kubernetes from main?', ok: 'Deploy'

        sh 'make -C jupyter-datascience-notebook publish'
        sh 'make -C jupyter-hub publish'
        sh 'make -C jupyter-hub deploy'
      }
    }

    stage('Data Refresh') {
      when {
        branch 'main'
      }
      steps {
        script {
          def refreshData = input(
            id: 'DataRefreshApproval',
            message: 'Publish pipeline image and trigger data refresh job?',
            ok: 'Run Data Refresh',
            parameters: [booleanParam(defaultValue: false, description: 'Check to run data refresh after deploy.', name: 'RUN_DATA_REFRESH')]
          )

          if (refreshData) {
            sh 'make -C mlb-data-pipeline publish'
            sh 'make -C mlb-data-pipeline run-job'
          } else {
            echo 'Skipping data refresh stage.'
          }
        }
      }
    }
  }

  post {
    always {
      sh 'rm -f ./jupyter-hub/deployment.ci.yaml || true'
    }
  }
}
