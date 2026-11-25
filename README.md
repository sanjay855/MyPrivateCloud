# MyPrivateCloud

### Personal Self-Hosted Cloud Storage | Windows + WSL2 | Docker | Jenkins CI/CD

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flask](https://img.shields.io/badge/Flask-Gunicorn-black)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![Jenkins](https://img.shields.io/badge/Jenkins-CI%2FCD-red)
![ngrok](https://img.shields.io/badge/ngrok-Secure_Tunnel-purple)

A personal self-hosted cloud storage platform built using Python, Flask, Docker, and Jenkins. It transforms local Windows storage into remotely accessible cloud storage with storage quotas, bandwidth tracking, authentication, file management, automated CI/CD deployment, and Android integration.

---

## Live Access

| Resource | Link |
|---|---|
| Cloud Dashboard | [MyPrivateCloud](https://perch-condition-peso.ngrok-free.dev) |
| GitHub Repository | [MyPrivateCloud](https://github.com/sanjay855/MyPrivateCloud) |

---

## Overview

MyPrivateCloud transforms a local Windows directory into a personal cloud storage platform accessible from anywhere through an HTTPS endpoint.

The application runs inside Docker containers hosted on WSL2 (Ubuntu), while files are stored directly on the Windows filesystem. ngrok provides secure external connectivity, and Jenkins automates application builds and deployments through a CI/CD pipeline.

The project combines cloud-style storage management, containerization, authentication, infrastructure automation, and mobile integration into a single self-hosted environment.

---

## System Architecture

```text
+-------------------------+
|     Android / Web      |
|   Browser / MacroDroid |
+------------+------------+
             |
             | HTTPS
             v
+-------------------------+
|       ngrok Edge       |
|    Secure Tunnel       |
+------------+------------+
             |
             | Docker Network
             v
+-------------------------+
|   Flask Application    |
|   Gunicorn Server     |
|   Docker Container    |
+------------+------------+
             |
             | Storage Mount
             v
+-------------------------+
|    Windows Storage     |
|   D:\MyPrivateCloud   |
+-------------------------+


+-------------------------+
|       GitHub            |
|    Source Code          |
+------------+------------+
             |
             | Push / Poll
             v
+-------------------------+
|       Jenkins           |
|     CI/CD Pipeline     |
+------------+------------+
             |
             v
+-------------------------+
| Syntax Verification    |
| Docker Image Build    |
| Application Deploy     |
+-------------------------+
```

---

## Key Features

### Storage Management

- 1.50 GB storage quota
- Real-time storage usage calculation
- Upload validation before saving files
- Upload restrictions when storage capacity is reached
- File upload, preview, download, and deletion
- Storage space automatically freed after file deletion

### Monthly Bandwidth Management

- 600 MB monthly transfer quota
- Tracks upload, preview, and download operations
- Persistent transfer tracking using JSON metadata
- Automatic monthly quota reset
- Request restrictions when the transfer quota is exceeded

### Authentication and Access Control

- Password-protected web login
- Session-based authentication for browser access
- API token authentication for mobile automation
- Authentication middleware protecting application endpoints

### Automated CI/CD

Jenkins automates application deployment through a pipeline consisting of:

1. Python syntax verification
2. Docker image build
3. Application container deployment

The pipeline uses targeted Docker Compose deployment to update the application container without intentionally restarting the ngrok tunnel.

### Android Integration

MacroDroid provides mobile integration with the cloud storage platform.

- Open the cloud dashboard from Android
- Upload files using the Android Share Sheet
- Upload photos and documents
- Send HTTP requests to the cloud API
- Perform automated uploads without browser-based login

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11 | Application logic |
| Web Framework | Flask | API and web application |
| Application Server | Gunicorn | WSGI application serving |
| Frontend | HTML5, CSS3, JavaScript | Responsive cloud dashboard |
| Containerization | Docker | Application isolation |
| Orchestration | Docker Compose | Container management |
| CI/CD | Jenkins | Automated build and deployment |
| Repository | GitHub | Source code management |
| Secure Tunnel | ngrok | Public HTTPS access |
| Mobile Automation | Android + MacroDroid | Mobile uploads and shortcuts |
| Host Storage | Windows 11 | Persistent file storage |
| Linux Environment | WSL2 + Ubuntu | Docker hosting environment |

---

## Repository Structure

```text
MyPrivateCloud/
│
├── app.py
├── Dockerfile
├── docker-compose.yml
├── Jenkinsfile
│
├── templates/
│   ├── index.html
│   └── login.html
│
├── meta/
│   └── transfer.json
│
└── README.md
```

| File/Directory | Description |
|---|---|
| `app.py` | Flask application, authentication, API routes, storage management, and quota enforcement |
| `Dockerfile` | Builds the Python application image using Gunicorn |
| `docker-compose.yml` | Defines application services, networking, storage mounts, and container configuration |
| `Jenkinsfile` | Defines the automated CI/CD pipeline |
| `templates/index.html` | Main dashboard and file management interface |
| `templates/login.html` | Login page |
| `meta/` | Persistent metadata used for transfer tracking and quota management |

---

## Infrastructure Design

### Host Storage

Files are stored directly on the Windows filesystem.

```text
D:\MyPrivateCloud
```

The directory is mounted into the Docker application container, allowing files to persist independently of the application container lifecycle.

### Container Networking

The application and ngrok services communicate through a dedicated Docker bridge network.

- Flask listens internally on port `5000`.
- The application port is not directly exposed to the host.
- ngrok forwards incoming HTTPS traffic to the application container.
- Internal service communication uses Docker networking.

### Remote Access

The cloud application is accessible through the ngrok HTTPS endpoint.

[Open MyPrivateCloud](https://perch-condition-peso.ngrok-free.dev)

---

## Deployment

### Prerequisites

- Windows 11
- WSL2
- Ubuntu
- Docker Engine
- Docker Compose v2
- Git
- Jenkins
- ngrok

### Clone the Repository

```bash
git clone https://github.com/sanjay855/MyPrivateCloud.git
cd MyPrivateCloud
```

### Build and Start the Containers

```bash
docker compose up -d --build
```

### Verify Container Status

```bash
docker compose ps
```

### View Application Logs

```bash
docker compose logs -f cloud-app
```

### Stop the Application

```bash
docker compose down
```

---

## CI/CD Pipeline

The project uses Jenkins to automate application build and deployment.

### Pipeline Workflow

```text
Developer Changes
       |
       v
    Git Push
       |
       v
 Jenkins Pipeline
       |
       v
 Python Syntax Check
       |
       v
 Docker Image Build
       |
       v
 Targeted Deployment
       |
       v
 Application Updated
```

### Pipeline Stages

| Stage | Description |
|---|---|
| Verify | Checks Python source code syntax using `py_compile` |
| Build | Builds the updated Docker image |
| Deploy | Recreates the application service using Docker Compose |

The deployment targets the cloud application container rather than the entire stack, helping keep the ngrok tunnel running during application updates.

---

## API Reference

| Method | Endpoint | Authentication | Description |
|---|---|---|---|
| GET | `/login` | Public | Displays the login page |
| POST | `/login` | Public | Authenticates the user |
| GET | `/` | Required | Loads the cloud dashboard |
| GET | `/api/status` | Required | Returns storage, transfer, and file information |
| POST | `/upload` | Required | Uploads files subject to quota restrictions |
| GET | `/view/<filename>` | Required | Displays supported files inline |
| GET | `/download/<filename>` | Required | Downloads a file |
| POST | `/delete/<filename>` | Required | Deletes a file and frees storage |

Protected endpoints support authenticated browser sessions and authorized API requests.

---

## Android MacroDroid Integration

MacroDroid connects Android file-sharing workflows to the cloud application.

### Upload Workflow

1. Share a file from an Android application.
2. MacroDroid receives the shared file.
3. MacroDroid sends an HTTP POST request to the cloud upload endpoint.
4. The request includes the file as multipart form data.
5. Flask validates authentication and storage limits.
6. The file is saved to the Windows storage directory.

### Upload Endpoint

```http
POST https://perch-condition-peso.ngrok-free.dev/upload
```

### Request Format

```text
Content-Type: multipart/form-data

file: Shared file
```

The mobile workflow uses API authentication configured privately in MacroDroid.

---

## Security Considerations

- Authentication is required for protected cloud operations.
- API access uses a separate authentication mechanism for mobile automation.
- The Flask application is not directly exposed through a host port.
- Public access is routed through the HTTPS ngrok tunnel.
- Filenames are sanitized using Werkzeug's `secure_filename`.
- Upload requests are validated against storage and bandwidth limits.
- Sensitive configuration values are kept outside the source repository.
- Persistent files and quota metadata are stored outside the application container.

---

## Project Goals

This project was built to gain practical experience with:

- Self-hosted cloud infrastructure
- Linux environments using WSL2
- Docker containerization
- Docker Compose orchestration
- Flask application deployment
- CI/CD pipeline implementation using Jenkins
- Secure remote access using ngrok
- API authentication and access control
- Storage and bandwidth quota management
- Android automation and HTTP integration
- Persistent storage and container lifecycle management

---

## Future Improvements

- File encryption at rest
- Automated backups
- Improved audit logging
- Advanced file search and filtering
- User-based storage quotas
- Monitoring and alerting
- Enhanced security controls
- Container health checks
- Deployment monitoring

---

## Author

**Sanjay**

Cloud Infrastructure | DevOps | Docker | Jenkins | Azure | Linux

GitHub: [sanjay855](https://github.com/sanjay855)

---

## AI-Assisted Development

AI tools were used during the development of MyPrivateCloud to assist with implementation, troubleshooting, planning, and improving the overall development workflow.
*MyPrivateCloud is a personal self-hosted cloud infrastructure project built for learning, experimentation, automation, and practical cloud engineering experience.*
