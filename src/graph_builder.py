
import json
import re
import networkx as nx
from pathlib import Path
from datetime import datetime, timezone
from entity_linker import (
    canonical_entity_id,
    canonical_entity_name,
    registered_aliases,
)
from relation_extractor import extract_relations

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_ROOT / "data" / "news_graph_rebuilt.graphml"

def normalize(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def canonical_id(name, entity_type):
    """Compatibility wrapper for the multilingual entity linker."""
    return canonical_entity_id(name, entity_type)


def add_entities(graph, entities, article_id):
    entity_records = []
    seen = set()

    for entity in entities:
        name = str(entity.get("name", "")).strip()
        entity_type = str(entity.get("type", "")).upper()
        if not name or entity_type not in {"PER", "ORG", "LOC"}:
            continue
        entity_id = canonical_id(name, entity_type)

        if not graph.has_node(entity_id):
            graph.add_node(
                entity_id,
                node_type="entity",
                name=canonical_entity_name(entity_id, name),
                entity_type=entity_type,
                aliases="|".join(sorted(set(
                    (*registered_aliases(entity_id), name)
                ))),
            )
        else:
            old_aliases = graph.nodes[entity_id].get("aliases", "")
            aliases = set(filter(None, old_aliases.split("|")))
            aliases.add(name)
            aliases.update(registered_aliases(entity_id))
            graph.nodes[entity_id]["aliases"] = "|".join(sorted(aliases))

        if entity_id in seen:
            continue
        seen.add(entity_id)

        graph.add_edge(
            article_id,
            entity_id,
            relation="MENTIONS",
            confidence=float(entity.get("confidence", 0.0)),
            evidence=name,
            extraction_method="NER",
        )

        entity_records.append({
            "id": entity_id,
            "name": name,
            "type": entity_type,
            "confidence": float(entity.get("confidence", 0.0)),
        })

    return entity_records



def extract_simple_relations(text, language, entities, article_id="unknown"):
    """Backward-compatible name for the modular relation extractor."""
    return extract_relations(text, language, entities, article_id)


def add_relations(graph, article_id, relations):
    reported_events = set()

    for fact in relations:
        subject = fact["subject"]
        obj = fact["object"]
        predicate = fact["predicate"]

        event = (
            subject if subject["type"] == "EVENT"
            else obj if obj["type"] == "EVENT"
            else None
        )

        event_id = None

        if event:
            event_id = event.get("id") or f"event:{event['event_type'].lower()}:{article_id}"

            if not graph.has_node(event_id):
                graph.add_node(
                    event_id,
                    node_type="event",
                    name=event["name"].title(),
                    event_type=event["event_type"],
                    source_article=article_id,
                    evidence=fact.get("evidence", ""),
                    confidence=float(fact.get("confidence", 0.0)),
                )

        def resolve_node(item):
            if item["type"] == "EVENT":
                return event_id

            node_id = item.get("id") or canonical_id(
                item["name"], item["type"]
            )

            if not graph.has_node(node_id):
                graph.add_node(
                    node_id,
                    node_type="entity",
                    name=canonical_entity_name(node_id, item["name"]),
                    entity_type=item["type"],
                    aliases=item["name"],
                )
            elif item.get("name"):
                aliases = set(filter(None, graph.nodes[node_id].get("aliases", "").split("|")))
                aliases.add(item["name"])
                graph.nodes[node_id]["aliases"] = "|".join(sorted(aliases))

            return node_id

        subject_id = resolve_node(subject)
        object_id = resolve_node(obj)

        graph.add_edge(
            subject_id,
            object_id,
            relation=predicate,
            source_article=article_id,
            confidence=float(fact.get("confidence", 0.0)),
            evidence=fact.get("evidence", ""),
            extraction_method="rule_based",
        )

        if event_id and event_id not in reported_events:
            graph.add_edge(
                article_id,
                event_id,
                relation="REPORTS_ON",
                source_article=article_id,
            )
            reported_events.add(event_id)


def load_graph():
    if GRAPH_PATH.exists():
        return nx.read_graphml(GRAPH_PATH)

    return nx.MultiDiGraph()


def save_graph(graph):
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, GRAPH_PATH)


def record_graph_update(graph, added_articles, skipped_articles, fetched_articles):
    """Append timestamped ingestion activity to GraphML-compatible metadata."""
    raw_history = graph.graph.get("update_history", "[]")
    try:
        history = json.loads(raw_history) if isinstance(raw_history, str) else []
    except json.JSONDecodeError:
        history = []
    if not isinstance(history, list):
        history = []
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "added_articles": int(added_articles),
        "skipped_articles": int(skipped_articles),
        "fetched_articles": int(fetched_articles),
    })
    graph.graph["update_history"] = json.dumps(history[-100:], ensure_ascii=False)


def process_article(graph, article, entities):
    article_id = f"article:{article['id']}"

    # Skip an already processed article ID
    if graph.has_node(article_id):
        print(f"Skipping existing article: {article['id']}")
        return False

    # Skip an article with an already stored URL
    dedupe_key = article.get("dedupe_key", "")

    if dedupe_key:
        for node_id, data in graph.nodes(data=True):
            if (
                data.get("node_type") == "article"
                and data.get("dedupe_key") == dedupe_key
            ):
                print(f"Skipping duplicate URL: {article['id']}")
                return False

    graph.add_node(
        article_id,
        node_type="article",
        article_id=article["id"],
        title=article.get("title", ""),
        language=article["language"],
        text=article["text"],
        source=article.get("source", "unknown"),
        publication_date=article.get("publication_date", "unknown"),
        url=article.get("url", ""),
        dedupe_key=dedupe_key,
    )

    entity_records = add_entities(graph, entities, article_id)

    relations = extract_simple_relations(
        article["text"],
        article["language"],
        entity_records,
        article_id,
    )

    add_relations(graph, article_id, relations)

    print(
        f"Processed {article['id']}: "
        f"{len(entity_records)} entities, "
        f"{len(relations)} relations"
    )

    return True
