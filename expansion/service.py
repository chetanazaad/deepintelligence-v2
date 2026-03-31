from collections import deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from re import findall

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from models.news_intelligence import CleanedNews, ClusterNewsMap, Edge, EventCluster, Node, RawNews, TimelineEntry


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in findall(r"[a-zA-Z0-9]{3,}", text or "")}


def _entity_overlap(node_entity: str, cluster_topic: str) -> bool:
    return bool(_tokens(node_entity).intersection(_tokens(cluster_topic)))


def _context_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _time_proximity(seed_ts: datetime | None, candidate_ts: datetime | None, max_days: int) -> bool:
    if seed_ts is None or candidate_ts is None:
        return False
    return abs((seed_ts - candidate_ts).total_seconds()) <= max_days * 86400


def _cluster_snapshot(db: Session) -> dict[int, dict[str, object]]:
    rows = db.execute(
        select(
            EventCluster.id,
            EventCluster.main_topic,
            func.max(func.coalesce(RawNews.published_at, RawNews.created_at)).label("latest_ts"),
            func.string_agg(func.coalesce(CleanedNews.normalized_text, ""), " ").label("context_text"),
        )
        .join(ClusterNewsMap, ClusterNewsMap.cluster_id == EventCluster.id)
        .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .group_by(EventCluster.id, EventCluster.main_topic)
    ).all()

    result: dict[int, dict[str, object]] = {}
    for row in rows:
        result[int(row.id)] = {
            "main_topic": str(row.main_topic),
            "latest_ts": row.latest_ts if isinstance(row.latest_ts, datetime) else None,
            "context_text": str(row.context_text or ""),
        }
    return result


def _first_node_by_cluster(db: Session) -> dict[int, Node]:
    nodes = db.execute(select(Node).order_by(Node.id.asc())).scalars().all()
    out: dict[int, Node] = {}
    for node in nodes:
        if node.cluster_id not in out:
            out[node.cluster_id] = node
    return out


def _ensure_node_for_cluster(
    db: Session,
    cluster_id: int,
    cluster_topic: str,
    context_text: str,
    latest_ts: datetime | None,
    by_cluster: dict[int, Node],
) -> Node:
    existing = by_cluster.get(cluster_id)
    if existing is not None:
        return existing

    entity = cluster_topic.split()[0] if cluster_topic else "event"
    node = Node(
        cluster_id=cluster_id,
        entity=entity,
        entity_type="topic",
        event_type="expansion",
        description=context_text[:1000] or cluster_topic,
        timestamp=latest_ts or datetime.now(timezone.utc),
        impact_type="neutral",
        confidence_score=0.6,
        is_anchor=False,
    )
    db.add(node)
    db.flush()
    by_cluster[cluster_id] = node
    return node


def expand_from_timeline(
    db: Session,
    max_depth: int = 2,
    similarity_threshold: float = 0.35,
    max_time_gap_days: int = 7,
) -> dict[str, int]:
    """
    Deterministic expansion from timeline nodes with strict gates:
    - entity overlap
    - context similarity
    - time proximity
    Depth is capped at 2.
    """
    depth_limit = min(max_depth, 2)

    seed_nodes = (
        db.execute(
            select(Node)
            .join(TimelineEntry, TimelineEntry.node_id == Node.id)
            .order_by(TimelineEntry.position_index.asc())
        )
        .scalars()
        .all()
    )
    if not seed_nodes:
        return {"new_nodes": 0, "new_edges": 0}

    cluster_data = _cluster_snapshot(db)
    if not cluster_data:
        return {"new_nodes": 0, "new_edges": 0}

    node_by_cluster = _first_node_by_cluster(db)
    existing_edges = {
        (r[0], r[1], r[2])
        for r in db.execute(select(Edge.from_node_id, Edge.to_node_id, Edge.relation_type)).all()
    }

    queue = deque([(node, 0) for node in seed_nodes])
    visited_node_ids = {n.id for n in seed_nodes}

    new_nodes = 0
    new_edges = 0

    while queue:
        base_node, depth = queue.popleft()
        if depth >= depth_limit:
            continue

        base_cluster = cluster_data.get(base_node.cluster_id)
        if base_cluster is None:
            continue

        base_context = str(base_cluster["context_text"])
        base_ts = base_node.timestamp

        for cluster_id, candidate in cluster_data.items():
            if cluster_id == base_node.cluster_id:
                continue

            topic = str(candidate["main_topic"])
            context = str(candidate["context_text"])
            latest_ts = candidate["latest_ts"] if isinstance(candidate["latest_ts"], datetime) else None

            if not _entity_overlap(base_node.entity, topic):
                continue
            if _context_similarity(base_context, context) < similarity_threshold:
                continue
            if not _time_proximity(base_ts, latest_ts, max_days=max_time_gap_days):
                continue

            target_node = _ensure_node_for_cluster(
                db=db,
                cluster_id=cluster_id,
                cluster_topic=topic,
                context_text=context,
                latest_ts=latest_ts,
                by_cluster=node_by_cluster,
            )
            if target_node.id not in visited_node_ids and target_node.cluster_id not in {n.cluster_id for n in seed_nodes}:
                new_nodes += 1

            edge_key = (base_node.id, target_node.id, "expands_to")
            if edge_key not in existing_edges:
                db.add(
                    Edge(
                        from_node_id=base_node.id,
                        to_node_id=target_node.id,
                        relation_type="expands_to",
                        confidence_score=0.6,
                    )
                )
                existing_edges.add(edge_key)
                new_edges += 1

            if target_node.id not in visited_node_ids:
                visited_node_ids.add(target_node.id)
                queue.append((target_node, depth + 1))

    db.commit()
    return {"new_nodes": new_nodes, "new_edges": new_edges}
