"""PDF and CSV report generation (ReportLab + pandas). Reports are built in memory."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .matching_engine import DISCLAIMER, score_band

ACCENT = colors.HexColor("#4f46e5")
MUTED = colors.HexColor("#6b7280")
_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise spreadsheet formula injection (cells starting with = + - @)."""
    if isinstance(value, str) and value.startswith(_FORMULA_CHARS):
        return "'" + value
    return value


def _t(value):
    """Escape for ReportLab paragraphs; built-in fonts are Latin-1 only."""
    text = "" if value is None else str(value)
    return escape(text.encode("latin-1", "replace").decode("latin-1"))


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=ACCENT, fontSize=20, spaceAfter=4, alignment=0),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=ACCENT, fontSize=13, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("s", parent=base["BodyText"], fontSize=8, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["BodyText"], fontSize=8.5, leading=11),
    }


def _bullets(items, style):
    return [Paragraph("&bull; " + _t(i), style) for i in items] or [Paragraph("-", style)]


def _table(data, widths, header=True):
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                     ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    table.setStyle(TableStyle(commands))
    return table


def _build(story, title):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=title,
                            author="AI Resume Screening & Job Matching System")
    doc.build(story)
    return buffer.getvalue()


def candidate_report_pdf(resume, candidate, analysis, skills, matches):
    """Individual candidate analysis report.

    resume/candidate: dict-like rows; analysis: dict with lists already decoded;
    skills: list of dicts(skill, category, mentions); matches: list of dicts with job_title + scores.
    """
    st = _styles()
    story = [Paragraph("Candidate Analysis Report", st["title"]),
             Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M} &middot; Source file: {_t(resume['original_filename'])}", st["small"]),
             Spacer(1, 6)]

    info = [
        ["Name", Paragraph(_t(candidate["name"]), st["cell"])],
        ["Email", Paragraph(_t(candidate["email"] or "Not found"), st["cell"])],
        ["Phone", Paragraph(_t(candidate["phone"] or "Not found"), st["cell"])],
        ["Highest education", Paragraph(_t(analysis.get("highest_education") or "Not detected"), st["cell"])],
        ["Estimated experience", f"{analysis.get('total_experience_years', 0):g} years (from dates / statements in the resume)"],
        ["Word count", str(analysis.get("word_count", 0))],
    ]
    story.append(_table(info, [45 * mm, 125 * mm], header=False))

    story.append(Paragraph("Extracted skills", st["h2"]))
    by_cat = {}
    for s in skills:
        by_cat.setdefault(s["category"], []).append(s["skill"])
    if by_cat:
        rows = [["Category", "Skills"]] + [[Paragraph(_t(c), st["cell"]), Paragraph(_t(", ".join(v)), st["cell"])]
                                           for c, v in by_cat.items()]
        story.append(_table(rows, [50 * mm, 120 * mm]))
    else:
        story.append(Paragraph("No skills from the taxonomy were detected.", st["body"]))

    for heading, key in (("Education", "education"), ("Work experience", "experience"),
                         ("Projects", "projects"), ("Certifications", "certifications")):
        story.append(Paragraph(heading, st["h2"]))
        story.extend(_bullets(analysis.get(key, []), st["body"]))

    story.append(Paragraph("Top keywords", st["h2"]))
    story.append(Paragraph(_t(", ".join(analysis.get("keywords", [])) or "-"), st["body"]))

    story.append(Paragraph("Job match results", st["h2"]))
    if matches:
        rows = [["Job", "Score", "Alignment", "Matched", "Missing skills"]]
        for m in matches:
            label, _css = score_band(m["overall_score"])
            rows.append([Paragraph(_t(m["job_title"]), st["cell"]), f"{m['overall_score']:.1f}%", label,
                         str(len(m["matched_skills"])), Paragraph(_t(", ".join(m["missing_skills"]) or "None"), st["cell"])])
        story.append(_table(rows, [48 * mm, 18 * mm, 32 * mm, 18 * mm, 54 * mm]))
    else:
        story.append(Paragraph("This resume has not been matched against a job yet.", st["body"]))

    story += [Spacer(1, 10), Paragraph(_t(DISCLAIMER), st["small"])]
    return _build(story, f"Candidate report - {candidate['name']}")


def ranking_rows(results):
    """Flatten ranking results (dicts) into export rows."""
    rows = []
    for r in results:
        label, _css = score_band(r["overall_score"])
        rows.append({
            "Rank": r.get("rank"),
            "Candidate": r["candidate_name"],
            "Email": r.get("candidate_email") or "",
            "Phone": r.get("candidate_phone") or "",
            "Overall similarity score (%)": r["overall_score"],
            "Alignment band": label,
            "TF-IDF similarity (%)": r["tfidf_score"],
            "Skill match (%)": "" if r["skill_score"] is None else r["skill_score"],
            "Keyword match (%)": r["keyword_score"],
            "Experience fit (%)": "" if r["experience_score"] is None else r["experience_score"],
            "Estimated experience (yrs)": r.get("total_experience_years", ""),
            "Matched skills": ", ".join(r["matched_skills"]),
            "Missing skills": ", ".join(r["missing_skills"]),
            "Flagged for review": "Yes" if r.get("is_shortlisted") else "",
            "Source file": r.get("original_filename", ""),
        })
    return rows


def _to_csv(rows, columns=None):
    frame = pd.DataFrame(rows, columns=columns)
    for col in frame.columns:
        if frame[col].dtype == object:
            frame[col] = frame[col].map(csv_safe)
    return frame.to_csv(index=False)


def ranking_csv(results):
    return _to_csv(ranking_rows(results), columns=list(ranking_rows([{
        "candidate_name": "", "overall_score": 0, "tfidf_score": 0, "skill_score": None,
        "keyword_score": 0, "experience_score": None, "matched_skills": [], "missing_skills": []}])[0].keys()))


def matching_csv(results):
    """All stored matching results (one row per resume/job pair)."""
    columns = ["Job", "Candidate", "Overall similarity score (%)", "Alignment band", "TF-IDF similarity (%)",
               "Skill match (%)", "Keyword match (%)", "Experience fit (%)", "Matched skills",
               "Missing skills", "Flagged for review", "Matched on"]
    rows = []
    for r in results:
        label, _css = score_band(r["overall_score"])
        rows.append({
            "Job": r["job_title"], "Candidate": r["candidate_name"],
            "Overall similarity score (%)": r["overall_score"], "Alignment band": label,
            "TF-IDF similarity (%)": r["tfidf_score"],
            "Skill match (%)": "" if r["skill_score"] is None else r["skill_score"],
            "Keyword match (%)": r["keyword_score"],
            "Experience fit (%)": "" if r["experience_score"] is None else r["experience_score"],
            "Matched skills": ", ".join(r["matched_skills"]), "Missing skills": ", ".join(r["missing_skills"]),
            "Flagged for review": "Yes" if r.get("is_shortlisted") else "", "Matched on": r["created_at"],
        })
    return _to_csv(rows, columns=columns)


def ranking_pdf(job, results):
    st = _styles()
    story = [Paragraph("Candidate Ranking Report", st["title"]),
             Paragraph(f"Job: <b>{_t(job['title'])}</b> &middot; {len(results)} candidate(s) &middot; "
                       f"Generated {datetime.now():%d %b %Y, %H:%M}", st["small"]),
             Spacer(1, 4),
             Paragraph("Required skills: " + _t(", ".join(job["required_skills"]) or "none specified"), st["body"]),
             Spacer(1, 8)]
    rows = [["#", "Candidate", "Score", "Skills", "Matched", "Missing skills"]]
    for r in results:
        skill = "-" if r["skill_score"] is None else f"{r['skill_score']:.0f}%"
        rows.append([str(r["rank"]), Paragraph(_t(r["candidate_name"]), st["cell"]), f"{r['overall_score']:.1f}%",
                     skill, str(len(r["matched_skills"])),
                     Paragraph(_t(", ".join(r["missing_skills"]) or "None"), st["cell"])])
    story.append(_table(rows, [10 * mm, 48 * mm, 18 * mm, 18 * mm, 18 * mm, 58 * mm]))
    story += [Spacer(1, 12), Paragraph(_t(DISCLAIMER), st["small"]),
              Paragraph("Ranking order is a convenience for review; no candidate should be rejected on score alone.", st["small"])]
    return _build(story, f"Ranking - {job['title']}")
