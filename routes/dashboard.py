"""Dashboard: all numbers come from the database."""
from flask import Blueprint, g, render_template

from models.database import get_db
from modules import services
from .helpers import login_required

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@bp.route("/dashboard")
@login_required
def index():
    stats = services.dashboard_stats(get_db(), g.user["id"])
    charts = {
        "skills": {"type": "bar", "horizontal": True, "label": "Resumes mentioning skill",
                   "labels": [s["skill"] for s in stats["skills"]], "values": [s["n"] for s in stats["skills"]]},
        "categories": {"type": "doughnut", "labels": [c["category"] for c in stats["categories"]],
                       "values": [c["n"] for c in stats["categories"]]},
        "bands": {"type": "doughnut", "labels": ["Strong (70+)", "Moderate (50-69)", "Partial (30-49)", "Low (<30)"],
                  "values": [stats["bands"]["strong"], stats["bands"]["moderate"],
                             stats["bands"]["partial"], stats["bands"]["low"]]},
        "jobs": {"type": "bar", "labels": [j["title"] for j in stats["jobs"] if j["n"]],
                 "datasets": [
                     {"label": "Average score", "values": [j["avg_score"] for j in stats["jobs"] if j["n"]]},
                     {"label": "Top score", "values": [j["top_score"] for j in stats["jobs"] if j["n"]]}]},
    }
    return render_template("dashboard.html", stats=stats, charts=charts)
