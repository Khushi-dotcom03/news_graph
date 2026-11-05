import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx
from dashboard.graph_explorer import (
    build_focused_graph,
    build_network_overview,
    list_entities,
    most_connected_entity,
)


class GraphExplorerTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_node("article:en", node_type="article", language="en", title="English story")
        self.graph.add_node("article:hi", node_type="article", language="hi", title="Hindi story")
        self.graph.add_node("entity:org:acme", node_type="entity", entity_type="ORG", name="Acme", aliases="एक्मे")
        self.graph.add_node("entity:org:beta", node_type="entity", entity_type="ORG", name="Beta Corp", aliases="")
        self.graph.add_node("entity:loc:delhi", node_type="entity", entity_type="LOC", name="Delhi", aliases="दिल्ली")
        self.graph.add_edge("entity:org:acme", "entity:org:beta", relation="PARTNERED_WITH", source_article="article:en", confidence=0.8, evidence="Acme partnered with Beta Corp.")
        self.graph.add_edge("entity:org:acme", "entity:loc:delhi", relation="LOCATED_IN", source_article="article:hi", confidence=0.7, evidence="एक्मे दिल्ली में है।")
        self.graph.add_edge("article:en", "entity:org:acme", relation="MENTIONS")
        self.graph.add_edge("article:en", "entity:org:beta", relation="MENTIONS")

    def test_search_matches_aliases(self):
        results = list_entities(self.graph, query="एक्मे", entity_types={"ORG"})
        self.assertEqual([row[0] for row in results], ["entity:org:acme"])

    def test_empty_entity_type_filter_returns_no_results(self):
        self.assertEqual(list_entities(self.graph, entity_types=set()), [])

    def test_initial_focus_prefers_an_entity_with_relationships(self):
        self.assertEqual(most_connected_entity(self.graph), "entity:org:acme")

    def test_filters_direct_relationships_by_type_language_and_article(self):
        focused = build_focused_graph(
            self.graph,
            "entity:org:acme",
            relation_types={"PARTNERED_WITH", "LOCATED_IN"},
            language="en",
            max_nodes=10,
        )
        self.assertEqual(set(focused.nodes), {"entity:org:acme", "entity:org:beta"})
        self.assertEqual(list(focused.edges(data="relation"))[0][2], "PARTNERED_WITH")

    def test_empty_relation_filter_returns_focus_only(self):
        focused = build_focused_graph(
            self.graph,
            "entity:org:acme",
            relation_types=set(),
        )
        self.assertEqual(list(focused.nodes), ["entity:org:acme"])
        self.assertEqual(focused.number_of_edges(), 0)

    def test_article_filter_shows_mentioned_entities_and_article_context(self):
        focused = build_focused_graph(
            self.graph,
            "entity:org:acme",
            relation_types={"MENTIONS"},
            language="en",
            source_article="article:en",
        )
        self.assertIn("article:en", focused)
        self.assertIn("entity:org:beta", focused)
        self.assertEqual(focused.number_of_edges(), 2)

    def test_article_filter_keeps_evidenced_relationship_edges(self):
        focused = build_focused_graph(
            self.graph,
            "entity:org:acme",
            relation_types={"PARTNERED_WITH"},
            language="en",
            source_article="article:en",
        )
        self.assertEqual(set(focused.nodes), {"entity:org:acme", "entity:org:beta"})
        self.assertEqual(list(focused.edges(data="relation"))[0][2], "PARTNERED_WITH")

    def test_node_limit_keeps_focus(self):
        focused = build_focused_graph(
            self.graph,
            "entity:org:acme",
            relation_types={"PARTNERED_WITH", "LOCATED_IN"},
            max_nodes=2,
        )
        self.assertLessEqual(focused.number_of_nodes(), 2)
        self.assertIn("entity:org:acme", focused)

    def test_network_overview_includes_articles_and_mentions_within_limit(self):
        overview = build_network_overview(
            self.graph,
            max_nodes=5,
            entity_types={"ORG", "LOC"},
            relation_types={"MENTIONS", "PARTNERED_WITH", "LOCATED_IN"},
        )
        self.assertLessEqual(overview.number_of_nodes(), 5)
        self.assertIn("article:en", overview)
        self.assertTrue(any(data.get("relation") == "MENTIONS" for _, _, data in overview.edges(data=True)))
        self.assertTrue(any(data.get("relation") == "PARTNERED_WITH" for _, _, data in overview.edges(data=True)))

    def test_network_overview_source_filter_keeps_relation_evidence_without_mentions(self):
        overview = build_network_overview(
            self.graph,
            max_nodes=10,
            entity_types={"ORG"},
            source_article="article:en",
            relation_types={"PARTNERED_WITH"},
        )
        self.assertEqual(set(overview.nodes), {"entity:org:acme", "entity:org:beta"})
        self.assertEqual(list(overview.edges(data="relation"))[0][2], "PARTNERED_WITH")


if __name__ == "__main__":
    unittest.main()
