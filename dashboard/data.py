"""Read-only dashboard summaries for the saved NetworkX graph."""

import json
from datetime import datetime, timezone
from pathlib import Path

from dashboard.graph_explorer import DEFAULT_GRAPH_PATH, load_graph


def _edges(graph):
    if graph.is_multigraph():
        yield from graph.edges(keys=True, data=True)
    else:
        for source, target, data in graph.edges(data=True):
            yield source, target, 0, data


def parse_publication_date(value):
    """Parse common NewsData date formats; return None when unavailable."""
    if not value or str(value).strip().casefold() in {"unknown", "none", "null"}:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def graph_summary(graph):
    """Return stable dashboard metrics and article/entity aggregates."""
    node_types = {}
    for node_id, data in graph.nodes(data=True):
        node_types[node_id] = data.get("node_type", "unknown")

    articles = [
        (node_id, data)
        for node_id, data in graph.nodes(data=True)
        if data.get("node_type") == "article"
    ]
    entities = [
        (node_id, data)
        for node_id, data in graph.nodes(data=True)
        if data.get("node_type") == "entity"
    ]
    events = [
        (node_id, data)
        for node_id, data in graph.nodes(data=True)
        if data.get("node_type") == "event"
    ]

    languages = {"en": 0, "hi": 0, "other": 0}
    for _, data in articles:
        language = data.get("language", "other")
        languages[language if language in {"en", "hi"} else "other"] += 1

    entity_types = {"PER": 0, "ORG": 0, "LOC": 0, "other": 0}
    for _, data in entities:
        entity_type = data.get("entity_type", "other")
        entity_types[entity_type if entity_type in {"PER", "ORG", "LOC"} else "other"] += 1

    mentions = {node_id: set() for node_id, _ in entities}
    relation_count = 0
    for source, target, _, data in _edges(graph):
        relation = data.get("relation", "")
        if relation == "MENTIONS" and node_types.get(target) == "entity":
            mentions.setdefault(target, set()).add(source)
        elif relation and relation != "REPORTS_ON":
            relation_count += 1

    article_lookup = dict(articles)
    entity_rows = []
    for node_id, data in entities:
        article_ids = mentions.get(node_id, set())
        entity_rows.append({
            "id": node_id,
            "name": data.get("name", node_id),
            "type": data.get("entity_type", "other"),
            "mentions": len(article_ids),
            "languages": sorted({article_lookup[item].get("language", "other") for item in article_ids if item in article_lookup}),
        })
    entity_rows.sort(key=lambda row: (-row["mentions"], str(row["name"]).casefold()))

    article_rows = []
    for node_id, data in articles:
        parsed = parse_publication_date(data.get("publication_date"))
        article_rows.append({
            "id": node_id,
            "title": data.get("title") or node_id,
            "source": data.get("source", "unknown"),
            "publication_date": data.get("publication_date", "unknown"),
            "parsed_date": parsed,
            "language": data.get("language", "other"),
            "url": data.get("url", ""),
        })
    article_rows.sort(key=lambda row: row["parsed_date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    return {
        "articles": len(articles),
        "entities": len(entities),
        "relationships": relation_count,
        "events": len(events),
        "languages": languages,
        "entity_types": entity_types,
        "top_entities": entity_rows,
        "recent_articles": article_rows,
        "graph_updates": recent_graph_updates(graph),
    }


def recent_graph_updates(graph, limit=10):
    """Read real saved update history; legacy graphs return an empty list."""
    raw = graph.graph.get("update_history", "[]")
    try:
        updates = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(updates, list):
        return []
    return list(reversed(updates[-limit:]))


def load_dashboard_graph(path=DEFAULT_GRAPH_PATH):
    return load_graph(Path(path))
