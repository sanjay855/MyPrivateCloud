pipeline {
    agent any

    environment {
        APP_DIR = "/root/private-cloud"
    }

    stages {
        stage('Verify Code & Templates') {
            steps {
                sh '''
                python3 -m py_compile app.py
                test -f templates/index.html
                test -f templates/login.html
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t private-cloud-app:latest .'
            }
        }

        stage('Deploy Updated Container') {
            steps {
                sh '''
                cp -r app.py templates Dockerfile docker-compose.yml $APP_DIR/
                cd $APP_DIR
                docker compose up -d --no-deps --build cloud-app
                '''
            }
        }
    }

    post {
        success {
            echo 'Private Cloud deployed cleanly without interrupting ngrok!'
        }
    }
}
