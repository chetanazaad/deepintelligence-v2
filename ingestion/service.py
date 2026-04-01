from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import RawNews


@dataclass(slots=True)
class RawArticle:
    source: str
    title: str
    content: str
    url: str | None = None
    published_at: datetime | None = None


def normalize_input(payload: dict[str, object]) -> RawArticle:
    published_at = payload.get("published_at")
    parsed_published_at = published_at if isinstance(published_at, datetime) else None

    return RawArticle(
        source=str(payload.get("source", "")).strip(),
        title=str(payload.get("title", "")).strip(),
        content=str(payload.get("content", "")).strip(),
        url=str(payload.get("url", "")).strip() or None,
        published_at=parsed_published_at,
    )


def generate_unique_id(title: str, source: str, published_at: datetime | None) -> str:
    timestamp = published_at.isoformat() if published_at else ""
    raw = f"{title.strip()}|{source.strip()}|{timestamp}"
    return sha256(raw.encode("utf-8")).hexdigest()


def insert_raw_news(db: Session, items: list[dict[str, object]]) -> tuple[int, int]:
    """
    Insert raw news into database while preventing duplicates by unique_id.
    Returns: (inserted_count, skipped_duplicates_count).
    """
    inserted = 0
    skipped = 0
    seen_in_batch: set[str] = set()

    for item in items:
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        source = str(item.get("source", "")).strip()
        url_value = item.get("url")
        url = str(url_value).strip() if isinstance(url_value, str) else None
        published_at = item.get("published_at")
        if not isinstance(published_at, datetime):
            published_at = None

        if not title or not content or not source:
            continue

        unique_id = generate_unique_id(title=title, source=source, published_at=published_at)

        # Skip duplicates within the same batch
        if unique_id in seen_in_batch:
            skipped += 1
            continue
        seen_in_batch.add(unique_id)

        # Skip duplicates already in DB
        exists = db.scalar(select(RawNews.id).where(RawNews.unique_id == unique_id))
        if exists is not None:
            skipped += 1
            continue

        db.add(
            RawNews(
                unique_id=unique_id,
                title=title,
                content=content,
                source=source,
                url=url,
                published_at=published_at,
            )
        )
        inserted += 1

    db.commit()
    return inserted, skipped
