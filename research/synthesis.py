"""Synthesis and Lead Generation.

Synthesizes data from the 5 pillars into structured summaries,
impact profiles, and generates scored Investigation Leads with explicit types.
"""

from typing import Any
from research.gather import PillarData
from research.typing import generate_candidates_from_text


def _synthesize_summary(node_entity: str, data: PillarData) -> dict[str, Any]:
    """Compile the top-level summary section."""
    phase = "Isolated Event"
    if data.timeline_context.get("is_anchor"):
        phase = "Trigger Event (Anchor)"
    elif data.timeline_context.get("position", 0) > 0:
        phase = f"Cascade Reaction (Position {data.timeline_context['position']})"

    # Combine text and extract top entities
    combined_text = " ".join(data.source_texts)
    top_entities = [e[0] for e in generate_candidates_from_text(combined_text, top_n=5)]
    # Ensure node entity is included
    if node_entity and node_entity not in top_entities:
        top_entities.insert(0, node_entity)

    return {
        "primary_entities": top_entities[:5],
        "source_diversity": data.source_count,
        "news_velocity": f"{data.news_velocity} related articles",
        "timeline_phase": phase,
    }


def _synthesize_causal_chain(data: PillarData) -> dict[str, Any]:
    """Compile causal predecessors and successors."""
    caused_by = []
    for pred in data.predecessors:
        caused_by.append(f"[{pred['relation']}] Node {pred['node_id']}: {pred['entity']}")

    resulted_in = []
    for succ in data.successors:
        resulted_in.append(f"[{succ['relation']}] Node {succ['node_id']}: {succ['entity']}")

    return {
        "caused_by": caused_by,
        "resulted_in": resulted_in,
    }


def _synthesize_impact_profile(data: PillarData) -> dict[str, Any]:
    """Compile consequence and sentiment profiling."""
    sectors = set()
    losers = 0
    winners = 0

    for imp in data.impacts:
        # Extract basic sectors from winner/loser tags (simple heuristic)
        for term in imp["short_winners"] + imp["long_winners"]:
            if term: sectors.add(term.split()[0].capitalize())
            winners += 1
        for term in imp["short_losers"] + imp["long_losers"]:
            if term: sectors.add(term.split()[0].capitalize())
            losers += 1

    net_dir = "Neutral"
    if losers > winners:
        net_dir = "Negative/Risk"
    elif winners > losers:
        net_dir = "Positive/Opportunity"

    return {
        "primary_sectors": list(sectors)[:5],
        "net_direction": net_dir,
    }


def _synthesize_signals(data: PillarData) -> list[str]:
    """Compile early warning signals."""
    warnings = []
    for sig in data.signals:
        prefix = "[STRONG]" if sig["strength"] and sig["strength"] > 0.7 else "[WEAK]"
        warnings.append(f"{prefix} {sig['type'].upper()}: {sig['phrase']}")
    return warnings


def _generate_investigation_leads(data: PillarData) -> list[dict[str, Any]]:
    """Generate scored and strongly-typed Investigation Leads.
    
    This is the bridge to recursive expansion. Calculates the base_score
    (Explanatory Value, Investigation Potential, Confidence) which serves
    as the permanent baseline.
    """
    leads = []
    combined_text = " ".join(data.source_texts)
    
    # 1. Generate from text frequencies
    candidates = generate_candidates_from_text(combined_text, top_n=10)
    
    # Add known existing entities to deduplicate or score boost
    existing_entities = {p["entity"].lower() for p in data.predecessors + data.successors}
    
    for entity, node_type in candidates:
        if entity.lower() in existing_entities:
            continue  # Already a node in the causal chain
            
        # Explanatory Value (Max 0.30)
        # Simple heuristic: higher count in source text means higher explanatory value
        count = combined_text.lower().count(entity.lower())
        explanatory = min((count / 10.0) * 0.30, 0.30)
        
        # Investigation Potential (Max 0.25)
        # Multiplier by entity type
        potential_weights = {
            "POLICY": 0.25,
            "COMPANY": 0.22,
            "COUNTRY": 0.20,
            "SECTOR": 0.18,
            "EVENT": 0.15,
            "PERSON": 0.15,
            "CONCEPT": 0.10,
        }
        potential = potential_weights.get(node_type, 0.10)
        
        # Confidence (Max 0.10)
        # Based on source diversity supporting this lead (using total data.source_count as proxy)
        confidence = min((data.source_count / 5.0) * 0.10, 0.10)
        
        base_score = explanatory + potential + confidence
        
        reason = "Frequent co-occurrence in source material"
        if node_type != "CONCEPT":
            reason = f"Primary {node_type.lower()} identified in event context"
            
        leads.append({
            "entity": entity,
            "type": node_type,
            "base_score": round(base_score, 3),
            "reason": reason,
        })
        
    # Sort by score descending
    leads.sort(key=lambda x: x["base_score"], reverse=True)
    return leads


# ---------------------------------------------------------------------------
# Main Synthesis Function
# ---------------------------------------------------------------------------

def synthesize_profile(node_entity: str, data: PillarData) -> dict[str, Any]:
    """Synthesize the full NodeResearchProfile JSON."""
    return {
        "summary": _synthesize_summary(node_entity, data),
        "causal_chain": _synthesize_causal_chain(data),
        "impact_profile": _synthesize_impact_profile(data),
        "signal_warnings": _synthesize_signals(data),
        "research_leads": _generate_investigation_leads(data),
    }
