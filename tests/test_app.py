"""Integration tests: auth, upload validation, jobs CRUD, DB ops, access control, exports, CSRF."""
import io
import os
import sqlite3
import tempfile
import unittest

from helpers import make_app, make_docx_bytes, make_pdf_bytes, register
from models import database
from modules import services


def upload(client, name, data):
    return client.post("/upload", data={"resumes": (io.BytesIO(data), name)}, content_type="multipart/form-data",
                       follow_redirects=True)


JOB_FORM = {"title": "Python Developer", "required_skills": "Python, Flask, SQL",
            "description": "Build REST APIs with Flask and SQL for our platform team.",
            "min_experience_years": "1", "education_requirement": "Bachelor's degree"}


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp)
        self.client = self.app.test_client()
        register(self.client)

    def db(self):
        return database.connect(self.app.config["DATABASE"])


class DatabaseTests(BaseCase):
    def test_schema_tables_exist(self):
        names = {r["name"] for r in self.db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"users", "resumes", "candidates", "job_descriptions", "resume_analysis",
                         "matching_results", "extracted_skills"} <= names)

    def test_init_db_is_idempotent(self):
        database.init_db(self.app.config["DATABASE"])
        database.init_db(self.app.config["DATABASE"])

    def test_foreign_keys_enforced_and_cascade(self):
        db = self.db()
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO resumes (user_id, original_filename, stored_filename, file_ext, file_size, file_hash, raw_text)"
                       " VALUES (999, 'a', 'b', 'pdf', 1, 'h', 't')")
        db.rollback()
        upload(self.client, "a.pdf", make_pdf_bytes())
        self.assertEqual(db.execute("SELECT COUNT(*) FROM extracted_skills").fetchone()[0] > 0, True)
        db.execute("DELETE FROM users"); db.commit()
        for table in ("resumes", "candidates", "resume_analysis", "extracted_skills"):
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_json_helpers(self):
        self.assertEqual(database.loads(database.dumps(["é", 1])), ["é", 1])
        self.assertEqual(database.loads("not json"), [])


class AuthTests(BaseCase):
    def test_register_validation(self):
        c = self.app.test_client()
        r = c.post("/register", data=dict(username="x", email="bad", password="short", confirm_password="no"))
        self.assertEqual(r.status_code, 400)
        r = c.post("/register", data=dict(username="tester", email="n@example.com", password="Passw0rd123",
                                          confirm_password="Passw0rd123"))
        self.assertIn(b"already registered", r.data)

    def test_password_is_hashed(self):
        row = self.db().execute("SELECT password_hash FROM users").fetchone()
        self.assertNotIn("Passw0rd123", row[0])
        self.assertTrue(row[0].startswith(("scrypt:", "pbkdf2:")))

    def test_login_logout_and_protection(self):
        c = self.app.test_client()
        self.assertEqual(c.get("/dashboard").status_code, 302)
        self.assertEqual(c.post("/login", data=dict(identity="tester", password="wrong")).status_code, 401)
        r = c.post("/login", data=dict(identity="tester", password="Passw0rd123"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/dashboard").status_code, 200)
        c.post("/logout")
        self.assertEqual(c.get("/dashboard").status_code, 302)

    def test_open_redirect_blocked(self):
        c = self.app.test_client()
        r = c.post("/login?next=https://evil.example", data=dict(identity="tester", password="Passw0rd123"))
        self.assertNotIn("evil.example", r.headers["Location"])


class UploadTests(BaseCase):
    def test_pdf_and_docx_upload(self):
        self.assertIn(b"Analysed", upload(self.client, "a.pdf", make_pdf_bytes()).data)
        self.assertIn(b"Analysed", upload(self.client, "b.docx", make_docx_bytes(["Other Person", "other@example.com", "SKILLS",
                      "Java, Spring Boot, MySQL, Docker and other tools for backend work", "EDUCATION", "M.Tech in CSE, Demo University"])).data)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 2)

    def test_multiple_files_in_one_request(self):
        r = self.client.post("/upload", data={"resumes": [(io.BytesIO(make_pdf_bytes()), "a.pdf"),
                             (io.BytesIO(make_docx_bytes()), "b.docx")]}, content_type="multipart/form-data")
        self.assertIn(b"2 of 2", r.data)

    def test_invalid_files_are_rejected_gracefully(self):
        for name, data, msg in [("x.txt", b"hello", b"Unsupported"), ("e.pdf", b"", b"empty"),
                                ("fake.pdf", b"not a pdf at all", b"signature"),
                                ("bad.pdf", b"%PDF-1.4 broken", b"corrupted"),
                                ("tiny.docx", make_docx_bytes(["hi"]), b"No readable text")]:
            r = upload(self.client, name, data)
            self.assertEqual(r.status_code, 200)
            self.assertIn(msg, r.data, name)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM resumes").fetchone()[0], 0)
        folder = os.path.join(self.app.config["UPLOAD_FOLDER"], "1")
        self.assertEqual(os.listdir(folder) if os.path.isdir(folder) else [], [])

    def test_oversize_rejected(self):
        self.app.config["MAX_FILE_SIZE"] = 500
        self.assertIn(b"too large", upload(self.client, "a.pdf", make_pdf_bytes()).data)

    def test_duplicate_detected(self):
        data = make_pdf_bytes()  # generated PDFs embed timestamps, so reuse the same bytes
        upload(self.client, "a.pdf", data)
        self.assertIn(b"already uploaded", upload(self.client, "copy.pdf", data).data)

    def test_delete_removes_file_and_rows(self):
        upload(self.client, "a.pdf", make_pdf_bytes())
        folder = os.path.join(self.app.config["UPLOAD_FOLDER"], "1")
        self.assertEqual(len(os.listdir(folder)), 1)
        self.assertEqual(self.client.post("/resumes/1/delete").status_code, 302)
        self.assertEqual(os.listdir(folder), [])


class JobTests(BaseCase):
    def test_create_edit_delete(self):
        self.assertEqual(self.client.post("/jobs/new", data=JOB_FORM).status_code, 302)
        row = self.db().execute("SELECT * FROM job_descriptions").fetchone()
        self.assertEqual(database.loads(row["required_skills_json"]), ["Python", "Flask", "SQL"])
        self.client.post("/jobs/1/edit", data={**JOB_FORM, "title": "Senior Python Developer"})
        self.assertEqual(self.db().execute("SELECT title FROM job_descriptions").fetchone()[0], "Senior Python Developer")
        self.client.post("/jobs/1/delete")
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM job_descriptions").fetchone()[0], 0)

    def test_validation(self):
        r = self.client.post("/jobs/new", data={**JOB_FORM, "title": "", "description": "short"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/jobs/new", data={**JOB_FORM, "min_experience_years": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM job_descriptions").fetchone()[0], 0)

    def test_skills_autodetected_when_blank(self):
        self.client.post("/jobs/new", data={**JOB_FORM, "required_skills": ""})
        skills = database.loads(self.db().execute("SELECT required_skills_json FROM job_descriptions").fetchone()[0])
        self.assertTrue({"Flask", "SQL", "REST API"} <= set(skills))

    def test_editing_job_clears_stale_results(self):
        upload(self.client, "a.pdf", make_pdf_bytes())
        self.client.post("/jobs/new", data=JOB_FORM)
        self.client.post("/matching/run", data={"job_id": 1})
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM matching_results").fetchone()[0], 1)
        self.client.post("/jobs/1/edit", data=JOB_FORM)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM matching_results").fetchone()[0], 0)


class MatchingFlowTests(BaseCase):
    def setUp(self):
        super().setUp()
        upload(self.client, "a.pdf", make_pdf_bytes())
        upload(self.client, "b.docx", make_docx_bytes(["Sam Painter", "sam@example.com", "SKILLS",
               "Photoshop, Illustrator, Figma, Branding and Typography for print campaigns", "EDUCATION", "Diploma in Design"]))
        self.client.post("/jobs/new", data=JOB_FORM)

    def test_run_rank_and_views(self):
        self.client.post("/matching/run", data={"job_id": 1})
        ranked = services.get_ranking(self.db(), 1, 1)
        self.assertEqual([r["candidate_name"] for r in ranked], ["Jane Tester", "Sam Painter"])
        self.assertEqual(ranked[0]["rank"], 1)
        for url in ("/ranking?job_id=1", "/matching/result/1", "/skill-gap?resume_id=1&job_id=1", "/matching", "/reports"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_rerun_updates_instead_of_duplicating(self):
        for _ in range(2):
            self.client.post("/matching/run", data={"job_id": 1})
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM matching_results").fetchone()[0], 2)

    def test_filters(self):
        self.client.post("/matching/run", data={"job_id": 1})
        db = self.db()
        self.assertEqual(len(services.get_ranking(db, 1, 1, min_score=40)), 1)
        self.assertEqual(len(services.get_ranking(db, 1, 1, skill="Flask")), 1)
        self.assertEqual(len(services.get_ranking(db, 1, 1, search="sam")), 1)
        self.assertEqual(services.get_ranking(db, 1, 1, min_score=40)[0]["rank"], 1)

    def test_flag_toggle(self):
        self.client.post("/matching/run", data={"job_id": 1})
        self.client.post("/ranking/flag/1", data={"next": "/ranking"})
        self.assertEqual(self.db().execute("SELECT is_shortlisted FROM matching_results WHERE id=1").fetchone()[0], 1)

    def test_exports(self):
        self.client.post("/matching/run", data={"job_id": 1})
        csv = self.client.get("/reports/ranking/1.csv")
        self.assertEqual(csv.mimetype, "text/csv")
        self.assertIn(b"Jane Tester", csv.data)
        self.assertIn(b"Job,Candidate", self.client.get("/reports/matching.csv").data)
        for url in ("/reports/ranking/1.pdf", "/reports/resume/1.pdf"):
            r = self.client.get(url)
            self.assertTrue(r.data.startswith(b"%PDF"), url)

    def test_dashboard_numbers_come_from_db(self):
        self.client.post("/matching/run", data={"job_id": 1})
        stats = services.dashboard_stats(self.db(), 1)
        self.assertEqual((stats["totals"]["resumes"], stats["totals"]["jobs"], stats["totals"]["matches"]), (2, 1, 2))
        self.assertEqual(stats["top_candidates"][0]["name"], "Jane Tester")
        self.assertIsNotNone(stats["totals"]["avg_score"])

    def test_demo_data_loader_is_repeatable(self):
        c2 = self.app.test_client(); register(c2, "demo", "d@example.com")
        c2.post("/settings/demo-data")
        n1 = self.db().execute("SELECT COUNT(*) FROM resumes WHERE user_id=2").fetchone()[0]
        c2.post("/settings/demo-data")
        n2 = self.db().execute("SELECT COUNT(*) FROM resumes WHERE user_id=2").fetchone()[0]
        self.assertEqual((n1, n2), (8, 8))


class AccessControlTests(BaseCase):
    def test_users_cannot_see_each_others_data(self):
        upload(self.client, "a.pdf", make_pdf_bytes())
        self.client.post("/jobs/new", data=JOB_FORM)
        self.client.post("/matching/run", data={"job_id": 1})
        other = self.app.test_client()
        register(other, "mallory", "m@example.com")
        for url in ("/resumes/1", "/resumes/1/file", "/reports/resume/1.pdf", "/jobs/1/edit", "/matching/result/1",
                    "/reports/ranking/1.csv", "/skill-gap?resume_id=1&job_id=1", "/ranking?job_id=1"):
            self.assertEqual(other.get(url).status_code, 404, url)
        for url in ("/resumes/1/delete", "/jobs/1/delete", "/ranking/flag/1"):
            self.assertEqual(other.post(url).status_code, 404, url)
        self.assertEqual(self.client.get("/resumes/1").status_code, 200)

    def test_anonymous_cannot_download_files(self):
        upload(self.client, "a.pdf", make_pdf_bytes())
        self.assertEqual(self.app.test_client().get("/resumes/1/file").status_code, 302)


class CsvSafetyTests(unittest.TestCase):
    def test_formula_injection_neutralised(self):
        from modules.report_generator import csv_safe
        self.assertEqual(csv_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(csv_safe("normal"), "normal")


class CsrfTests(unittest.TestCase):
    def test_post_without_token_rejected_and_with_token_accepted(self):
        from config import TestConfig

        class Cfg(TestConfig):
            DATABASE = os.path.join(tempfile.mkdtemp(), "c.db")
            UPLOAD_FOLDER = os.path.join(tempfile.mkdtemp(), "u")
            CSRF_ENABLED = True
        from app import create_app
        client = create_app(Cfg).test_client()
        data = dict(username="csrf", email="c@example.com", password="Passw0rd123", confirm_password="Passw0rd123")
        self.assertEqual(client.post("/register", data=data).status_code, 400)
        import re
        page = client.get("/register").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([0-9a-f]+)"', page).group(1)
        self.assertEqual(client.post("/register", data={**data, "csrf_token": token}).status_code, 302)
        # every authenticated form must carry the token too
        dash = client.get("/settings").get_data(as_text=True)
        self.assertGreaterEqual(dash.count('name="csrf_token"'), 4)


if __name__ == "__main__":
    unittest.main()
