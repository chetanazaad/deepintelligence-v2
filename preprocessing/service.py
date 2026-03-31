import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, RawNews

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SPECIAL_CHAR_RE = re.compile(r"[^a-zA-Z0-9\s.,;:!?'\-]")


def clean_text(text: str) -> str:
    """Remove HTML and noisy special characters, then normalize spaces."""
    no_html = _HTML_TAG_RE.sub(" ", text or "")
    no_special = _SPECIAL_CHAR_RE.sub(" ", no_html)
    return _WHITESPACE_RE.sub(" ", no_special).strip()


def normalize_text(text: str) -> str:
    """Deterministic normalization: lowercase and trim."""
    return _WHITESPACE_RE.sub(" ", (text or "").lower()).strip()


def infer_language(text: str) -> str:
    """
    Lightweight deterministic language heuristic.
    Returns 'en' for mostly ASCII alphabetic content, otherwise 'unknown'.
    """
    if not text:
        return "unknown"

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "unknown"

    ascii_letters = [ch for ch in letters if "a" <= ch.lower() <= "z"]
    ratio = len(ascii_letters) / len(letters)
    return "en" if ratio >= 0.85 else "unknown"


def similarity_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_fuzzy_duplicate(headline: str, existing_headlines: list[str], threshold: float = 0.92) -> bool:
    normalized_headline = normalize_text(clean_text(headline))
    if not normalized_headline:
        return False

    for existing in existing_headlines:
        if similarity_score(normalized_headline, existing) >= threshold:
            return True
    return False


def preprocess_and_store(db: Session, fuzzy_threshold: float = 0.92, limit: int = 500) -> dict[str, int]:
    """
    Process uncleaned raw news and store deterministic cleaned records.
    Deduplication layers:
    - exact duplicate by raw_news.unique_id
    - fuzzy duplicate by headline similarity
    """
    existing_processed = db.execute(
        select(RawNews.unique_id, RawNews.title).join(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
    ).all()
    existing_unique_ids = {row[0] for row in existing_processed}
    existing_headlines = [normalize_text(clean_text(row[1])) for row in existing_processed if row[1]]

    rows = (
        db.execute(
            select(RawNews)
            .outerjoin(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
            .where(CleanedNews.id.is_(None))
            .order_by(RawNews.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    inserted = 0
    skipped_exact = 0
    skipped_fuzzy = 0

    for raw in rows:
        if raw.unique_id in existing_unique_ids:
            skipped_exact += 1
            continue

        if is_fuzzy_duplicate(raw.title, existing_headlines, threshold=fuzzy_threshold):
            skipped_fuzzy += 1
            continue

        cleaned = clean_text(raw.content)
        normalized = normalize_text(cleaned)
        language = infer_language(normalized)

        db.add(
            CleanedNews(
                raw_news_id=raw.id,
                cleaned_text=cleaned,
                normalized_text=normalized,
                language=language,
            )
        )
        inserted += 1
        existing_unique_ids.add(raw.unique_id)
        existing_headlines.append(normalize_text(clean_text(raw.title)))

    db.commit()
    return {
        "inserted": inserted,
        "skipped_exact": skipped_exact,
        "skipped_fuzzy": skipped_fuzzy,
    }
