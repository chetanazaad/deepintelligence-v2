import re
from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, RawNews

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SPECIAL_CHAR_RE = re.compile(r"[^a-zA-Z0-9\s.,;:!?'\-]")

_DEDUP_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was",
    "were", "with", "has", "have", "had", "not", "but", "its", "this",
    "will", "can", "all", "been", "into", "than", "may", "new", "also",
    "said", "says", "just",
}


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
    """SequenceMatcher similarity ratio (kept for backward compatibility)."""
    return SequenceMatcher(None, a, b).ratio()


def is_fuzzy_duplicate(headline: str, existing_headlines: list[str], threshold: float = 0.92) -> bool:
    """Legacy O(n) per-call fuzzy check (kept for backward compatibility)."""
    normalized_headline = normalize_text(clean_text(headline))
    if not normalized_headline:
        return False

    for existing in existing_headlines:
        if similarity_score(normalized_headline, existing) >= threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# DedupIndex — O(n) approximate duplicate detection
# ---------------------------------------------------------------------------

class DedupIndex:
    """Fast approximate dedup index using 4-level filtering.

    Level 1 — Exact hash:    O(1) SHA256 of normalized text.
    Level 2 — Token buckets: Headlines grouped by sorted keyword-pairs.
                              Only bucket-mates are candidates.
    Level 3 — Trigram gate:   Fast set-intersection rejects non-similar
                              candidates before expensive comparison.
    Level 4 — SequenceMatcher: Only runs on the tiny set that passes
                               all previous gates.

    Overall complexity: ~O(n) with small constant factor for bucket
    collisions, instead of O(n²) pairwise comparison.
    """

    def __init__(self, threshold: float = 0.92) -> None:
        self.threshold = threshold
        self._trigram_gate = threshold * 0.75  # looser pre-filter
        self._exact_hashes: set[str] = set()
        self._buckets: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)

    # ---- Internal helpers ----

    @staticmethod
    def _fingerprint(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _significant_tokens(text: str) -> list[str]:
        words = [w for w in text.split() if len(w) >= 3 and w not in _DEDUP_STOPWORDS]
        return sorted(words)

    @staticmethod
    def _trigrams(text: str) -> set[str]:
        if len(text) < 3:
            return {text} if text else set()
        return {text[i : i + 3] for i in range(len(text) - 2)}

    def _bucket_keys(self, text: str, tokens: list[str]) -> list[str]:
        keys: list[str] = []

        # Prefix bucket: first 16 characters
        if text:
            keys.append(f"p:{text[:16]}")

        # Token-pair buckets (top-4 tokens, all 2-combinations)
        top = tokens[:4]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                keys.append(f"t:{top[i]}_{top[j]}")

        # Single-token fallback for very short titles
        if len(top) >= 1:
            keys.append(f"s:{top[0]}")

        return keys

    @staticmethod
    def _trigram_similarity(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(len(a), len(b))

    # ---- Public API ----

    def add(self, headline: str) -> None:
        """Add a normalized headline to the index."""
        normalized = normalize_text(clean_text(headline))
        if not normalized:
            return

        fp = self._fingerprint(normalized)
        self._exact_hashes.add(fp)

        tokens = self._significant_tokens(normalized)
        tg = self._trigrams(normalized)
        entry = (normalized, tg)

        for key in self._bucket_keys(normalized, tokens):
            self._buckets[key].append(entry)

    def is_duplicate(self, headline: str) -> bool:
        """Check whether headline is a fuzzy duplicate of any indexed entry.

        Returns True if a match is found at any level, False otherwise.
        """
        normalized = normalize_text(clean_text(headline))
        if not normalized:
            return False

        # Level 1: exact hash
        if self._fingerprint(normalized) in self._exact_hashes:
            return True

        # Level 2: collect candidates from matching buckets
        tokens = self._significant_tokens(normalized)
        seen: set[str] = set()
        candidates: list[tuple[str, set[str]]] = []
        for key in self._bucket_keys(normalized, tokens):
            for entry in self._buckets.get(key, []):
                text_id = id(entry)
                if text_id not in seen:
                    seen.add(text_id)
                    candidates.append(entry)

        if not candidates:
            return False

        # Level 3 + 4: trigram pre-filter then SequenceMatcher
        headline_trigrams = self._trigrams(normalized)
        for candidate_text, candidate_trigrams in candidates:
            if self._trigram_similarity(headline_trigrams, candidate_trigrams) < self._trigram_gate:
                continue
            if SequenceMatcher(None, normalized, candidate_text).ratio() >= self.threshold:
                return True

        return False


# ---------------------------------------------------------------------------
# Main preprocessing function
# ---------------------------------------------------------------------------

def preprocess_and_store(db: Session, fuzzy_threshold: float = 0.92, limit: int = 500) -> dict[str, int]:
    """
    Process uncleaned raw news and store deterministic cleaned records.

    Deduplication layers:
    - exact duplicate by raw_news.unique_id
    - fuzzy duplicate by headline similarity (token-bucketed, near O(n))
    """
    # Build index from already-processed headlines
    existing_processed = db.execute(
        select(RawNews.unique_id, RawNews.title).join(CleanedNews, CleanedNews.raw_news_id == RawNews.id)
    ).all()
    existing_unique_ids = {row[0] for row in existing_processed}

    dedup = DedupIndex(threshold=fuzzy_threshold)
    for row in existing_processed:
        if row[1]:
            dedup.add(row[1])

    # Fetch unprocessed raw news
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

        if dedup.is_duplicate(raw.title):
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
        dedup.add(raw.title)

    db.commit()
    return {
        "inserted": inserted,
        "skipped_exact": skipped_exact,
        "skipped_fuzzy": skipped_fuzzy,
    }
