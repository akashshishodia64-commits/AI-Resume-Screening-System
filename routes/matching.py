"""Resume matching, candidate ranking, skill-gap analysis."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from models.database import get_db
from modules import matching_engine, services
from modules.skill_gap import analyze_skill_gap
from .helpers import login_required, safe_next

bp = Blueprint("matching", __name__)


def _jobs(db):
    return db.execute("SELECT id, title, required_skills_json FROM job_descriptions WHERE user_id = ? ORDER BY id DESC",
                      (g.user["id"],)).fetchall()


def _resumes(db):
    return db.execute("SELECT r.id, c.name, r.original_filename FROM resumes r JOIN candidates c ON c.resume_id = r.id"
                      " WHERE r.user_id = ? ORDER BY c.name", (g.user["id"],)).fetchall()


@bp.route("/matching")
@login_required
def index():
    db = get_db()
    recent = [services.decode_match(r) for r in db.execute(
        "SELECT m.*, c.name AS candidate_name, j.title AS job_title FROM matching_results m"
        " JOIN candidates c ON c.resume_id = m.resume_id JOIN job_descriptions j ON j.id = m.job_id"
        " WHERE m.user_id = ? ORDER BY m.created_at DESC, m.id DESC LIMIT 15", (g.user["id"],)).fetchall()]
    return render_template("matching.html", jobs=_jobs(db), resumes=_resumes(db), recent=recent,
                           disclaimer=matching_engine.DISCLAIMER,
                           weights=services.user_weights(g.user, current_app.config["DEFAULT_WEIGHTS"]),
                           selected_job=request.args.get("job_id", type=int))


@bp.route("/matching/run", methods=["POST"])
@login_required
def run():
    db = get_db()
    job_id = request.form.get("job_id", type=int)
    resume_ids = request.form.getlist("resume_ids", type=int)
    if not job_id:
        flash("Select a job first.", "danger")
        return redirect(url_for("matching.index"))
    try:
        count = services.run_matching(db, g.user, job_id, resume_ids or None, current_app.config["DEFAULT_WEIGHTS"])
    except LookupError as exc:
        flash(str(exc) + (" Upload resumes first." if "resumes" in str(exc) else ""), "danger")
        return redirect(url_for("matching.index"))
    flash(f"Matched {count} resume(s). Scores show text similarity - review candidates manually.", "success")
    return redirect(url_for("matching.ranking", job_id=job_id))


@bp.route("/matching/result/<int:match_id>")
@login_required
def result(match_id):
    match = services.get_match(get_db(), g.user["id"], match_id)
    if match is None:
        abort(404)
    return render_template("match_detail.html", m=match, disclaimer=matching_engine.DISCLAIMER)


@bp.route("/ranking")
@login_required
def ranking():
    db = get_db()
    jobs = _jobs(db)
    job_id = request.args.get("job_id", type=int)
    if job_id is None and jobs:
        with_results = db.execute(
            "SELECT job_id FROM matching_results WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (g.user["id"],)).fetchone()
        job_id = with_results["job_id"] if with_results else jobs[0]["id"]
    job = services.get_job(db, g.user["id"], job_id) if job_id else None
    if job_id and job is None:
        abort(404)
    filters = {"min_score": request.args.get("min_score", default=0, type=float) or 0,
               "skill": (request.args.get("skill") or "").strip(),
               "q": (request.args.get("q") or "").strip(),
               "sort": request.args.get("sort", "score")}
    results, total = [], 0
    if job:
        total = db.execute("SELECT COUNT(*) FROM matching_results WHERE job_id = ? AND user_id = ?",
                           (job_id, g.user["id"])).fetchone()[0]
        results = services.get_ranking(db, g.user["id"], job_id, filters["min_score"], filters["skill"],
                                       filters["q"], filters["sort"])
    chart = {"type": "bar", "horizontal": True, "label": "Similarity score (%)",
             "labels": [r["candidate_name"] for r in results[:10]],
             "values": [r["overall_score"] for r in results[:10]], "max": 100}
    return render_template("ranking.html", jobs=jobs, job=job, results=results, total=total, filters=filters,
                           chart=chart, disclaimer=matching_engine.DISCLAIMER)


@bp.route("/ranking/flag/<int:match_id>", methods=["POST"])
@login_required
def flag(match_id):
    db = get_db()
    cur = db.execute("UPDATE matching_results SET is_shortlisted = 1 - is_shortlisted WHERE id = ? AND user_id = ?",
                     (match_id, g.user["id"]))
    db.commit()
    if not cur.rowcount:
        abort(404)
    return redirect(safe_next(request.form.get("next")))


@bp.route("/skill-gap")
@login_required
def skill_gap():
    db = get_db()
    resumes, jobs = _resumes(db), _jobs(db)
    resume_id = request.args.get("resume_id", type=int)
    job_id = request.args.get("job_id", type=int)
    gap = resume = job = None
    if resume_id and job_id:
        job = services.get_job(db, g.user["id"], job_id)
        bundles = services.load_resume_bundles(db, g.user["id"], [resume_id])
        if job is None or not bundles:
            abort(404)
        resume = bundles[0]
        gap = analyze_skill_gap(job["required_skills"], resume["raw_text"], resume["skills"])
    return render_template("skillgap.html", resumes=resumes, jobs=jobs, gap=gap, resume=resume, job=job,
                           resume_id=resume_id, job_id=job_id)
