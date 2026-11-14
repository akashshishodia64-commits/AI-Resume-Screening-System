import os
import tempfile
import unittest
from datetime import date

from helpers import SAMPLE_TEXT, make_docx_bytes, make_pdf_bytes
from modules import resume_analyzer as ra
from modules import resume_parser as rp


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_pdf_extraction(self):
        text = rp.extract_text(self.write("a.pdf", make_pdf_bytes()), "pdf")
        self.assertIn("jane.tester@example.com", text)
        self.assertIn("Flask", text)

    def test_docx_extraction(self):
        text = rp.extract_text(self.write("a.docx", make_docx_bytes()), "docx")
        self.assertIn("JANE TESTER", text)
        self.assertIn("B.Tech", text)

    def test_docx_table_text_is_read(self):
        import docx, io
        d = docx.Document()
        t = d.add_table(rows=1, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "Skills", "Python, Flask, SQL and lots of other words to pass the length check"
        buf = io.BytesIO(); d.save(buf)
        text = rp.extract_text(self.write("t.docx", buf.getvalue()), "docx")
        self.assertIn("Python, Flask", text)

    def test_corrupted_pdf_rejected(self):
        with self.assertRaises(rp.ResumeParseError):
            rp.extract_text(self.write("bad.pdf", b"%PDF-1.4 this is not really a pdf"), "pdf")

    def test_corrupted_docx_rejected(self):
        with self.assertRaises(rp.ResumeParseError):
            rp.extract_text(self.write("bad.docx", b"PK\x03\x04garbage"), "docx")

    def test_empty_document_rejected(self):
        with self.assertRaises(rp.ResumeParseError):
            rp.extract_text(self.write("e.docx", make_docx_bytes(["hi"])), "docx")


class UploadValidationTests(unittest.TestCase):
    def test_accepts_valid(self):
        self.assertEqual(rp.validate_upload("cv.PDF", make_pdf_bytes()), "pdf")
        self.assertEqual(rp.validate_upload("cv.docx", make_docx_bytes()), "docx")

    def test_rejects_bad_extension(self):
        with self.assertRaises(rp.UploadValidationError):
            rp.validate_upload("cv.exe", b"MZ....")

    def test_rejects_empty_and_oversize(self):
        with self.assertRaises(rp.UploadValidationError):
            rp.validate_upload("cv.pdf", b"")
        with self.assertRaises(rp.UploadValidationError):
            rp.validate_upload("cv.pdf", b"%PDF-" + b"0" * 2000, max_size=1000)

    def test_rejects_spoofed_signature(self):
        with self.assertRaises(rp.UploadValidationError):
            rp.validate_upload("cv.pdf", b"just text pretending to be a pdf")
        with self.assertRaises(rp.UploadValidationError):
            rp.validate_upload("cv.docx", b"plain text")


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.info = ra.analyze_resume("\n".join(SAMPLE_TEXT))

    def test_contact_details(self):
        self.assertEqual(self.info["name"], "Jane Tester")
        self.assertEqual(self.info["email"], "jane.tester@example.com")
        self.assertEqual(self.info["phone"], "+91 98765 43210")

    def test_education_level(self):
        self.assertEqual(self.info["highest_education"], "Bachelor's")
        self.assertEqual(self.info["highest_education_level"], 2)

    def test_experience_years_from_dates(self):
        self.assertAlmostEqual(self.info["total_experience_years"], 3.0, delta=0.1)

    def test_overlapping_ranges_not_double_counted(self):
        lines = ["Jan 2020 - Dec 2021", "Jun 2020 - Dec 2021"]
        self.assertAlmostEqual(ra.estimate_experience_years(lines, "", today=date(2024, 1, 1)), 2.0, delta=0.1)

    def test_present_uses_today(self):
        yrs = ra.estimate_experience_years(["Jan 2023 - Present"], "", today=date(2025, 1, 1))
        self.assertAlmostEqual(yrs, 2.0, delta=0.15)

    def test_skills_detected(self):
        names = {s["name"] for s in self.info["skills"]}
        self.assertTrue({"Python", "Flask", "SQL", "Git", "Docker", "REST API"} <= names)

    def test_degree_false_positives(self):
        self.assertEqual(ra.detect_levels("will be great with MS Office; Scrum Master"), set())
        self.assertEqual(ra.detect_levels("B.E. in Electronics"), {2})
        self.assertEqual(ra.detect_levels("Master of Science"), {3})

    def test_name_falls_back_to_email(self):
        info = ra.analyze_resume("skills: python flask sql\ncontact: priya.nair@example.com\n" + "x " * 40)
        self.assertEqual(info["name"], "Priya Nair")


if __name__ == "__main__":
    unittest.main()
