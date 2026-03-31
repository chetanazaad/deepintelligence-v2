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
