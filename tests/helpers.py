"""Shared test utilities: temp app, sample file builders."""
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from app import create_app
from config import TestConfig

SAMPLE_TEXT = [
    "JANE TESTER", "jane.tester@example.com | +91 98765 43210", "SKILLS",
    "Python, Flask, SQL, Git, REST API, Docker", "EXPERIENCE", "Software Engineer, Acme",
    "Jan 2020 - Dec 2022", "Built REST APIs with Flask and SQL", "EDUCATION",
    "B.Tech in Computer Science, Sample University, 2015 - 2019",
]


def make_app(tmpdir=None):
    tmp = tmpdir or tempfile.mkdtemp()

    class Cfg(TestConfig):
        DATABASE = os.path.join(tmp, "test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
    return create_app(Cfg)


def make_pdf_bytes(lines=SAMPLE_TEXT):
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buf, pagesize=A4).build([Paragraph(l, styles["Normal"]) for l in lines])
    return buf.getvalue()


def make_docx_bytes(lines=SAMPLE_TEXT):
    d = docx.Document()
    for l in lines:
        d.add_paragraph(l)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def register(client, username="tester", email="t@example.com", password="Passw0rd123"):
    return client.post("/register", data=dict(username=username, email=email, password=password,
                                              confirm_password=password), follow_redirects=True)
