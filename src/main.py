
from fetch_news import fetch_news

from nlp import extract_entities
from graph_builder import (
    load_graph,
    save_graph,
    process_article,
    record_graph_update,
)


def main():
    articles = fetch_news()
    graph = load_graph()
    added_articles = 0
    skipped_articles = 0

    if not articles:
        print("No new feed items were fetched.")

    for article in articles:
        article_id = f"article:{article['id']}"

        # Don't run the NLP models again for saved articles.
        if graph.has_node(article_id):
            print(f"Already processed: {article['id']}")
            skipped_articles += 1
            continue

        dedupe_key = article.get("dedupe_key", "")
        if dedupe_key and any(
            data.get("node_type") == "article"
            and data.get("dedupe_key") == dedupe_key
            for _, data in graph.nodes(data=True)
        ):
            print(f"Already stored article URL: {article['url']}")
            skipped_articles += 1
            continue

        entities = extract_entities(
            article["text"],
            article["language"],
        )

        print(f"\nArticle: {article['id']}")
        print(f"Extracted entities: {len(entities)}")

        if process_article(graph, article, entities):
            added_articles += 1

    record_graph_update(graph, added_articles, skipped_articles, len(articles))
    save_graph(graph)

    print("\nGraph saved successfully.")
    print(f"New articles added this update: {added_articles}")
    print(f"Already known articles skipped: {skipped_articles}")
    print("Total nodes:", graph.number_of_nodes())
    print("Total edges:", graph.number_of_edges())


if __name__ == "__main__":
    main()
