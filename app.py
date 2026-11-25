import os
import json
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, render_template, send_from_directory,
    redirect, url_for, session, jsonify
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-9988")

STORAGE_DIR = "/app/storage"
META_FILE = "/app/meta/transfer.json"

MAX_STORAGE_BYTES = int(1.5 * 1024 * 1024 * 1024)  # 1.50 GB
MAX_TRANSFER_BYTES = 600 * 1024 * 1024             # 600 MB

APP_PASSWORD = os.environ.get("APP_PASSWORD", "MyCloudPass123")
API_TOKEN = os.environ.get("API_TOKEN", "macrodroid-secret-token")

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(META_FILE), exist_ok=True)


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0 or unit == "GB":
            return f"{size:.2f} {unit}" if unit == "GB" else f"{size:.1f} {unit}"
        size /= 1024.0


def get_storage_used():
    total = 0
    for root, _, files in os.walk(STORAGE_DIR):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def get_transfer_bytes():
    current_month = datetime.now().strftime("%Y-%m")
    data = {"month": current_month, "bytes": 0}
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r") as f:
                saved = json.load(f)
            if saved.get("month") == current_month:
                data = saved
            else:
                save_transfer_bytes(0)
        except Exception:
            save_transfer_bytes(0)
    else:
        save_transfer_bytes(0)
    return data["bytes"]


def save_transfer_bytes(amount):
    current_month = datetime.now().strftime("%Y-%m")
    with open(META_FILE, "w") as f:
        json.dump({"month": current_month, "bytes": amount}, f)


def add_transfer_bytes(delta):
    current = get_transfer_bytes()
    save_transfer_bytes(current + delta)


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("logged_in") or request.headers.get("X-API-Token") == API_TOKEN:
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("login"))
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        return redirect(url_for("login", error=1))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth_required
def index():
    return render_template("index.html")


@app.route("/api/status")
@auth_required
def api_status():
    used_storage = get_storage_used()
    avail_storage = max(0, MAX_STORAGE_BYTES - used_storage)
    space_pct = round((used_storage / MAX_STORAGE_BYTES) * 100, 1)

    used_transfer = get_transfer_bytes()
    transfer_pct = round((used_transfer / MAX_TRANSFER_BYTES) * 100, 1)

    files_list = []
    for name in sorted(os.listdir(STORAGE_DIR)):
        fp = os.path.join(STORAGE_DIR, name)
        if os.path.isfile(fp):
            stat = os.stat(fp)
            mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            files_list.append({
                "name": name,
                "size": format_bytes(stat.st_size),
                "modified": mod_time
            })

    return jsonify({
        "total_space": "1.50 GB",
        "used_space": format_bytes(used_storage),
        "available_space": format_bytes(avail_storage),
        "space_percent": space_pct,
        "transfer_used": format_bytes(used_transfer),
        "transfer_limit": "600.0 MB",
        "transfer_percent": transfer_pct,
        "files": files_list
    })


@app.route("/upload", methods=["POST"])
@auth_required
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file selected."}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    f.seek(0, os.SEEK_END)
    file_size = f.tell()
    f.seek(0)

    if get_storage_used() + file_size > MAX_STORAGE_BYTES:
        return jsonify({"error": "Exceeds 1.50 GB total storage limit."}), 413

    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return jsonify({"error": "Exceeds 600 MB monthly transfer limit."}), 429

    filename = secure_filename(f.filename)
    f.save(os.path.join(STORAGE_DIR, filename))
    add_transfer_bytes(file_size)

    return jsonify({"status": "ok", "file": filename}), 201


@app.route("/view/<filename>")
@auth_required
def view_file(filename):
    safe_name = secure_filename(filename)
    fp = os.path.join(STORAGE_DIR, safe_name)
    if not os.path.isfile(fp):
        return "File not found", 404
    file_size = os.path.getsize(fp)
    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return "Monthly 600 MB transfer limit reached.", 429
    add_transfer_bytes(file_size)
    return send_from_directory(STORAGE_DIR, safe_name, as_attachment=False)


@app.route("/download/<filename>")
@auth_required
def download_file(filename):
    safe_name = secure_filename(filename)
    fp = os.path.join(STORAGE_DIR, safe_name)
    if not os.path.isfile(fp):
        return "File not found", 404
    file_size = os.path.getsize(fp)
    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return "Monthly 600 MB transfer limit reached.", 429
    add_transfer_bytes(file_size)
    return send_from_directory(STORAGE_DIR, safe_name, as_attachment=True)


@app.route("/delete/<filename>", methods=["POST"])
@auth_required
def delete_file(filename):
    safe_name = secure_filename(filename)
    fp = os.path.join(STORAGE_DIR, safe_name)
    if os.path.isfile(fp):
        os.remove(fp)
        return jsonify({"status": "deleted"}), 200
    return jsonify({"error": "File not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
