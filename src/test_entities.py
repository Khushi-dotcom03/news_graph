
import json
from pathlib import Path
from collections import Counter

from nlp import extract_entities

DATA_PATH = Path("data/sample_news.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    articles = json.load(f)

total_entities = 0
type_counts = Counter()

for article in articles:
    entities = extract_entities(
        article["text"],
        article["language"]
    )

    total_entities += len(entities)

    for entity in entities:
        type_counts[entity["type"]] += 1

    print(f"\nArticle: {article['id']}")
    print("Entities:", entities)

print("\n========== SUMMARY ==========")
print("Articles:", len(articles))
print("Total entities:", total_entities)
print("Entity types:", type_counts)
