from re import findall

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.news_intelligence import Impact, Node


# ---------------------------------------------------------------------------
# Event-type detection keywords (expanded: 6 types, 15-25 keywords each)
# ---------------------------------------------------------------------------

_EVENT_TYPE_KEYWORDS: dict[str, set[str]] = {
    "supply": {
        "supply", "shortage", "inventory", "production", "output", "shipment",
        "export", "import", "disruption", "logistics", "freight", "manufacturing",
        "capacity", "stockpile", "warehouse", "bottleneck", "scarcity",
    },
    "demand": {
        "demand", "consumption", "orders", "buying", "retail", "usage",
        "spending", "consumer", "sales", "growth", "appetite", "purchasing",
        "ecommerce", "subscription", "adoption", "market",
    },
    "policy": {
        "policy", "regulation", "tax", "ban", "tariff", "sanction", "subsidy",
        "legislation", "compliance", "mandate", "reform", "governance",
        "deregulation", "enforcement", "quota", "restriction", "amendment",
    },
    "financial": {
        "rate", "inflation", "earnings", "credit", "liquidity", "funding", "debt",
        "interest", "bond", "equity", "dividend", "banking", "loan",
        "default", "yield", "monetary", "fiscal", "reserve",
    },
    "geopolitical": {
        "war", "conflict", "military", "sanctions", "treaty", "alliance",
        "invasion", "missile", "nuclear", "border", "tension", "diplomacy",
        "sovereignty", "occupation", "ceasefire", "embargo", "retaliation",
    },
    "technology": {
        "technology", "innovation", "digital", "cyber", "artificial",
        "automation", "software", "semiconductor", "chip", "patent",
        "startup", "platform", "cloud", "data", "blockchain",
    },
}


# ---------------------------------------------------------------------------
# Sector detection keywords
# ---------------------------------------------------------------------------

_SECTOR_KEYWORDS: dict[str, set[str]] = {
    "energy": {
        "oil", "gas", "energy", "petroleum", "crude", "fuel", "solar",
        "wind", "renewable", "coal", "nuclear", "opec", "refinery", "pipeline",
    },
    "banking": {
        "bank", "banking", "lender", "loan", "credit", "deposit",
        "mortgage", "fintech", "payment", "insurance", "underwriting",
    },
    "technology": {
        "tech", "software", "semiconductor", "chip", "cloud", "saas",
        "platform", "data", "digital", "cyber", "startup", "venture",
    },
    "defense": {
        "defense", "military", "arms", "weapon", "missile", "navy",
        "aerospace", "security", "intelligence", "surveillance",
    },
    "agriculture": {
        "agriculture", "crop", "grain", "wheat", "rice", "fertilizer",
        "farm", "livestock", "food", "harvest", "commodity", "soybean",
    },
    "healthcare": {
        "health", "pharma", "pharmaceutical", "hospital", "vaccine",
        "drug", "medical", "biotech", "clinical", "patient",
    },
    "infrastructure": {
        "infrastructure", "construction", "transport", "railway", "port",
        "highway", "bridge", "housing", "real", "estate", "development",
    },
    "manufacturing": {
        "manufacturing", "factory", "industrial", "steel", "auto",
        "automotive", "assembly", "component", "machinery", "textile",
    },
}


# ---------------------------------------------------------------------------
# Direction cues — positive / negative signal in the text
# ---------------------------------------------------------------------------

_POSITIVE_CUES = {
    "growth", "surge", "boost", "gain", "rise", "increase", "expand",
    "improve", "rally", "upgrade", "recover", "bullish", "strong", "upside",
}

_NEGATIVE_CUES = {
    "decline", "drop", "crash", "crisis", "fall", "loss", "collapse",
    "downturn", "recession", "slump", "bearish", "weak", "downside", "cut",
}


# ---------------------------------------------------------------------------
# Impact rules — structured direct + indirect winners/losers
# ---------------------------------------------------------------------------

_IMPACT_RULES: dict[str, dict[str, list[str]]] = {
    "supply": {
        "short_term_winners": [
            "DIRECT: commodity producers & exporters",
            "DIRECT: logistics & freight operators",
            "INDIRECT: domestic manufacturers (import-substitution)",
            "INDIRECT: alternative-material suppliers",
        ],
        "short_term_losers": [
            "DIRECT: downstream consumers & importers",
            "DIRECT: energy-intensive industries",
            "INDIRECT: retail chains dependent on imports",
            "INDIRECT: transport-cost-sensitive exporters",
        ],
        "long_term_winners": [
            "DIRECT: supply-chain automation providers",
            "DIRECT: domestic manufacturing capacity builders",
            "INDIRECT: nearshoring logistics platforms",
            "INDIRECT: inventory-management technology firms",
        ],
        "long_term_losers": [
            "DIRECT: high-cost, low-efficiency producers",
            "DIRECT: regions dependent on single-source imports",
            "INDIRECT: legacy distribution networks",
        ],
    },
    "demand": {
        "short_term_winners": [
            "DIRECT: consumer brands & retailers",
            "DIRECT: e-commerce platforms",
            "INDIRECT: advertising & marketing agencies",
            "INDIRECT: last-mile delivery services",
        ],
        "short_term_losers": [
            "DIRECT: budget/discount competitors losing margin",
            "DIRECT: inventory-heavy legacy retailers",
            "INDIRECT: warehouse operators with excess capacity",
        ],
        "long_term_winners": [
            "DIRECT: scalable digital platforms",
            "DIRECT: subscription-model businesses",
            "INDIRECT: consumer-data analytics firms",
            "INDIRECT: adaptive supply-chain operators",
        ],
        "long_term_losers": [
            "DIRECT: brick-and-mortar-only retailers",
            "DIRECT: low-innovation consumer goods firms",
            "INDIRECT: outdated distribution models",
        ],
    },
    "policy": {
        "short_term_winners": [
            "DIRECT: compliant incumbents & first-movers",
            "DIRECT: legal, audit & compliance service providers",
            "INDIRECT: local/domestic alternatives to restricted goods",
            "INDIRECT: government-aligned infrastructure contractors",
        ],
        "short_term_losers": [
            "DIRECT: non-compliant firms facing penalties",
            "DIRECT: cross-border operators under new restrictions",
            "INDIRECT: industries in newly regulated sectors",
            "INDIRECT: consumers facing higher compliance-driven prices",
        ],
        "long_term_winners": [
            "DIRECT: policy-aligned green/clean industries",
            "DIRECT: public-infrastructure project operators",
            "INDIRECT: ESG-compliant investment funds",
        ],
        "long_term_losers": [
            "DIRECT: legacy operators resisting transition",
            "DIRECT: high-emission asset owners",
            "INDIRECT: jurisdictions losing competitive advantage",
        ],
    },
    "financial": {
        "short_term_winners": [
            "DIRECT: cash-rich corporations & sovereign funds",
            "DIRECT: short-duration fixed-income holders",
            "INDIRECT: defensive sectors (utilities, staples)",
            "INDIRECT: distressed-debt investors",
        ],
        "short_term_losers": [
            "DIRECT: highly leveraged companies",
            "DIRECT: speculative & growth assets",
            "INDIRECT: rate-sensitive sectors (real estate, autos)",
            "INDIRECT: emerging-market borrowers",
        ],
        "long_term_winners": [
            "DIRECT: risk-managed lenders & insurers",
            "DIRECT: capital-efficient business models",
            "INDIRECT: financial-technology disruptors",
        ],
        "long_term_losers": [
            "DIRECT: overleveraged borrowers & zombie firms",
            "DIRECT: weak-balance-sheet banks",
            "INDIRECT: pension funds with duration mismatch",
        ],
    },
    "geopolitical": {
        "short_term_winners": [
            "DIRECT: defense & aerospace contractors",
            "DIRECT: energy exporters in non-conflict zones",
            "INDIRECT: cybersecurity & surveillance firms",
            "INDIRECT: alternative trade-route logistics providers",
        ],
        "short_term_losers": [
            "DIRECT: companies operating in conflict zones",
            "DIRECT: airlines & shipping through affected corridors",
            "INDIRECT: tourism & hospitality in affected regions",
            "INDIRECT: multinational firms with sanctioned counterparts",
        ],
        "long_term_winners": [
            "DIRECT: domestic defense industry build-out",
            "DIRECT: critical-mineral diversification strategies",
            "INDIRECT: allied-nation infrastructure programs",
        ],
        "long_term_losers": [
            "DIRECT: economies dependent on sanctioned trade",
            "DIRECT: cross-border investment exposed to geopolitical risk",
            "INDIRECT: global-supply-chain-dependent manufacturers",
        ],
    },
    "technology": {
        "short_term_winners": [
            "DIRECT: AI & cloud-platform leaders",
            "DIRECT: semiconductor manufacturers",
            "INDIRECT: enterprise-software integrators",
            "INDIRECT: venture capital in emerging tech",
        ],
        "short_term_losers": [
            "DIRECT: legacy IT vendors losing market share",
            "DIRECT: workforce segments facing automation",
            "INDIRECT: hardware-dependent business models",
        ],
        "long_term_winners": [
            "DIRECT: platform-economy operators",
            "DIRECT: IP-rich patent portfolios",
            "INDIRECT: digital-infrastructure builders",
            "INDIRECT: data-governance & privacy firms",
        ],
        "long_term_losers": [
            "DIRECT: non-digital-native businesses",
            "DIRECT: manual-process-dependent industries",
            "INDIRECT: regions with low digital infrastructure",
        ],
    },
}


# ---------------------------------------------------------------------------
# Sector-specific impact actors
# ---------------------------------------------------------------------------

_SECTOR_ACTORS: dict[str, dict[str, list[str]]] = {
    "energy": {
        "winners": ["oil & gas majors", "renewable-energy developers", "energy traders"],
        "losers": ["energy-importing economies", "fossil-fuel-dependent utilities"],
    },
    "banking": {
        "winners": ["well-capitalized banks", "fintech lenders"],
        "losers": ["sub-prime lenders", "under-capitalized regional banks"],
    },
    "technology": {
        "winners": ["cloud providers", "chip designers", "cybersecurity firms"],
        "losers": ["legacy hardware vendors", "manual-process industries"],
    },
    "defense": {
        "winners": ["defense contractors", "surveillance-tech firms"],
        "losers": ["peace-dividend sectors", "dual-use export firms"],
    },
    "agriculture": {
        "winners": ["agri-commodity exporters", "fertilizer producers"],
        "losers": ["food-importing nations", "smallholder farmers"],
    },
    "healthcare": {
        "winners": ["pharma majors", "biotech innovators", "medical-device makers"],
        "losers": ["uninsured populations", "generic-drug-only firms"],
    },
    "infrastructure": {
        "winners": ["construction conglomerates", "cement & steel producers"],
        "losers": ["urban commuters (during construction)", "displaced communities"],
    },
    "manufacturing": {
        "winners": ["automated-factory operators", "precision-component makers"],
        "losers": ["labor-intensive assembly plants", "high-cost-region factories"],
    },
}


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in findall(r"[a-zA-Z0-9]{3,}", text or "")}


def classify_event_type(text: str) -> str:
    """Classify event type by strongest keyword-match score."""
    terms = _tokenize(text)
    scores = {
        event_type: len(terms.intersection(keywords))
        for event_type, keywords in _EVENT_TYPE_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return "policy"  # safe default
    return ranked[0][0]


def _detect_sectors(text: str) -> list[str]:
    """Detect which sectors are mentioned in the text."""
    terms = _tokenize(text)
    hits: list[tuple[str, int]] = []
    for sector, keywords in _SECTOR_KEYWORDS.items():
        overlap = len(terms.intersection(keywords))
        if overlap >= 1:
            hits.append((sector, overlap))

    hits.sort(key=lambda x: x[1], reverse=True)
    return [sector for sector, _ in hits[:3]]  # top 3 sectors


def _detect_direction(text: str) -> str:
    """Detect whether the event has a positive, negative, or neutral direction."""
    terms = _tokenize(text)
    positive = len(terms.intersection(_POSITIVE_CUES))
    negative = len(terms.intersection(_NEGATIVE_CUES))

    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _compute_confidence(text: str, event_type: str, sectors: list[str]) -> float:
    """Multi-signal confidence: keyword match + direction clarity + sector relevance.

    Weights:
    - Keyword match (0.50): how many event-type keywords hit
    - Direction clarity (0.30): clear positive/negative signal
    - Sector relevance (0.20): text mentions specific sectors
    """
    terms = _tokenize(text)

    # Signal 1: keyword match strength
    hits = len(terms.intersection(_EVENT_TYPE_KEYWORDS.get(event_type, set())))
    keyword_signal = min(hits / 5.0, 1.0)

    # Signal 2: direction clarity
    positive_hits = len(terms.intersection(_POSITIVE_CUES))
    negative_hits = len(terms.intersection(_NEGATIVE_CUES))
    direction_signal = min(abs(positive_hits - negative_hits) / 3.0, 1.0)

    # Signal 3: sector relevance
    sector_signal = min(len(sectors) / 2.0, 1.0)

    raw = (0.50 * keyword_signal) + (0.30 * direction_signal) + (0.20 * sector_signal)
    return round(min(max(raw, 0.25), 0.95), 3)


def _build_impact_lists(
    event_type: str,
    text: str,
    sectors: list[str],
) -> dict[str, list[str]]:
    """Build winners/losers lists from event-type rules + sector actors.

    1) Start with the primary event-type rules (direct + indirect).
    2) Detect secondary event type — if it scores >= 50% of primary,
       blend its rules as indirect effects.
    3) Append sector-specific actors for detected sectors.
    """
    rules = _IMPACT_RULES.get(event_type, _IMPACT_RULES["policy"])

    result: dict[str, list[str]] = {
        "short_term_winners": list(rules["short_term_winners"]),
        "short_term_losers": list(rules["short_term_losers"]),
        "long_term_winners": list(rules["long_term_winners"]),
        "long_term_losers": list(rules["long_term_losers"]),
    }

    # ---- Secondary type blending ----
    terms = _tokenize(text)
    scores = {
        et: len(terms.intersection(kw))
        for et, kw in _EVENT_TYPE_KEYWORDS.items()
        if et != event_type
    }
    primary_score = len(terms.intersection(_EVENT_TYPE_KEYWORDS.get(event_type, set())))

    if scores:
        secondary_type, secondary_score = max(scores.items(), key=lambda x: x[1])
        if primary_score > 0 and secondary_score >= (primary_score * 0.5):
            secondary_rules = _IMPACT_RULES.get(secondary_type, {})
            for key in result:
                for entry in secondary_rules.get(key, []):
                    blended = entry.replace("DIRECT:", "INDIRECT (secondary):").replace("INDIRECT:", "INDIRECT (secondary):")
                    if blended not in result[key]:
                        result[key].append(blended)

    # ---- Sector-specific actors ----
    for sector in sectors:
        actors = _SECTOR_ACTORS.get(sector, {})
        for actor in actors.get("winners", []):
            entry = f"SECTOR [{sector}]: {actor}"
            if entry not in result["short_term_winners"]:
                result["short_term_winners"].append(entry)
        for actor in actors.get("losers", []):
            entry = f"SECTOR [{sector}]: {actor}"
            if entry not in result["short_term_losers"]:
                result["short_term_losers"].append(entry)

    return result


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _upsert_impact(
    db: Session,
    node: Node,
    event_type: str,
    confidence_score: float,
    impact_lists: dict[str, list[str]],
) -> None:
    current = db.scalar(select(Impact).where(Impact.node_id == node.id))

    if current is None:
        db.add(
            Impact(
                node_id=node.id,
                short_term_winners=impact_lists["short_term_winners"],
                short_term_losers=impact_lists["short_term_losers"],
                long_term_winners=impact_lists["long_term_winners"],
                long_term_losers=impact_lists["long_term_losers"],
                confidence_score=confidence_score,
            )
        )
    else:
        current.short_term_winners = impact_lists["short_term_winners"]
        current.short_term_losers = impact_lists["short_term_losers"]
        current.long_term_winners = impact_lists["long_term_winners"]
        current.long_term_losers = impact_lists["long_term_losers"]
        current.confidence_score = confidence_score

    node.impact_type = event_type


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_impact(db: Session, limit: int = 500) -> dict[str, int]:
    """
    Deterministic impact analysis (incremental, sector-aware).

    Steps:
    1) Fetch nodes WITHOUT existing impact entries
    2) Classify event type (supply/demand/policy/financial/geopolitical/technology)
    3) Detect relevant sectors from node text
    4) Detect direction (positive/negative/neutral)
    5) Compute multi-signal confidence score
    6) Build structured winners/losers with direct/indirect + sector actors
    7) Blend secondary event-type rules if strongly detected
    8) Persist impact row
    """
    rows = (
        db.execute(
            select(Node)
            .outerjoin(Impact, Impact.node_id == Node.id)
            .where(Impact.id.is_(None))
            .order_by(Node.created_at.asc(), Node.id.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if not rows:
        return {"processed_nodes": 0, "impact_rows_written": 0}

    impact_rows_written = 0
    for node in rows:
        text = f"{node.event_type or ''} {node.entity or ''} {node.description or ''}"

        event_type = classify_event_type(text)
        sectors = _detect_sectors(text)
        confidence = _compute_confidence(text, event_type, sectors)
        impact_lists = _build_impact_lists(event_type, text, sectors)

        _upsert_impact(
            db=db,
            node=node,
            event_type=event_type,
            confidence_score=confidence,
            impact_lists=impact_lists,
        )
        impact_rows_written += 1

    db.commit()
    return {"processed_nodes": len(rows), "impact_rows_written": impact_rows_written}
