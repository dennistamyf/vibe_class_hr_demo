import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from hr_screening import (
    CriterionAssessment,
    InterviewQuestion,
    InterviewResponse,
    OpenRouterError,
    ScreeningEvaluation,
    create_bundle,
    discover_folders,
    screen_candidate,
    _contains_cv_quote,
    listing_files,
    rank_candidates,
)


def evaluation(score: float, pipeline: bool = False, year: int | None = None) -> ScreeningEvaluation:
    return ScreeningEvaluation(
        candidate_identity="Candidate",
        criteria=[CriterionAssessment(criterion="Evidence", score=3, role_or_project="Not stated", evidence="CV quote")],
        strengths=[],
        concerns=[],
        missing_information=[],
        overall_score=score,
        recommendation="Maybe",
        recommendation_reason="Relevant evidence is present. Some role details need probing.",
        direct_pipeline_ownership=pipeline,
        pipeline_ownership_evidence="CV quote" if pipeline else "No direct evidence",
        most_recent_relevant_year=year,
    )


class ScreeningTests(unittest.TestCase):
    def test_discovery_returns_only_sorted_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "batch_02").mkdir()
            (root / "batch_01").mkdir()
            (root / "notes.txt").touch()
            self.assertEqual([path.name for path in discover_folders(root)], ["batch_01", "batch_02"])

    def test_listing_requires_expected_job_and_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "listing_01"
            folder.mkdir()
            (folder / "listing_01.txt").write_text("Role", encoding="utf-8")
            (folder / "scoring template.txt").write_text("Score", encoding="utf-8")
            self.assertEqual(listing_files(folder)[2], [])
            (folder / "other.txt").write_text("Ambiguous", encoding="utf-8")
            self.assertTrue(listing_files(folder)[2])

    def test_ranking_applies_score_then_pipeline_then_year_then_filename(self) -> None:
        entries = [
            (Path("z_recent.pdf"), evaluation(90, True, 2025)),
            (Path("a_old.pdf"), evaluation(90, True, 2022)),
            (Path("b_pipeline.pdf"), evaluation(90, True, 2025)),
            (Path("top_score.pdf"), evaluation(91, False, 2020)),
        ]
        ranked = rank_candidates(entries)
        self.assertEqual([path.name for path, _ in ranked], ["top_score.pdf", "b_pipeline.pdf", "z_recent.pdf", "a_old.pdf"])

    @patch("hr_screening._openrouter_chat")
    def test_screening_rejects_evidence_not_found_in_cv(self, chat) -> None:
        result = evaluation(80).model_dump()
        result["criteria"][0]["evidence"] = "Invented experience"
        chat.side_effect = [
            json.dumps(result),
            json.dumps({"quotes": [{"criterion": "Evidence", "quote": "Invented experience"}]}),
        ]
        with self.assertRaisesRegex(OpenRouterError, "could not be verified"):
            screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV contains a real result")

    @patch("hr_screening._openrouter_chat")
    def test_screening_falls_back_to_filename_for_non_string_identity(self, chat) -> None:
        result = evaluation(80).model_dump()
        result["candidate_identity"] = {"name": "Candidate"}
        chat.return_value = json.dumps(result)
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate_file.pdf", "CV quote")
        self.assertEqual(screened.candidate_identity, "candidate file")

    @patch("hr_screening._openrouter_chat")
    def test_screening_marks_unverifiable_context_missing(self, chat) -> None:
        result = evaluation(80).model_dump()
        result["criteria"][0]["role_or_project"] = "Invented role context"
        chat.return_value = json.dumps(result)
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertEqual(screened.criteria[0].role_or_project, "Not stated")
        self.assertTrue(any("could not be verified" in item for item in screened.missing_information))

    @patch("hr_screening._openrouter_chat")
    def test_screening_removes_unverifiable_pipeline_tie_break_claim(self, chat) -> None:
        result = evaluation(80, pipeline=True).model_dump()
        result["pipeline_ownership_evidence"] = "Invented pipeline evidence"
        chat.return_value = json.dumps(result)
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertFalse(screened.direct_pipeline_ownership)
        self.assertEqual(screened.pipeline_ownership_evidence, "No direct evidence")

    @patch("hr_screening._openrouter_chat")
    def test_screening_omits_year_not_present_in_cv(self, chat) -> None:
        chat.return_value = json.dumps(evaluation(80, year=2026).model_dump())
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertIsNone(screened.most_recent_relevant_year)
        self.assertTrue(any("year was not verifiable" in item for item in screened.missing_information))

    def test_cv_quote_matching_ignores_punctuation_and_line_breaks(self) -> None:
        cv_text = "Increased win rate in the target segment by 9 percentage\npoints."
        self.assertTrue(_contains_cv_quote(cv_text, "increased win rate in the target segment, by 9 percentage points"))
        self.assertFalse(_contains_cv_quote(cv_text, "increased revenue by 9 percent"))

    @patch("hr_screening._openrouter_chat")
    def test_screening_uses_focused_quote_extraction_for_unverifiable_quotes(self, chat) -> None:
        invalid = evaluation(80).model_dump()
        invalid["criteria"][0]["evidence"] = "Invented quote"
        extracted = {"quotes": [{"criterion": "Evidence", "quote": "CV quote"}]}
        chat.side_effect = [json.dumps(invalid), json.dumps(extracted)]
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertEqual(screened.criteria[0].evidence, "CV quote")
        self.assertEqual(chat.call_count, 2)

    @patch("hr_screening._openrouter_chat")
    def test_screening_accepts_no_quote_only_for_zero_score(self, chat) -> None:
        result = evaluation(80).model_dump()
        result["criteria"][0]["score"] = 0
        result["criteria"][0]["evidence"] = "Unsupported paraphrase"
        chat.side_effect = [
            json.dumps(result),
            json.dumps({"quotes": [{"criterion": "Evidence", "quote": ""}]}),
        ]
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertEqual(screened.criteria[0].evidence, "No direct evidence in the CV.")
        self.assertTrue(any("scored 0" in item for item in screened.missing_information))

    @patch("hr_screening._openrouter_chat")
    def test_screening_normalizes_criteria_mapping(self, chat) -> None:
        result = evaluation(80).model_dump()
        criterion = result["criteria"].pop()
        criterion.pop("criterion")
        result["criteria"] = {"Evidence": criterion}
        chat.return_value = json.dumps(result)
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertEqual(screened.criteria[0].criterion, "Evidence")

    @patch("hr_screening._openrouter_chat")
    def test_screening_normalizes_scalar_narrative_fields(self, chat) -> None:
        result = evaluation(80).model_dump()
        result["strengths"] = "A verified strength."
        result["concerns"] = None
        result["missing_information"] = "No direct attribution evidence."
        chat.return_value = json.dumps(result)
        screened = screen_candidate("not-a-real-key", "model", "job", "guidance", "candidate.pdf", "CV quote")
        self.assertEqual(screened.strengths, ["A verified strength."])
        self.assertEqual(screened.concerns, [])
        self.assertEqual(screened.missing_information, ["No direct attribution evidence."])

    def test_bundle_contains_reports_and_copies_selected_cv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "candidate.pdf"
            source.write_bytes(b"fictional PDF fixture")
            response = InterviewResponse(
                questions=[InterviewQuestion(question="How?", why_this_matters="Probe the claim.", evidence_or_gap="CV quote")]
            )
            output = create_bundle(
                [(source, "CV")],
                [(source, evaluation(80))],
                1,
                {source.name: response},
                root / "output",
            )
            self.assertEqual((output / "selected_candidates" / source.name).read_bytes(), source.read_bytes())
            self.assertTrue((output / "scoring_sheet.md").is_file())
            self.assertTrue((output / "interview_questions" / "candidate.md").is_file())
            self.assertFalse(list((root / "output").glob(".hr-bundle-*")))

    @patch("hr_screening._openrouter_chat")
    def test_interview_generation_normalizes_wrapped_plan(self, chat) -> None:
        from hr_screening import generate_interview_questions

        chat.return_value = json.dumps(
            {
                "candidate": "Candidate",
                "interview_plan": {
                    "questions": [
                        {
                            "prompt": "How did you make the decision?",
                            "rationale": "Understand the trade-off.",
                            "evidence_gap": "The CV names the result but not the method.",
                        }
                    ]
                },
            }
        )
        response = generate_interview_questions("not-a-real-key", "model", "job", "guidance", evaluation(80))
        self.assertEqual(response.questions[0].question, "How did you make the decision?")
        self.assertEqual(response.questions[0].why_this_matters, "Understand the trade-off.")

    def test_failed_bundle_assembly_removes_staging_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "candidate.pdf"
            source.write_bytes(b"fictional PDF fixture")
            with self.assertRaises(KeyError):
                create_bundle([(source, "CV")], [(source, evaluation(80))], 1, {}, root / "output")
            self.assertEqual(list((root / "output").iterdir()), [])


if __name__ == "__main__":
    unittest.main()