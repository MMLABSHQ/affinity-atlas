"""Bounded research -> review -> concept construction pipeline.

This is a deterministic prototype, not an LLM-powered autonomous agent.
It never interprets Qloo's input-signal score as a compatibility percentage.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from qloo_client import QlooClient, QlooError
from decision_engine import compile_proposals
from agent_reviewer import review_formats, configured as llm_configured


def venue_assessment(name: str) -> dict:
    """Heuristic venue screening, NOT proof of permission or availability."""
    n = name.casefold()
    public_space = ("el rastro", "plaza", "street", "calle", "parque", "park", "square")
    if any(x in n for x in public_space):
        return {"tier": "space_requires_permits", "note": "Public/commercial space: permits and feasibility must be checked"}
    if any(x in n for x in ("museo", "museum", "galeria", "gallery", "palacio")):
        return {"tier": "institution_requires_approval", "note": "Cultural institution: programming, permission and availability unverified"}
    if any(x in n for x in ("circulo", "círculo", "institut", "instituto", "centro", "centre", "teatro", "theatre", "auditorio")):
        return {"tier": "candidate_to_contact", "note": "Cultural candidate: capacity, approval and availability unverified"}
    return {"tier": "unverified", "note": "Venue type and event feasibility unverified"}


def entity_brief(e: dict, kind: str, seed_id: str) -> dict:
    details = e.get("query") or {}
    explanation = details.get("explainability") if isinstance(details, dict) else None
    signal = explanation.get("signal.interests.entities", []) if isinstance(explanation, dict) else []
    # Presence of the matching input signal is traceability, NOT a 0-100 affinity score.
    matched = any(isinstance(s, dict) and s.get("entity_id") == seed_id for s in signal)
    result = {
        "name": str(e.get("name", "Sin nombre")),
        "entity_id": str(e.get("entity_id", "")),
        "type": kind,
        "source": "Qloo /v2/insights",
        "explainability_present": isinstance(explanation, dict),
        "seed_signal_referenced": matched,
    }
    if kind == "place":
        result["venue_review"] = venue_assessment(result["name"])
    return result


def build_concepts(anchor: dict, branches: dict[str, list[dict]], city: str, objective: str) -> list[dict]:
    """Backward-compatible entry point; delegates to objective-aware review."""
    concepts, _ = compile_proposals(anchor, branches, city, objective)
    return concepts


def run_research(key: str, artist: str, city: str, objective: str) -> dict:
    client = QlooClient(key)
    audit: list[dict] = []
    start = time.monotonic()
    candidate = client.search_artist(artist)
    seed_id = str(candidate.get("entity_id", ""))
    if not seed_id:
        raise QlooError("El artista no incluye un entity_id")
    anchor = {
        "name": str(candidate.get("name", artist)), "entity_id": seed_id,
        "type": "artist", "source": "Qloo /search", "explainability_present": False,
        "seed_signal_referenced": False,
    }
    audit.append({"phase": "Resolve", "detail": f"Resolved artist: {anchor['name']}", "status": "ok"})
    branches = {"movie": [], "brand": [], "place": []}
    warnings = []
    # Three read-only discovery requests; each branch may fail independently.
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(client.insights, seed_id, kind, city): kind
            for kind in branches
        }
        for f in as_completed(future_map):
            kind = future_map[f]
            try:
                results, branch_warnings = f.result()
                branches[kind] = [entity_brief(e, kind, seed_id) for e in results]
                audit.append({"phase": "Research", "detail": f"{kind}: {len(results)} entities", "status": "ok" if results else "empty"})
                for w in branch_warnings:
                    warnings.append({"branch": kind, "detail": str(w)[:300]})
            except QlooError as e:
                warnings.append({"branch": kind, "detail": str(e)})
                audit.append({"phase": "Research", "detail": f"{kind}: API call failed", "status": "warning"})
    selected_formats, review_status = review_formats(anchor, branches, city, objective)
    if selected_formats:
        # Model proposes only format IDs; deterministic engine allocates all
        # Qloo evidence, checks venue type and enforces per-concept diversity.
        concepts, decision = compile_proposals(anchor, branches, city, objective,
                                               selected_formats=selected_formats)
        if len(concepts) != 3:
            selected_formats, review_status = None, "choice_rejected_by_critic"
    if not selected_formats:
        concepts, decision = compile_proposals(anchor, branches, city, objective)
    agent_review = {
        "mode": "bounded_llm" if selected_formats else "rule_based",
        "status": review_status,
        "chosen_formats": selected_formats or [x["format"] for x in decision["diversity_audit"]],
        "evidence_policy": "AI selects format IDs only; all entities are Qloo-sourced, assigned and validated in code",
    }
    decision["agent_review"] = agent_review
    if llm_configured():
        audit.append({"phase": "Agent review", "detail": (
            "LLM choice accepted after evidence checks" if selected_formats
            else "Bounded LLM unavailable/invalid; verified rule policy used"),
            "status": "ok" if selected_formats else "fallback"})
    audit.append({"phase": "Decide", "detail": f"Objective routed to {decision['intent']['primary']} editorial policy", "status": "ok"})
    audit.append({"phase": "Critique", "detail": f"{len(decision['rejected'])} alternatives screened out or deprioritized; venues not confirmed", "status": "ok"})
    audit.append({"phase": "Revise", "detail": f"{len(concepts)} goal-aligned, Qloo-grounded proposals retained", "status": "ok" if concepts else "warning"})
    return {
        "artist": anchor, "city": city, "objective": objective,
        "branches": branches, "concepts": concepts, "decision": decision, "warnings": warnings,
        "trace": audit, "elapsed_ms": round((time.monotonic() - start) * 1000),
        "agent_review": agent_review,
        "method": ("Qloo live research + bounded LLM choice + deterministic evidence critique"
                   if selected_formats else
                   "Qloo live research + goal-aware rule-based decision and critique"),
    }
