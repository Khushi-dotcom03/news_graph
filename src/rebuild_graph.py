
import networkx as nx
from pathlib import Path

from nlp import extract_entities
from graph_builder import process_article

OLD_PATH = Path("data/news_graph.graphml")
NEW_PATH = Path("data/news_graph_rebuilt.graphml")


def rebuild():
    old_graph = nx.read_graphml(OLD_PATH)
    new_graph = nx.MultiDiGraph()

    articles = [
        (node, data)
        for node, data in old_graph.nodes(data=True)
        if data.get("node_type") == "article"
    ]

    print(f"Articles to reprocess: {len(articles)}")

    for node_id, data in articles:
        article = {
            "id": data.get("article_id", node_id.replace("article:", "")),
            "language": data.get("language", "en"),
            "text": data.get("text", ""),
            "source": data.get("source", "unknown"),
            "publication_date": data.get("publication_date", "unknown"),
        }

        if not article["text"].strip():
            print("Skipping empty article:", article["id"])
            continue

        entities = extract_entities(
            article["text"],
            article["language"]
        )

        process_article(new_graph, article, entities)

    nx.write_graphml(new_graph, NEW_PATH)

    print("\nRebuild completed!")
    print("New nodes:", new_graph.number_of_nodes())
    print("New edges:", new_graph.number_of_edges())
    print("Saved to:", NEW_PATH)


if __name__ == "__main__":
    rebuild()
