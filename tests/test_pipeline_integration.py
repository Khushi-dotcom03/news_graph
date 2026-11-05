import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import fetch_news
import graph_builder
import main as pipeline_main
from dashboard.data import graph_summary, load_dashboard_graph
from dashboard.graph_explorer import list_entities, load_graph
from dashboard.insights import entity_insights


def api_response(results):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "success", "results": results}
    return response


class PipelineIntegrationTests(unittest.TestCase):
    def test_fetch_news_uses_mocked_english_and_hindi_responses_and_deduplicates(self):
        en_payload = [
            {
                "article_id": "en-1",
                "title": "<b>Acme</b> partnered with Beta",
                "description": "Read more",
                "content": "Acme partnered with Beta in Delhi.",
                "source_id": "english-wire",
                "pubDate": "2026-11-04T10:00:00Z",
                "link": "https://news.test/en-story/?utm_source=feed",
            },
            {
                "article_id": "en-duplicate",
                "title": "Duplicate feed result",
                "description": "",
                "content": "Duplicate body text.",
                "source_id": "english-wire",
                "pubDate": "2026-11-04T10:00:00Z",
                "link": "https://news.test/en-story/",
            },
        ]
        hi_payload = [{
            "article_id": "hi-1",
            "title": "टाटा मोटर्स ने महिंद्रा के साथ साझेदारी की",
            "description": "",
            "content": "टाटा मोटर्स ने महिंद्रा के साथ साझेदारी की।",
            "source_id": "hindi-wire",
            "pubDate": "2026-11-04T11:00:00Z",
            "link": "https://news.test/hi-story/",
        }]

        with patch.object(fetch_news, "API_KEY", "fake-test-key"), patch.object(
            fetch_news.requests, "get", side_effect=[api_response(en_payload), api_response(hi_payload)]
        ) as get:
            articles = fetch_news.fetch_news()

        self.assertEqual(get.call_count, 2)
        self.assertEqual({item["language"] for item in articles}, {"en", "hi"})
        self.assertEqual({item["id"] for item in articles}, {"en-1", "hi-1"})
        english = next(item for item in articles if item["language"] == "en")
        self.assertIn("Acme", english["text"])
        self.assertNotIn("<b>", english["text"])
        self.assertEqual(english["source"], "english-wire")
        self.assertEqual(english["publication_date"], "2026-11-04T10:00:00Z")
        self.assertEqual(english["dedupe_key"], "https://news.test/en-story")

    def test_incremental_main_saves_bilingual_metadata_entities_relations_and_history(self):
        articles = [
            {
                "id": "en-int-1", "language": "en",
                "title": "Acme partnered with Beta in Delhi",
                "text": "Acme partnered with Beta in Delhi.",
                "source": "english-wire", "publication_date": "2026-11-04T10:00:00Z",
                "url": "https://news.test/en-int-1", "dedupe_key": "https://news.test/en-int-1",
            },
            {
                "id": "hi-int-1", "language": "hi",
                "title": "टाटा मोटर्स ने महिंद्रा के साथ साझेदारी की",
                "text": "टाटा मोटर्स ने महिंद्रा के साथ साझेदारी की।",
                "source": "hindi-wire", "publication_date": "2026-11-04T11:00:00Z",
                "url": "https://news.test/hi-int-1", "dedupe_key": "https://news.test/hi-int-1",
            },
        ]
        entity_predictions = {
            "en": [
                {"name": "Acme", "type": "ORG", "confidence": 0.91},
                {"name": "Beta", "type": "ORG", "confidence": 0.89},
                {"name": "Delhi", "type": "LOC", "confidence": 0.94},
            ],
            "hi": [
                {"name": "टाटा मोटर्स", "type": "ORG", "confidence": 0.93},
                {"name": "महिंद्रा", "type": "ORG", "confidence": 0.90},
            ],
        }

        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            graph_path = Path(temp_dir) / "integration.graphml"
            with patch.object(graph_builder, "GRAPH_PATH", graph_path), patch.object(
                pipeline_main, "fetch_news", return_value=articles
            ), patch.object(
                pipeline_main, "extract_entities",
                side_effect=lambda text, language: entity_predictions[language],
            ) as extract:
                pipeline_main.main()
                self.assertEqual(extract.call_count, 2)
                first = nx.read_graphml(graph_path)
                node_count, edge_count = first.number_of_nodes(), first.number_of_edges()
                pipeline_main.main()
                self.assertEqual(extract.call_count, 2, "saved articles must not rerun NER")

            graph = nx.read_graphml(graph_path)
            self.assertEqual(graph.number_of_nodes(), node_count)
            self.assertEqual(graph.number_of_edges(), edge_count)
            for article in articles:
                node_id = f"article:{article['id']}"
                self.assertTrue(graph.has_node(node_id))
                metadata = graph.nodes[node_id]
                self.assertEqual(metadata["language"], article["language"])
                self.assertEqual(metadata["title"], article["title"])
                self.assertEqual(metadata["source"], article["source"])
                self.assertEqual(metadata["publication_date"], article["publication_date"])
                self.assertEqual(metadata["url"], article["url"])
                self.assertEqual(metadata["text"], article["text"])

            relations = [data for _, _, data in graph.edges(data=True) if data.get("relation") == "PARTNERED_WITH"]
            self.assertEqual(len(relations), 2)
            self.assertTrue(all(data.get("evidence") for data in relations))
            self.assertTrue(all(data.get("source_article") in {"article:en-int-1", "article:hi-int-1"} for data in relations))
            self.assertTrue(all(data.get("confidence") for data in relations))
            self.assertTrue(graph.has_node("entity:org:tata_motors"))
            mentions = [data for _, _, data in graph.edges(data=True) if data.get("relation") == "MENTIONS"]
            self.assertEqual(len(mentions), 5)
            self.assertEqual(len(__import__("json").loads(graph.graph["update_history"])), 2)
            self.assertEqual(__import__("json").loads(graph.graph["update_history"])[1]["added_articles"], 0)

    def test_main_skips_a_second_article_with_same_url_before_ner(self):
        articles = [
            {"id": "first", "language": "en", "title": "Acme", "text": "Acme.", "dedupe_key": "same-url", "url": "https://news.test/story"},
            {"id": "second", "language": "en", "title": "Acme copy", "text": "Acme.", "dedupe_key": "same-url", "url": "https://news.test/story?tracking=1"},
        ]
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            with patch.object(graph_builder, "GRAPH_PATH", Path(temp_dir) / "dedupe.graphml"), patch.object(
                pipeline_main, "fetch_news", return_value=articles
            ), patch.object(pipeline_main, "extract_entities", return_value=[]) as extract:
                pipeline_main.main()
                self.assertEqual(extract.call_count, 1)
            graph = nx.read_graphml(Path(temp_dir) / "dedupe.graphml")
            saved_articles = [node for node, data in graph.nodes(data=True) if data.get("node_type") == "article"]
            self.assertEqual(saved_articles, ["article:first"])

    def test_both_existing_graphml_files_load_without_file_or_data_changes(self):
        for filename in ("news_graph.graphml", "news_graph_rebuilt.graphml"):
            path = PROJECT_ROOT / "data" / filename
            original_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            direct = nx.read_graphml(path)
            explorer = load_graph(path)
            dashboard_graph = load_dashboard_graph(path)
            self.assertEqual((direct.number_of_nodes(), direct.number_of_edges()), (explorer.number_of_nodes(), explorer.number_of_edges()))
            self.assertEqual((direct.number_of_nodes(), direct.number_of_edges()), (dashboard_graph.number_of_nodes(), dashboard_graph.number_of_edges()))
            self.assertGreater(direct.number_of_nodes(), 0)
            self.assertGreater(direct.number_of_edges(), 0)
            summary = graph_summary(dashboard_graph)
            self.assertEqual(summary["articles"], sum(data.get("node_type") == "article" for _, data in direct.nodes(data=True)))
            self.assertTrue(list_entities(direct))
            selected_id = list_entities(direct)[0][0]
            self.assertIsNotNone(entity_insights(direct, selected_id))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original_digest)


if __name__ == "__main__":
    unittest.main()
