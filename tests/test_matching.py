import unittest

from helpers import SAMPLE_TEXT  # noqa: F401
from modules import matching_engine as me
from modules.skill_gap import analyze_skill_gap

JOB = {"title": "Python Developer",
       "description": "Build REST APIs with Flask and SQL. Machine learning is a plus.",
       "required_skills": ["Python", "Flask", "SQL", "Machine Learning", "REST API", "Git"],
       "min_experience_years": 2, "education_requirement": "Bachelor's degree"}
GOOD = {"raw_text": "Python developer with Flask, SQL and Git. Built REST APIs.", "skills": [],
        "total_experience_years": 3, "highest_education_level": 2}
BAD = {"raw_text": "Graphic designer using Photoshop and Illustrator for branding campaigns",
       "skills": [], "total_experience_years": 5, "highest_education_level": 0}


class SkillGapTests(unittest.TestCase):
    def test_spec_example(self):
        gap = analyze_skill_gap(JOB["required_skills"], "Python, Flask, SQL and Git experience")
        self.assertEqual((gap["matched_count"], gap["missing_count"], gap["match_pct"]), (4, 2, 66.67))
        self.assertEqual(set(gap["missing"]), {"Machine Learning", "REST API"})
        self.assertTrue(gap["recommendations"])

    def test_full_match_has_no_missing(self):
        gap = analyze_skill_gap(["Python"], "python")
        self.assertEqual(gap["missing"], [])
        self.assertEqual(gap["match_pct"], 100.0)

    def test_no_required_skills(self):
        self.assertIsNone(analyze_skill_gap([], "python")["match_pct"])

    def test_aliases_count_as_matches(self):
        gap = analyze_skill_gap(["REST API", "Scikit-learn"], "built restful apis with sklearn")
        self.assertEqual(gap["missing"], [])


class MatchingScoreTests(unittest.TestCase):
    def test_relevant_resume_outscores_irrelevant(self):
        good, bad = me.match_resumes(JOB, [GOOD, BAD])
        self.assertGreater(good["overall_score"], bad["overall_score"] + 30)
        self.assertEqual(bad["matched_skills"], [])

    def test_missing_skills_reported(self):
        good = me.match_resumes(JOB, [GOOD])[0]
        self.assertEqual(good["missing_skills"], ["Machine Learning"])
        self.assertEqual(good["skill_score"], 83.3)

    def test_scores_bounded_and_deterministic(self):
        a = me.match_resumes(JOB, [GOOD, BAD])
        b = me.match_resumes(JOB, [GOOD, BAD])
        self.assertEqual([r["overall_score"] for r in a], [r["overall_score"] for r in b])
        for r in a:
            self.assertTrue(0 <= r["overall_score"] <= 100)

    def test_tfidf_cosine_identical_text_is_high(self):
        sims = me.tfidf_similarities("python flask sql", ["python flask sql", "baking bread"])
        self.assertGreater(sims[0], 0.99)
        self.assertEqual(sims[1], 0.0)

    def test_tfidf_handles_empty_vocabulary(self):
        self.assertEqual(me.tfidf_similarities("the and of", ["the of"]), [0.0])

    def test_inapplicable_components_dropped_and_weights_renormalised(self):
        job = {**JOB, "required_skills": [], "min_experience_years": 0}
        res = me.match_resumes(job, [GOOD])[0]
        self.assertIsNone(res["skill_score"])
        self.assertIsNone(res["experience_score"])
        self.assertAlmostEqual(sum(res["weights_used"].values()), 1.0, places=2)

    def test_custom_weights_change_result(self):
        skills_only = me.match_resumes(JOB, [GOOD], weights={"skills": 1, "tfidf": 0, "keywords": 0, "experience": 0})[0]
        self.assertAlmostEqual(skills_only["overall_score"], skills_only["skill_score"], places=1)

    def test_experience_and_education_checks(self):
        junior = {**GOOD, "total_experience_years": 1}
        res = me.match_resumes(JOB, [junior])[0]
        self.assertEqual(res["experience_score"], 50.0)
        self.assertEqual(res["education_met"], 1)
        self.assertEqual(me.match_resumes(JOB, [BAD])[0]["education_met"], 0)

    def test_ranking_orders_and_ties(self):
        ranked = me.rank_results([{"overall_score": 50}, {"overall_score": 80}, {"overall_score": 50}])
        self.assertEqual([r["rank"] for r in ranked], [1, 2, 2])

    def test_bands(self):
        self.assertEqual(me.score_band(75)[0], "Strong alignment")
        self.assertEqual(me.score_band(10)[0], "Low alignment")


if __name__ == "__main__":
    unittest.main()
