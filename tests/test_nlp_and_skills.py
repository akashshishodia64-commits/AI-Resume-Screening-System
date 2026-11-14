import unittest

from helpers import SAMPLE_TEXT  # noqa: F401  (also sets sys.path)
from modules import nlp_processor as nlp
from modules.skill_extractor import extract_skills, normalize_skill, parse_skill_list, skill_in_text


class NlpPreprocessingTests(unittest.TestCase):
    def test_tokenize_keeps_tech_tokens(self):
        toks = nlp.tokenize("Used C++, C#, Node.js and scikit-learn.")
        for expected in ("c++", "c#", "node.js", "scikit", "learn"):
            self.assertIn(expected, toks)

    def test_stopwords_removed(self):
        out = nlp.preprocess("The candidate is working with the Python and Flask")
        self.assertEqual(out, ["python", "flask"])

    def test_clean_text_preserves_lines_when_asked(self):
        self.assertEqual(nlp.clean_text("a  b\n\n\n\nc", keep_lines=True), "a b\n\nc")
        self.assertEqual(nlp.clean_text("a  b\n c", keep_lines=False), "a b c")

    def test_keywords_ranked_by_frequency(self):
        kws = nlp.extract_keywords("flask flask flask python python sql", top_n=2)
        self.assertEqual(kws, ["flask", "python"])

    def test_empty_input(self):
        self.assertEqual(nlp.preprocess(""), [])
        self.assertEqual(nlp.clean_text(None), "")


class SkillExtractionTests(unittest.TestCase):
    def names(self, text):
        return {s["name"] for s in extract_skills(text)}

    def test_basic_extraction_and_aliases(self):
        found = self.names("Skills: python3, Flask, sklearn, RESTful APIs, PostgreSQL")
        self.assertTrue({"Python", "Flask", "Scikit-learn", "REST API", "PostgreSQL"} <= found)

    def test_word_boundaries(self):
        self.assertNotIn("Java", self.names("Expert in JavaScript"))
        self.assertNotIn("SQL", self.names("Experienced with MySQL only"))
        self.assertNotIn("JavaScript", self.names("Built services with Node.js"))
        self.assertIn("Node.js", self.names("Built services with Node.js"))

    def test_special_character_skills(self):
        self.assertTrue({"C++", "C#"} <= self.names("C++ and C# developer"))

    def test_counts(self):
        skills = {s["name"]: s["count"] for s in extract_skills("Python python PYTHON flask")}
        self.assertEqual(skills["Python"], 3)

    def test_parse_skill_list_dedupes_and_normalises(self):
        self.assertEqual(parse_skill_list("python, Flask; SQL\nrest api | python, Salesforce Apex"),
                         ["Python", "Flask", "SQL", "REST API", "Salesforce Apex"])

    def test_normalize_unknown_keeps_spelling(self):
        self.assertEqual(normalize_skill("  Salesforce Apex "), "Salesforce Apex")

    def test_skill_in_text_custom_skill(self):
        self.assertTrue(skill_in_text("worked on Salesforce Apex triggers", "Salesforce Apex"))
        self.assertFalse(skill_in_text("worked on triggers", "Salesforce Apex"))


if __name__ == "__main__":
    unittest.main()
