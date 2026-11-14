"""Turn raw resume text into structured data (contact info, sections, experience...)."""
import re
from datetime import date

from .nlp_processor import BULLET_CHARS, clean_text, extract_keywords, word_count
from .skill_extractor import extract_skills

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w])(\+?\d[\d\s().\-]{8,18}\d)(?![\w])")
YEAR_RANGE_ONLY_RE = re.compile(r"^\s*(?:19|20)\d{2}\s*[-\u2013\u2014]\s*(?:19|20)\d{2}\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-\u2022\u2013\u2014*]|\d+[.)])\s+")

SECTION_PATTERNS = {
    "summary": r"(?:professional |career )?(?:summary|profile|objective)|about me",
    "education": r"education(?: (?:&|and) (?:training|certifications?))?|academic (?:background|qualifications?|details)|qualifications?",
    "experience": r"(?:work |professional |relevant |industrial )?experience|employment(?: history)?|work history|career history|internships?",
    "projects": r"(?:academic |personal |key |selected |major )?projects?",
    "skills": r"(?:technical |core |key |it )?skills?(?: (?:&|and) (?:tools|technologies))?|technologies|tech stack|technical proficiency|competencies",
    "certifications": r"certifications?|certificates?|licen[sc]es?(?: (?:&|and) certifications?)?|courses|training",
    "other": r"achievements?|awards?(?: (?:&|and) achievements?)?|honou?rs|hobbies|interests|languages|references|declaration|publications?|extra[- ]?curricular(?: activities)?|personal details",
}
_SECTION_RES = {name: re.compile(rf"(?:{pat})", re.IGNORECASE) for name, pat in SECTION_PATTERNS.items()}

NOT_A_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "developer", "engineer", "analyst", "intern", "scientist",
    "student", "manager", "address", "profile", "summary", "objective", "contact", "email", "phone",
    "linkedin", "github", "portfolio", "synthetic", "sample", "fresher", "graduate", "software",
    "data", "python", "full", "stack", "web", "machine", "learning", "designer", "consultant",
}

# Degree levels: 1 diploma, 2 bachelor, 3 master, 4 doctorate. Ambiguous abbreviations
# (B.E., M.S., B.A.) need their dots so "be" / "MS Office" are not mistaken for degrees.
_LEVEL_PATTERNS = [
    (4, "PhD", re.compile(r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctor of philosophy\b", re.I)),
    (3, "Master's", re.compile(
        r"\bm\.?\s?tech\b|\bm\.?\s?sc\b|\bmba\b|\bm\.?c\.?a\b|\bpgdm\b|\bpost[- ]?graduate\b"
        r"|\bmaster(?:'s|s)?\s+(?:of|in|degree)\b|\bmasters\b", re.I)),
    (3, "Master's", re.compile(r"\bM\.(?:E|S|A)\.|\bM\.Eng\b")),
    (2, "Bachelor's", re.compile(
        r"\bb\.?\s?tech\b|\bb\.?\s?sc\b|\bbca\b|\bb\.?\s?com\b|\bbachelor(?:'s|s)?\b|\bundergraduate\b", re.I)),
    (2, "Bachelor's", re.compile(r"\bB\.(?:E|S|A)\.?(?=[\s,)\-]|$)|\bB\.Eng\b")),
    (1, "Diploma", re.compile(r"\bdiploma\b|\bpolytechnic\b|\bassociate degree\b", re.I)),
]
LEVEL_LABELS = {0: "Not detected", 1: "Diploma", 2: "Bachelor's", 3: "Master's", 4: "PhD"}
INSTITUTION_RE = re.compile(r"\b(university|college|institute|school|academy|iit|nit)\b", re.I)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
DATE_RANGE_RE = re.compile(
    r"(?:(?P<m1>[A-Za-z]{3,9})\.?,?\s+)?(?P<y1>(?:19|20)\d{2})\s*(?:-|\u2013|\u2014|to)\s*"
    r"(?:(?P<pres>present|current|now|ongoing|till date)|(?:(?P<m2>[A-Za-z]{3,9})\.?,?\s+)?(?P<y2>(?:19|20)\d{2}))",
    re.IGNORECASE)
EXPLICIT_YEARS_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}?experience", re.IGNORECASE)


def detect_levels(text):
    """Set of degree levels mentioned in `text`."""
    levels = set()
    for level, _label, pattern in _LEVEL_PATTERNS:
        if pattern.search(text or ""):
            levels.add(level)
    return levels


def level_label(level):
    return LEVEL_LABELS.get(level, "Not detected")


def _heading_of(line):
    """Return the canonical section name if `line` is a section heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 45:
        return None
    normal = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", stripped).lower()
    normal = re.sub(r"\s+", " ", normal)
    if not normal:
        return None
    for name, pattern in _SECTION_RES.items():
        if pattern.fullmatch(normal):
            return name
    return None


def split_sections(text):
    sections = {"header": []}
    current = "header"
    for line in text.split("\n"):
        heading = _heading_of(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.strip())
    return sections


def extract_email(text):
    match = EMAIL_RE.search(text or "")
    return match.group(0).rstrip(".").lower() if match else None


def extract_phone(text):
    for match in PHONE_RE.finditer(text or ""):
        candidate = match.group(1).strip()
        digits = re.sub(r"\D", "", candidate)
        if not 10 <= len(digits) <= 13:
            continue
        if YEAR_RANGE_ONLY_RE.match(candidate):
            continue
        return re.sub(r"\s+", " ", candidate)
    return None


def extract_name(header_lines, email=None, fallback=None):
    for line in header_lines[:8]:
        candidate = line.strip(" \t|,-")
        if not candidate or any(ch in candidate for ch in "@/:0123456789"):
            continue
        if re.search(r"https?|www\.|linkedin|github", candidate, re.I):
            continue
        words = candidate.split()
        if not 2 <= len(words) <= 4 or len(candidate) > 40:
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            continue
        if any(w.lower().strip(".") in NOT_A_NAME_WORDS for w in words):
            continue
        return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in words)
    if email:
        local = re.sub(r"\d+", " ", email.split("@")[0])
        parts = [p for p in re.split(r"[._\-\s]+", local) if len(p) > 1]
        if parts:
            return " ".join(p.capitalize() for p in parts[:3])
    return fallback or "Unknown Candidate"


def _strip_bullet(line):
    return BULLET_RE.sub("", line).strip()


def _items(lines, limit, max_len=140):
    """Headline-style items first (non-bullet lines); fall back to bullets."""
    heads = [l.strip() for l in lines if not BULLET_RE.match(l) and len(l.strip()) <= max_len]
    items = heads or [_strip_bullet(l) for l in lines]
    return [i for i in items if i][:limit]


def extract_education(sections, text):
    lines = sections.get("education", [])
    pool = lines if lines else text.split("\n")
    entries = []
    for line in pool:
        if detect_levels(line) or (lines and INSTITUTION_RE.search(line)):
            clean = _strip_bullet(line)
            if clean and clean not in entries:
                entries.append(clean[:200])
    return entries[:6]


def estimate_experience_years(experience_lines, full_text, today=None):
    """Union of dated ranges in the experience section vs. any explicit 'N years of experience'."""
    today = today or date.today()
    intervals = []
    for match in DATE_RANGE_RE.finditer("\n".join(experience_lines)):
        m1 = MONTHS.get((match.group("m1") or "")[:3].lower(), 1)
        y1 = int(match.group("y1"))
        if match.group("pres"):
            end = today.year * 12 + today.month
        else:
            m2 = MONTHS.get((match.group("m2") or "")[:3].lower(), 12)
            end = int(match.group("y2")) * 12 + m2
        start = y1 * 12 + m1
        if end < start or end - start > 600:
            continue
        intervals.append((start, end + 1))  # inclusive of the final month
    intervals.sort()
    months, cur_start, cur_end = 0, None, None
    for start, end in intervals:
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                months += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        months += cur_end - cur_start
    computed = months / 12
    explicit = max((float(m) for m in EXPLICIT_YEARS_RE.findall(full_text or "")), default=0.0)
    return round(min(max(computed, explicit), 50), 1)


def analyze_resume(text, filename=None):
    """Full structured analysis of one resume's text."""
    text = clean_text(text)
    sections = split_sections(text)
    email = extract_email(text)
    phone = extract_phone(text)
    stem = re.sub(r"[_\-.]+", " ", filename.rsplit(".", 1)[0]).title() if filename else None
    name = extract_name(sections.get("header", []), email, stem)

    education = extract_education(sections, text)
    edu_text = "\n".join(education) if education else ""
    levels = detect_levels(edu_text)
    highest = max(levels) if levels else 0

    experience_lines = sections.get("experience", [])
    # Keywords should describe the work, not the contact block.
    keyword_text = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", text)
    keyword_text = re.sub(r"\b(?:" + "|".join(re.escape(w) for w in name.split()) + r")\b", " ", keyword_text, flags=re.I)
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "education": education,
        "highest_education": level_label(highest) if highest else None,
        "highest_education_level": highest,
        "experience": [_strip_bullet(l)[:220] for l in experience_lines][:14],
        "projects": _items(sections.get("projects", []), 10),
        "certifications": _items(sections.get("certifications", []), 10),
        "total_experience_years": estimate_experience_years(experience_lines, text),
        "keywords": extract_keywords(keyword_text, 15),
        "skills": extract_skills(text),
        "word_count": word_count(text),
    }
