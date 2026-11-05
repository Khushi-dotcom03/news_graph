"""Conservative multilingual entity normalization and linking.

Only explicitly registered aliases are cross-linked. Unseen names receive
type-aware IDs; no fuzzy or transliteration-based merging is performed.
"""

import re
import unicodedata


def normalize_entity_name(name):
    """Normalize Unicode and whitespace without changing the script."""
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFKC", name)
    return re.sub(r"\s+", " ", name).strip().casefold()


# Explicit bilingual pairs for the current demonstration. Add new pairs only
# when there is evidence that both names refer to the same real-world entity.
_CANONICAL_ENTITIES = {
    "entity:org:tata_motors": {
        "type": "ORG",
        "name": "Tata Motors",
        "aliases": ("Tata Motors", "टाटा मोटर्स"),
    },
    "entity:loc:gujarat": {
        "type": "LOC",
        "name": "Gujarat",
        "aliases": ("Gujarat", "गुजरात"),
    },
}

_ALIAS_TO_ID = {
    (entity["type"], normalize_entity_name(alias)): entity_id
    for entity_id, entity in _CANONICAL_ENTITIES.items()
    for alias in entity["aliases"]
}


def canonical_entity_id(name, entity_type):
    """Return a stable type-aware ID, applying only explicit alias links."""
    normalized = normalize_entity_name(name)
    entity_type = str(entity_type or "").upper()
    known_id = _ALIAS_TO_ID.get((entity_type, normalized))
    if known_id:
        return known_id

    slug = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
    return f"entity:{entity_type.lower()}:{slug}"


def canonical_entity_name(entity_id, fallback):
    """Return the display name for a registered entity or the given name."""
    entity = _CANONICAL_ENTITIES.get(entity_id)
    return entity["name"] if entity else fallback


def registered_aliases(entity_id):
    """Return known aliases for an explicit canonical entity ID."""
    entity = _CANONICAL_ENTITIES.get(entity_id)
    return entity["aliases"] if entity else ()
