"""Text preprocessing: cleaning, tokenisation, stop-word removal, keyword extraction.

The pipeline is self-contained (no NLTK/spaCy corpus downloads) so it works offline.
"""
import re
import unicodedata
from collections import Counter

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# Words that appear in nearly every resume / job post and carry no matching signal.
DOMAIN_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "responsible", "responsibilities", "responsibility",
    "work", "worked", "working", "experience", "experienced", "year", "years", "month", "months",
    "good", "strong", "excellent", "ability", "able", "skills", "skill", "knowledge", "etc", "eg",
    "e.g", "i.e", "including", "include", "includes", "using", "use", "used", "will", "must",
    "candidate", "candidates", "role", "position", "job", "company", "team", "teams", "looking",
    "required", "requirements", "preferred", "plus", "highly", "proven", "demonstrated", "like",
    "well", "new", "also", "across", "within", "various", "multiple", "based", "related",
    "built", "developed", "designed", "implemented", "created", "managed", "led", "worked", "helped",
    "improved", "maintained", "deployed", "wrote", "education", "projects", "project", "certifications",
    "summary", "objective", "profile", "university", "college", "institute", "bachelor", "master",
    "synthetic", "sample", "fictional", "present", "current", "jan", "feb", "mar", "apr", "may",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "email", "phone", "mobile", "address",
}
STOPWORDS = frozenset(ENGLISH_STOP_WORDS) | DOMAIN_STOPWORDS

# Keeps tokens such as c++, c#, node.js, asp.net, scikit (hyphens are split).
TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:[+#]{1,2}|(?:\.[a-z0-9]+)+)?")
BULLET_CHARS = "•●▪◦‣·∙■□◆◇➢➤►▶✓✔*"


def clean_text(text, keep_lines=True):
    """Normalise unicode/whitespace. With keep_lines=True, line breaks survive
    (needed for section detection); otherwise everything is collapsed to one line."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    for ch in BULLET_CHARS:
        text = text.replace(ch, "•") if ch != "*" else text
    text = re.sub(r"[ \t\f\v]+", " ", text)
    if keep_lines:
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text):
    """Lower-case and split into word tokens."""
    return TOKEN_RE.findall((text or "").lower())


def remove_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1 and not t.isdigit()]


def preprocess(text):
    """clean -> tokenise -> remove stop words. Returns a list of tokens."""
    return remove_stopwords(tokenize(clean_text(text, keep_lines=False)))


def preprocess_to_string(text):
    return " ".join(preprocess(text))


def extract_keywords(text, top_n=15, min_len=3):
    """Most frequent meaningful terms (ties broken alphabetically)."""
    counts = Counter(t for t in preprocess(text) if len(t) >= min_len)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:top_n]]


def word_count(text):
    return len(tokenize(text))
