"""Evidence-backed, sentence-level relation rules for English and Hindi.

These rules are intentionally conservative and are a baseline, not a trained
relation extraction model. Every prediction retains its sentence evidence.
"""

import hashlib
import re


TRIGGERS = {
    "en": {
        "ANNOUNCED": r"\b(?:announc(?:e|es|ed|ing)|unveiled|declared)\b",
        "OPENED": r"\b(?:open(?:s|ed|ing)?|inaugurat(?:e|es|ed)|launched|established)\b",
        "ACQUIRED": r"\b(?:acquir(?:e|es|ed|ing)|bought|purchased|took over)\b",
        "APPOINTED": r"\b(?:appoint(?:s|ed|ing)?|named|nominated)\b",
        "WORKS_FOR": r"\b(?:works? for|working for|joined|employed by)\b",
        "PARTNERED_WITH": r"\b(?:partner(?:s|ed|ing)? with|formed a partnership with)\b",
        "INVESTED_IN": r"\b(?:invest(?:s|ed|ing)? in|made an investment in)\b",
    },
    "hi": {
        "ANNOUNCED": r"घोषणा की|ऐलान किया|घोषित किया",
        "OPENED": r"खोला|खोली|उद्घाटन किया|शुरू किया|स्थापित किया",
        "ACQUIRED": r"अधिग्रहण किया|खरीदा|खरीदी",
        "APPOINTED": r"नियुक्त किया|नियुक्ति की",
        "WORKS_FOR": r"काम करता है|काम करती है|काम करते हैं|में शामिल हुए|में शामिल हुई|के लिए काम",
        "PARTNERED_WITH": r"साझेदारी की|भागीदारी की|साझेदार बना|साझेदार बनी",
        "INVESTED_IN": r"निवेश किया|निवेश करेगी|निवेश करेगा|निवेश में",
    },
}

EVENT_RELATIONS = {"ANNOUNCED", "OPENED"}
PAIR_RELATIONS = {"ACQUIRED", "PARTNERED_WITH", "INVESTED_IN"}


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?।])\s+", text) if part.strip()]


def _entity_spans(sentence, entities):
    spans = []
    folded_sentence = sentence.casefold()
    for entity in entities:
        name = str(entity.get("name", "")).strip()
        if not name:
            continue
        folded_name = name.casefold()
        start = 0
        while True:
            found = folded_sentence.find(folded_name, start)
            if found < 0:
                break
            end = found + len(folded_name)
            # Avoid matching a Latin entity name inside a longer token.
            if name.isascii():
                before_ok = found == 0 or not sentence[found - 1].isalnum()
                after_ok = end == len(sentence) or not sentence[end].isalnum()
            else:
                before_ok = after_ok = True
            if before_ok and after_ok:
                spans.append((found, end, entity))
            start = found + max(1, len(folded_name))
    return spans


def _nearest(items, position, before):
    candidates = [item for item in items if (item[1] <= position if before else item[0] >= position)]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1]) if before else min(candidates, key=lambda item: item[0])


def _make_event(article_id, relation, sentence):
    event_type = "ANNOUNCEMENT" if relation == "ANNOUNCED" else "OPENING"
    digest = hashlib.sha1(f"{event_type}:{sentence}".encode("utf-8")).hexdigest()[:12]
    return {
        "id": f"event:{event_type.lower()}:{article_id}:{digest}",
        "name": relation.title(),
        "type": "EVENT",
        "event_type": event_type,
    }


def extract_relations(text, language, entities, article_id="unknown"):
    """Extract narrow high-evidence rules; ambiguous subject/object pairs skip."""
    if language not in TRIGGERS or not isinstance(text, str):
        return []

    facts = []
    for sentence in _sentences(text):
        spans = _entity_spans(sentence, entities)
        organizations = [span for span in spans if span[2].get("type") == "ORG"]
        people = [span for span in spans if span[2].get("type") == "PER"]
        locations = [span for span in spans if span[2].get("type") == "LOC"]

        for relation, pattern in TRIGGERS[language].items():
            trigger = re.search(pattern, sentence, re.IGNORECASE)
            if not trigger:
                continue
            position = trigger.start()

            if relation in EVENT_RELATIONS:
                organization = _nearest(organizations, position, before=True)
                if not organization:
                    continue
                event = _make_event(article_id, relation, sentence)
                facts.append({
                    "subject": organization[2],
                    "predicate": relation,
                    "object": event,
                    "evidence": sentence,
                    "confidence": 0.72,
                })
                location = (
                    _nearest(locations, position, before=False)
                    or _nearest(locations, position, before=True)
                )
                if location:
                    facts.append({
                        "subject": event,
                        "predicate": "LOCATED_IN",
                        "object": location[2],
                        "evidence": sentence,
                        "confidence": 0.68,
                    })
            elif relation in PAIR_RELATIONS:
                if language == "hi":
                    prior_orgs = [item for item in organizations if item[1] <= position]
                    prior_orgs.sort(key=lambda item: item[0])
                    subject, obj = (prior_orgs[-2:] if len(prior_orgs) >= 2 else (None, None))
                else:
                    subject = _nearest(organizations, position, before=True)
                    obj = _nearest(organizations, position, before=False)
                if subject and obj and subject[2] is not obj[2]:
                    facts.append({
                        "subject": subject[2],
                        "predicate": relation,
                        "object": obj[2],
                        "evidence": sentence,
                        "confidence": 0.70,
                    })
            elif relation == "APPOINTED":
                organization = _nearest(organizations, position, before=True)
                person = _nearest(people, position, before=False)
                if language == "hi" and not person:
                    person = _nearest(people, position, before=True)
                if organization and person:
                    facts.append({
                        "subject": organization[2],
                        "predicate": relation,
                        "object": person[2],
                        "evidence": sentence,
                        "confidence": 0.68,
                    })
            elif relation == "WORKS_FOR":
                person_before = _nearest(people, position, before=True)
                person_after = _nearest(people, position, before=False)
                organization_before = _nearest(organizations, position, before=True)
                organization_after = _nearest(organizations, position, before=False)
                person = person_before or person_after
                organization = organization_before or organization_after if language == "hi" else organization_after or organization_before
                if person and organization:
                    facts.append({
                        "subject": person[2],
                        "predicate": relation,
                        "object": organization[2],
                        "evidence": sentence,
                        "confidence": 0.65,
                    })

    return facts
