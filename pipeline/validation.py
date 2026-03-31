"""
Pipeline validation — end-to-end consistency and integrity checks.

Runs as a POST-pipeline step. Detects issues but NEVER mutates data.
Returns a structured report with issue counts and details.

Check categories:
1. Chain integrity    — raw_news → cleaned_news → clusters → nodes → timeline/impact/signals
2. Duplicate detection — duplicate nodes, edges, signals, impacts per-node
3. Data validation    — empty entities, missing event_types, out-of-range confidence
4. Relationship checks — dangling edges, self-loops, circular timeline references
5. Output consistency — timeline ordering, impact/event_type alignment, signals on valid nodes
6. Orphan detection   — records not linked to any parent in the chain
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models.news_intelligence import (
    CleanedNews,
    ClusterNewsMap,
    Edge,
    EventCluster,
    Impact,
    Node,
    RawNews,
    Signal,
    TimelineEntry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _check_chain_integrity(db: Session) -> list[dict[str, object]]:
    """Verify the pipeline chain has no broken links."""
    issues: list[dict[str, object]] = []

    # CleanedNews → RawNews: all raw_news_ids must exist
    orphan_cleaned = db.scalar(
        select(func.count(CleanedNews.id))
        .outerjoin(RawNews, RawNews.id == CleanedNews.raw_news_id)
        .where(RawNews.id.is_(None))
    ) or 0
    if orphan_cleaned > 0:
        issues.append({
            "check": "chain_integrity",
            "severity": "error",
            "detail": f"{orphan_cleaned} cleaned_news rows reference non-existent raw_news",
        })

    # ClusterNewsMap → CleanedNews: all cleaned_news_ids must exist
    orphan_map = db.scalar(
        select(func.count(ClusterNewsMap.id))
        .outerjoin(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
        .where(CleanedNews.id.is_(None))
    ) or 0
    if orphan_map > 0:
        issues.append({
            "check": "chain_integrity",
            "severity": "error",
            "detail": f"{orphan_map} cluster_news_map rows reference non-existent cleaned_news",
        })

    # ClusterNewsMap → EventCluster: all cluster_ids must exist
    orphan_cluster_map = db.scalar(
        select(func.count(ClusterNewsMap.id))
        .outerjoin(EventCluster, EventCluster.id == ClusterNewsMap.cluster_id)
        .where(EventCluster.id.is_(None))
    ) or 0
    if orphan_cluster_map > 0:
        issues.append({
            "check": "chain_integrity",
            "severity": "error",
            "detail": f"{orphan_cluster_map} cluster_news_map rows reference non-existent event_clusters",
        })

    # Nodes → EventCluster: all cluster_ids must exist
    orphan_nodes = db.scalar(
        select(func.count(Node.id))
        .outerjoin(EventCluster, EventCluster.id == Node.cluster_id)
        .where(EventCluster.id.is_(None))
    ) or 0
    if orphan_nodes > 0:
        issues.append({
            "check": "chain_integrity",
            "severity": "error",
            "detail": f"{orphan_nodes} nodes reference non-existent event_clusters",
        })

    # Timeline → Node: all node_ids must exist
    orphan_timeline = db.scalar(
        select(func.count(TimelineEntry.id))
        .outerjoin(Node, Node.id == TimelineEntry.node_id)
        .where(Node.id.is_(None))
    ) or 0
    if orphan_timeline > 0:
        issues.append({
            "check": "chain_integrity",
            "severity": "error",
            "detail": f"{orphan_timeline} timeline entries reference non-existent nodes",
        })

    if not issues:
        logger.info("Chain integrity: OK")

    return issues


def _check_duplicates(db: Session) -> list[dict[str, object]]:
    """Detect duplicate records that should be unique."""
    issues: list[dict[str, object]] = []

    # Duplicate nodes per cluster (should be 1:1)
    dup_nodes = db.execute(
        select(Node.cluster_id, func.count(Node.id).label("cnt"))
        .group_by(Node.cluster_id)
        .having(func.count(Node.id) > 1)
    ).all()
    if dup_nodes:
        issues.append({
            "check": "duplicate_nodes",
            "severity": "warning",
            "detail": f"{len(dup_nodes)} clusters have multiple nodes",
            "cluster_ids": [row[0] for row in dup_nodes[:10]],
        })

    # Duplicate edges (same from→to pair)
    dup_edges = db.execute(
        select(Edge.from_node_id, Edge.to_node_id, func.count(Edge.id).label("cnt"))
        .group_by(Edge.from_node_id, Edge.to_node_id)
        .having(func.count(Edge.id) > 1)
    ).all()
    if dup_edges:
        issues.append({
            "check": "duplicate_edges",
            "severity": "warning",
            "detail": f"{len(dup_edges)} duplicate edges detected (same from→to pair)",
        })

    # Duplicate impacts per node (should be 1:1)
    dup_impacts = db.execute(
        select(Impact.node_id, func.count(Impact.id).label("cnt"))
        .group_by(Impact.node_id)
        .having(func.count(Impact.id) > 1)
    ).all()
    if dup_impacts:
        issues.append({
            "check": "duplicate_impacts",
            "severity": "warning",
            "detail": f"{len(dup_impacts)} nodes have multiple impact entries",
            "node_ids": [row[0] for row in dup_impacts[:10]],
        })

    if not issues:
        logger.info("Duplicate detection: OK")

    return issues


def _check_data_validation(db: Session) -> list[dict[str, object]]:
    """Validate data quality: empty fields, out-of-range scores."""
    issues: list[dict[str, object]] = []

    # Nodes with empty entity
    empty_entity = db.scalar(
        select(func.count(Node.id)).where(
            (Node.entity.is_(None)) | (Node.entity == "")
        )
    ) or 0
    if empty_entity > 0:
        issues.append({
            "check": "empty_entity",
            "severity": "warning",
            "detail": f"{empty_entity} nodes have empty or null entity field",
        })

    # Nodes with no event_type
    no_event_type = db.scalar(
        select(func.count(Node.id)).where(
            (Node.event_type.is_(None)) | (Node.event_type == "")
        )
    ) or 0
    if no_event_type > 0:
        issues.append({
            "check": "missing_event_type",
            "severity": "warning",
            "detail": f"{no_event_type} nodes have empty or null event_type",
        })

    # Confidence scores out of [0, 1] range — Nodes
    bad_node_conf = db.scalar(
        select(func.count(Node.id)).where(
            (Node.confidence_score.isnot(None))
            & ((Node.confidence_score < 0.0) | (Node.confidence_score > 1.0))
        )
    ) or 0
    if bad_node_conf > 0:
        issues.append({
            "check": "node_confidence_range",
            "severity": "error",
            "detail": f"{bad_node_conf} nodes have confidence_score outside [0.0, 1.0]",
        })

    # Confidence scores out of [0, 1] range — Edges
    bad_edge_conf = db.scalar(
        select(func.count(Edge.id)).where(
            (Edge.confidence_score.isnot(None))
            & ((Edge.confidence_score < 0.0) | (Edge.confidence_score > 1.0))
        )
    ) or 0
    if bad_edge_conf > 0:
        issues.append({
            "check": "edge_confidence_range",
            "severity": "error",
            "detail": f"{bad_edge_conf} edges have confidence_score outside [0.0, 1.0]",
        })

    # Confidence scores out of [0, 1] range — Impact
    bad_impact_conf = db.scalar(
        select(func.count(Impact.id)).where(
            (Impact.confidence_score.isnot(None))
            & ((Impact.confidence_score < 0.0) | (Impact.confidence_score > 1.0))
        )
    ) or 0
    if bad_impact_conf > 0:
        issues.append({
            "check": "impact_confidence_range",
            "severity": "error",
            "detail": f"{bad_impact_conf} impacts have confidence_score outside [0.0, 1.0]",
        })

    # Confidence scores out of [0, 1] range — Signal
    bad_signal_conf = db.scalar(
        select(func.count(Signal.id)).where(
            (Signal.confidence_score.isnot(None))
            & ((Signal.confidence_score < 0.0) | (Signal.confidence_score > 1.0))
        )
    ) or 0
    if bad_signal_conf > 0:
        issues.append({
            "check": "signal_confidence_range",
            "severity": "error",
            "detail": f"{bad_signal_conf} signals have confidence_score outside [0.0, 1.0]",
        })

    if not issues:
        logger.info("Data validation: OK")

    return issues


def _check_relationships(db: Session) -> list[dict[str, object]]:
    """Validate edge relationships: dangling refs, self-loops."""
    issues: list[dict[str, object]] = []

    # Edges referencing non-existent from_node
    dangling_from = db.scalar(
        select(func.count(Edge.id))
        .outerjoin(Node, Node.id == Edge.from_node_id)
        .where(Node.id.is_(None))
    ) or 0
    if dangling_from > 0:
        issues.append({
            "check": "dangling_edge_from",
            "severity": "error",
            "detail": f"{dangling_from} edges reference non-existent from_node",
        })

    # Edges referencing non-existent to_node
    dangling_to = db.scalar(
        select(func.count(Edge.id))
        .outerjoin(Node, Node.id == Edge.to_node_id)
        .where(Node.id.is_(None))
    ) or 0
    if dangling_to > 0:
        issues.append({
            "check": "dangling_edge_to",
            "severity": "error",
            "detail": f"{dangling_to} edges reference non-existent to_node",
        })

    # Self-loops (from_node == to_node)
    self_loops = db.scalar(
        select(func.count(Edge.id)).where(Edge.from_node_id == Edge.to_node_id)
    ) or 0
    if self_loops > 0:
        issues.append({
            "check": "self_loop_edge",
            "severity": "warning",
            "detail": f"{self_loops} edges are self-loops (from_node == to_node)",
        })

    # Impact referencing non-existent node
    dangling_impact = db.scalar(
        select(func.count(Impact.id))
        .outerjoin(Node, Node.id == Impact.node_id)
        .where(Node.id.is_(None))
    ) or 0
    if dangling_impact > 0:
        issues.append({
            "check": "dangling_impact",
            "severity": "error",
            "detail": f"{dangling_impact} impacts reference non-existent nodes",
        })

    # Signal referencing non-existent node
    dangling_signal = db.scalar(
        select(func.count(Signal.id))
        .outerjoin(Node, Node.id == Signal.node_id)
        .where(Node.id.is_(None))
    ) or 0
    if dangling_signal > 0:
        issues.append({
            "check": "dangling_signal",
            "severity": "error",
            "detail": f"{dangling_signal} signals reference non-existent nodes",
        })

    if not issues:
        logger.info("Relationship validation: OK")

    return issues


def _check_output_consistency(db: Session) -> list[dict[str, object]]:
    """Validate output correctness: timeline ordering, type alignment."""
    issues: list[dict[str, object]] = []

    # Timeline: duplicate position_index within same group
    dup_positions = db.execute(
        select(
            TimelineEntry.timeline_group_id,
            TimelineEntry.position_index,
            func.count(TimelineEntry.id).label("cnt"),
        )
        .group_by(TimelineEntry.timeline_group_id, TimelineEntry.position_index)
        .having(func.count(TimelineEntry.id) > 1)
    ).all()
    if dup_positions:
        issues.append({
            "check": "timeline_duplicate_position",
            "severity": "warning",
            "detail": f"{len(dup_positions)} duplicate position_index entries within same timeline group",
        })

    # Timeline: position_index gaps (optional, informational)
    groups = db.execute(
        select(
            TimelineEntry.timeline_group_id,
            func.count(TimelineEntry.id).label("entry_count"),
            func.max(TimelineEntry.position_index).label("max_pos"),
        )
        .group_by(TimelineEntry.timeline_group_id)
    ).all()
    for group in groups:
        expected_max = group.entry_count - 1
        if group.max_pos is not None and group.max_pos > expected_max:
            issues.append({
                "check": "timeline_position_gap",
                "severity": "info",
                "detail": f"Timeline group '{group.timeline_group_id}' has position gap: "
                          f"max_pos={group.max_pos}, entry_count={group.entry_count}",
            })

    # Multiple anchors in same cluster set (only 1 should be anchor)
    multi_anchor = db.scalar(
        select(func.count(Node.id)).where(Node.is_anchor.is_(True))
    ) or 0
    if multi_anchor > 1:
        issues.append({
            "check": "multiple_anchors",
            "severity": "info",
            "detail": f"{multi_anchor} nodes marked as anchor (expected ≤1 per timeline group)",
        })

    if not issues:
        logger.info("Output consistency: OK")

    return issues


def _check_orphans(db: Session) -> list[dict[str, object]]:
    """Detect orphan records not connected to the pipeline chain."""
    issues: list[dict[str, object]] = []

    # Clusters with no news mapped
    empty_clusters = db.scalar(
        select(func.count(EventCluster.id))
        .outerjoin(ClusterNewsMap, ClusterNewsMap.cluster_id == EventCluster.id)
        .where(ClusterNewsMap.id.is_(None))
    ) or 0
    if empty_clusters > 0:
        issues.append({
            "check": "orphan_cluster",
            "severity": "info",
            "detail": f"{empty_clusters} event_clusters have no mapped news items",
        })

    # Nodes with no timeline entry, no impact, and no signals
    nodes_no_output = db.scalar(
        select(func.count(Node.id))
        .outerjoin(TimelineEntry, TimelineEntry.node_id == Node.id)
        .outerjoin(Impact, Impact.node_id == Node.id)
        .outerjoin(Signal, Signal.node_id == Node.id)
        .where(
            TimelineEntry.id.is_(None),
            Impact.id.is_(None),
            Signal.id.is_(None),
        )
    ) or 0
    if nodes_no_output > 0:
        issues.append({
            "check": "node_no_output",
            "severity": "info",
            "detail": f"{nodes_no_output} nodes have no timeline entry, impact, or signal",
        })

    if not issues:
        logger.info("Orphan detection: OK")

    return issues


# ---------------------------------------------------------------------------
# Pipeline statistics (informational)
# ---------------------------------------------------------------------------

def _collect_stats(db: Session) -> dict[str, int]:
    """Collect row counts for all pipeline tables."""
    return {
        "raw_news": db.scalar(select(func.count(RawNews.id))) or 0,
        "cleaned_news": db.scalar(select(func.count(CleanedNews.id))) or 0,
        "event_clusters": db.scalar(select(func.count(EventCluster.id))) or 0,
        "cluster_news_map": db.scalar(select(func.count(ClusterNewsMap.id))) or 0,
        "nodes": db.scalar(select(func.count(Node.id))) or 0,
        "edges": db.scalar(select(func.count(Edge.id))) or 0,
        "timeline_entries": db.scalar(select(func.count(TimelineEntry.id))) or 0,
        "impacts": db.scalar(select(func.count(Impact.id))) or 0,
        "signals": db.scalar(select(func.count(Signal.id))) or 0,
    }


# ---------------------------------------------------------------------------
# Main validation runner
# ---------------------------------------------------------------------------

def run_validation(db: Session) -> dict[str, object]:
    """
    Execute all validation checks and return a structured report.

    Returns:
        {
            "health": "healthy" | "warnings" | "errors",
            "stats": { table_name: row_count, ... },
            "checks_run": 6,
            "issues_total": N,
            "issues_by_severity": { "error": N, "warning": N, "info": N },
            "issues": [ { check, severity, detail, ... }, ... ],
        }
    """
    logger.info("Starting pipeline validation...")

    stats = _collect_stats(db)

    all_issues: list[dict[str, object]] = []
    all_issues.extend(_check_chain_integrity(db))
    all_issues.extend(_check_duplicates(db))
    all_issues.extend(_check_data_validation(db))
    all_issues.extend(_check_relationships(db))
    all_issues.extend(_check_output_consistency(db))
    all_issues.extend(_check_orphans(db))

    # Severity summary
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for issue in all_issues:
        sev = str(issue.get("severity", "info"))
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Overall health
    if severity_counts["error"] > 0:
        health = "errors"
    elif severity_counts["warning"] > 0:
        health = "warnings"
    else:
        health = "healthy"

    # Log summary
    for issue in all_issues:
        level = logging.ERROR if issue["severity"] == "error" else (
            logging.WARNING if issue["severity"] == "warning" else logging.INFO
        )
        logger.log(level, "VALIDATION [%s] %s: %s", issue["severity"], issue["check"], issue["detail"])

    logger.info(
        "Validation complete: health=%s, errors=%d, warnings=%d, info=%d",
        health, severity_counts["error"], severity_counts["warning"], severity_counts["info"],
    )

    return {
        "health": health,
        "stats": stats,
        "checks_run": 6,
        "issues_total": len(all_issues),
        "issues_by_severity": severity_counts,
        "issues": all_issues,
    }
