<div align="center">

# ☁️ MyPrivateCloud
### *Your Personal, Self-Hosted, Quota-Enforced Cloud Engine on Windows + WSL2*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-Gunicorn-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Jenkins](https://img.shields.io/badge/Jenkins-CI%2FCD-D24939?style=for-the-badge&logo=jenkins&logoColor=white)](https://jenkins.io)
[![ngrok](https://img.shields.io/badge/ngrok-Static_Edge-1F1E37?style=for-the-badge&logo=ngrok&logoColor=white)](https://ngrok.com)

**"Why rent cloud space when your own machine can run a zero-downtime, CI/CD-backed private cloud accessible from anywhere in the world?"**

</div>

---

## 🚀 Overview

**MyPrivateCloud** transforms a local Windows directory (`D:\MyPrivateCloud`) into a secure, globally reachable personal cloud storage platform—complete with a modern responsive web UI, real-time storage & bandwidth telemetry, dual authentication (Web Session + Mobile API Token), automated **Jenkins CI/CD** deployments, and one-tap **Android MacroDroid** integration.

Instead of exposing router ports or paying for third-party subscriptions, everything runs inside isolated **Docker** containers on **WSL2**, tunneled securely over HTTPS via a static **ngrok** edge endpoint.

---

## 🏗️ System Architecture

```text
+-----------------------+         HTTPS (Static URL)        +---------------------------+
|   📱 Android / Web    | --------------------------------> |    🌐 ngrok Edge Tunnel   |
|  (Chrome / MacroDroid)|                                   |   (Private Docker Net)    |
+-----------------------+                                   +-------------+-------------+
                                                                          |
                                                                 Internal Port 5000
                                                                          v
+-----------------------+         Docker Volume Mount       +---------------------------+
|  💾 Windows Storage   | <===============================> |   🐍 Flask + Gunicorn     |
|  (D:\MyPrivateCloud)  |       & Monthly JSON Quota        |    (private-cloud-app)    |
+-----------------------+                                   +-------------+-------------+
                                                                          ^
                                                            Zero-Downtime Rolling Rebuild
                                                                          |
+-----------------------+          Git Push / Poll          +---------------------------+
|   🐙 GitHub Repo      | --------------------------------> |   ⚙️ Jenkins CI/CD        |
|   (MyPrivateCloud)    |                                   |  (Syntax -> Build -> Up)  |
+-----------------------+                                   +---------------------------+
```

---

## ✨ Key Features

* **📊 Hard Quota & Bandwidth Guardrails:**
  * **1.50 GB Storage Vault:** Real-time disk calculation blocks uploads before exceeding your allocated storage cap (`HTTP 413`).
  * **600.0 MB Monthly Transfer Meter:** Tracks every upload, preview, and download in `meta/transfer.json`, automatically resetting on the 1st of every month (`HTTP 429` if exceeded).
* **🔐 Dual-Layer Authentication (`@auth_required`):**
  * **Web UI:** Session-backed login portal (`login.html`) protected by `APP_PASSWORD`.
  * **Headless API:** Header-based `X-API-Token` authentication built specifically for automated mobile uploads without browser cookies.
* **⚡ Zero-Downtime Jenkins CI/CD:**
  * Every commit triggers a 3-stage pipeline: Python bytecode syntax verification (`py_compile`), Docker image build, and targeted container replacement (`docker compose up -d --no-deps --build cloud-app`)—keeping the **ngrok** tunnel alive throughout deployments.
* **📱 Native Android Workflow (MacroDroid):**
  * Launch the dashboard from a home-screen widget or share any photo/PDF straight from Android's **Share Sheet** into `D:\MyPrivateCloud` in the background.

---

## 🛠️ Tech Stack

| Layer | Technology | Role |
| :--- | :--- | :--- |
| **Backend & Server** | Python 3.11, Flask, Gunicorn | REST API, quota enforcement, file streaming, multi-worker WSGI serving |
| **Frontend** | HTML5, Vanilla JS, CSS3 | Responsive dark-mode dashboard with live storage/transfer progress bars |
| **Containerization** | Docker, Docker Compose | Isolated `cloud-net` bridge network, host volume mounts, auto-restart policies |
| **Ingress Tunnel** | ngrok (`ngrok/ngrok:latest`) | Encrypted HTTPS public endpoint mapped internally to `cloud-app:5000` |
| **CI/CD Automation** | Jenkins (`lts-jdk17`) | Automated syntax checks, image builds, and zero-downtime container rollouts |
| **Mobile Client** | Android + MacroDroid | One-tap dashboard launcher & background `multipart/form-data` Share uploader |

---

## 📂 Repository Structure

```text
private-cloud/
├── app.py                  # Core Flask application, quota logic, & auth middleware
├── Dockerfile              # Lightweight Python 3.11-slim + Gunicorn production image
├── docker-compose.yml      # Multi-container orchestration (cloud-app + ngrok)
├── Jenkinsfile             # Declarative CI/CD pipeline (Verify -> Build -> Deploy)
├── templates/
│   ├── index.html          # Main cloud dashboard, live telemetry meters, & file manager
│   └── login.html          # Password-protected authentication portal
└── meta/                   # Persistent runtime storage for transfer.json (git-ignored)
```

---

## 🚦 Quick Start & Deployment

### 1. Prerequisites
* Windows 11 with **WSL2 (Ubuntu)** and **Docker Engine / Compose v2**
* A free **ngrok** account (Authtoken + Static Dev Domain)
* A local storage directory on Windows (e.g., `D:\MyPrivateCloud` $\rightarrow$ `/mnt/d/MyPrivateCloud`)

### 2. Configure Environment Variables
Update `docker-compose.yml` (or inject via a `.env` file) with your credentials:

```yaml
environment:
  - APP_PASSWORD=YourStrongWebPassword
  - API_TOKEN=YourMacroDroidSecretToken
  - SECRET_KEY=YourRandomFlaskSessionKey
```

### 3. Launch the Stack
```bash
git clone https://github.com/sanjay855/MyPrivateCloud.git
cd MyPrivateCloud
docker compose up -d --build
```

Verify both services are healthy:
```bash
docker compose ps
```

---

## 🔌 API Reference (For Automation & Mobile Shortcuts)

All endpoints accept either an active browser session cookie **or** the `X-API-Token` request header.

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` / `POST` | `/login` | Public | Renders login UI or authenticates `password` form field |
| `GET` | `/` | Required | Renders the main cloud storage dashboard |
| `GET` | `/api/status` | Required | Returns JSON telemetry (`used_space`, `transfer_used`, `files[]`) |
| `POST` | `/upload` | Required | Accepts `multipart/form-data` (`file`) if within 1.5 GB & 600 MB quotas |
| `GET` | `/view/<filename>` | Required | Streams file inline in the browser (counts toward transfer quota) |
| `GET` | `/download/<filename>` | Required | Forces file attachment download (counts toward transfer quota) |
| `POST` | `/delete/<filename>` | Required | Removes file from disk and frees storage quota |

---

## 📱 Android MacroDroid Integration

Turn your phone into a native client in two minutes:

1. **Trigger:** *Receive Share* (All File Types)
2. **Action:** *HTTP Request* $\rightarrow$ `POST https://<your-domain>.ngrok-free.dev/upload`
3. **Headers:**
   * `X-API-Token`: `<YourMacroDroidSecretToken>`
   * `ngrok-skip-browser-warning`: `1`
4. **Body:** *Multipart Form Data* $\rightarrow$ File parameter named `file` mapped to `{shared_file}`

---

## 🔒 Security Best Practices

* **Never commit real tokens to public repositories:** Store `NGROK_AUTHTOKEN`, `APP_PASSWORD`, and `API_TOKEN` inside a local `.env` file (listed in `.gitignore`) or inject them via Jenkins Credentials.
* **Internal Network Isolation:** `cloud-app` does not bind port `5000` to the host interface—traffic can only enter through the authenticated `ngrok` reverse proxy over `cloud-net`.
* **Filename Sanitization:** Every upload, view, download, and delete request passes through `werkzeug.utils.secure_filename` to prevent directory traversal attacks.

---
