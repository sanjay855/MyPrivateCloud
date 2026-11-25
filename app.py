import os
import json
import time
import secrets
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

# In-memory request tracker and single-use tokens
# REQUEST_TRACKER: {req_id: {"name": str, "time": str, "created": float, "status": "pending"|"approved"|"denied", "link": str|None}}
REQUEST_TRACKER = {}
GUEST_TOKENS = {}  # {token: {"name": str, "expires": float}}

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


def auth_required(allow_guest=False):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            is_owner = session.get("logged_in") or request.headers.get("X-API-Token") == API_TOKEN
            is_guest = allow_guest and session.get("guest_mode")

            if is_owner or is_guest:
                return f(*args, **kwargs)
            if session.get("guest_mode") and not allow_guest:
                return jsonify({"error": "Read-only guest preview: actions disabled."}), 403
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return decorated
    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session.clear()
            session["logged_in"] = True
            return redirect(url_for("index"))
        return redirect(url_for("login", error=1))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/request-guest", methods=["POST"])
def request_guest():
    data = request.get_json(silent=True) or request.form
    guest_name = (data.get("name") or "").strip()[:40]
    if not guest_name:
        return jsonify({"error": "Please enter your name."}), 400

    # Clean entries older than 30 minutes
    now = time.time()
    for k in [k for k, v in REQUEST_TRACKER.items() if now - v["created"] > 1800]:
        REQUEST_TRACKER.pop(k, None)

    pending_count = sum(1 for v in REQUEST_TRACKER.values() if v["status"] == "pending")
    if pending_count >= 10:
        return jsonify({"error": "Approval queue is full. Try again later."}), 429

    req_id = secrets.token_urlsafe(8)
    REQUEST_TRACKER[req_id] = {
        "name": guest_name,
        "time": datetime.now().strftime("%I:%M:%S %p"),
        "created": now,
        "status": "pending",
        "link": None
    }
    return jsonify({
        "status": "pending",
        "req_id": req_id,
        "message": "Request sent! Waiting for Sanjay to approve..."
    }), 201


@app.route("/check-guest/<req_id>")
def check_guest(req_id):
    item = REQUEST_TRACKER.get(req_id)
    if not item:
        return jsonify({"status": "expired"}), 404
    if item["status"] == "approved":
        # Deliver the link once to the waiting browser, then clear it from tracker
        link = item["link"]
        REQUEST_TRACKER.pop(req_id, None)
        return jsonify({"status": "approved", "one_time_link": link})
    if item["status"] == "denied":
        REQUEST_TRACKER.pop(req_id, None)
        return jsonify({"status": "denied"})
    return jsonify({"status": "pending"})


@app.route("/api/guest-requests")
@auth_required(allow_guest=False)
def list_guest_requests():
    items = [
        {"id": k, "name": v["name"], "time": v["time"]}
        for k, v in REQUEST_TRACKER.items()
        if v["status"] == "pending"
    ]
    return jsonify({"requests": items})


@app.route("/approve-guest/<req_id>", methods=["POST"])
@auth_required(allow_guest=False)
def approve_guest(req_id):
    item = REQUEST_TRACKER.get(req_id)
    if not item or item["status"] != "pending":
        return jsonify({"error": "Request not found or already handled."}), 404

    token = secrets.token_urlsafe(16)
    GUEST_TOKENS[token] = {
        "name": item["name"],
        "expires": time.time() + 600  # 10-minute window to open once
    }
    link = f"https://perch-condition-peso.ngrok-free.dev/guest/{token}"
    item["status"] = "approved"
    item["link"] = link
    return jsonify({"status": "approved", "guest_name": item["name"]})


@app.route("/deny-guest/<req_id>", methods=["POST"])
@auth_required(allow_guest=False)
def deny_guest(req_id):
    item = REQUEST_TRACKER.get(req_id)
    if item:
        item["status"] = "denied"
    return jsonify({"status": "denied"})


@app.route("/guest/<token>")
def guest_login(token):
    # Immediately burn the token on first click so no second use is possible
    entry = GUEST_TOKENS.pop(token, None)
    if not entry or time.time() > entry["expires"]:
        return "Access Denied: This one-time guest link has already been used or expired.", 403

    session.clear()
    session["guest_mode"] = True
    session["guest_name"] = entry["name"]
    return redirect(url_for("index"))


@app.route("/")
@auth_required(allow_guest=True)
def index():
    return render_template("index.html", is_guest=bool(session.get("guest_mode")), guest_name=session.get("guest_name", ""))


@app.route("/api/status")
@auth_required(allow_guest=True)
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
        "files": files_list,
        "is_guest": bool(session.get("guest_mode"))
    })


@app.route("/upload", methods=["POST"])
@auth_required(allow_guest=False)
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
@auth_required(allow_guest=False)
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
@auth_required(allow_guest=False)
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
@auth_required(allow_guest=False)
def delete_file(filename):
    safe_name = secure_filename(filename)
    fp = os.path.join(STORAGE_DIR, safe_name)
    if os.path.isfile(fp):
        os.remove(fp)
        return jsonify({"status": "deleted"}), 200
    return jsonify({"error": "File not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
