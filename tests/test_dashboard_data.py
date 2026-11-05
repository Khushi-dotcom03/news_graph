import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import networkx as nx
from dashboard.data import graph_summary, load_dashboard_graph, recent_graph_updates
from graph_builder import record_graph_update


class DashboardDataTests(unittest.TestCase):
    def make_graph(self):
        graph = nx.MultiDiGraph()
        graph.add_node("article:1", node_type="article", language="en", title="Example story", source="Wire", publication_date="2026-11-01", url="https://example.test/news")
        graph.add_node("article:2", node_type="article", language="hi", title="समाचार", source="Wire HI", publication_date="unknown")
        graph.add_node("entity:org:acme", node_type="entity", entity_type="ORG", name="Acme", aliases="एक्मे")
        graph.add_node("entity:per:lee", node_type="entity", entity_type="PER", name="Lee", aliases="")
        graph.add_node("event:announcement:1", node_type="event", event_type="ANNOUNCEMENT")
        graph.add_edge("article:1", "entity:org:acme", relation="MENTIONS")
        graph.add_edge("article:2", "entity:org:acme", relation="MENTIONS")
        graph.add_edge("entity:org:acme", "entity:per:lee", relation="APPOINTED")
        graph.add_edge("entity:org:acme", "event:announcement:1", relation="ANNOUNCED")
        graph.add_edge("article:1", "event:announcement:1", relation="REPORTS_ON")
        return graph

    def test_summary_counts_entities_articles_relations_and_languages(self):
        summary = graph_summary(self.make_graph())
        self.assertEqual(summary["articles"], 2)
        self.assertEqual(summary["entities"], 2)
        self.assertEqual(summary["relationships"], 2)
        self.assertEqual(summary["events"], 1)
        self.assertEqual(summary["languages"]["en"], 1)
        self.assertEqual(summary["languages"]["hi"], 1)
        self.assertEqual(summary["top_entities"][0]["mentions"], 2)

    def test_update_history_is_persisted_as_graphml_compatible_metadata(self):
        graph = self.make_graph()
        record_graph_update(graph, added_articles=1, skipped_articles=2, fetched_articles=3)
        updates = recent_graph_updates(graph)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["added_articles"], 1)

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / "graph.graphml"
            nx.write_graphml(graph, path)
            restored = load_dashboard_graph(path)
        saved_updates = recent_graph_updates(restored)
        self.assertEqual(saved_updates[0]["fetched_articles"], 3)

    def test_legacy_graph_without_update_metadata_reports_no_updates(self):
        self.assertEqual(recent_graph_updates(self.make_graph()), [])


if __name__ == "__main__":
    unittest.main()
