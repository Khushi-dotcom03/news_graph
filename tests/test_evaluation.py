import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluate import calculate_prf, evaluate_ner, evaluate_relations, load_dataset


class EvaluationTests(unittest.TestCase):
    def test_prf_calculation(self):
        metrics = calculate_prf(2, 1, 2)
        self.assertEqual(metrics["precision"], 2 / 3)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertAlmostEqual(metrics["f1"], 4 / 7)

    def test_empty_annotations_have_undefined_not_invented_scores(self):
        result = evaluate_ner([])
        self.assertEqual(result["en"]["evaluated_examples"], 0)
        self.assertIsNone(result["en"]["metrics"]["f1"])
        self.assertIsNone(result["hi"]["metrics"]["precision"])

    def test_ner_metrics_are_reported_separately_by_language(self):
        examples = [
            {"id": "en-1", "language": "en", "text": "Acme named Lee in Delhi.", "entities": [
                {"text": "Acme", "type": "ORG"}, {"text": "Lee", "type": "PER"}
            ]},
            {"id": "hi-1", "language": "hi", "text": "टाटा मोटर्स ने निवेश किया।", "entities": [
                {"text": "टाटा मोटर्स", "type": "ORG"}
            ]},
        ]

        def predictor(text, language):
            if language == "en":
                return [{"name": "Acme", "type": "ORG"}, {"name": "Delhi", "type": "LOC"}]
            return [{"name": "टाटा मोटर्स", "type": "ORG"}]

        result = evaluate_ner(examples, predictor)
        self.assertEqual(result["en"]["metrics"]["true_positive"], 1)
        self.assertEqual(result["en"]["metrics"]["false_positive"], 1)
        self.assertEqual(result["en"]["metrics"]["false_negative"], 1)
        self.assertEqual(result["hi"]["metrics"]["f1"], 1.0)

    def test_relation_metrics_are_exact_and_reported_per_predicate(self):
        entities = [
            {"text": "Acme", "type": "ORG"},
            {"text": "Beta", "type": "ORG"},
            {"text": "Lee", "type": "PER"},
        ]
        examples = [{
            "id": "r-1", "language": "en", "text": "Acme acquired Beta and appointed Lee.",
            "entities": entities,
            "relations": [
                {"subject": {"text": "Acme", "type": "ORG"}, "predicate": "ACQUIRED", "object": {"text": "Beta", "type": "ORG"}},
                {"subject": {"text": "Acme", "type": "ORG"}, "predicate": "APPOINTED", "object": {"text": "Lee", "type": "PER"}},
            ],
        }]

        def predictor(text, language, annotated_entities, article_id):
            return [{
                "subject": {"name": "Acme", "type": "ORG"},
                "predicate": "ACQUIRED",
                "object": {"name": "Beta", "type": "ORG"},
            }, {
                "subject": {"name": "Acme", "type": "ORG"},
                "predicate": "WORKS_FOR",
                "object": {"name": "Beta", "type": "ORG"},
            }]

        result = evaluate_relations(examples, predictor)
        self.assertEqual(result["overall"]["true_positive"], 1)
        self.assertEqual(result["overall"]["false_positive"], 1)
        self.assertEqual(result["overall"]["false_negative"], 1)
        self.assertEqual(result["by_relation"]["APPOINTED"]["false_negative"], 1)
        self.assertEqual(result["by_relation"]["WORKS_FOR"]["false_positive"], 1)

    def test_template_is_empty_of_ground_truth(self):
        template = Path(__file__).resolve().parents[1] / "data" / "evaluation_data.template.json"
        dataset = load_dataset(template)
        self.assertEqual(dataset["ner_examples"], [])
        self.assertEqual(dataset["relation_examples"], [])


if __name__ == "__main__":
    unittest.main()
