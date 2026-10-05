def publishIfMain(String moduleDir) {
  if (env.BRANCH_NAME == 'main') {
    withDockerRegistry([credentialsId: 'docker-pat', url: 'https://index.docker.io/v1/']) {
      sh "make -C ${moduleDir} publish"
    }
  }
}

pipeline {
  agent {
    label 'build-jenkins-base || build-base'
  }

  options {
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

          command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
          command -v helm >/dev/null 2>&1 || { echo "helm is required"; exit 1; }
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

        stage('Build MLB Data Pipeline Image') {
          steps {
            sh 'make -C mlb-data-pipeline docker'
          }
        }
      }
    }

    stage('Test') {
      steps {
        sh 'make -C jupyter-hub validate'
      }
    }

    stage('Deploy') {
      when {
        branch 'main'
      }
      steps {
        input message: 'Deploy to Kubernetes from main?', ok: 'Deploy'

        script {
          publishIfMain('jupyter-datascience-notebook')
        }

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
            publishIfMain('mlb-data-pipeline')
            sh 'make -C mlb-data-pipeline run-job'
          } else {
            echo 'Skipping data refresh stage.'
          }
        }
      }
    }
  }

}
