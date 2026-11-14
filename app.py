"""AI-Powered Resume Screening & Job Matching System - Flask application factory.

Run:  python app.py        (development server on http://127.0.0.1:5000)
"""
import json
import secrets
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request, session

from config import Config
from models import database
from modules.matching_engine import score_band


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    database.init_db(app.config["DATABASE"])
    database.init_app(app)

    from routes import auth, dashboard, jobs, matching, reports, resumes, settings
    for module in (auth, dashboard, resumes, jobs, matching, reports, settings):
        app.register_blueprint(module.bp)

    @app.before_request
    def load_user():
        user_id = session.get("user_id")
        g.user = None
        if user_id is not None:
            g.user = database.get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if g.user is None:
                session.clear()

    @app.before_request
    def csrf_protect():
        if not app.config.get("CSRF_ENABLED", True) or request.method in ("GET", "HEAD", "OPTIONS"):
            return
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        expected = session.get("csrf_token")
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            abort(400, description="Your session expired or the form was tampered with. Please reload the page and try again.")

    @app.context_processor
    def inject_globals():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return {"csrf_token": session["csrf_token"], "theme": (g.user["theme"] if g.get("user") else "dark")}

    @app.template_filter("band")
    def band_filter(score):
        return score_band(score or 0)[0]

    @app.template_filter("band_css")
    def band_css_filter(score):
        return score_band(score or 0)[1]

    @app.template_filter("filesize")
    def filesize_filter(n):
        return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"

    @app.template_filter("pct")
    def pct_filter(value, digits=1):
        return "-" if value is None else f"{value:.{digits}f}%"

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
        if g.get("user"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def _error(code, title, message):
        if request.path.startswith("/settings/theme"):
            return jsonify(error=message), code
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(e):
        return _error(400, "Bad request", getattr(e, "description", None) or "The request could not be processed.")

    @app.errorhandler(404)
    def not_found(_e):
        return _error(404, "Not found", "That page or record does not exist (or it belongs to another account).")

    @app.errorhandler(413)
    def too_large(_e):
        return _error(413, "Upload too large", "The upload exceeds the size limit. Try fewer or smaller files.")

    @app.errorhandler(500)
    def server_error(_e):
        return _error(500, "Something went wrong", "An unexpected error occurred. Nothing was lost; please try again.")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
