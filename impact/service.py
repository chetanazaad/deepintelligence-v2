from re import findall

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import Impact, Node

_EVENT_TYPE_KEYWORDS: dict[str, set[str]] = {
    "supply": {"supply", "shortage", "inventory", "production", "output", "shipment"},
    "demand": {"demand", "consumption", "orders", "buying", "retail", "usage"},
    "policy": {"policy", "regulation", "tax", "ban", "tariff", "sanction", "subsidy"},
    "financial": {"rate", "inflation", "earnings", "credit", "liquidity", "funding", "debt"},
}

_IMPACT_RULES: dict[str, dict[str, list[str]]] = {
    "supply": {
        "short_term_winners": ["producers", "commodity exporters", "logistics providers"],
        "short_term_losers": ["consumers", "importers", "energy-intensive industries"],
        "long_term_winners": ["supply-chain automation", "domestic manufacturers"],
        "long_term_losers": ["inefficient producers", "high-cost regions"],
    },
    "demand": {
        "short_term_winners": ["consumer brands", "retailers", "service providers"],
        "short_term_losers": ["discount competitors", "inventory-heavy laggards"],
        "long_term_winners": ["scalable platforms", "adaptive suppliers"],
        "long_term_losers": ["outdated business models", "low-innovation firms"],
    },
    "policy": {
        "short_term_winners": ["compliant incumbents", "local alternatives", "legal services"],
        "short_term_losers": ["non-compliant firms", "cross-border operators", "regulated sectors"],
        "long_term_winners": ["policy-aligned industries", "infrastructure projects"],
        "long_term_losers": ["legacy operators", "high-emission assets"],
    },
    "financial": {
        "short_term_winners": ["cash-rich firms", "short-duration assets", "defensive sectors"],
        "short_term_losers": ["high-debt companies", "speculative assets", "rate-sensitive sectors"],
        "long_term_winners": ["risk-managed lenders", "capital-efficient businesses"],
        "long_term_losers": ["overleveraged borrowers", "weak-balance-sheet firms"],
    },
}


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in findall(r"[a-zA-Z0-9]{3,}", text or "")}


def classify_event_type(text: str) -> str:
    terms = _tokenize(text)
    scores = {
        event_type: len(terms.intersection(keywords))
        for event_type, keywords in _EVENT_TYPE_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return "policy"
    return ranked[0][0]


def _confidence_from_match(text: str, event_type: str) -> float:
    terms = _tokenize(text)
    hits = len(terms.intersection(_EVENT_TYPE_KEYWORDS[event_type]))
    return min(0.55 + (0.1 * hits), 0.95)


def _upsert_impact(
    db: Session,
    node: Node,
    event_type: str,
    confidence_score: float,
) -> None:
    rules = _IMPACT_RULES[event_type]
    current = db.scalar(select(Impact).where(Impact.node_id == node.id))

    if current is None:
        db.add(
            Impact(
                node_id=node.id,
                short_term_winners=rules["short_term_winners"],
                short_term_losers=rules["short_term_losers"],
                long_term_winners=rules["long_term_winners"],
                long_term_losers=rules["long_term_losers"],
                confidence_score=confidence_score,
            )
        )
    else:
        current.short_term_winners = rules["short_term_winners"]
        current.short_term_losers = rules["short_term_losers"]
        current.long_term_winners = rules["long_term_winners"]
        current.long_term_losers = rules["long_term_losers"]
        current.confidence_score = confidence_score

    node.impact_type = event_type


def analyze_impact(db: Session, limit: int = 500) -> dict[str, int]:
    """
    Deterministic impact analysis:
    - classify each node as supply/demand/policy/financial
    - assign short/long-term winners and losers via fixed rules
    - store results in impact table
    """
    rows = (
        db.execute(select(Node).order_by(Node.created_at.asc(), Node.id.asc()).limit(limit))
        .scalars()
        .all()
    )
    if not rows:
        return {"processed_nodes": 0, "impact_rows_written": 0}

    impact_rows_written = 0
    for node in rows:
        text = f"{node.event_type or ''} {node.entity or ''} {node.description or ''}"
        event_type = classify_event_type(text)
        confidence_score = _confidence_from_match(text, event_type)
        _upsert_impact(db=db, node=node, event_type=event_type, confidence_score=confidence_score)
        impact_rows_written += 1

    db.commit()
    return {"processed_nodes": len(rows), "impact_rows_written": impact_rows_written}
