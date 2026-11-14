"""Skill-gap analysis: required vs. candidate skills, plus improvement recommendations."""
from .skill_extractor import RELATED, extract_skills, normalize_skill, skill_category, skill_in_text

CATEGORY_TIPS = {
    "Programming Languages": "Build and publish a small project in {skill} on GitHub (e.g. a CLI tool or API) so the skill is demonstrable.",
    "Web & Frameworks": "Create a working mini-app with {skill} and describe its features in your project section.",
    "Databases & Data Engineering": "Practise {skill} on a real dataset (schema design, joins/aggregations or pipelines) and add the project to your resume.",
    "Machine Learning & AI": "Complete an end-to-end {skill} project on a public dataset (data prep, training, evaluation) and document the results.",
    "Data Analysis & BI": "Build a dashboard or analysis notebook that uses {skill} and publish it with a short write-up of the insights.",
    "Cloud & DevOps": "Deploy a sample application using {skill} (free tiers are enough) and note what you automated.",
    "Tools & Practices": "Use {skill} in a team-style workflow on one of your projects and mention it in the project bullets.",
    "Other": "Gain hands-on practice with {skill} (course + small project) and list concrete outcomes on your resume.",
}


def analyze_skill_gap(required_skills, resume_text, resume_skills=None):
    """Compare required skills with what a resume mentions.

    required_skills: list of skill names (aliases are normalised).
    resume_skills:   optional list of dicts/strings already extracted from the resume,
                     used for the 'additional skills' list.
    """
    required = []
    for skill in required_skills or []:
        name = normalize_skill(skill)
        if name and name.lower() not in {r.lower() for r in required}:
            required.append(name)

    matched = [s for s in required if skill_in_text(resume_text, s)]
    missing = [s for s in required if s not in matched]
    total = len(required)
    match_pct = round(len(matched) / total * 100, 2) if total else None

    if resume_skills is None:
        resume_skills = extract_skills(resume_text)
    resume_names = [s["name"] if isinstance(s, dict) else str(s) for s in resume_skills]
    required_lower = {r.lower() for r in required}
    extra = [n for n in resume_names if n.lower() not in required_lower]

    by_category = {}
    for skill in required:
        cat = skill_category(skill)
        bucket = by_category.setdefault(cat, {"matched": [], "missing": []})
        bucket["matched" if skill in matched else "missing"].append(skill)

    return {
        "required": required,
        "matched": matched,
        "missing": missing,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "total_required": total,
        "match_pct": match_pct,
        "extra_skills": extra,
        "by_category": by_category,
        "recommendations": build_recommendations(missing, resume_names, match_pct),
    }


def build_recommendations(missing, candidate_skills, match_pct=None):
    """Plain-language suggestions for closing the gap."""
    recs = []
    if not missing:
        if match_pct is not None:
            recs.append("All required skills are present. Strengthen the profile with measurable results "
                        "(numbers, scale, impact) in your project and experience bullets.")
        return recs

    have = {s.lower() for s in candidate_skills}
    if match_pct is not None and match_pct < 50:
        top = ", ".join(missing[:3])
        recs.append(f"Prioritise the highest-impact gaps first: {top}.")

    for skill in missing[:6]:
        related = [r for r in RELATED.get(skill, []) if r.lower() in have]
        if related:
            recs.append(f"{skill}: your experience with {', '.join(related[:2])} transfers well. "
                        f"If you have used {skill}, name it explicitly in your skills and project bullets; "
                        f"otherwise a short hands-on project would close the gap quickly.")
        else:
            recs.append(f"{skill}: " + CATEGORY_TIPS.get(skill_category(skill), CATEGORY_TIPS["Other"]).format(skill=skill))
    if len(missing) > 6:
        recs.append(f"{len(missing) - 6} further missing skills: {', '.join(missing[6:])}.")
    recs.append("If you already have experience with a 'missing' skill, add it to your resume - "
                "matching is based on what the document actually states.")
    return recs
