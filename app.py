import os
import re
import io
import json
import base64
import shutil
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, render_template, send_from_directory,
    redirect, url_for, session, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import pyotp
import qrcode

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-9988")

STORAGE_DIR = "/app/storage"
USERS_DIR = os.path.join(STORAGE_DIR, "users")
PUBLIC_DIR = os.path.join(STORAGE_DIR, "public")
ARCHIVE_DIR = os.path.join(STORAGE_DIR, "archive")
META_DIR = "/app/meta"

DB_FILE = os.path.join(META_DIR, "cloud.db")
TRANSFER_FILE = os.path.join(META_DIR, "transfer.json")
PUBLIC_OWNERS_FILE = os.path.join(META_DIR, "public_owners.json")

TOTAL_DRIVE_BYTES = int(1.5 * 1024 * 1024 * 1024)  # 1.50 GB total drive
USER_QUOTA_BYTES = 30 * 1024 * 1024                # 30.0 MB combined per regular user
MAX_TRANSFER_BYTES = 600 * 1024 * 1024             # 600.0 MB monthly bandwidth

API_TOKEN = os.environ.get("API_TOKEN", "macrodroid-secret-token")

for d in (USERS_DIR, PUBLIC_DIR, ARCHIVE_DIR, META_DIR):
    os.makedirs(d, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            totp_secret TEXT NOT NULL,
            is_approved INTEGER NOT NULL DEFAULT 0,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


def has_admin():
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    conn.close()
    return row is not None


def get_admin_username():
    conn = get_db()
    row = conn.execute("SELECT username FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1").fetchone()
    conn.close()
    return row["username"] if row else None


def make_qr_data_uri(username, secret):
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="MyPrivateCloud")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0 or unit == "GB":
            return f"{size:.2f} {unit}" if unit == "GB" else f"{size:.1f} {unit}"
        size /= 1024.0


def load_public_owners():
    if os.path.exists(PUBLIC_OWNERS_FILE):
        try:
            with open(PUBLIC_OWNERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_public_owners(mapping):
    with open(PUBLIC_OWNERS_FILE, "w") as f:
        json.dump(mapping, f)


def get_folder_size(folder_path):
    if not os.path.exists(folder_path):
        return 0
    total = 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def get_user_combined_used(username):
    """Calculates combined bytes used across a user's private folder and their public uploads."""
    private_bytes = get_folder_size(os.path.join(USERS_DIR, username))
    owners = load_public_owners()
    public_bytes = 0
    for fname, owner in owners.items():
        if owner == username:
            fp = os.path.join(PUBLIC_DIR, fname)
            if os.path.isfile(fp):
                public_bytes += os.path.getsize(fp)
    return private_bytes + public_bytes


def get_transfer_bytes():
    current_month = datetime.now().strftime("%Y-%m")
    data = {"month": current_month, "bytes": 0}
    if os.path.exists(TRANSFER_FILE):
        try:
            with open(TRANSFER_FILE, "r") as f:
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
    with open(TRANSFER_FILE, "w") as f:
        json.dump({"month": current_month, "bytes": amount}, f)


def add_transfer_bytes(delta):
    save_transfer_bytes(get_transfer_bytes() + delta)


def resolve_scope_folder(scope, current_user, is_admin):
    """
    Strictly resolves folder paths and prevents directory traversal:
    - 'private': user's own private folder
    - 'public': shared public folder
    - 'user:<name>': admin-only view of any user's private folder
    - 'archive': admin-only view of archived user folders
    """
    if scope == "public":
        os.makedirs(PUBLIC_DIR, exist_ok=True)
        return PUBLIC_DIR, "public"

    if scope == "archive" and is_admin:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        return ARCHIVE_DIR, "archive"

    if scope.startswith("user:") and is_admin:
        target_user = re.sub(r"[^a-z0-9_]", "", scope.split(":", 1)[1].lower())
        if target_user:
            target_dir = os.path.abspath(os.path.join(USERS_DIR, target_user))
            if target_dir.startswith(os.path.abspath(USERS_DIR) + os.sep):
                os.makedirs(target_dir, exist_ok=True)
                return target_dir, f"user:{target_user}"

    own_dir = os.path.abspath(os.path.join(USERS_DIR, current_user))
    os.makedirs(own_dir, exist_ok=True)
    return own_dir, "private"


def login_required(admin_only=False):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Support MacroDroid API token uploads directly into Admin's private folder
            if request.headers.get("X-API-Token") == API_TOKEN and not admin_only:
                admin_name = get_admin_username()
                if not admin_name:
                    return jsonify({"error": "Admin account not initialized yet."}), 400
                request.current_user = {"username": admin_name, "is_admin": 1, "is_approved": 1}
                return f(*args, **kwargs)

            user_id = session.get("user_id")
            if not user_id:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Unauthorized"}), 401
                return redirect(url_for("login"))

            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            conn.close()

            if not user or not user["is_approved"]:
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Account pending approval or revoked."}), 403
                return redirect(url_for("login"))

            if admin_only and not user["is_admin"]:
                return jsonify({"error": "Admin privileges required."}), 403

            request.current_user = dict(user)
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():
    admin_exists = has_admin()
    if request.method == "POST":
        username_or_email = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        otp_code = (request.form.get("otp") or "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email)
        ).fetchone()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", admin_exists=admin_exists, error="Invalid username/email or password.")

        if not user["is_approved"]:
            return render_template("login.html", admin_exists=admin_exists, error="Your account is waiting for Administrator approval.")

        totp = pyotp.TOTP(user["totp_secret"])
        if not totp.verify(otp_code, valid_window=1):
            return render_template("login.html", admin_exists=admin_exists, error="Invalid 6-digit Authenticator App code.")

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])
        return redirect(url_for("index"))

    return render_template("login.html", admin_exists=admin_exists)


@app.route("/register", methods=["POST"])
def register():
    admin_exists = has_admin()
    raw_username = (request.form.get("username") or "").strip().lower()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not re.match(r"^[a-z0-9_]{3,20}$", raw_username):
        return render_template(
            "login.html", admin_exists=admin_exists,
            reg_error="Username must be 3–20 lowercase letters, numbers, or underscores."
        )
    if "@" not in email or len(email) < 5:
        return render_template("login.html", admin_exists=admin_exists, reg_error="Please enter a valid Email ID.")
    if len(password) < 6:
        return render_template("login.html", admin_exists=admin_exists, reg_error="Password must be at least 6 characters.")

    is_first_admin = 1 if not admin_exists else 0
    is_approved = 1 if is_first_admin else 0
    totp_secret = pyotp.random_base32()
    pw_hash = generate_password_hash(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO users (username, email, password_hash, totp_secret, is_approved, is_admin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (raw_username, email, pw_hash, totp_secret, is_approved, is_first_admin, created_at)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("login.html", admin_exists=admin_exists, reg_error="Username or Email ID is already registered.")
    conn.close()

    os.makedirs(os.path.join(USERS_DIR, raw_username), exist_ok=True)

    qr_uri = make_qr_data_uri(raw_username, totp_secret)
    msg = (
        "Admin account created! Scan the QR code below, then click Continue to Sign In."
        if is_first_admin else
        "Account registered! Scan this QR code in your Authenticator app now."
    )
    return render_template(
        "login.html",
        admin_exists=True,
        is_first_admin=bool(is_first_admin),
        qr_uri=qr_uri,
        totp_secret=totp_secret,
        reg_success=msg
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required()
def index():
    u = request.current_user
    return render_template("index.html", username=u["username"], is_admin=bool(u["is_admin"]))


@app.route("/api/status")
@login_required()
def api_status():
    u = request.current_user
    username = u["username"]
    is_admin = bool(u["is_admin"])
    scope = request.args.get("scope", "private")
    target_dir, resolved_scope = resolve_scope_folder(scope, username, is_admin)

    # Storage meter: Admin sees full 1.50 GB drive; regular users see their 30.0 MB combined quota
    if is_admin:
        used_bytes = get_folder_size(STORAGE_DIR)
        limit_bytes = TOTAL_DRIVE_BYTES
        limit_label = "1.50 GB"
    else:
        used_bytes = get_user_combined_used(username)
        limit_bytes = USER_QUOTA_BYTES
        limit_label = "30.0 MB"

    space_pct = round((used_bytes / limit_bytes) * 100, 1) if limit_bytes else 0

    used_transfer = get_transfer_bytes()
    transfer_pct = round((used_transfer / MAX_TRANSFER_BYTES) * 100, 1)

    owners = load_public_owners()
    files_list = []

    if resolved_scope == "archive":
        # List files across archived user folders as "folder/filename"
        for arch_folder in sorted(os.listdir(ARCHIVE_DIR)):
            afp = os.path.join(ARCHIVE_DIR, arch_folder)
            if os.path.isdir(afp):
                for fname in sorted(os.listdir(afp)):
                    fp = os.path.join(afp, fname)
                    if os.path.isfile(fp):
                        stat = os.stat(fp)
                        files_list.append({
                            "name": f"{arch_folder}/{fname}",
                            "owner": arch_folder.split("_")[0],
                            "size": format_bytes(stat.st_size),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                        })
    else:
        default_owner = (
            resolved_scope.split(":", 1)[1] if resolved_scope.startswith("user:")
            else ("shared" if resolved_scope == "public" else username)
        )
        for name in sorted(os.listdir(target_dir)):
            fp = os.path.join(target_dir, name)
            if os.path.isfile(fp):
                stat = os.stat(fp)
                owner = owners.get(name, default_owner) if resolved_scope == "public" else default_owner
                files_list.append({
                    "name": name,
                    "owner": owner,
                    "size": format_bytes(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                })

    return jsonify({
        "used_space": format_bytes(used_bytes),
        "quota_limit": limit_label,
        "space_percent": space_pct,
        "transfer_used": format_bytes(used_transfer),
        "transfer_limit": "600.0 MB",
        "transfer_percent": transfer_pct,
        "files": files_list
    })


@app.route("/upload", methods=["POST"])
@login_required()
def upload():
    u = request.current_user
    username = u["username"]
    is_admin = bool(u["is_admin"])
    scope = request.args.get("scope", "private")

    if scope == "archive":
        return jsonify({"error": "Cannot upload directly into archived folders."}), 400

    target_dir, resolved_scope = resolve_scope_folder(scope, username, is_admin)

    if "file" not in request.files:
        return jsonify({"error": "No file selected."}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    f.seek(0, os.SEEK_END)
    file_size = f.tell()
    f.seek(0)

    # Check total 1.50 GB drive limit
    if get_folder_size(STORAGE_DIR) + file_size > TOTAL_DRIVE_BYTES:
        return jsonify({"error": "Exceeds total 1.50 GB drive capacity."}), 413

    # Check 30.0 MB combined user quota (private + public) for non-admin users
    if not is_admin:
        if get_user_combined_used(username) + file_size > USER_QUOTA_BYTES:
            return jsonify({"error": "Exceeds your 30.0 MB personal + public storage limit."}), 413

    # Check 600.0 MB monthly bandwidth limit
    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return jsonify({"error": "Exceeds 600.0 MB monthly bandwidth limit."}), 429

    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error": "Invalid filename."}), 400

    f.save(os.path.join(target_dir, filename))
    add_transfer_bytes(file_size)

    if resolved_scope == "public":
        owners = load_public_owners()
        owners[filename] = username
        save_public_owners(owners)

    return jsonify({"status": "ok", "file": filename}), 201


def _resolve_file_for_read_or_delete(filename, scope, username, is_admin):
    target_dir, resolved_scope = resolve_scope_folder(scope, username, is_admin)
    if resolved_scope == "archive":
        parts = filename.split("/", 1)
        if len(parts) != 2:
            return None, None, resolved_scope
        arch_dir = secure_filename(parts[0])
        safe_name = secure_filename(parts[1])
        fp = os.path.abspath(os.path.join(ARCHIVE_DIR, arch_dir, safe_name))
        if not fp.startswith(os.path.abspath(ARCHIVE_DIR) + os.sep):
            return None, None, resolved_scope
        return os.path.dirname(fp), os.path.basename(fp), resolved_scope

    safe_name = secure_filename(filename)
    fp = os.path.abspath(os.path.join(target_dir, safe_name))
    if not fp.startswith(os.path.abspath(target_dir) + os.sep):
        return None, None, resolved_scope
    return target_dir, safe_name, resolved_scope


@app.route("/view/<path:filename>")
@login_required()
def view_file(filename):
    u = request.current_user
    scope = request.args.get("scope", "private")
    folder, safe_name, _ = _resolve_file_for_read_or_delete(filename, scope, u["username"], bool(u["is_admin"]))
    if not folder or not safe_name or not os.path.isfile(os.path.join(folder, safe_name)):
        return "File not found", 404

    fp = os.path.join(folder, safe_name)
    file_size = os.path.getsize(fp)
    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return "Monthly 600.0 MB transfer limit reached.", 429
    add_transfer_bytes(file_size)
    return send_from_directory(folder, safe_name, as_attachment=False)


@app.route("/download/<path:filename>")
@login_required()
def download_file(filename):
    u = request.current_user
    scope = request.args.get("scope", "private")
    folder, safe_name, _ = _resolve_file_for_read_or_delete(filename, scope, u["username"], bool(u["is_admin"]))
    if not folder or not safe_name or not os.path.isfile(os.path.join(folder, safe_name)):
        return "File not found", 404

    fp = os.path.join(folder, safe_name)
    file_size = os.path.getsize(fp)
    if get_transfer_bytes() + file_size > MAX_TRANSFER_BYTES:
        return "Monthly 600.0 MB transfer limit reached.", 429
    add_transfer_bytes(file_size)
    return send_from_directory(folder, safe_name, as_attachment=True)


@app.route("/delete/<path:filename>", methods=["POST"])
@login_required()
def delete_file(filename):
    u = request.current_user
    is_admin = bool(u["is_admin"])
    scope = request.args.get("scope", "private")

    if scope == "public" and not is_admin:
        return jsonify({"error": "Only the Administrator can delete files in the Public Shared Folder."}), 403

    folder, safe_name, resolved_scope = _resolve_file_for_read_or_delete(filename, scope, u["username"], is_admin)
    if not folder or not safe_name:
        return jsonify({"error": "Invalid file path."}), 400

    fp = os.path.join(folder, safe_name)
    if os.path.isfile(fp):
        os.remove(fp)
        if resolved_scope == "public":
            owners = load_public_owners()
            if safe_name in owners:
                owners.pop(safe_name, None)
                save_public_owners(owners)
        return jsonify({"status": "deleted"}), 200
    return jsonify({"error": "File not found"}), 404


# ================= ADMIN USER MANAGEMENT API =================

@app.route("/api/admin/users")
@login_required(admin_only=True)
def admin_list_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY is_admin DESC, id DESC").fetchall()
    conn.close()

    users = []
    for r in rows:
        is_adm = bool(r["is_admin"])
        used = get_folder_size(STORAGE_DIR) if is_adm else get_user_combined_used(r["username"])
        users.append({
            "id": r["id"],
            "username": r["username"],
            "email": r["email"],
            "created_at": r["created_at"],
            "used_space": format_bytes(used),
            "quota_limit": "1.50 GB" if is_adm else "30.0 MB",
            "is_approved": bool(r["is_approved"]),
            "is_admin": is_adm
        })
    return jsonify({"users": users})


@app.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required(admin_only=True)
def admin_toggle_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or user["is_admin"]:
        conn.close()
        return jsonify({"error": "Cannot modify this account."}), 400

    new_status = 0 if user["is_approved"] else 1
    conn.execute("UPDATE users SET is_approved = ? WHERE id = ?", (new_status, user_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated", "is_approved": bool(new_status)})


@app.route("/api/admin/users/<int:user_id>/reset-2fa", methods=["POST"])
@login_required(admin_only=True)
def admin_reset_2fa(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or user["is_admin"]:
        conn.close()
        return jsonify({"error": "Cannot reset 2FA for this account."}), 400

    new_secret = pyotp.random_base32()
    conn.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (new_secret, user_id))
    conn.commit()
    conn.close()

    qr_uri = make_qr_data_uri(user["username"], new_secret)
    return jsonify({
        "username": user["username"],
        "totp_secret": new_secret,
        "qr_uri": qr_uri
    })


@app.route("/api/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required(admin_only=True)
def admin_delete_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or user["is_admin"]:
        conn.close()
        return jsonify({"error": "Cannot delete this account."}), 400

    uname = user["username"]
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Move user's private folder into /app/storage/archive/<username>_<timestamp>
    user_folder = os.path.join(USERS_DIR, uname)
    if os.path.isdir(user_folder):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_folder = os.path.join(ARCHIVE_DIR, f"{uname}_{stamp}")
        shutil.move(user_folder, dest_folder)

    return jsonify({"status": "archived_and_deleted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
