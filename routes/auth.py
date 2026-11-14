"""Registration, login, logout."""
import re
import time

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models.database import get_db
from .helpers import safe_next

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")
_FAILED = {}                 # (ip, username) -> [timestamps]; in-memory throttle for a single-process dev server
MAX_ATTEMPTS, WINDOW = 5, 300


def _throttled(key):
    now = time.time()
    attempts = [t for t in _FAILED.get(key, []) if now - t < WINDOW]
    _FAILED[key] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def validate_registration(form, min_len=8):
    errors = []
    username = (form.get("username") or "").strip()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    if not USERNAME_RE.match(username):
        errors.append("Username must be 3-30 characters: letters, numbers, dot, dash or underscore.")
    if not EMAIL_RE.match(email) or len(email) > 120:
        errors.append("Enter a valid email address.")
    if len(password) < min_len:
        errors.append(f"Password must be at least {min_len} characters.")
    elif not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors.append("Password must contain both letters and numbers.")
    if password != (form.get("confirm_password") or ""):
        errors.append("Passwords do not match.")
    return {"username": username, "email": email, "password": password}, errors


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        data, errors = validate_registration(request.form, current_app.config["MIN_PASSWORD_LENGTH"])
        db = get_db()
        if not errors:
            clash = db.execute("SELECT 1 FROM users WHERE username = ? OR email = ?",
                               (data["username"], data["email"])).fetchone()
            if clash:
                errors.append("That username or email is already registered.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form), 400
        cur = db.execute("INSERT INTO users (username, email, password_hash, full_name) VALUES (?, ?, ?, ?)",
                         (data["username"], data["email"], generate_password_hash(data["password"]), data["username"]))
        db.commit()
        session.clear()
        session["user_id"] = cur.lastrowid
        flash("Welcome! Your account is ready. Try 'Load sample data' in Settings for a quick demo.", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        identity = (request.form.get("identity") or "").strip()
        password = request.form.get("password") or ""
        key = (request.remote_addr, identity.lower())
        if _throttled(key):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return render_template("login.html", form=request.form), 429
        user = get_db().execute("SELECT * FROM users WHERE username = ? OR email = ?", (identity, identity)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            _FAILED.setdefault(key, []).append(time.time())
            flash("Invalid username/email or password.", "danger")
            return render_template("login.html", form=request.form), 401
        _FAILED.pop(key, None)
        session.clear()
        session["user_id"] = user["id"]
        return redirect(safe_next(request.args.get("next")))
    return render_template("login.html", form={})


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
