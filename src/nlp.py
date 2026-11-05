
import re
import unicodedata
import math
from functools import lru_cache


# Confidence threshold
MIN_CONFIDENCE = 0.60

MODEL_BY_LANGUAGE = {
    "en": "dslim/bert-base-NER",
    "hi": "Lokeshwaran/xlm-roberta-base-fintuned-panx-ta-hi",
}


@lru_cache(maxsize=2)
def _get_ner_pipeline(language):
    """Load each language model only when it is first needed."""
    from transformers import pipeline

    return pipeline(
        "token-classification",
        model=MODEL_BY_LANGUAGE[language],
        aggregation_strategy="simple",
    )

# Generic terms incorrectly classified as named entities
GENERIC_TERMS = {
    "मुख्यमंत्री",
    "राष्ट्रीय अध्यक्ष",
    "प्रदेश अध्यक्ष",
    "चुनाव",
    "मिडटर्म चुनाव",
    "भारतीय",
    "मंच",
    "मि",
    "chief minister",
    "president",
    "election",
    "midterm election",
    "indian",
    "चांदी",
    "चांद",
    "चा",
    "ंदी",
    "सर्",
    "फा",
    "अंतरराष्ट्रीय बाजार",
    "सर्राफा बाजार",
    "मल्टी कमोडिटी एक्सचेंज",
}
def normalize_name(name):
    name = unicodedata.normalize("NFKC", name)
    return re.sub(r"\s+", " ", name).strip().casefold()


NORMALIZED_GENERIC_TERMS = {normalize_name(term) for term in GENERIC_TERMS}


def clean_entities(results, text):
    """
    Merge adjacent fragments of the same entity type,
    filter noisy predictions and remove duplicates.
    """

    if not isinstance(text, str) or not isinstance(results, (list, tuple)):
        return []

    valid_results = []
    for item in results:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start"), item.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        valid_results.append({**item, "start": start, "end": end, "score": score})
    results = sorted(valid_results, key=lambda item: item["start"])

    merged = []

    for result in results:

        entity_type = result.get("entity_group")

        if entity_type not in {"PER", "ORG", "LOC"}:
            continue

        start = result["start"]
        end = result["end"]
        if start < 0 or end <= start or end > len(text):
            continue

        current = {
            "start": start,
            "end": end,
            "type": entity_type,
            "confidence": result["score"]
        }

        if merged:
            previous = merged[-1]

            gap = text[previous["end"]:current["start"]]

            # Merge overlapping fragments or whitespace-separated fragments
            # from the same model entity group; preserve punctuation boundaries.
            overlaps = current["start"] <= previous["end"]
            joins_with_space = (
                not gap.strip()
                and current["start"] - previous["end"] <= 1
            )
            if previous["type"] == current["type"] and (
                overlaps or joins_with_space
            ):
                previous["end"] = max(
                    previous["end"], current["end"]
                )

                previous["confidence"] = min(
                    previous["confidence"],
                    current["confidence"]
                )

                continue

        merged.append(current)

    entities = []
    seen = set()

    for item in merged:

        name = text[item["start"]:item["end"]].strip()
        confidence = item["confidence"]

        if not name:
            continue

        if confidence < MIN_CONFIDENCE:
            continue

        normalized = normalize_name(name)

        if normalized in NORMALIZED_GENERIC_TERMS:
            continue

        if len(normalized) < 2:
            continue

        key = (normalized, item["type"])

        if key in seen:
            continue

        seen.add(key)

        entities.append({
            "name": name,
            "type": item["type"],
            "confidence": round(confidence, 4)
        })

    return entities

def extract_entities(text, language):
    """
    Extract and clean named entities from English or Hindi news.
    """

    if language not in MODEL_BY_LANGUAGE:
        raise ValueError(f"Unsupported language: {language}")
    if not isinstance(text, str) or not text.strip():
        return []

    # Remove irrelevant city-rate listing sections before NER
    if language == "hi":
        cutoff_patterns = [
            r"यहां जानें देश के बड़े शहरों",
            r"यहाँ जानें देश के बड़े शहरों",
        ]

        for pattern in cutoff_patterns:
            match = re.search(pattern, text)

            if match:
                text = text[:match.start()]
                break

    results = _get_ner_pipeline(language)(text)

    return clean_entities(results, text)


if __name__ == "__main__":

    english_text = (
        "Tata Motors announced a new factory in Gujarat."
    )

    hindi_text = (
        "टाटा मोटर्स ने गुजरात में एक नए कारखाने की घोषणा की।"
    )

    print("\nEnglish entities:")
    print(extract_entities(english_text, "en"))

    print("\nHindi entities:")
    print(extract_entities(hindi_text, "hi"))
