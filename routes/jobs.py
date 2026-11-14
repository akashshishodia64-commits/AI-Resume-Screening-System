"""Job description management (create, list, edit, delete)."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from models.database import get_db, loads
from modules import services
from .helpers import login_required

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@bp.route("")
@login_required
def index():
    rows = get_db().execute(
        "SELECT j.*, COUNT(m.id) AS match_count, ROUND(AVG(m.overall_score), 1) AS avg_score"
        " FROM job_descriptions j LEFT JOIN matching_results m ON m.job_id = j.id"
        " WHERE j.user_id = ? GROUP BY j.id ORDER BY j.id DESC", (g.user["id"],)).fetchall()
    jobs = [{**dict(r), "skills": loads(r["required_skills_json"])} for r in rows]
    return render_template("jobs.html", jobs=jobs)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        clean, errors = services.validate_job_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("job_form.html", job=None, form=request.form), 400
        services.create_job(get_db(), g.user["id"], clean)
        flash("Job created." + (" Required skills were auto-detected from the description." if clean["auto_detected"] else ""),
              "success")
        return redirect(url_for("jobs.index"))
    return render_template("job_form.html", job=None, form={})


@bp.route("/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def edit(job_id):
    db = get_db()
    job = services.get_job(db, g.user["id"], job_id)
    if job is None:
        abort(404)
    if request.method == "POST":
        clean, errors = services.validate_job_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("job_form.html", job=job, form=request.form), 400
        services.update_job(db, g.user["id"], job_id, clean)
        flash("Job updated. Previous match results for it were cleared - run matching again.", "success")
        return redirect(url_for("jobs.index"))
    form = {"title": job["title"], "description": job["description"],
            "required_skills": ", ".join(job["required_skills"]),
            "min_experience_years": f"{job['min_experience_years']:g}",
            "education_requirement": job["education_requirement"] or ""}
    return render_template("job_form.html", job=job, form=form)


@bp.route("/<int:job_id>/delete", methods=["POST"])
@login_required
def delete(job_id):
    if services.delete_job(get_db(), g.user["id"], job_id):
        flash("Job deleted along with its match results.", "success")
        return redirect(url_for("jobs.index"))
    abort(404)
