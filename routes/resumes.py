"""Resume upload, analysis views, original-file download, deletion."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_from_directory, url_for

from models.database import get_db, loads
from modules import services
from .helpers import login_required, owned_or_404

bp = Blueprint("resumes", __name__)


def _upload_opts():
    c = current_app.config
    return {"allowed": tuple(c["ALLOWED_EXTENSIONS"]), "max_size": c["MAX_FILE_SIZE"], "min_chars": c["MIN_TEXT_CHARS"]}


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    results = None
    if request.method == "POST":
        files = [f for f in request.files.getlist("resumes") if f and f.filename]
        limit = current_app.config["MAX_FILES_PER_UPLOAD"]
        if not files:
            flash("Choose at least one PDF or DOCX file.", "danger")
        elif len(files) > limit:
            flash(f"Please upload at most {limit} files at a time.", "danger")
        else:
            opts = _upload_opts()
            results = []
            for f in files:
                data = f.stream.read(opts["max_size"] + 1)
                results.append(services.save_resume(get_db(), g.user["id"], f.filename, data,
                                                    current_app.config["UPLOAD_FOLDER"], **opts))
            ok = sum(r["ok"] for r in results)
            flash(f"{ok} of {len(results)} file(s) analysed successfully.", "success" if ok else "danger")
    return render_template("upload.html", results=results,
                           max_mb=current_app.config["MAX_FILE_SIZE"] // 1024 // 1024,
                           limit=current_app.config["MAX_FILES_PER_UPLOAD"])


@bp.route("/resumes")
@login_required
def index():
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT r.id, r.original_filename, r.file_ext, r.file_size, r.uploaded_at, c.name, c.email,"
           " a.total_experience_years, a.highest_education,"
           " (SELECT COUNT(*) FROM extracted_skills s WHERE s.resume_id = r.id) AS skill_count,"
           " (SELECT MAX(overall_score) FROM matching_results m WHERE m.resume_id = r.id) AS best_score"
           " FROM resumes r JOIN candidates c ON c.resume_id = r.id JOIN resume_analysis a ON a.resume_id = r.id"
           " WHERE r.user_id = ?")
    args = [g.user["id"]]
    if q:
        like = "%" + q.replace("%", "").replace("_", "") + "%"
        sql += (" AND (c.name LIKE ? OR r.original_filename LIKE ? OR EXISTS ("
                "SELECT 1 FROM extracted_skills s WHERE s.resume_id = r.id AND s.skill LIKE ?))")
        args += [like, like, like]
    rows = get_db().execute(sql + " ORDER BY r.id DESC", args).fetchall()
    return render_template("resumes.html", resumes=rows, q=q)


@bp.route("/resumes/<int:resume_id>")
@login_required
def detail(resume_id):
    db = get_db()
    row = owned_or_404(db.execute(
        "SELECT r.*, c.name, c.email, c.phone, a.* FROM resumes r JOIN candidates c ON c.resume_id = r.id"
        " JOIN resume_analysis a ON a.resume_id = r.id WHERE r.id = ? AND r.user_id = ?",
        (resume_id, g.user["id"])).fetchone())
    skills = db.execute("SELECT skill, category, mentions FROM extracted_skills WHERE resume_id = ?"
                        " ORDER BY category, mentions DESC, skill", (resume_id,)).fetchall()
    by_category = {}
    for s in skills:
        by_category.setdefault(s["category"], []).append(s)
    matches = [services.decode_match(m) for m in db.execute(
        "SELECT m.*, j.title AS job_title FROM matching_results m JOIN job_descriptions j ON j.id = m.job_id"
        " WHERE m.resume_id = ? AND m.user_id = ? ORDER BY m.overall_score DESC", (resume_id, g.user["id"])).fetchall()]
    analysis = {k: loads(row[k + "_json"]) for k in ("education", "experience", "projects", "certifications", "keywords")}
    return render_template("analysis.html", resume=row, analysis=analysis, by_category=by_category,
                           skill_total=len(skills), matches=matches)


@bp.route("/resumes/<int:resume_id>/file")
@login_required
def download(resume_id):
    row = owned_or_404(get_db().execute(
        "SELECT original_filename, stored_filename FROM resumes WHERE id = ? AND user_id = ?",
        (resume_id, g.user["id"])).fetchone())
    folder = f"{current_app.config['UPLOAD_FOLDER']}/{g.user['id']}"
    return send_from_directory(folder, row["stored_filename"], as_attachment=True, download_name=row["original_filename"])


@bp.route("/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete(resume_id):
    if services.delete_resume(get_db(), g.user["id"], resume_id, current_app.config["UPLOAD_FOLDER"]):
        flash("Resume deleted.", "success")
        return redirect(url_for("resumes.index"))
    abort(404)
