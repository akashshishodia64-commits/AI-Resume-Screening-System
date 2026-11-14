"""Account settings, matching weights, theme, demo data, workspace reset."""
from pathlib import Path
import shutil

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models.database import dumps, get_db
from modules import services
from .helpers import login_required

bp = Blueprint("settings", __name__, url_prefix="/settings")
WEIGHT_LABELS = {"skills": "Required-skill match", "tfidf": "TF-IDF text similarity",
                 "keywords": "Keyword overlap", "experience": "Experience fit"}


@bp.route("", methods=["GET", "POST"])
@login_required
def index():
    db = get_db()
    defaults = current_app.config["DEFAULT_WEIGHTS"]
    if request.method == "POST":
        name = (request.form.get("full_name") or "").strip()[:80]
        theme = request.form.get("theme") if request.form.get("theme") in ("dark", "light") else g.user["theme"]
        weights, errors = {}, []
        for key in defaults:
            try:
                value = float(request.form.get(f"w_{key}", defaults[key] * 100))
                if not 0 <= value <= 100:
                    raise ValueError
                weights[key] = value / 100
            except ValueError:
                errors.append(f"Weight for {WEIGHT_LABELS[key]} must be between 0 and 100.")
        if not errors and sum(weights.values()) <= 0:
            errors.append("At least one weight must be above zero.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute("UPDATE users SET full_name = ?, theme = ?, weights_json = ? WHERE id = ?",
                       (name or g.user["username"], theme, dumps(weights), g.user["id"]))
            db.commit()
            flash("Settings saved. Re-run matching to apply new weights to existing results.", "success")
            return redirect(url_for("settings.index"))
    return render_template("settings.html", weights=services.user_weights(g.user, defaults),
                           labels=WEIGHT_LABELS, defaults=defaults)


@bp.route("/theme", methods=["POST"])
@login_required
def theme():
    value = request.form.get("theme")
    if value not in ("dark", "light"):
        return jsonify(error="invalid theme"), 400
    get_db().execute("UPDATE users SET theme = ? WHERE id = ?", (value, g.user["id"]))
    get_db().commit()
    return jsonify(theme=value)


@bp.route("/password", methods=["POST"])
@login_required
def password():
    current, new = request.form.get("current_password") or "", request.form.get("new_password") or ""
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if not check_password_hash(g.user["password_hash"], current):
        flash("Current password is incorrect.", "danger")
    elif len(new) < minimum or not (any(c.isalpha() for c in new) and any(c.isdigit() for c in new)):
        flash(f"New password needs at least {minimum} characters with letters and numbers.", "danger")
    elif new != request.form.get("confirm_password"):
        flash("New passwords do not match.", "danger")
    else:
        get_db().execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), g.user["id"]))
        get_db().commit()
        flash("Password updated.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/demo-data", methods=["POST"])
@login_required
def demo_data():
    c = current_app.config
    counts = services.load_demo_data(
        get_db(), g.user, c["UPLOAD_FOLDER"], c["SAMPLE_DATA_DIR"], default_weights=c["DEFAULT_WEIGHTS"],
        allowed=tuple(c["ALLOWED_EXTENSIONS"]), max_size=c["MAX_FILE_SIZE"], min_chars=c["MIN_TEXT_CHARS"])
    flash(f"Loaded synthetic sample data: {counts['resumes']} resumes, {counts['jobs']} jobs, "
          f"{counts['matches']} match results ({counts['skipped']} already present).", "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/reset", methods=["POST"])
@login_required
def reset():
    if (request.form.get("confirm") or "").strip().upper() != "DELETE":
        flash("Type DELETE to confirm resetting your workspace.", "danger")
        return redirect(url_for("settings.index"))
    db = get_db()
    db.execute("DELETE FROM resumes WHERE user_id = ?", (g.user["id"],))      # cascades to analysis/skills/matches
    db.execute("DELETE FROM job_descriptions WHERE user_id = ?", (g.user["id"],))
    db.commit()
    shutil.rmtree(Path(current_app.config["UPLOAD_FOLDER"]) / str(g.user["id"]), ignore_errors=True)
    flash("Workspace reset: all your resumes, jobs and results were deleted.", "success")
    return redirect(url_for("dashboard.index"))
