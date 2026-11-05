"""Annotation-driven evaluation for NER and relation extraction.

No built-in labels or scores are provided. NER is exact-match on normalized
surface form and entity type. Relation evaluation uses the manually annotated
entities in each record as input, isolating relation extraction from NER.
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

from relation_extractor import extract_relations


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "data" / "evaluation_data.template.json"


def normalize_text(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", value).strip().casefold()


def calculate_prf(true_positive, false_positive, false_negative):
    """Compute micro P/R/F1; undefined denominators are returned as null."""
    tp, fp, fn = int(true_positive), int(false_positive), int(false_negative)
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    f1_denominator = 2 * tp + fp + fn
    precision = tp / precision_denominator if precision_denominator else None
    recall = tp / recall_denominator if recall_denominator else None
    f1 = 2 * tp / f1_denominator if f1_denominator else None
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def load_dataset(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "1.0":
        raise ValueError("Dataset must be a JSON object with schema_version '1.0'.")
    for key in ("ner_examples", "relation_examples"):
        if not isinstance(dataset.get(key), list):
            raise ValueError(f"Dataset field {key!r} must be a list.")
    return dataset


def _validate_example(example, task, index):
    if not isinstance(example, dict):
        raise ValueError(f"{task} example at index {index} must be an object.")
    for required in ("id", "language", "text"):
        if not isinstance(example.get(required), str) or not example[required].strip():
            raise ValueError(f"{task} example {index} needs a non-empty string {required!r}.")
    if example["language"] not in {"en", "hi"}:
        raise ValueError(f"{task} example {example['id']!r} language must be 'en' or 'hi'.")


def _entity_key(entity):
    if not isinstance(entity, dict):
        raise ValueError("Entities must be objects with text/name and type.")
    text = entity.get("text", entity.get("name", ""))
    entity_type = str(entity.get("type", "")).upper()
    if not normalize_text(text) or entity_type not in {"PER", "ORG", "LOC"}:
        raise ValueError("Entity annotations need non-empty text and type PER, ORG, or LOC.")
    return normalize_text(text), entity_type


def _endpoint_key(endpoint):
    if not isinstance(endpoint, dict):
        raise ValueError("Relation endpoints must be objects.")
    entity_type = str(endpoint.get("type", "")).upper()
    if entity_type == "EVENT":
        event_type = normalize_text(endpoint.get("event_type", ""))
        if not event_type:
            raise ValueError("EVENT endpoints need an event_type.")
        return "EVENT", event_type
    return _entity_key(endpoint)


def _relation_key(relation):
    if not isinstance(relation, dict):
        raise ValueError("Relations must be objects.")
    predicate = str(relation.get("predicate", "")).strip().upper()
    if not predicate:
        raise ValueError("Relations need a predicate.")
    return (
        _endpoint_key(relation.get("subject")),
        predicate,
        _endpoint_key(relation.get("object")),
    )


def _check_unique_ids(examples, task):
    ids = [example.get("id") for example in examples if isinstance(example, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{task} example IDs must be unique within their list.")


def evaluate_ner(examples, predictor=None):
    """Return separate exact-match scores for English and Hindi."""
    if predictor is None:
        from nlp import extract_entities
        predictor = extract_entities
    _check_unique_ids(examples, "NER")
    totals = {language: [0, 0, 0] for language in ("en", "hi")}
    counts = {language: 0 for language in ("en", "hi")}

    for index, example in enumerate(examples):
        _validate_example(example, "NER", index)
        if not isinstance(example.get("entities"), list):
            raise ValueError(f"NER example {example['id']!r} needs an entities list.")
        expected = {_entity_key(item) for item in example["entities"]}
        predicted = {_entity_key(item) for item in predictor(example["text"], example["language"])}
        tp = len(expected & predicted)
        counts[example["language"]] += 1
        totals[example["language"]][0] += tp
        totals[example["language"]][1] += len(predicted - expected)
        totals[example["language"]][2] += len(expected - predicted)

    return {
        language: {
            "evaluated_examples": counts[language],
            "metrics": calculate_prf(*totals[language]),
        }
        for language in ("en", "hi")
    }


def evaluate_relations(examples, predictor=None):
    """Score exact typed subject-predicate-object triples overall and by type."""
    if predictor is None:
        predictor = extract_relations
    _check_unique_ids(examples, "Relation")
    overall = [0, 0, 0]
    per_relation = {}
    per_language = {language: [0, 0, 0] for language in ("en", "hi")}

    for index, example in enumerate(examples):
        _validate_example(example, "Relation", index)
        entities = example.get("entities")
        relations = example.get("relations")
        if not isinstance(entities, list) or not isinstance(relations, list):
            raise ValueError(f"Relation example {example['id']!r} needs entities and relations lists.")
        for entity in entities:
            _entity_key(entity)

        predicted_relations = predictor(
            example["text"],
            example["language"],
            entities,
            example["id"],
        )
        expected_by_key = {_relation_key(item): item for item in relations}
        predicted_by_key = {_relation_key(item): item for item in predicted_relations}
        all_keys = set(expected_by_key) | set(predicted_by_key)
        tp = len(set(expected_by_key) & set(predicted_by_key))
        fp = len(set(predicted_by_key) - set(expected_by_key))
        fn = len(set(expected_by_key) - set(predicted_by_key))
        for target, values in ((overall, (tp, fp, fn)), (per_language[example["language"]], (tp, fp, fn))):
            for position, value in enumerate(values):
                target[position] += value
        for key in all_keys:
            predicate = key[1]
            counts = per_relation.setdefault(predicate, [0, 0, 0])
            if key in expected_by_key and key in predicted_by_key:
                counts[0] += 1
            elif key in predicted_by_key:
                counts[1] += 1
            else:
                counts[2] += 1

    return {
        "evaluated_examples": len(examples),
        "overall": calculate_prf(*overall),
        "by_language": {language: calculate_prf(*values) for language, values in per_language.items()},
        "by_relation": {predicate: calculate_prf(*values) for predicate, values in sorted(per_relation.items())},
    }


def evaluate_dataset(dataset, ner_predictor=None, relation_predictor=None):
    return {
        "schema_version": dataset["schema_version"],
        "ner": evaluate_ner(dataset["ner_examples"], ner_predictor),
        "relations": evaluate_relations(dataset["relation_examples"], relation_predictor),
        "notes": [
            "Scores are calculated only from manually supplied annotations.",
            "NER uses exact match after Unicode, whitespace, and case normalization.",
            "Relation evaluation uses each record's annotated entities as input, isolating relation extraction from NER.",
            "Null metrics indicate an undefined denominator or no evaluable labels; they are not zero accuracy.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_DATASET, help="Manual annotation JSON file.")
    parser.add_argument("--output", type=Path, help="Optional path for the JSON metrics report.")
    args = parser.parse_args()

    dataset = load_dataset(args.input)
    report = evaluate_dataset(dataset)
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    if not dataset["ner_examples"] and not dataset["relation_examples"]:
        print("No annotations supplied; no evaluation scores were calculated.")


if __name__ == "__main__":
    main()
