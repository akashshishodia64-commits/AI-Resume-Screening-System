"""Application configuration."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_secret_key() -> str:
    """Use SECRET_KEY from the environment, else create/persist a random one locally."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = BASE_DIR / "database" / ".secret_key"
    try:
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        key_file.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return secrets.token_hex(32)  # sessions reset on restart, but the app still works


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = _load_secret_key()

    DATABASE = str(BASE_DIR / "database" / "resume_screening.db")
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    SAMPLE_DATA_DIR = str(BASE_DIR / "sample_data")

    # Uploads
    ALLOWED_EXTENSIONS = {"pdf", "docx"}
    MAX_FILE_SIZE = 5 * 1024 * 1024            # per resume
    MAX_CONTENT_LENGTH = 40 * 1024 * 1024      # whole request
    MAX_FILES_PER_UPLOAD = 20
    MIN_TEXT_CHARS = 50                        # below this a resume is treated as empty

    # Auth / session
    MIN_PASSWORD_LENGTH = 8
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_ENABLED = True

    # Matching weights (normalised at run time). Users can override in Settings.
    DEFAULT_WEIGHTS = {"skills": 0.45, "tfidf": 0.30, "keywords": 0.15, "experience": 0.10}


class TestConfig(Config):
    TESTING = True
    CSRF_ENABLED = False
