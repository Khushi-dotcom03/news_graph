"""Entity-focused article, relationship, evidence, and trend summaries."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from dashboard.data import parse_publication_date


def _edges(graph):
    if graph.is_multigraph():
        yield from graph.edges(keys=True, data=True)
    else:
        for source, target, data in graph.edges(data=True):
            yield source, target, 0, data


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.today()


def _article_row(graph, article_id):
    data = graph.nodes.get(article_id, {})
    published = parse_publication_date(data.get("publication_date"))
    return {
        "id": article_id,
        "title": data.get("title") or article_id,
        "source": data.get("source", "unknown"),
        "publication_date": data.get("publication_date", "unknown"),
        "date": published.date() if published else None,
        "language": data.get("language", "unknown"),
        "url": data.get("url", ""),
    }


def entity_insights(graph, entity_id, window_days=30, today=None):
    """Summarize one entity using only information stored in the graph."""
    if entity_id not in graph or graph.nodes[entity_id].get("node_type") != "entity":
        return None
    today = _as_date(today or date.today())
    window_days = max(1, int(window_days))
    start_date = today - timedelta(days=window_days - 1)
    entity = graph.nodes[entity_id]
    mention_article_ids = set()
    relations = []
    connected = {}

    for source, target, _, data in _edges(graph):
        relation = data.get("relation", "")
        if relation == "MENTIONS" and target == entity_id and graph.nodes[source].get("node_type") == "article":
            mention_article_ids.add(source)
            continue
        if entity_id not in {source, target} or relation in {"MENTIONS", "REPORTS_ON"}:
            continue

        other_id = target if source == entity_id else source
        other_data = graph.nodes.get(other_id, {})
        article_id = data.get("source_article")
        if not article_id and graph.nodes.get(source, {}).get("node_type") == "article":
            article_id = source
        article = _article_row(graph, article_id) if article_id in graph else None
        relation_row = {
            "subject": graph.nodes[source].get("name", source),
            "predicate": relation,
            "object": other_data.get("name", other_id),
            "other_id": other_id,
            "other_type": other_data.get("entity_type") or other_data.get("event_type") or other_data.get("node_type", "unknown"),
            "evidence": data.get("evidence", ""),
            "confidence": data.get("confidence"),
            "article": article,
        }
        relations.append(relation_row)
        if other_data.get("node_type") == "entity":
            connected[other_id] = {
                "id": other_id,
                "name": other_data.get("name", other_id),
                "type": other_data.get("entity_type", "unknown"),
                "relation": relation,
            }

    articles = [_article_row(graph, article_id) for article_id in mention_article_ids]
    articles.sort(key=lambda row: row["date"] or date.min, reverse=True)
    mentions_by_date = Counter(
        row["date"] for row in articles
        if row["date"] and start_date <= row["date"] <= today
    )
    timeseries = [
        {"date": start_date + timedelta(days=offset), "mentions": mentions_by_date.get(start_date + timedelta(days=offset), 0)}
        for offset in range(window_days)
    ]

    aliases = entity.get("aliases", "")
    if isinstance(aliases, str):
        aliases = sorted(set(alias.strip() for alias in aliases.split("|") if alias.strip()))
    elif not isinstance(aliases, (list, tuple, set)):
        aliases = []

    relations.sort(
        key=lambda row: (
            row["article"]["date"] if row["article"] and row["article"]["date"] else date.min,
            row["predicate"],
        ),
        reverse=True,
    )
    return {
        "id": entity_id,
        "name": entity.get("name", entity_id),
        "type": entity.get("entity_type", "unknown"),
        "aliases": list(aliases),
        "article_count": len(mention_article_ids),
        "recent_mentions": sum(mentions_by_date.values()),
        "articles": articles,
        "connected_entities": sorted(connected.values(), key=lambda row: str(row["name"]).casefold()),
        "relationships": relations,
        "trend_start": start_date,
        "trend_end": today,
        "timeseries": timeseries,
        "dated_mentions": sum(mentions_by_date.values()),
    }


def trending_entities(graph, window_days=30, today=None, limit=10):
    """Rank entities by distinct article mentions with valid dates in a window."""
    today = _as_date(today or date.today())
    window_days = max(1, int(window_days))
    start_date = today - timedelta(days=window_days - 1)
    article_mentions = {}
    for source, target, _, data in _edges(graph):
        if data.get("relation") != "MENTIONS":
            continue
        if graph.nodes.get(source, {}).get("node_type") != "article":
            continue
        if graph.nodes.get(target, {}).get("node_type") != "entity":
            continue
        published = parse_publication_date(graph.nodes[source].get("publication_date"))
        if published and start_date <= published.date() <= today:
            article_mentions.setdefault(target, set()).add(source)

    ranked = [
        {
            "id": entity_id,
            "name": graph.nodes[entity_id].get("name", entity_id),
            "type": graph.nodes[entity_id].get("entity_type", "unknown"),
            "articles": len(article_ids),
        }
        for entity_id, article_ids in article_mentions.items()
    ]
    ranked.sort(key=lambda row: (-row["articles"], str(row["name"]).casefold()))
    return ranked[:max(0, limit)]
