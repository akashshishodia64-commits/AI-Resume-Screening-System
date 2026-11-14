"""Application services: the glue between routes, the database and the NLP/ML modules.

Every function takes the DB connection explicitly and scopes data by user_id, so a user
can never read or modify another user's resumes, jobs or results.
"""
import hashlib
import json
import uuid
from pathlib import Path

from models.database import dumps, loads
from . import matching_engine, resume_analyzer, resume_parser
from .skill_extractor import extract_skills, parse_skill_list

# ----------------------------------------------------------------------------- settings


def user_weights(user_row, defaults=None):
    """Matching weights for a user: saved overrides on top of the defaults."""
    weights = dict(defaults or matching_engine.DEFAULT_WEIGHTS)
    saved = loads(user_row["weights_json"], default={}) if user_row is not None else {}
    if isinstance(saved, dict):
        weights.update({k: float(v) for k, v in saved.items() if k in weights})
    return weights


# ----------------------------------------------------------------------------- resumes


def save_resume(db, user_id, filename, data, upload_dir, *, allowed=("pdf", "docx"),
                max_size=5 * 1024 * 1024, min_chars=50):
    """Validate, store, parse and analyse one uploaded resume.

    Returns {'ok': bool, 'filename': str, 'message': str, 'resume_id': int|None}.
    A failed upload never leaves a file or half-written rows behind.
    """
    result = {"ok": False, "filename": filename or "(unnamed)", "message": "", "resume_id": None}
    try:
        ext = resume_parser.validate_upload(filename, data, allowed, max_size)
    except resume_parser.UploadValidationError as exc:
        result["message"] = str(exc)
        return result

    digest = hashlib.sha256(data).hexdigest()
    dup = db.execute("SELECT id FROM resumes WHERE user_id = ? AND file_hash = ?", (user_id, digest)).fetchone()
    if dup:
        result["message"] = "This exact file was already uploaded."
        result["resume_id"] = dup["id"]
        return result

    user_dir = Path(upload_dir) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = user_dir / stored
    path.write_bytes(data)

    try:
        text = resume_parser.extract_text(path, ext, min_chars=min_chars)
        info = resume_analyzer.analyze_resume(text, filename)
        cur = db.execute(
            "INSERT INTO resumes (user_id, original_filename, stored_filename, file_ext, file_size, file_hash, raw_text)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, filename, stored, ext, len(data), digest, text))
        resume_id = cur.lastrowid
        db.execute("INSERT INTO candidates (user_id, resume_id, name, email, phone) VALUES (?, ?, ?, ?, ?)",
                   (user_id, resume_id, info["name"], info["email"], info["phone"]))
        db.execute(
            "INSERT INTO resume_analysis (resume_id, education_json, experience_json, projects_json,"
            " certifications_json, keywords_json, total_experience_years, highest_education,"
            " highest_education_level, word_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (resume_id, dumps(info["education"]), dumps(info["experience"]), dumps(info["projects"]),
             dumps(info["certifications"]), dumps(info["keywords"]), info["total_experience_years"],
             info["highest_education"], info["highest_education_level"], info["word_count"]))
        db.executemany(
            "INSERT INTO extracted_skills (resume_id, skill, category, mentions) VALUES (?, ?, ?, ?)",
            [(resume_id, s["name"], s["category"], s["count"]) for s in info["skills"]])
        db.commit()
    except resume_parser.ResumeParseError as exc:
        db.rollback()
        path.unlink(missing_ok=True)
        result["message"] = str(exc)
        return result
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise

    result.update(ok=True, resume_id=resume_id,
                  message=f"Analysed: {info['name']} - {len(info['skills'])} skills detected.")
    return result


def delete_resume(db, user_id, resume_id, upload_dir):
    row = db.execute("SELECT stored_filename FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user_id)).fetchone()
    if row is None:
        return False
    db.execute("DELETE FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user_id))
    db.commit()
    (Path(upload_dir) / str(user_id) / row["stored_filename"]).unlink(missing_ok=True)
    return True


def load_resume_bundles(db, user_id, resume_ids=None):
    """Resumes joined with candidate + analysis + skill names, as plain dicts."""
    sql = ("SELECT r.id, r.original_filename, r.raw_text, r.uploaded_at, c.name, c.email, c.phone,"
           " a.total_experience_years, a.highest_education, a.highest_education_level"
           " FROM resumes r JOIN candidates c ON c.resume_id = r.id JOIN resume_analysis a ON a.resume_id = r.id"
           " WHERE r.user_id = ?")
    args = [user_id]
    if resume_ids is not None:
        resume_ids = [int(i) for i in resume_ids]
        if not resume_ids:
            return []
        sql += " AND r.id IN (" + ",".join("?" * len(resume_ids)) + ")"
        args += resume_ids
    rows = db.execute(sql + " ORDER BY r.id", args).fetchall()
    bundles = [dict(r) for r in rows]
    if bundles:
        ids = [b["id"] for b in bundles]
        skills = db.execute(
            "SELECT resume_id, skill FROM extracted_skills WHERE resume_id IN (" + ",".join("?" * len(ids)) + ")"
            " ORDER BY mentions DESC, skill", ids).fetchall()
        by_resume = {}
        for s in skills:
            by_resume.setdefault(s["resume_id"], []).append(s["skill"])
        for b in bundles:
            b["skills"] = by_resume.get(b["id"], [])
    return bundles


# ----------------------------------------------------------------------------- jobs


def validate_job_form(form):
    """Return (clean_dict, errors_list). Required skills are auto-detected if left blank."""
    errors = []
    title = (form.get("title") or "").strip()
    description = (form.get("description") or "").strip()
    education = (form.get("education_requirement") or "").strip()
    skills = parse_skill_list(form.get("required_skills") or "")
    auto_detected = False

    if not 3 <= len(title) <= 120:
        errors.append("Job title must be between 3 and 120 characters.")
    if len(description) < 30:
        errors.append("Job description must be at least 30 characters so matching has something to work with.")
    elif len(description) > 20000:
        errors.append("Job description is too long (20,000 character limit).")
    if len(education) > 200:
        errors.append("Education requirement is too long (200 character limit).")
    if len(skills) > 60:
        errors.append("Please list at most 60 required skills.")

    raw_exp = (form.get("min_experience_years") or "0").strip() or "0"
    try:
        min_exp = float(raw_exp)
        if not 0 <= min_exp <= 50:
            raise ValueError
    except ValueError:
        min_exp = 0.0
        errors.append("Minimum experience must be a number between 0 and 50.")

    if not skills and description and not errors:
        skills = [s["name"] for s in extract_skills(f"{title}\n{description}")][:25]
        auto_detected = bool(skills)

    clean = {"title": title, "description": description, "required_skills": skills,
             "min_experience_years": min_exp, "education_requirement": education or None,
             "auto_detected": auto_detected}
    return clean, errors


def create_job(db, user_id, clean):
    cur = db.execute(
        "INSERT INTO job_descriptions (user_id, title, description, required_skills_json, min_experience_years,"
        " education_requirement) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, clean["title"], clean["description"], dumps(clean["required_skills"]),
         clean["min_experience_years"], clean["education_requirement"]))
    db.commit()
    return cur.lastrowid


def update_job(db, user_id, job_id, clean):
    """Update a job. Stored matching results for it become stale, so they are removed."""
    cur = db.execute(
        "UPDATE job_descriptions SET title = ?, description = ?, required_skills_json = ?, min_experience_years = ?,"
        " education_requirement = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (clean["title"], clean["description"], dumps(clean["required_skills"]), clean["min_experience_years"],
         clean["education_requirement"], job_id, user_id))
    if cur.rowcount:
        db.execute("DELETE FROM matching_results WHERE job_id = ? AND user_id = ?", (job_id, user_id))
    db.commit()
    return bool(cur.rowcount)


def delete_job(db, user_id, job_id):
    cur = db.execute("DELETE FROM job_descriptions WHERE id = ? AND user_id = ?", (job_id, user_id))
    db.commit()
    return bool(cur.rowcount)


def job_to_dict(row):
    return {"id": row["id"], "title": row["title"], "description": row["description"],
            "required_skills": loads(row["required_skills_json"]),
            "min_experience_years": row["min_experience_years"] or 0,
            "education_requirement": row["education_requirement"]}


def get_job(db, user_id, job_id):
    row = db.execute("SELECT * FROM job_descriptions WHERE id = ? AND user_id = ?", (job_id, user_id)).fetchone()
    return job_to_dict(row) if row else None


# ----------------------------------------------------------------------------- matching


def run_matching(db, user, job_id, resume_ids=None, default_weights=None):
    """Match the chosen resumes (default: all) against one job and store the results.

    Returns the number of resumes scored. Raises LookupError for unknown jobs/resumes."""
    job = get_job(db, user["id"], job_id)
    if job is None:
        raise LookupError("Job not found.")
    everyone = load_resume_bundles(db, user["id"])
    targets = everyone if resume_ids is None else [r for r in everyone if r["id"] in {int(i) for i in resume_ids}]
    if not targets:
        raise LookupError("No resumes to match.")

    weights = user_weights(user, default_weights)
    results = matching_engine.match_resumes(job, targets, weights, corpus_texts=[r["raw_text"] for r in everyone])
    for resume, res in zip(targets, results):
        db.execute(
            "INSERT INTO matching_results (user_id, resume_id, job_id, overall_score, tfidf_score, skill_score,"
            " keyword_score, experience_score, education_met, matched_skills_json, missing_skills_json,"
            " keywords_json, strengths_json, gaps_json, recommendations_json, corpus_size)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(resume_id, job_id) DO UPDATE SET overall_score = excluded.overall_score,"
            " tfidf_score = excluded.tfidf_score, skill_score = excluded.skill_score,"
            " keyword_score = excluded.keyword_score, experience_score = excluded.experience_score,"
            " education_met = excluded.education_met, matched_skills_json = excluded.matched_skills_json,"
            " missing_skills_json = excluded.missing_skills_json, keywords_json = excluded.keywords_json,"
            " strengths_json = excluded.strengths_json, gaps_json = excluded.gaps_json,"
            " recommendations_json = excluded.recommendations_json, corpus_size = excluded.corpus_size,"
            " created_at = datetime('now')",
            (user["id"], resume["id"], job_id, res["overall_score"], res["tfidf_score"], res["skill_score"],
             res["keyword_score"], res["experience_score"], res["education_met"], dumps(res["matched_skills"]),
             dumps(res["missing_skills"]), dumps(res["keywords"]), dumps(res["strengths"]), dumps(res["gaps"]),
             dumps(res["recommendations"]), res["corpus_size"]))
    db.commit()
    return len(results)


def decode_match(row):
    """sqlite Row -> dict with JSON columns decoded."""
    d = dict(row)
    for key in ("matched_skills", "missing_skills", "keywords", "strengths", "gaps", "recommendations"):
        d[key] = loads(d.pop(key + "_json", None))
    return d


_MATCH_SELECT = (
    "SELECT m.*, c.name AS candidate_name, c.email AS candidate_email, c.phone AS candidate_phone,"
    " r.original_filename, a.total_experience_years, a.highest_education, j.title AS job_title"
    " FROM matching_results m"
    " JOIN resumes r ON r.id = m.resume_id JOIN candidates c ON c.resume_id = m.resume_id"
    " JOIN resume_analysis a ON a.resume_id = m.resume_id JOIN job_descriptions j ON j.id = m.job_id"
)


def get_match(db, user_id, match_id):
    row = db.execute(_MATCH_SELECT + " WHERE m.id = ? AND m.user_id = ?", (match_id, user_id)).fetchone()
    return decode_match(row) if row else None


def get_ranking(db, user_id, job_id, min_score=0.0, skill=None, search=None, sort="score"):
    """Ranked results for a job. Ranks are computed on the full pool, then filters are applied,
    so filtering never renumbers candidates."""
    rows = db.execute(_MATCH_SELECT + " WHERE m.job_id = ? AND m.user_id = ?", (job_id, user_id)).fetchall()
    ranked = matching_engine.rank_results([decode_match(r) for r in rows])
    if min_score:
        ranked = [r for r in ranked if r["overall_score"] >= min_score]
    if skill:
        wanted = {s.lower() for s in parse_skill_list(skill)}
        ranked = [r for r in ranked if wanted <= {s.lower() for s in r["matched_skills"]}]
    if search:
        needle = search.lower()
        ranked = [r for r in ranked if needle in r["candidate_name"].lower()]
    if sort == "name":
        ranked.sort(key=lambda r: r["candidate_name"].lower())
    elif sort == "skills":
        ranked.sort(key=lambda r: (-(r["skill_score"] or 0), -r["overall_score"]))
    elif sort == "experience":
        ranked.sort(key=lambda r: (-(r["total_experience_years"] or 0), -r["overall_score"]))
    return ranked


def all_match_results(db, user_id):
    rows = db.execute(_MATCH_SELECT + " WHERE m.user_id = ? ORDER BY j.title, m.overall_score DESC", (user_id,)).fetchall()
    return [decode_match(r) for r in rows]


# ----------------------------------------------------------------------------- dashboard


def dashboard_stats(db, user_id):
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
    avg = one("SELECT AVG(overall_score) FROM matching_results WHERE user_id = ?", user_id)
    stats = {
        "resumes": one("SELECT COUNT(*) FROM resumes WHERE user_id = ?", user_id),
        "jobs": one("SELECT COUNT(*) FROM job_descriptions WHERE user_id = ?", user_id),
        "matches": one("SELECT COUNT(*) FROM matching_results WHERE user_id = ?", user_id),
        "avg_score": round(avg, 1) if avg is not None else None,
    }
    top = db.execute(
        "SELECT m.id, m.overall_score, m.skill_score, c.name, j.title AS job_title FROM matching_results m"
        " JOIN candidates c ON c.resume_id = m.resume_id JOIN job_descriptions j ON j.id = m.job_id"
        " WHERE m.user_id = ? ORDER BY m.overall_score DESC, c.name LIMIT 5", (user_id,)).fetchall()
    recent = db.execute(
        "SELECT r.id, r.original_filename, r.uploaded_at, c.name, a.total_experience_years,"
        " (SELECT COUNT(*) FROM extracted_skills s WHERE s.resume_id = r.id) AS skill_count"
        " FROM resumes r JOIN candidates c ON c.resume_id = r.id JOIN resume_analysis a ON a.resume_id = r.id"
        " WHERE r.user_id = ? ORDER BY r.id DESC LIMIT 6", (user_id,)).fetchall()
    skills = db.execute(
        "SELECT s.skill, COUNT(*) AS n FROM extracted_skills s JOIN resumes r ON r.id = s.resume_id"
        " WHERE r.user_id = ? GROUP BY s.skill ORDER BY n DESC, s.skill LIMIT 10", (user_id,)).fetchall()
    categories = db.execute(
        "SELECT s.category, COUNT(*) AS n FROM extracted_skills s JOIN resumes r ON r.id = s.resume_id"
        " WHERE r.user_id = ? GROUP BY s.category ORDER BY n DESC", (user_id,)).fetchall()
    bands = db.execute(
        "SELECT SUM(overall_score >= 70) AS strong, SUM(overall_score >= 50 AND overall_score < 70) AS moderate,"
        " SUM(overall_score >= 30 AND overall_score < 50) AS partial, SUM(overall_score < 30) AS low"
        " FROM matching_results WHERE user_id = ?", (user_id,)).fetchone()
    jobs = db.execute(
        "SELECT j.id, j.title, COUNT(m.id) AS n, ROUND(AVG(m.overall_score), 1) AS avg_score,"
        " MAX(m.overall_score) AS top_score FROM job_descriptions j"
        " LEFT JOIN matching_results m ON m.job_id = j.id WHERE j.user_id = ?"
        " GROUP BY j.id ORDER BY j.id DESC LIMIT 8", (user_id,)).fetchall()
    return {
        "totals": stats,
        "top_candidates": [dict(r) for r in top],
        "recent": [dict(r) for r in recent],
        "skills": [dict(r) for r in skills],
        "categories": [dict(r) for r in categories],
        "bands": {k: (bands[k] or 0) for k in ("strong", "moderate", "partial", "low")},
        "jobs": [dict(r) for r in jobs],
    }


# ----------------------------------------------------------------------------- demo data


def load_demo_data(db, user, upload_dir, sample_dir, *, default_weights=None, **upload_opts):
    """Import the bundled synthetic resumes/jobs for this user and match them.
    Returns a dict of counts. Safe to run repeatedly (duplicates are skipped)."""
    sample_dir = Path(sample_dir)
    counts = {"resumes": 0, "jobs": 0, "matches": 0, "skipped": 0}

    jobs_file = sample_dir / "jobs.json"
    job_ids = []
    if jobs_file.exists():
        for item in json.loads(jobs_file.read_text(encoding="utf-8")):
            existing = db.execute("SELECT id FROM job_descriptions WHERE user_id = ? AND title = ?",
                                  (user["id"], item["title"])).fetchone()
            if existing:
                job_ids.append(existing["id"])
                counts["skipped"] += 1
                continue
            clean, errors = validate_job_form({
                "title": item["title"], "description": item["description"],
                "required_skills": ", ".join(item.get("required_skills", [])),
                "min_experience_years": str(item.get("min_experience_years", 0)),
                "education_requirement": item.get("education_requirement", "")})
            if not errors:
                job_ids.append(create_job(db, user["id"], clean))
                counts["jobs"] += 1

    for path in sorted((sample_dir / "resumes").glob("*")):
        if path.suffix.lower().lstrip(".") not in ("pdf", "docx"):
            continue
        res = save_resume(db, user["id"], path.name, path.read_bytes(), upload_dir, **upload_opts)
        counts["resumes" if res["ok"] else "skipped"] += 1

    if load_resume_bundles(db, user["id"]):
        for job_id in job_ids:
            counts["matches"] += run_matching(db, user, job_id, default_weights=default_weights)
    return counts
