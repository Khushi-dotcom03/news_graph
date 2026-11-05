
import re
import networkx as nx
from pathlib import Path


GRAPH_PATH = Path("data/news_graph.graphml")

# Seed aliases for our initial English-Hindi demonstration.
# Later, we'll replace this tiny dictionary with scalable entity linking.
ALIASES = {
    "tata motors": "entity:org:tata_motors",
    "टाटा मोटर्स": "entity:org:tata_motors",
    "gujarat": "entity:loc:gujarat",
    "गुजरात": "entity:loc:gujarat",
}

CANONICAL_NAMES = {
    "entity:org:tata_motors": "Tata Motors",
    "entity:loc:gujarat": "Gujarat",
}


def normalize(text):
    """Normalize whitespace and case for simple matching."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def canonical_id(name, entity_type):
    """Return a stable ID for a known alias or an unseen entity."""
    key = normalize(name)

    if key in ALIASES:
        return ALIASES[key]

    slug = re.sub(r"[^\w]+", "_", key, flags=re.UNICODE).strip("_")
    return f"entity:{entity_type.lower()}:{slug}"


def add_entities(graph, entities, article_id):
    """Add entity nodes and link each article to the entities it mentions."""
    entity_ids = []

    for entity in entities:
        name = entity["name"]
        entity_type = entity["type"]
        entity_id = canonical_id(name, entity_type)

        display_name = CANONICAL_NAMES.get(entity_id, name)

        if not graph.has_node(entity_id):
            graph.add_node(
                entity_id,
                node_type="entity",
                name=display_name,
                entity_type=entity_type,
            )

        graph.add_edge(
            article_id,
            entity_id,
            relation="MENTIONS",
        )

        entity_ids.append({
            "id": entity_id,
            "name": name,
            "type": entity_type,
        })

    return entity_ids


def extract_simple_relations(text, language, entities):
    """
    Extract only relationships supported by our initial sentence patterns.

    Returns a list of proposed facts. This is a small prototype,
    not a general-purpose relation extraction model.
    """
    relations = []

    organizations = [e for e in entities if e["type"] == "ORG"]
    locations = [e for e in entities if e["type"] == "LOC"]

    if not organizations or not locations:
        return relations

    if language == "en":
        has_announcement = bool(
            re.search(r"\bannounc(?:e|ed|es|ing)\b", text, re.I)
        )
        has_factory = bool(
            re.search(r"\bfactor(?:y|ies)\b", text, re.I)
        )

    elif language == "hi":
        has_announcement = bool(
            re.search(r"घोषणा|ऐलान", text)
        )
        has_factory = bool(
            re.search(r"कारखाना|कारखाने|फैक्टरी|फैक्ट्रि", text)
        )

    else:
        return relations

    if has_announcement and has_factory:
        relations.append({
            "subject": organizations[0],
            "predicate": "ANNOUNCED",
            "object": {
                "name": "factory",
                "type": "EVENT",
            },
        })

        relations.append({
            "subject": {
                "name": "factory",
                "type": "EVENT",
            },
            "predicate": "LOCATED_IN",
            "object": locations[0],
        })

    return relations



def add_relations(graph, article_id, relations):
    """Add relations and preserve article provenance."""

    for fact in relations:
        subject = fact["subject"]
        obj = fact["object"]
        predicate = fact["predicate"]

        # Get subject ID
        if subject["type"] == "EVENT":
            subject_id = f"event:factory:{article_id}"

            if not graph.has_node(subject_id):
                graph.add_node(
                    subject_id,
                    node_type="event",
                    name="Factory announcement",
                    event_type="FACTORY_ANNOUNCEMENT",
                )
        else:
            subject_id = subject.get("id") or canonical_id(
                subject["name"], subject["type"]
            )

        # Get object ID
        if obj["type"] == "EVENT":
            object_id = f"event:factory:{article_id}"

            if not graph.has_node(object_id):
                graph.add_node(
                    object_id,
                    node_type="event",
                    name="Factory announcement",
                    event_type="FACTORY_ANNOUNCEMENT",
                )
        else:
            object_id = obj.get("id") or canonical_id(
                obj["name"], obj["type"]
            )

            if not graph.has_node(object_id):
                graph.add_node(
                    object_id,
                    node_type="entity",
                    name=CANONICAL_NAMES.get(
                        object_id, obj["name"]
                    ),
                    entity_type=obj["type"],
                )

        # Add the relation
        graph.add_edge(
            subject_id,
            object_id,
            relation=predicate,
            source_article=article_id,
        )

        # Link the article to the event
        if graph.nodes[object_id].get("node_type") == "event":
            graph.add_edge(
                article_id,
                object_id,
                relation="REPORTS_ON",
                source_article=article_id,
            )


def load_graph():
    """Load the saved graph, or start a new one."""
    if GRAPH_PATH.exists():
        return nx.read_graphml(GRAPH_PATH)

    return nx.MultiDiGraph()


def save_graph(graph):
    """Persist the graph between runs."""
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, GRAPH_PATH)


def process_article(graph, article, entities):
    """Add one previously unseen article to the graph."""
    article_id = f"article:{article['id']}"

    if graph.has_node(article_id):
        print(f"Skipping already processed article: {article['id']}")
        return False

    graph.add_node(
        article_id,
        node_type="article",
        language=article["language"],
        text=article["text"],
    )

    entity_records = add_entities(
        graph,
        entities,
        article_id,
    )

    relations = extract_simple_relations(
        article["text"],
        article["language"],
        entity_records,
    )

    add_relations(graph, article_id, relations)

    print(
        f"Processed {article['id']}: "
        f"{len(entity_records)} entities, "
        f"{len(relations)} relations"
    )

    return True