"""PDF / CSV exports. Everything is scoped to the signed-in user."""
from flask import Blueprint, Response, abort, g, render_template

from models.database import get_db, loads
from modules import report_generator, services
from .helpers import login_required

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _csv(text, filename):
    return Response("\ufeff" + text, mimetype="text/csv",  # BOM so Excel opens UTF-8 correctly
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf(data, filename):
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.route("")
@login_required
def index():
    db = get_db()
    jobs = db.execute(
        "SELECT j.id, j.title, COUNT(m.id) AS n FROM job_descriptions j LEFT JOIN matching_results m ON m.job_id = j.id"
        " WHERE j.user_id = ? GROUP BY j.id ORDER BY j.id DESC", (g.user["id"],)).fetchall()
    resumes = db.execute(
        "SELECT r.id, c.name, r.original_filename FROM resumes r JOIN candidates c ON c.resume_id = r.id"
        " WHERE r.user_id = ? ORDER BY c.name", (g.user["id"],)).fetchall()
    total_matches = db.execute("SELECT COUNT(*) FROM matching_results WHERE user_id = ?", (g.user["id"],)).fetchone()[0]
    return render_template("reports.html", jobs=jobs, resumes=resumes, total_matches=total_matches)


@bp.route("/resume/<int:resume_id>.pdf")
@login_required
def resume_pdf(resume_id):
    db = get_db()
    row = db.execute(
        "SELECT r.original_filename, c.name, c.email, c.phone, a.* FROM resumes r"
        " JOIN candidates c ON c.resume_id = r.id JOIN resume_analysis a ON a.resume_id = r.id"
        " WHERE r.id = ? AND r.user_id = ?", (resume_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    analysis = {k: loads(row[k + "_json"]) for k in ("education", "experience", "projects", "certifications", "keywords")}
    analysis.update(total_experience_years=row["total_experience_years"], word_count=row["word_count"],
                    highest_education=row["highest_education"])
    skills = db.execute("SELECT skill, category, mentions FROM extracted_skills WHERE resume_id = ?"
                        " ORDER BY category, mentions DESC", (resume_id,)).fetchall()
    matches = [services.decode_match(m) for m in db.execute(
        "SELECT m.*, j.title AS job_title FROM matching_results m JOIN job_descriptions j ON j.id = m.job_id"
        " WHERE m.resume_id = ? AND m.user_id = ? ORDER BY m.overall_score DESC", (resume_id, g.user["id"])).fetchall()]
    pdf = report_generator.candidate_report_pdf(row, row, analysis, [dict(s) for s in skills], matches)
    return _pdf(pdf, f"candidate_report_{resume_id}.pdf")


def _ranking_or_404(job_id):
    db = get_db()
    job = services.get_job(db, g.user["id"], job_id)
    if job is None:
        abort(404)
    return job, services.get_ranking(db, g.user["id"], job_id)


@bp.route("/ranking/<int:job_id>.csv")
@login_required
def ranking_csv(job_id):
    _job, results = _ranking_or_404(job_id)
    return _csv(report_generator.ranking_csv(results), f"ranking_job_{job_id}.csv")


@bp.route("/ranking/<int:job_id>.pdf")
@login_required
def ranking_pdf(job_id):
    job, results = _ranking_or_404(job_id)
    return _pdf(report_generator.ranking_pdf(job, results), f"ranking_job_{job_id}.pdf")


@bp.route("/matching.csv")
@login_required
def matching_csv():
    return _csv(report_generator.matching_csv(services.all_match_results(get_db(), g.user["id"])), "matching_results.csv")
