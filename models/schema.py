"""SQLite schema. Every statement is idempotent (IF NOT EXISTS)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    theme         TEXT NOT NULL DEFAULT 'dark',
    weights_json  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,
    file_ext          TEXT NOT NULL,
    file_size         INTEGER NOT NULL,
    file_hash         TEXT NOT NULL,
    raw_text          TEXT NOT NULL,
    uploaded_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, file_hash)
);

CREATE TABLE IF NOT EXISTS candidates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id  INTEGER NOT NULL UNIQUE REFERENCES resumes(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    email      TEXT,
    phone      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resume_analysis (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id                INTEGER NOT NULL UNIQUE REFERENCES resumes(id) ON DELETE CASCADE,
    education_json           TEXT NOT NULL DEFAULT '[]',
    experience_json          TEXT NOT NULL DEFAULT '[]',
    projects_json            TEXT NOT NULL DEFAULT '[]',
    certifications_json      TEXT NOT NULL DEFAULT '[]',
    keywords_json            TEXT NOT NULL DEFAULT '[]',
    total_experience_years   REAL NOT NULL DEFAULT 0,
    highest_education        TEXT,
    highest_education_level  INTEGER NOT NULL DEFAULT 0,
    word_count               INTEGER NOT NULL DEFAULT 0,
    analyzed_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS extracted_skills (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    skill     TEXT NOT NULL,
    category  TEXT NOT NULL,
    mentions  INTEGER NOT NULL DEFAULT 1,
    UNIQUE (resume_id, skill)
);

CREATE TABLE IF NOT EXISTS job_descriptions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL,
    required_skills_json  TEXT NOT NULL DEFAULT '[]',
    min_experience_years  REAL NOT NULL DEFAULT 0,
    education_requirement TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matching_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id             INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    job_id                INTEGER NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    overall_score         REAL NOT NULL,
    tfidf_score           REAL NOT NULL,
    skill_score           REAL,
    keyword_score         REAL NOT NULL,
    experience_score      REAL,
    education_met         INTEGER,
    matched_skills_json   TEXT NOT NULL DEFAULT '[]',
    missing_skills_json   TEXT NOT NULL DEFAULT '[]',
    keywords_json         TEXT NOT NULL DEFAULT '[]',
    strengths_json        TEXT NOT NULL DEFAULT '[]',
    gaps_json             TEXT NOT NULL DEFAULT '[]',
    recommendations_json  TEXT NOT NULL DEFAULT '[]',
    corpus_size           INTEGER NOT NULL DEFAULT 0,
    is_shortlisted        INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (resume_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_resumes_user   ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user      ON job_descriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_skills_resume  ON extracted_skills(resume_id);
CREATE INDEX IF NOT EXISTS idx_skills_skill   ON extracted_skills(skill);
CREATE INDEX IF NOT EXISTS idx_match_job      ON matching_results(job_id, overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_match_user     ON matching_results(user_id);
"""
