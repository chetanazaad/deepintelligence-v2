from datetime import datetime, timezone
from hashlib import sha256
from re import findall

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    Edge,
    EventCluster,
    Node,
    RawNews,
    TimelineEntry,
)

_EVENT_TYPE_RULES = {
    "triggers": {"launch", "announce", "surge", "spike", "breakout", "sanction"},
    "causes": {"because", "due", "impact", "driven", "caused", "result"},
    "precedes": {"before", "ahead", "prior", "prelude"},
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _extract_terms(text: str) -> set[str]:
    return {token.lower() for token in findall(r"[a-zA-Z0-9]{3,}", text or "")}


def _relation_type(current_text: str, previous_text: str) -> str:
    current_terms = _extract_terms(current_text)
    previous_terms = _extract_terms(previous_text)
    joined = current_terms.union(previous_terms)

    if joined.intersection(_EVENT_TYPE_RULES["causes"]):
        return "causes"
    if joined.intersection(_EVENT_TYPE_RULES["triggers"]):
        return "triggers"
    return "precedes"


def _event_type(text: str) -> str:
    terms = _extract_terms(text)
    if terms.intersection(_EVENT_TYPE_RULES["triggers"]):
        return "trigger"
    if terms.intersection(_EVENT_TYPE_RULES["causes"]):
        return "causal"
    return "update"


def _entity_from_topic(topic: str) -> str:
    words = [w for w in topic.split() if w.strip()]
    return words[0] if words else "event"


def _build_timeline_group_id(anchor_cluster_key: str) -> str:
    digest = sha256(anchor_cluster_key.encode("utf-8")).hexdigest()[:12]
    return f"timeline-{digest}"


def _get_or_create_node(
    db: Session,
    cluster_id: int,
    entity: str,
    event_type: str,
    description: str,
    timestamp: datetime | None,
    is_anchor: bool,
) -> Node:
    node = db.scalar(select(Node).where(Node.cluster_id == cluster_id))
    if node is None:
        node = Node(
            cluster_id=cluster_id,
            entity=entity,
            entity_type="topic",
            event_type=event_type,
            description=description,
            timestamp=timestamp,
            impact_type="neutral",
            confidence_score=0.7,
            is_anchor=is_anchor,
        )
        db.add(node)
        db.flush()
        return node

    node.entity = entity
    node.entity_type = "topic"
    node.event_type = event_type
    node.description = description
    node.timestamp = timestamp
    node.impact_type = "neutral"
    node.confidence_score = 0.7
    node.is_anchor = is_anchor
    db.flush()
    return node


def build_timeline(db: Session, max_clusters: int = 200) -> dict[str, int | str]:
    """
    Deterministic timeline builder:
    1) score clusters by frequency + recency + source count
    2) choose anchor cluster
    3) create/update nodes for scored clusters
    4) build backward edges (causes/precedes/triggers)
    5) persist ordered timeline rows
    """
    stats_rows = db.execute(
        select(
            EventCluster.id,
            EventCluster.cluster_key,
            EventCluster.main_topic,
            func.count(ClusterNewsMap.id).label("frequency"),
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("latest_ts"),
            func.count(func.distinct(RawNews.source)).label("source_count"),
        )
        .join(ClusterNewsMap, ClusterNewsMap.cluster_id == EventCluster.id)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .group_by(EventCluster.id, EventCluster.cluster_key, EventCluster.main_topic)
    ).all()

    if not stats_rows:
        return {
            "anchor_cluster_id": "",
            "nodes_created_or_updated": 0,
            "edges_created": 0,
            "timeline_entries": 0,
        }

    now = _now_utc()
    cluster_stats: list[dict[str, object]] = []
    for row in stats_rows[:max_clusters]:
        latest = row.latest_ts
        if isinstance(latest, datetime):
            age_days = max((now - latest).total_seconds() / 86400.0, 0.0)
        else:
            age_days = 365.0

        recency_score = max(0.0, 30.0 - age_days) / 30.0
        score = float(row.frequency) + float(row.source_count) + recency_score

        cluster_stats.append(
            {
                "cluster_id": row.id,
                "cluster_key": row.cluster_key,
                "main_topic": row.main_topic,
                "frequency": int(row.frequency),
                "source_count": int(row.source_count),
                "latest_ts": latest if isinstance(latest, datetime) else None,
                "score": score,
            }
        )

    cluster_stats.sort(
        key=lambda x: (
            float(x["score"]),
            int(x["frequency"]),
            int(x["source_count"]),
            x["latest_ts"] or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    anchor_cluster_id = int(cluster_stats[0]["cluster_id"])
    anchor_cluster_key = str(cluster_stats[0]["cluster_key"])

    # ---- Batch-fetch titles for all clusters in one query ----
    all_cluster_ids = [int(info["cluster_id"]) for info in cluster_stats]
    title_rows = db.execute(
        select(ClusterNewsMap.cluster_id, RawNews.title)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .where(ClusterNewsMap.cluster_id.in_(all_cluster_ids))
        .order_by(ClusterNewsMap.cluster_id, RawNews.created_at.desc())
    ).all()

    from collections import defaultdict
    titles_by_cluster: dict[int, list[str]] = defaultdict(list)
    for row in title_rows:
        if len(titles_by_cluster[row[0]]) < 3:
            titles_by_cluster[row[0]].append(row[1])

    nodes: list[Node] = []
    for info in cluster_stats:
        cluster_id = int(info["cluster_id"])
        titles = titles_by_cluster.get(cluster_id, [])

        main_topic = str(info["main_topic"])
        description = " | ".join([t for t in titles if t]) or main_topic
        event_type = _event_type(f"{main_topic} {description}")
        entity = _entity_from_topic(main_topic)
        timestamp = info["latest_ts"] if isinstance(info["latest_ts"], datetime) else None

        node = _get_or_create_node(
            db=db,
            cluster_id=cluster_id,
            entity=entity,
            event_type=event_type,
            description=description,
            timestamp=timestamp,
            is_anchor=(cluster_id == anchor_cluster_id),
        )
        nodes.append(node)

    # Backward timeline: newest/anchor first, then older events.
    nodes.sort(key=lambda n: n.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    anchor_index = next((i for i, n in enumerate(nodes) if n.cluster_id == anchor_cluster_id), 0)
    if anchor_index != 0:
        anchor_node = nodes.pop(anchor_index)
        nodes.insert(0, anchor_node)

    # ---- Scoped edge dedup: only load edges for nodes in current timeline ----
    current_node_ids = [n.id for n in nodes]
    existing_edges = {
        (from_id, to_id, relation)
        for from_id, to_id, relation in db.execute(
            select(Edge.from_node_id, Edge.to_node_id, Edge.relation_type)
            .where(Edge.from_node_id.in_(current_node_ids))
        ).all()
    }

    edges_created = 0
    for idx in range(len(nodes) - 1):
        current_node = nodes[idx]
        previous_node = nodes[idx + 1]
        relation = _relation_type(current_node.description or "", previous_node.description or "")
        key = (current_node.id, previous_node.id, relation)
        if key in existing_edges:
            continue

        db.add(
            Edge(
                from_node_id=current_node.id,
                to_node_id=previous_node.id,
                relation_type=relation,
                confidence_score=0.65,
            )
        )
        existing_edges.add(key)
        edges_created += 1

    timeline_group_id = _build_timeline_group_id(anchor_cluster_key)
    db.execute(delete(TimelineEntry).where(TimelineEntry.timeline_group_id == timeline_group_id))

    for position, node in enumerate(nodes):
        db.add(
            TimelineEntry(
                node_id=node.id,
                position_index=position,
                timeline_group_id=timeline_group_id,
            )
        )

    db.commit()
    return {
        "anchor_cluster_id": anchor_cluster_id,
        "nodes_created_or_updated": len(nodes),
        "edges_created": edges_created,
        "timeline_entries": len(nodes),
        "timeline_group_id": timeline_group_id,
    }
