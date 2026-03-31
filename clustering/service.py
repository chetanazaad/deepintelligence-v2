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
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
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


def _choose_main_topic(keywords: set[str]) -> str:
    if not keywords:
        return "general-event"
    return " ".join(sorted(keywords)[:3])


def _build_cluster_key(main_topic: str, first_member_id: int) -> str:
    raw = f"{main_topic}|{first_member_id}"
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def cluster_cleaned_news(
    db: Session,
    similarity_threshold: float = 0.45,
    batch_size: int = 500,
) -> dict[str, int]:
    """
    Rule-based clustering for unclustered cleaned_news rows.
    - similarity = weighted keyword overlap + text similarity
    - creates event_clusters
    - maps cleaned news to cluster_news_map
    """
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
        return {"clusters_created": 0, "mapped_news": 0}

    buckets: list[ClusterBucket] = []
    for item in items:
        best_bucket_index = -1
        best_score = 0.0

        for idx, bucket in enumerate(buckets):
            score = _bucket_similarity(item, bucket)
            if score > best_score:
                best_score = score
                best_bucket_index = idx

        if best_bucket_index >= 0 and best_score >= similarity_threshold:
            target = buckets[best_bucket_index]
            target.member_ids.append(item.cleaned_news_id)
            target.titles.append(item.title)
            target.texts.append(item.text)
            target.keywords.update(item.keywords)
        else:
            buckets.append(
                ClusterBucket(
                    member_ids=[item.cleaned_news_id],
                    titles=[item.title],
                    texts=[item.text],
                    keywords=set(item.keywords),
                )
            )

    clusters_created = 0
    mapped_news = 0

    for bucket in buckets:
        main_topic = _choose_main_topic(bucket.keywords)
        cluster = EventCluster(
            cluster_key=_build_cluster_key(main_topic=main_topic, first_member_id=bucket.member_ids[0]),
            main_topic=main_topic,
        )
        db.add(cluster)
        db.flush()
        clusters_created += 1

        for cleaned_news_id in bucket.member_ids:
            db.add(ClusterNewsMap(cluster_id=cluster.id, cleaned_news_id=cleaned_news_id))
            mapped_news += 1

    db.commit()
    return {"clusters_created": clusters_created, "mapped_news": mapped_news}
