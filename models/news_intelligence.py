from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class RawNews(Base):
    __tablename__ = "raw_news"
    __table_args__ = (
        UniqueConstraint("unique_id", name="uq_raw_news_unique_id"),
        Index("ix_raw_news_source", "source"),
        Index("ix_raw_news_published_at", "published_at"),
        Index("ix_raw_news_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    unique_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    cleaned_news_items: Mapped[list["CleanedNews"]] = relationship(
        back_populates="raw_news",
        cascade="all, delete-orphan",
    )


class CleanedNews(Base):
    __tablename__ = "cleaned_news"
    __table_args__ = (
        Index("ix_cleaned_news_raw_news_id", "raw_news_id"),
        Index("ix_cleaned_news_language", "language"),
        Index("ix_cleaned_news_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_news_id: Mapped[int] = mapped_column(ForeignKey("raw_news.id", ondelete="CASCADE"), nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    raw_news: Mapped["RawNews"] = relationship(back_populates="cleaned_news_items")
    cluster_links: Mapped[list["ClusterNewsMap"]] = relationship(
        back_populates="cleaned_news",
        cascade="all, delete-orphan",
    )


class EventCluster(Base):
    __tablename__ = "event_clusters"
    __table_args__ = (
        Index("ix_event_clusters_cluster_key", "cluster_key"),
        Index("ix_event_clusters_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cluster_key: Mapped[str] = mapped_column(String(255), nullable=False)
    main_topic: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    news_links: Mapped[list["ClusterNewsMap"]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
    )
    nodes: Mapped[list["Node"]] = relationship(back_populates="cluster", cascade="all, delete-orphan")


class ClusterNewsMap(Base):
    __tablename__ = "cluster_news_map"
    __table_args__ = (
        UniqueConstraint("cluster_id", "cleaned_news_id", name="uq_cluster_news_map_cluster_cleaned"),
        Index("ix_cluster_news_map_cluster_id", "cluster_id"),
        Index("ix_cluster_news_map_cleaned_news_id", "cleaned_news_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("event_clusters.id", ondelete="CASCADE"), nullable=False)
    cleaned_news_id: Mapped[int] = mapped_column(ForeignKey("cleaned_news.id", ondelete="CASCADE"), nullable=False)

    cluster: Mapped["EventCluster"] = relationship(back_populates="news_links")
    cleaned_news: Mapped["CleanedNews"] = relationship(back_populates="cluster_links")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_cluster_id", "cluster_id"),
        Index("ix_nodes_entity", "entity"),
        Index("ix_nodes_timestamp", "timestamp"),
        Index("ix_nodes_created_at", "created_at"),
        # Recursive expansion indexes
        Index("ix_nodes_parent_node_id", "parent_node_id"),
        Index("ix_nodes_expansion_depth", "expansion_depth"),
        Index("ix_nodes_research_status", "research_status"),
        Index("ix_nodes_expansion_status", "expansion_status"),
        Index("ix_nodes_importance_score", "importance_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("event_clusters.id", ondelete="CASCADE"), nullable=False)
    entity: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    impact_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anchor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # --- Recursive expansion fields ---
    expansion_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    parent_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True,
    )
    research_status: Mapped[str] = mapped_column(
        String(50), default="not_started", nullable=False, server_default="not_started",
    )
    expansion_status: Mapped[str] = mapped_column(
        String(50), default="not_started", nullable=False, server_default="not_started",
    )
    importance_score: Mapped[float] = mapped_column(
        Float, default=0.5, nullable=False, server_default="0.5",
    )
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    expanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships ---
    cluster: Mapped["EventCluster"] = relationship(back_populates="nodes")
    outgoing_edges: Mapped[list["Edge"]] = relationship(
        back_populates="from_node",
        foreign_keys="Edge.from_node_id",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["Edge"]] = relationship(
        back_populates="to_node",
        foreign_keys="Edge.to_node_id",
        cascade="all, delete-orphan",
    )
    timeline_entries: Mapped[list["TimelineEntry"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )
    impacts: Mapped[list["Impact"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    research_logs: Mapped[list["NodeResearchLog"]] = relationship(
        back_populates="node", cascade="all, delete-orphan",
    )
    research_profile: Mapped["NodeResearchProfile | None"] = relationship(
        back_populates="node", cascade="all, delete-orphan", uselist=False,
    )

    # Self-referential parent/children for expansion tree
    parent: Mapped["Node | None"] = relationship(
        back_populates="children",
        remote_side="Node.id",
        foreign_keys=[parent_node_id],
    )
    children: Mapped[list["Node"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_node_id],
    )


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        Index("ix_edges_from_node_id", "from_node_id"),
        Index("ix_edges_to_node_id", "to_node_id"),
        Index("ix_edges_relation_type", "relation_type"),
        Index("ix_edges_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    from_node: Mapped["Node"] = relationship(back_populates="outgoing_edges", foreign_keys=[from_node_id])
    to_node: Mapped["Node"] = relationship(back_populates="incoming_edges", foreign_keys=[to_node_id])


class TimelineEntry(Base):
    __tablename__ = "timeline"
    __table_args__ = (
        Index("ix_timeline_node_id", "node_id"),
        Index("ix_timeline_group_id", "timeline_group_id"),
        Index("ix_timeline_position_index", "position_index"),
        Index("ix_timeline_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timeline_group_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="timeline_entries")


class Impact(Base):
    __tablename__ = "impact"
    __table_args__ = (
        Index("ix_impact_node_id", "node_id"),
        Index("ix_impact_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    short_term_winners: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    short_term_losers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    long_term_winners: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    long_term_losers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="impacts")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_node_id", "node_id"),
        Index("ix_signals_signal_type", "signal_type"),
        Index("ix_signals_entity", "entity"),
        Index("ix_signals_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_span: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="signals")


class NodeResearchLog(Base):
    """Audit trail for every research attempt on a node.

    A node can be researched multiple times (re-research after new data
    ingestion, recovery from failure, different parameters). This table
    stores the full history.
    """

    __tablename__ = "node_research_log"
    __table_args__ = (
        Index("ix_research_log_node_id", "node_id"),
        Index("ix_research_log_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    research_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_qualified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    gate_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="research_logs")


class NodeResearchProfile(Base):
    """1:1 profile storing the heavy JSON intelligence for a Node.
    
    Contains the research version and the comprehensive JSON blob
    of summary, causal chain, impact profile, signal warnings, and
    investigation leads.
    """

    __tablename__ = "node_research_profile"
    __table_args__ = (
        Index("ix_node_research_profile_node_id", "node_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True, nullable=False)
    research_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    research_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="research_profile")


class LeadQueue(Base):
    """The central nervous system of the expansion loop.
    
    Tracks investigation leads generated by the Node Research Engine,
    manages their context-aware scoring, and dictates what the
    Recursive Expansion Engine investigates next.
    """

    __tablename__ = "lead_queue"
    __table_args__ = (
        Index("ix_lead_queue_source_node_id", "source_node_id"),
        Index("ix_lead_queue_status", "status"),
        Index("ix_lead_queue_entity", "entity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_goals.id", ondelete="SET NULL"), nullable=True)
    entity: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score_profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    base_score: Mapped[float] = mapped_column(Float, nullable=False)
    dynamic_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    source_node: Mapped["Node"] = relationship("Node", foreign_keys=[source_node_id])
    goal: Mapped["InvestigationGoal | None"] = relationship("InvestigationGoal", foreign_keys=[goal_id])


class InvestigationGoal(Base):
    """The purpose layer of the intelligence system.
    
    Gives the expansion loop a reason to investigate. Every expansion
    decision is evaluated against the active goal's question and keywords.
    Supports hierarchical sub-goals via parent_goal_id.
    """

    __tablename__ = "investigation_goals"
    __table_args__ = (
        Index("ix_investigation_goals_status", "status"),
        Index("ix_investigation_goals_origin_node_id", "origin_node_id"),
        Index("ix_investigation_goals_parent_goal_id", "parent_goal_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("investigation_goals.id", ondelete="CASCADE"), nullable=True,
    )
    origin_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    goal_question: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completion_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expansion_budget: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    expansions_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stall_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    origin_node: Mapped["Node"] = relationship("Node", foreign_keys=[origin_node_id])
    parent_goal: Mapped["InvestigationGoal | None"] = relationship(
        "InvestigationGoal", remote_side="InvestigationGoal.id", foreign_keys=[parent_goal_id],
    )


class EvaluationSnapshot(Base):
    """Point-in-time snapshot of all system evaluation metrics.

    Created after pipeline runs, expansion cycles, manual triggers,
    or benchmark executions. Used for longitudinal learning analysis
    and system health dashboards.
    """

    __tablename__ = "evaluation_snapshots"
    __table_args__ = (
        Index("ix_evaluation_snapshots_snapshot_type", "snapshot_type"),
        Index("ix_evaluation_snapshots_system_version", "system_version"),
        Index("ix_evaluation_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pipeline_run | expansion_cycle | manual | benchmark
    system_version: Mapped[str] = mapped_column(String(50), default="v1.0", nullable=False)
    benchmark_scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("benchmark_scenarios.id", ondelete="SET NULL"), nullable=True,
    )

    # Graph totals
    total_nodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_edges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_leads_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Goal success metrics (Part 1)
    goal_success_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_goal_completion: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_goal_coverage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_goal_efficiency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_goal_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Expansion quality (Part 2)
    expansion_success_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    useful_node_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rejected_lead_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    merge_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    enhancement_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_lead_contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_novelty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Knowledge quality (Part 3)
    knowledge_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    knowledge_growth: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    connection_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    research_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    compression_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Explanatory power (Part 4)
    explanation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Knowledge reuse (Part 5)
    reuse_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    link_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duplicate_prevention_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Investigation efficiency (Part 6)
    avg_nodes_per_goal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_expansions_per_goal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    budget_efficiency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Longitudinal (Part 7)
    graph_growth_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    knowledge_growth_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_loop_risk: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GoalEvaluation(Base):
    """Per-goal evaluation record.

    Created when a goal reaches a terminal state (completed, abandoned)
    or on-demand via the evaluation API.
    """

    __tablename__ = "goal_evaluations"
    __table_args__ = (
        Index("ix_goal_evaluations_goal_id", "goal_id"),
        Index("ix_goal_evaluations_snapshot_id", "snapshot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("investigation_goals.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_snapshots.id", ondelete="SET NULL"), nullable=True,
    )

    completion_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    efficiency_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    satisfaction_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    explanation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    nodes_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nodes_enhanced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nodes_linked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expansions_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expansion_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    knowledge_categories_required: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    knowledge_categories_covered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    causal_chain_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    evaluation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    goal: Mapped["InvestigationGoal"] = relationship("InvestigationGoal", foreign_keys=[goal_id])


class BenchmarkScenario(Base):
    """Reusable investigation scenario for version-to-version comparison."""

    __tablename__ = "benchmark_scenarios"
    __table_args__ = (
        Index("ix_benchmark_scenarios_name", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal_question: Mapped[str] = mapped_column(Text, nullable=False)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    seed_entities: Mapped[list] = mapped_column(JSON, nullable=False)
    expected_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    expected_min_completion: Mapped[float] = mapped_column(Float, default=0.50, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BenchmarkResult(Base):
    """Links a benchmark scenario execution to its evaluation snapshot."""

    __tablename__ = "benchmark_results"
    __table_args__ = (
        Index("ix_benchmark_results_scenario_id", "scenario_id"),
        Index("ix_benchmark_results_system_version", "system_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("benchmark_scenarios.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("evaluation_snapshots.id", ondelete="CASCADE"), nullable=False)
    system_version: Mapped[str] = mapped_column(String(50), nullable=False)

    completion_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    efficiency_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    explanation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    knowledge_density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class IntelligenceAssessment(Base):
    """Represents a structured intelligence report synthesized for an InvestigationGoal."""

    __tablename__ = "intelligence_assessments"
    __table_args__ = (
        Index("ix_intelligence_assessments_goal_id", "goal_id"),
        Index("ix_intelligence_assessments_status", "status"),
        Index("ix_intelligence_assessments_version", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("investigation_goals.id", ondelete="CASCADE"), nullable=False)

    assessment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")

    assessment_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    knowledge_gaps: Mapped[dict] = mapped_column(JSON, nullable=False)
    alternative_explanations: Mapped[dict] = mapped_column(JSON, nullable=False)
    future_scenarios: Mapped[dict] = mapped_column(JSON, nullable=False)
    executive_summary: Mapped[dict] = mapped_column(JSON, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)

    goal: Mapped["InvestigationGoal"] = relationship("InvestigationGoal", foreign_keys=[goal_id])


class AssessmentQualityMetric(Base):
    """Tracks quality and accuracy metrics of generated assessments over time."""

    __tablename__ = "assessment_quality_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("intelligence_assessments.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("evaluation_snapshots.id", ondelete="SET NULL"), nullable=True)

    evidence_strength: Mapped[float] = mapped_column(Float, nullable=False)
    causal_consistency: Mapped[float] = mapped_column(Float, nullable=False)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    stability_score: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    assessment: Mapped["IntelligenceAssessment"] = relationship("IntelligenceAssessment", foreign_keys=[assessment_id])
