from datetime import datetime, timezone

import feedparser


def _to_datetime_utc(value: object) -> datetime | None:
    if value is None:
        return None

    if hasattr(value, "tm_year"):
        return datetime(
            value.tm_year,
            value.tm_mon,
            value.tm_mday,
            value.tm_hour,
            value.tm_min,
            value.tm_sec,
            tzinfo=timezone.utc,
        )
    return None


def fetch_rss_feed(feed_url: str, source: str) -> list[dict[str, object]]:
    """
    Fetch RSS entries and normalize into deterministic dictionaries.
    """
    parsed = feedparser.parse(feed_url)
    items: list[dict[str, object]] = []

    for entry in parsed.entries:
        title = str(getattr(entry, "title", "")).strip()
        content = str(getattr(entry, "summary", "")).strip()
        url = str(getattr(entry, "link", "")).strip() or None
        published_at = _to_datetime_utc(getattr(entry, "published_parsed", None))

        if not title or not content:
            continue

        items.append(
            {
                "title": title,
                "content": content,
                "source": source.strip(),
                "url": url,
                "published_at": published_at,
            }
        )

    return items
