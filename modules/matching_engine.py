"""Resume <-> job matching.

Overall score = weighted blend of
  * skills      - share of the job's required skills found in the resume
  * tfidf       - cosine similarity of TF-IDF vectors (job text vs resume text)
  * keywords    - share of the job's top keywords present in the resume
  * experience  - candidate's estimated years / required years (capped at 100%)
Components that do not apply (e.g. no required skills listed) are dropped and the
remaining weights are re-normalised. Education is reported but not scored.

IMPORTANT: this is a *text-similarity* measure. It is not a prediction of hiring
suitability, and it cannot see qualities that are not written in the document.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .nlp_processor import extract_keywords, preprocess
from .skill_extractor import skill_category
from .skill_gap import analyze_skill_gap
from .resume_analyzer import detect_levels, level_label

DEFAULT_WEIGHTS = {"skills": 0.45, "tfidf": 0.30, "keywords": 0.15, "experience": 0.10}
DISCLAIMER = ("Scores measure how closely a resume's wording and skills overlap with a job description. "
              "They are screening aids, not an assessment of a person's suitability - always review resumes manually.")

BANDS = [(70, "Strong alignment", "high"), (50, "Moderate alignment", "mid"),
         (30, "Partial alignment", "low"), (0, "Low alignment", "vlow")]


def score_band(score):
    """(label, css-class) for a 0-100 score."""
    for threshold, label, css in BANDS:
        if score >= threshold:
            return label, css
    return BANDS[-1][1], BANDS[-1][2]


def normalise_weights(weights, available):
    """Keep only the available components and scale them to sum to 1."""
    base = {**DEFAULT_WEIGHTS, **(weights or {})}
    chosen = {k: max(float(base.get(k, 0)), 0.0) for k in available}
    total = sum(chosen.values())
    if total <= 0:
        return {k: 1 / len(available) for k in available}
    return {k: v / total for k, v in chosen.items()}


def build_job_text(job):
    parts = [job.get("title", ""), job.get("description", ""), " ".join(job.get("required_skills", []))]
    return "\n".join(p for p in parts if p)


def tfidf_similarities(job_text, resume_texts, corpus_texts=None):
    """Cosine similarity (0-1) of each resume to the job. The vectoriser is fitted on the job,
    the resumes and (optionally) the wider corpus so IDF reflects the candidate pool."""
    if not resume_texts:
        return []
    fit_docs = [job_text] + list(corpus_texts if corpus_texts is not None else resume_texts)
    vectorizer = TfidfVectorizer(tokenizer=preprocess, lowercase=False, token_pattern=None,
                                 ngram_range=(1, 2), sublinear_tf=True)
    try:
        vectorizer.fit(fit_docs)
        job_vec = vectorizer.transform([job_text])
        resume_vecs = vectorizer.transform(resume_texts)
    except ValueError:  # empty vocabulary
        return [0.0] * len(resume_texts)
    return [float(x) for x in cosine_similarity(job_vec, resume_vecs)[0]]


def keyword_overlap(job_keywords, resume_text):
    resume_tokens = set(preprocess(resume_text))
    hits = [k for k in job_keywords if k in resume_tokens]
    score = len(hits) / len(job_keywords) if job_keywords else 0.0
    return score, hits


def education_check(requirement, candidate_level):
    """True/False when the requirement names a degree level, None when it can't be judged."""
    levels = detect_levels(requirement or "")
    if not levels:
        return None
    return candidate_level >= min(levels)


def build_strengths(gap, tfidf, exp_years, min_years, edu_met, candidate_level):
    strengths = []
    if gap["matched"]:
        top = ", ".join(gap["matched"][:4])
        strengths.append(f"Covers {gap['matched_count']} of {gap['total_required']} required skills, including {top}.")
    for cat, bucket in gap["by_category"].items():
        if len(bucket["matched"]) >= 2:
            strengths.append(f"Solid {cat} coverage ({', '.join(bucket['matched'][:4])}).")
    if min_years and exp_years >= min_years:
        strengths.append(f"Estimated experience ({exp_years:g} yrs) meets the stated requirement ({min_years:g} yrs).")
    if edu_met:
        strengths.append(f"Detected qualification ({level_label(candidate_level)}) meets the education requirement.")
    if tfidf >= 0.35:
        strengths.append("Resume wording overlaps strongly with the job description.")
    return strengths or ["No strong alignment signals were detected automatically."]


def build_gaps(gap, tfidf, exp_years, min_years, edu_met, requirement):
    gaps = []
    if gap["missing"]:
        gaps.append(f"Missing required skills: {', '.join(gap['missing'])}.")
    if min_years and exp_years < min_years:
        gaps.append(f"Estimated experience ({exp_years:g} yrs) is below the requirement ({min_years:g} yrs). "
                    "Estimates come from dates in the resume and may be incomplete.")
    if edu_met is False:
        gaps.append(f"Education requirement not confirmed from the resume ({requirement}).")
    if tfidf < 0.15:
        gaps.append("Little overlap between the resume's wording and the job description.")
    return gaps or ["No gaps detected automatically."]


def match_one(job, resume, tfidf, job_keywords, weights=None):
    """Score a single resume. `tfidf` is its precomputed cosine similarity (0-1)."""
    text = resume["raw_text"]
    gap = analyze_skill_gap(job.get("required_skills", []), text, resume.get("skills"))
    kw_score, kw_hits = keyword_overlap(job_keywords, text)

    min_years = float(job.get("min_experience_years") or 0)
    exp_years = float(resume.get("total_experience_years") or 0)
    exp_score = min(exp_years / min_years, 1.0) if min_years > 0 else None
    skill_score = gap["match_pct"] / 100 if gap["match_pct"] is not None else None

    components = {"tfidf": tfidf, "keywords": kw_score}
    if skill_score is not None:
        components["skills"] = skill_score
    if exp_score is not None:
        components["experience"] = exp_score
    w = normalise_weights(weights, list(components))
    overall = round(sum(components[k] * w[k] for k in components) * 100, 1)

    level = int(resume.get("highest_education_level") or 0)
    edu_met = education_check(job.get("education_requirement"), level)

    return {
        "overall_score": overall,
        "tfidf_score": round(tfidf * 100, 1),
        "skill_score": round(skill_score * 100, 1) if skill_score is not None else None,
        "keyword_score": round(kw_score * 100, 1),
        "experience_score": round(exp_score * 100, 1) if exp_score is not None else None,
        "education_met": None if edu_met is None else int(edu_met),
        "matched_skills": gap["matched"],
        "missing_skills": gap["missing"],
        "keywords": kw_hits,
        "strengths": build_strengths(gap, tfidf, exp_years, min_years, edu_met, level),
        "gaps": build_gaps(gap, tfidf, exp_years, min_years, edu_met, job.get("education_requirement")),
        "recommendations": gap["recommendations"],
        "weights_used": {k: round(v, 3) for k, v in w.items()},
    }


def match_resumes(job, resumes, weights=None, corpus_texts=None):
    """Score many resumes against one job. Returns results in the same order as `resumes`.

    job:     dict(title, description, required_skills[list], min_experience_years, education_requirement)
    resumes: list of dict(raw_text, skills[list of names], total_experience_years, highest_education_level, ...)
    """
    if not resumes:
        return []
    job_text = build_job_text(job)
    sims = tfidf_similarities(job_text, [r["raw_text"] for r in resumes], corpus_texts)
    job_keywords = extract_keywords(job_text, 25)
    results = []
    for resume, sim in zip(resumes, sims):
        result = match_one(job, resume, sim, job_keywords, weights)
        result["corpus_size"] = 1 + len(corpus_texts if corpus_texts is not None else resumes)
        results.append(result)
    return results


def rank_results(results):
    """Sort descending by overall score (stable) and attach 1-based ranks (ties share a rank)."""
    ordered = sorted(results, key=lambda r: -r["overall_score"])
    rank, prev = 0, None
    for position, item in enumerate(ordered, start=1):
        if item["overall_score"] != prev:
            rank, prev = position, item["overall_score"]
        item["rank"] = rank
    return ordered
