from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
from re import findall

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, ClusterNewsMap, EventCluster, RawNews

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "said",
    "says",
    "than",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}


@dataclass(slots=True)
class NewsItem:
    cleaned_news_id: int
    title: str
    text: str
    keywords: set[str]


@dataclass(slots=True)
class ClusterBucket:
    member_ids: list[int] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ExistingClusterProfile:
    """Lightweight representation of an existing DB cluster for matching."""
    cluster_id: int
    keywords: set[str]
    sample_texts: list[str]


# ---------------------------------------------------------------------------
# Shared helpers (unchanged signatures)
# ---------------------------------------------------------------------------

def extract_keywords(text: str, max_terms: int = 20) -> set[str]:
    tokens = [token.lower() for token in findall(r"[a-zA-Z0-9]{3,}", text or "")]
    filtered = [token for token in tokens if token not in _STOPWORDS]
    return set(filtered[:max_terms])


def keyword_overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a.intersection(b))
    return intersection / min(len(a), len(b))


def text_similarity_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _bucket_similarity(item: NewsItem, bucket: ClusterBucket) -> float:
    keyword_score = keyword_overlap_score(item.keywords, bucket.keywords)
    if not bucket.texts:
        return keyword_score

    text_score = max(text_similarity_score(item.text, existing_text) for existing_text in bucket.texts)
    # Slightly favor keyword match over full-string similarity.
    return (0.6 * keyword_score) + (0.4 * text_score)


# ---------------------------------------------------------------------------
# Improved helpers
# ---------------------------------------------------------------------------

def _profile_similarity(item: NewsItem, profile: ExistingClusterProfile) -> float:
    """Score how well a new item matches an existing DB cluster profile."""
    keyword_score = keyword_overlap_score(item.keywords, profile.keywords)
    if keyword_score < 0.15:
        return 0.0  # fast skip — not worth comparing text

    if not profile.sample_texts:
        return keyword_score

    text_score = max(
        text_similarity_score(item.text, sample)
        for sample in profile.sample_texts
    )
    return (0.6 * keyword_score) + (0.4 * text_score)


def _choose_main_topic(titles: list[str], keywords: set[str]) -> str:
    """Frequency-based topic from member titles, not just sorted keywords."""
    if not titles:
        if not keywords:
            return "general-event"
        return " ".join(sorted(keywords)[:3])

    word_counts: Counter[str] = Counter()
    for title in titles:
        tokens = [t.lower() for t in findall(r"[a-zA-Z0-9]{3,}", title)]
        filtered = [t for t in tokens if t not in _STOPWORDS]
        word_counts.update(filtered)

    top = [word for word, _ in word_counts.most_common(5)]
    return " ".join(top[:3]) if top else "general-event"


def _build_cluster_key(keywords: set[str]) -> str:
    """Stable cluster key from sorted keywords — independent of member IDs."""
    canonical = "|".join(sorted(keywords)[:5])
    return sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _merge_similar_buckets(
    buckets: list[ClusterBucket],
    merge_threshold: float = 0.65,
) -> list[ClusterBucket]:
    """Iteratively merge new-bucket pairs with high keyword overlap.

    Runs until no more merges are possible. This prevents near-duplicate
    clusters from being persisted separately.
    """
    if len(buckets) <= 1:
        return buckets

    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(buckets):
            j = i + 1
            while j < len(buckets):
                score = keyword_overlap_score(buckets[i].keywords, buckets[j].keywords)
                if score >= merge_threshold:
                    # absorb bucket[j] into bucket[i]
                    buckets[i].member_ids.extend(buckets[j].member_ids)
                    buckets[i].titles.extend(buckets[j].titles)
                    buckets[i].texts.extend(buckets[j].texts)
                    buckets[i].keywords.update(buckets[j].keywords)
                    buckets.pop(j)
                    changed = True
                else:
                    j += 1
            i += 1

    return buckets


# ---------------------------------------------------------------------------
# Existing cluster profile loader
# ---------------------------------------------------------------------------

def _load_existing_profiles(db: Session, max_clusters: int = 300) -> list[ExistingClusterProfile]:
    """Load keyword profiles of existing DB clusters for matching new items.

    Keeps only sample texts (up to 3 per cluster) to limit memory and
    SequenceMatcher cost. Keyword sets are built from ALL member titles.
    """
    rows = db.execute(
        select(ClusterNewsMap.cluster_id, CleanedNews.normalized_text, RawNews.title)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
    ).all()

    if not rows:
        return []

    cluster_data: dict[int, dict[str, list[str]]] = defaultdict(lambda: {"texts": [], "titles": []})
    for cluster_id, text, title in rows:
        data = cluster_data[cluster_id]
        if len(data["texts"]) < 5:
            data["texts"].append(text or "")
        data["titles"].append(title or "")

    profiles: list[ExistingClusterProfile] = []
    for cluster_id, data in list(cluster_data.items())[:max_clusters]:
        keywords: set[str] = set()
        for title in data["titles"]:
            keywords.update(extract_keywords(title))

        profiles.append(
            ExistingClusterProfile(
                cluster_id=cluster_id,
                keywords=keywords,
                sample_texts=data["texts"][:3],
            )
        )

    return profiles


# ---------------------------------------------------------------------------
# Main clustering function
# ---------------------------------------------------------------------------

def cluster_cleaned_news(
    db: Session,
    similarity_threshold: float = 0.45,
    batch_size: int = 500,
    merge_threshold: float = 0.65,
) -> dict[str, int]:
    """
    Rule-based clustering for unclustered cleaned_news rows.

    Improvements over naive single-pass:
    1) Match new items against existing DB clusters first
    2) Best-match selection across all candidates (existing + new buckets)
    3) Post-assignment merge pass for similar new buckets
    4) Stable cluster key (keyword-based, not member-ID-based)
    5) Frequency-based main_topic from member title words
    """
    # ---- Fetch unclustered items ----
    rows = (
        db.execute(
            select(CleanedNews.id, CleanedNews.normalized_text, RawNews.title)
            .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
            .outerjoin(ClusterNewsMap, ClusterNewsMap.cleaned_news_id == CleanedNews.id)
            .where(ClusterNewsMap.id.is_(None))
            .order_by(CleanedNews.created_at.asc(), CleanedNews.id.asc())
            .limit(batch_size)
        )
        .all()
    )

    items: list[NewsItem] = []
    for row in rows:
        text = row[1] or ""
        title = row[2] or ""
        item = NewsItem(
            cleaned_news_id=row[0],
            title=title,
            text=text,
            keywords=extract_keywords(f"{title} {text}"),
        )
        items.append(item)

    if not items:
        return {"clusters_created": 0, "mapped_news": 0, "merged_to_existing": 0}

    # ---- Load existing cluster profiles for matching ----
    existing_profiles = _load_existing_profiles(db)

    # ---- Assign each item to best match (existing cluster or new bucket) ----
    mapped_to_existing: dict[int, list[int]] = defaultdict(list)
    new_buckets: list[ClusterBucket] = []

    for item in items:
        # Score against existing DB clusters
        best_existing_id: int | None = None
        best_existing_score = 0.0
        for profile in existing_profiles:
            score = _profile_similarity(item, profile)
            if score > best_existing_score:
                best_existing_score = score
                best_existing_id = profile.cluster_id

        # Score against new in-memory buckets
        best_bucket_idx = -1
        best_bucket_score = 0.0
        for idx, bucket in enumerate(new_buckets):
            score = _bucket_similarity(item, bucket)
            if score > best_bucket_score:
                best_bucket_score = score
                best_bucket_idx = idx

        # Choose best overall match
        if (
            best_existing_id is not None
            and best_existing_score >= similarity_threshold
            and best_existing_score >= best_bucket_score
        ):
            # Best match is an existing DB cluster
            mapped_to_existing[best_existing_id].append(item.cleaned_news_id)

        elif best_bucket_idx >= 0 and best_bucket_score >= similarity_threshold:
            # Best match is a new bucket
            target = new_buckets[best_bucket_idx]
            target.member_ids.append(item.cleaned_news_id)
            target.titles.append(item.title)
            target.texts.append(item.text)
            target.keywords.update(item.keywords)

        else:
            # No good match — create a new bucket
            new_buckets.append(
                ClusterBucket(
                    member_ids=[item.cleaned_news_id],
                    titles=[item.title],
                    texts=[item.text],
                    keywords=set(item.keywords),
                )
            )

    # ---- Merge similar new buckets ----
    new_buckets = _merge_similar_buckets(new_buckets, merge_threshold)

    # ---- Persist results ----
    clusters_created = 0
    mapped_news = 0
    merged_to_existing = 0

    # Map items that matched existing clusters
    for cluster_id, news_ids in mapped_to_existing.items():
        for cleaned_news_id in news_ids:
            db.add(ClusterNewsMap(cluster_id=cluster_id, cleaned_news_id=cleaned_news_id))
            mapped_news += 1
            merged_to_existing += 1

    # Create new clusters for remaining buckets
    for bucket in new_buckets:
        main_topic = _choose_main_topic(bucket.titles, bucket.keywords)
        cluster = EventCluster(
            cluster_key=_build_cluster_key(bucket.keywords),
            main_topic=main_topic,
        )
        db.add(cluster)
        db.flush()
        clusters_created += 1

        for cleaned_news_id in bucket.member_ids:
            db.add(ClusterNewsMap(cluster_id=cluster.id, cleaned_news_id=cleaned_news_id))
            mapped_news += 1

    db.commit()
    return {
        "clusters_created": clusters_created,
        "mapped_news": mapped_news,
        "merged_to_existing": merged_to_existing,
    }
