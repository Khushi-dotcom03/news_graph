import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx
from dashboard.insights import entity_insights, trending_entities


class EntityInsightsTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_node("article:recent", node_type="article", title="Recent article", source="Daily News", publication_date="2026-11-03", language="en", url="https://example.test/recent")
        self.graph.add_node("article:older", node_type="article", title="Older article", source="Hindi Wire", publication_date="2026-10-01", language="hi", url="")
        self.graph.add_node("article:unknown", node_type="article", title="Undated article", source="Wire", publication_date="unknown", language="en", url="")
        self.graph.add_node("article:future", node_type="article", title="Future article", source="Wire", publication_date="2026-11-05", language="en", url="")
        self.graph.add_node("entity:org:acme", node_type="entity", entity_type="ORG", name="Acme", aliases="Acme Corp|एक्मे")
        self.graph.add_node("entity:per:lee", node_type="entity", entity_type="PER", name="Lee", aliases="")
        self.graph.add_node("event:appointed:1", node_type="event", event_type="APPOINTMENT", name="Appointment")
        for article in ["article:recent", "article:older", "article:unknown", "article:future"]:
            self.graph.add_edge(article, "entity:org:acme", relation="MENTIONS")
        self.graph.add_edge("entity:org:acme", "entity:per:lee", relation="APPOINTED", source_article="article:recent", evidence="Acme appointed Lee.", confidence=0.68)
        self.graph.add_edge("entity:org:acme", "event:appointed:1", relation="APPOINTED", source_article="article:recent", evidence="Acme appointed Lee.", confidence=0.68)

    def test_entity_insights_include_aliases_articles_connections_and_evidence(self):
        result = entity_insights(self.graph, "entity:org:acme", window_days=7, today=date(2026, 11, 4))
        self.assertEqual(result["aliases"], ["Acme Corp", "एक्मे"])
        self.assertEqual(result["article_count"], 4)
        self.assertEqual(result["recent_mentions"], 1)
        self.assertEqual(result["articles"][0]["title"], "Future article")
        self.assertEqual(result["connected_entities"][0]["name"], "Lee")
        self.assertEqual(result["relationships"][0]["evidence"], "Acme appointed Lee.")
        self.assertEqual(result["relationships"][0]["article"]["source"], "Daily News")

    def test_trending_uses_only_dated_articles_inside_window(self):
        rows = trending_entities(self.graph, window_days=7, today=date(2026, 11, 4))
        self.assertEqual(rows, [{"id": "entity:org:acme", "name": "Acme", "type": "ORG", "articles": 1}])

    def test_unknown_entity_returns_no_insights(self):
        self.assertIsNone(entity_insights(self.graph, "missing", today=date(2026, 11, 4)))


if __name__ == "__main__":
    unittest.main()
