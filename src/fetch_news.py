
import os
import re
import hashlib
import html
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("NEWSDATA_API_KEY")
API_URL = "https://newsdata.io/api/1/latest"


def clean_text(text):
    """Remove HTML, unwanted boilerplate and excessive whitespace."""

    if not isinstance(text, str) or not text.strip():
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)

    # Remove common news-page boilerplate
    boilerplate = [
        r"ONLY AVAILABLE IN PAID\s*PLANS.*",
        r"Read more\s*$",
        r"Also Read:.*",
        r"Follow us on.*",
    ]

    for pattern in boilerplate:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Cut off known Hindi city-list section
    city_list_patterns = [
        r"यहां जानें देश के बड़े शहरों",
        r"यहाँ जानें देश के बड़े शहरों",
    ]

    for pattern in city_list_patterns:
        match = re.search(pattern, text)
        if match:
            text = text[:match.start()]
            break

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url):
    """Normalize URLs for duplicate detection."""

    if not url:
        return ""

    try:
        parts = urlsplit(url.strip())
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/"),
            "",
            ""
        ))
    except Exception:
        return url.strip().lower()


def make_id(value):
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:16]


def fetch_language_news(language, size=10):

    if not API_KEY:
        raise ValueError("NEWSDATA_API_KEY not found in .env")

    params = {
        "apikey": API_KEY,
        "country": "in",
        "language": language,
        "size": size,
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict) or data.get("status") != "success":
        # Avoid printing the full API payload, which may contain request details.
        print(f"NewsData.io returned an unsuccessful response for {language}.")
        return []

    articles = []

    results = data.get("results", [])
    if not isinstance(results, list):
        print(f"NewsData.io returned malformed results for {language}.")
        return []

    for item in results:
        if not isinstance(item, dict):
            continue

        title = clean_text(item.get("title") or "")
        description = clean_text(item.get("description") or "")
        content = clean_text(item.get("content") or "")

        # Keep title and description even if full content is unavailable
        text = " ".join(
            part for part in [title, description, content]
            if part
        ).strip()

        if not text:
            continue

        url = item.get("link") or ""
        if not isinstance(url, str):
            url = ""
        normalized_url = normalize_url(url)

        article_id = item.get("article_id")

        if not article_id:
            fallback = normalized_url or f"{language}:{text}"
            article_id = make_id(fallback)

        articles.append({
            "id": str(article_id),
            "language": language,
            "title": title,
            "text": text,
            "source": str(item.get("source_id") or "unknown"),
            "publication_date": str(item.get("pubDate") or "unknown"),
            "url": url,
            "dedupe_key": normalized_url or make_id(
                f"{language}:{text.casefold()}"
            ),
        })

    return articles


def fetch_news():

    all_articles = []
    seen = set()

    for language in ["en", "hi"]:

        try:
            articles = fetch_language_news(language)

            added = 0

            for article in articles:

                key = article["dedupe_key"]

                if key in seen:
                    continue

                seen.add(key)
                all_articles.append(article)
                added += 1

            print(
                f"{language}: fetched {len(articles)}, "
                f"added {added} unique articles"
            )

        except requests.RequestException as error:
            print(f"Error fetching {language} news:", error)
        except (ValueError, TypeError) as error:
            print(f"Invalid news response for {language}:", error)

    print(f"\nTotal unique articles: {len(all_articles)}")

    return all_articles
