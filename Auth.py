"""
Auth.py - login / register backend for the Drukyul Dynamic Portfolio.

Put this file in the same folder as app.py (the Streamlit dashboard).
    pip install -r requirements.txt
    python Auth.py                      -> website + login on http://127.0.0.1:5000
    python -m streamlit run app.py      -> dashboard on http://localhost:8501

After login, the website asks /api/dashboard-link for a 5-minute sign-in link.
auth_gate.py (used by app.py) checks that link with the same secret key.
"""
import os
import re
import secrets
import sqlite3
from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "drukyul.db")
TOKEN_MAX_AGE = 60 * 60 * 24 * 7   # website login: 7 days
DASH_TOKEN_MAX_AGE = 300           # dashboard hand-off link: 5 minutes
SITE_URL = os.environ.get("DRUKYUL_SITE_URL", "http://127.0.0.1:5000")
DASHBOARD_URL = os.environ.get("DRUKYUL_DASHBOARD_URL", "http://localhost:8501")


def load_secret():
    """Use DRUKYUL_SECRET if set, otherwise create and reuse a local .auth_secret file."""
    env = os.environ.get("DRUKYUL_SECRET")
    if env:
        return env
    path = os.path.join(BASE, ".auth_secret")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    value = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)
    return value


SECRET = load_secret()
app = Flask(__name__)
serializer = URLSafeTimedSerializer(SECRET)
dash_serializer = URLSafeTimedSerializer(SECRET, salt="dashboard")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS guestbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


def user_from_dashboard_token(token):
    """Used by auth_gate.py in the Streamlit dashboard. Returns {'name','email'} or None."""
    try:
        uid = dash_serializer.loads(token, max_age=DASH_TOKEN_MAX_AGE)["uid"]
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return None
    db = sqlite3.connect(DB_PATH)
    try:
        row = db.execute("SELECT name, email FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        db.close()
    return {"name": row[0], "email": row[1]} if row else None


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        uid = serializer.loads(header[7:], max_age=TOKEN_MAX_AGE)["uid"]
    except (BadSignature, SignatureExpired):
        return None
    return get_db().execute("SELECT id, name, email FROM users WHERE id = ?", (uid,)).fetchone()


def error(msg, code=400):
    return jsonify(error=msg), code


@app.route("/")
def home():
    return send_from_directory(BASE, "index.html")


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if len(name) < 2:
        return error("Please enter your name.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return error("Please enter a valid email address.")
    if len(password) < 6:
        return error("Password must be at least 6 characters.")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return error("That email is already registered. Try logging in.", 409)
    cur = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    db.commit()
    token = serializer.dumps({"uid": cur.lastrowid})
    return jsonify(token=token, user={"name": name, "email": email}), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return error("Email or password is incorrect.", 401)
    token = serializer.dumps({"uid": user["id"]})
    return jsonify(token=token, user={"name": user["name"], "email": user["email"]})


@app.get("/api/me")
def me():
    user = current_user()
    if not user:
        return error("Not logged in.", 401)
    return jsonify(user={"name": user["name"], "email": user["email"]})


@app.get("/api/dashboard-link")
def dashboard_link():
    user = current_user()
    if not user:
        return error("Please log in to open the dashboard.", 401)
    token = dash_serializer.dumps({"uid": user["id"]})
    return jsonify(url=f"{DASHBOARD_URL}/?token={token}")


@app.get("/api/guestbook")
def guestbook_list():
    rows = get_db().execute(
        """SELECT g.message, g.created_at, u.name FROM guestbook g
           JOIN users u ON u.id = g.user_id ORDER BY g.id DESC LIMIT 30"""
    ).fetchall()
    return jsonify(entries=[dict(r) for r in rows])


@app.post("/api/guestbook")
def guestbook_add():
    user = current_user()
    if not user:
        return error("Please log in to sign the guestbook.", 401)
    message = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not 2 <= len(message) <= 280:
        return error("Message must be 2 to 280 characters.")
    db = get_db()
    db.execute("INSERT INTO guestbook (user_id, message) VALUES (?, ?)", (user["id"], message))
    db.commit()
    return jsonify(ok=True), 201


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("DRUKYUL_DEBUG") == "1")
