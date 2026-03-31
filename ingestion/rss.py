import logging
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger(__name__)


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


def fetch_rss_feed(feed_url: str, source: str, timeout: int = 15) -> list[dict[str, object]]:
    """
    Fetch RSS entries and normalize into deterministic dictionaries.

    Applies a network timeout and catches errors so a single failed feed
    never crashes the pipeline.
    """
    try:
        response = urllib.request.urlopen(feed_url, timeout=timeout)
        raw_data = response.read()
        parsed = feedparser.parse(raw_data)
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        logger.warning("Network error fetching RSS feed %s: %s", feed_url, exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching RSS feed %s: %s", feed_url, exc)
        return []

    if parsed.bozo and not parsed.entries:
        logger.warning("Malformed feed %s: %s", feed_url, parsed.bozo_exception)
        return []

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

    logger.info("Fetched %d entries from %s (%s)", len(items), source, feed_url)
    return items
