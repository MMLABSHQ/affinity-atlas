"""Bounded, deterministic, goal-aware reviewer for Qloo-backed editorial concepts.

NOT a generative LLM or autonomous agent. A transparent decision layer that:
parse goal -> propose available formats -> verify evidence -> rank -> revise selection.
Qloo supplies entities only, not endorsements, venues, budgets or deals.
"""
from __future__ import annotations

import re

INTENT_TOKENS = {
    "cinema": ("film", "movie", "cinema", "screen", "pelicula", "película", "cine", "proyecci", "documentary"),
    "audio": ("audio", "music", "listening", "sound", "immersive", "acoustic", "sonido", "música", "musica", "escucha", "inmersiv", "instalaci"),
    "education": ("educat", "student", "learning", "workshop", "taller", "aprendiz", "escuela", "formativ", "didactic", "didáctic"),
    "community": ("community", "neighborhood", "public", "participat", "comunidad", "barrio", "vecinal", "participativ"),
    "interdisciplinary": ("cross-disciplinary", "interdisciplinary", "cross-domain", "hybrid", "multidisciplin", "interdisciplin", "cruzad", "híbrid", "hibrid"),
}
CONSTRAINT_TOKENS = {
    "budget_unverified": ("budget", "affordable", "low-cost", "cheap", "econom", "presupuesto", "barato", "asequible", "coste", "costo"),
    "accessibility_unverified": ("accessib", "accessible", "accesib", "movilidad reducida"),
}
PREFERENCES = {
    "cinema": ("screening", "salon", "workshop", "listening", "exhibition"),
    "audio": ("listening", "exhibition", "salon", "screening", "workshop"),
    "education": ("workshop", "salon", "exhibition", "listening", "screening"),
    "community": ("workshop", "screening", "salon", "listening", "exhibition"),
    "interdisciplinary": ("salon", "screening", "listening", "workshop", "exhibition"),
}
# Generic case remains interdisciplinary; an objective in Spanish and English works.
DEFAULT_INTENT = "interdisciplinary"
VENUE_ORDER = ("candidate_to_contact", "institution_requires_approval", "unverified")


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(token in text for token in terms)


def _count_distinct_hits(text: str, terms: tuple[str, ...]) -> int:
    """Count distinct keyword regions; 'music' and 'musica' aren't two votes."""
    spans = []
    for term in sorted(terms, key=len, reverse=True):
        for match in re.finditer(re.escape(term), text):
            a, b = match.span()
            if all(b <= x or a >= y for x, y in spans):
                spans.append((a, b))
    return len(spans)


def parse_objective(objective: str) -> dict:
    low = objective.casefold()
    hits = {intent: _count_distinct_hits(low, terms) for intent, terms in INTENT_TOKENS.items()}
    # Film/education beats generic 'cross-disciplinary' whenever explicitly requested.
    primary = max(hits, key=lambda k: (hits[k], -list(INTENT_TOKENS).index(k)))
    if not hits[primary]:
        primary = DEFAULT_INTENT
    elif hits["interdisciplinary"] and hits[primary] == hits["interdisciplinary"]:
        # Explicit interdisciplinary goal should win if no other dominant intent.
        primary = "interdisciplinary"
    constraints = [name for name, terms in CONSTRAINT_TOKENS.items() if _matches(low, terms)]
    return {"primary": primary, "signals": [k for k, v in hits.items() if v],
            "constraints": constraints, "method": "keyword intent routing (transparent rules, not an LLM)"}


def _eligible_venues(places: list[dict], intent: dict) -> tuple[list[dict], list[dict]]:
    accepted, rejected = [], []
    for place in places:
        tier = place.get("venue_review", {}).get("tier", "unverified")
        if tier == "space_requires_permits":
            rejected.append({"item": place.get("name", "?"), "reason": "Public/open space: excluded from automatic venue shortlist; permits would be required."})
        else:
            accepted.append(place)
    prefer_institutions = intent["primary"] == "education" and "budget_unverified" not in intent["constraints"]
    ranks = {tier: idx for idx, tier in enumerate(VENUE_ORDER)}
    if prefer_institutions:
        ranks = {"institution_requires_approval": 0, "candidate_to_contact": 1, "unverified": 2}
    accepted.sort(key=lambda p: (ranks.get(p.get("venue_review", {}).get("tier"), 3), places.index(p)))
    return accepted, rejected


# Formats have evidence requirements, but no preassigned entities or venues.
FORMATS = (
    ("screening", "Cinema in Resonance", "Screening + listening session", ("movie",)),
    ("workshop", "Listening Lab", "Facilitated educational workshop", ("movie",)),
    ("listening", "Architecture of Listening", "Immersive sound installation", ("brand",)),
    ("exhibition", "Sound and Form", "Guided sound-design exhibition", ("brand",)),
    ("salon", "Cross-Sense Salon", "Interdisciplinary cultural programme", ("movie", "brand")),
)


def _pick_unused(pool: list[dict], used: set[str]) -> tuple[dict, bool]:
    for e in pool:
        if e.get("entity_id") not in used:
            return e, False
    return pool[0], True  # alternatives exhausted, declare reuse


def _description(strategy: str, artist: str, city: str, venue: dict, media: dict) -> str:
    v = venue["name"]
    movie = media.get("movie", {}).get("name", "")
    brand = media.get("brand", {}).get("name", "")
    if strategy == "screening":
        return f"Explore a screening/listening dialogue between {artist} and ‘{movie}’, with {v} in {city} as a possible venue. Screening rights and bookings are unverified."
    if strategy == "workshop":
        return f"Prototype a guided student workshop connecting the music of {artist} and ‘{movie}’. Assess {v} for educational suitability; curriculum, rights, access and availability are unverified."
    if strategy == "listening":
        return f"Investigate an immersive listening installation inspired by {artist} and {brand} as an audio-design reference. {v} is a candidate, not a booked venue, and {brand} is not a sponsor."
    if strategy == "exhibition":
        return f"Explore a guided sound-design exhibition interpreting {artist} and {brand} as separate Qloo leads. Assess {v} in {city}; educational suitability, access and partnerships are unverified."
    return f"Investigate an interdisciplinary salon around {artist}, ‘{movie}’ and {brand}, using separate Qloo leads. {v} is an unverified venue candidate; the combination is an editorial hypothesis."


def compile_proposals(anchor: dict, branches: dict, city: str, objective: str,
                      selected_formats: list[str] | None = None) -> tuple[list[dict], dict]:
    intent = parse_objective(objective)
    venues, rejected = _eligible_venues(branches.get("place", []), intent)
    ranked = sorted(FORMATS, key=lambda sp: PREFERENCES[intent["primary"]].index(sp[0]))
    if selected_formats is not None:
        # The LLM may choose/order ONLY these known formats; entities are never
        # accepted from the model and are allocated here from real Qloo results.
        ranked = sorted((f for f in FORMATS if f[0] in selected_formats),
                        key=lambda f: selected_formats.index(f[0]))
        rejected.extend({"item": title, "reason": "Not selected by bounded AI review; still eligible for another brief."}
                        for strategy, title, _, _ in FORMATS if strategy not in selected_formats)
    selected = []
    used = {"movie": set(), "brand": set(), "place": set()}
    diversity_audit = []
    considered = 0
    for strategy, title, event_format, needs in ranked:
        if not venues or any(not branches.get(kind) for kind in needs):
            continue
        considered += 1
        if len(selected) >= 3:
            rejected.append({"item": title, "reason": "Not selected: lower priority for this programming objective."})
            continue
        media = {}
        reused = []
        for kind in needs:
            media[kind], is_reuse = _pick_unused(branches[kind], used[kind])
            if is_reuse:
                reused.append(kind)
        venue, is_reuse = _pick_unused(venues, used["place"])
        if is_reuse:
            reused.append("place")
        evidence = [anchor, *(media[k] for k in needs), venue]
        if not all(e.get("entity_id") and str(e.get("source", "")).startswith("Qloo ") for e in evidence):
            rejected.append({"item": title, "reason": "Missing source-backed entity ID."})
            continue
        for kind in needs:
            used[kind].add(media[kind]["entity_id"])
        used["place"].add(venue["entity_id"])
        reason = (f"Selected for the '{intent['primary']}' objective using eligible format, "
                  "source-backed Qloo entities, preliminary venue screening and evidence diversity.")
        if reused:
            reason += f" Reused {', '.join(reused)} because unused alternatives were exhausted."
        concept = {
            "title": title, "format": event_format, "city": city, "objective": objective,
            "description": _description(strategy, anchor["name"], city, venue, media),
            "evidence": evidence, "decision_reason": reason,
            "facts_from_qloo": "These entities were returned by Qloo for the artist; Qloo did not recommend this particular event combination.",
            "creative_inference": "The event format and combined concept are editorial hypotheses, NOT Qloo facts, agreements, feasibility findings or sponsorships.",
            "checks_required": ["Venue suitability, cost, capacity, availability and approval",
                                "Film screening and music/public-performance rights (if applicable)",
                                "Artist/brand permissions and any sponsorship"],
            "confidence_note": "Input-signal score is not a calibrated compatibility percentage; no venue or agreement is confirmed.",
        }
        if "accessibility_unverified" in intent["constraints"]:
            concept["checks_required"].append("Accessibility, step-free access and accommodations (NOT verified by Qloo)")
        if "budget_unverified" in intent["constraints"]:
            concept["checks_required"].append("Itemized budget and affordability (NOT verified by Qloo)")
        selected.append(concept)
        diversity_audit.append({"format": strategy, "venue": venue["name"],
                                "movie": media.get("movie", {}).get("name"),
                                "brand": media.get("brand", {}).get("name"),
                                "reused": reused})
    return selected, {"intent": intent, "considered": considered, "selected": len(selected),
                      "rejected": rejected, "diversity_audit": diversity_audit,
                      "caveat": "Ranking is an editorial policy, not a compatibility/feasibility score. Different Qloo results do not establish a relationship between each other."}
