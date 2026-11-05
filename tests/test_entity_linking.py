import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from entity_linker import canonical_entity_id
from nlp import clean_entities
from graph_builder import add_entities
import networkx as nx


class EntityLinkingTests(unittest.TestCase):
    def test_explicit_english_hindi_aliases_share_ids(self):
        self.assertEqual(
            canonical_entity_id("Tata Motors", "ORG"),
            canonical_entity_id("टाटा मोटर्स", "ORG"),
        )
        self.assertEqual(
            canonical_entity_id("Gujarat", "LOC"),
            canonical_entity_id("गुजरात", "LOC"),
        )

    def test_unregistered_similar_names_are_not_fuzzy_merged(self):
        self.assertNotEqual(
            canonical_entity_id("Tata Motor", "ORG"),
            canonical_entity_id("टाटा मोटर्स", "ORG"),
        )

    def test_entity_type_is_part_of_linking_key(self):
        self.assertNotEqual(
            canonical_entity_id("Gujarat", "ORG"),
            canonical_entity_id("Gujarat", "LOC"),
        )

    def test_graph_stores_bilingual_aliases_on_one_entity(self):
        graph = nx.MultiDiGraph()
        graph.add_node("article:test", node_type="article")
        add_entities(
            graph,
            [
                {"name": "Tata Motors", "type": "ORG", "confidence": 0.9},
                {"name": "टाटा मोटर्स", "type": "ORG", "confidence": 0.9},
            ],
            "article:test",
        )
        entity_nodes = [
            node for node, data in graph.nodes(data=True)
            if data.get("node_type") == "entity"
        ]
        self.assertEqual(entity_nodes, ["entity:org:tata_motors"])
        self.assertIn("Tata Motors", graph.nodes[entity_nodes[0]]["aliases"])
        self.assertIn("टाटा मोटर्स", graph.nodes[entity_nodes[0]]["aliases"])

    def test_clean_entities_merges_fragments_and_filters_noise(self):
        text = "Tata Motors announced the election in Gujarat."
        results = [
            {"start": 0, "end": 4, "entity_group": "ORG", "score": 0.92},
            {"start": 5, "end": 11, "entity_group": "ORG", "score": 0.88},
            {"start": 26, "end": 34, "entity_group": "MISC", "score": 0.99},
            {"start": 38, "end": 45, "entity_group": "LOC", "score": 0.95},
        ]
        self.assertEqual(
            clean_entities(results, text),
            [
                {"name": "Tata Motors", "type": "ORG", "confidence": 0.88},
                {"name": "Gujarat", "type": "LOC", "confidence": 0.95},
            ],
        )

    def test_clean_entities_ignores_malformed_model_spans(self):
        results = [
            {"start": "bad", "end": 3, "entity_group": "ORG", "score": 0.9},
            {"start": 0, "end": 4, "entity_group": "ORG", "score": "not-a-score"},
            {"start": 0, "end": 4, "entity_group": "ORG", "score": float("nan")},
            None,
        ]
        self.assertEqual(clean_entities(results, "Acme"), [])


if __name__ == "__main__":
    unittest.main()
