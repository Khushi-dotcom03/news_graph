import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import networkx as nx
from graph_builder import add_relations
from relation_extractor import extract_relations


class RelationExtractionTests(unittest.TestCase):
    def setUp(self):
        self.entities = [
            {"id": "entity:org:acme", "name": "Acme", "type": "ORG"},
            {"id": "entity:org:beta", "name": "Beta Corp", "type": "ORG"},
            {"id": "entity:per:lee", "name": "Lee", "type": "PER"},
            {"id": "entity:loc:delhi", "name": "Delhi", "type": "LOC"},
        ]

    def test_extracts_supported_english_relationship_with_sentence_evidence(self):
        facts = extract_relations(
            "Acme partnered with Beta Corp.", "en", self.entities, "article:1"
        )
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["predicate"], "PARTNERED_WITH")
        self.assertEqual(facts[0]["evidence"], "Acme partnered with Beta Corp.")

    def test_extracts_hindi_partnership_with_subject_order(self):
        entities = [
            {"id": "entity:org:acme", "name": "एक्स", "type": "ORG"},
            {"id": "entity:org:beta", "name": "वाई", "type": "ORG"},
        ]
        facts = extract_relations("एक्स ने वाई के साथ साझेदारी की।", "hi", entities)
        self.assertEqual([fact["predicate"] for fact in facts], ["PARTNERED_WITH"])
        self.assertEqual(facts[0]["subject"]["name"], "एक्स")
        self.assertEqual(facts[0]["object"]["name"], "वाई")

    def test_relation_does_not_cross_sentence_boundary(self):
        facts = extract_relations(
            "Acme made a statement. Beta Corp expanded.", "en", self.entities
        )
        self.assertEqual(facts, [])

    def test_each_event_has_sentence_specific_id_and_graph_evidence(self):
        text = "Acme announced a plant in Delhi. Acme opened an office in Delhi."
        facts = extract_relations(text, "en", self.entities, "article:1")
        event_facts = [fact for fact in facts if fact["object"]["type"] == "EVENT"]
        self.assertEqual(len(event_facts), 2)
        self.assertNotEqual(event_facts[0]["object"]["id"], event_facts[1]["object"]["id"])

        graph = nx.MultiDiGraph()
        graph.add_node("article:1", node_type="article")
        add_relations(graph, "article:1", facts)
        event_nodes = [node for node, data in graph.nodes(data=True) if data.get("node_type") == "event"]
        self.assertEqual(len(event_nodes), 2)
        self.assertTrue(all(graph.nodes[node].get("evidence") for node in event_nodes))


if __name__ == "__main__":
    unittest.main()
