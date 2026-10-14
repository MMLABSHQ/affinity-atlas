"""Optional, bounded LLM format selector: never invents Qloo evidence.

The model can choose/order only 3 of 5 predefined format IDs.
All artist/movie/brand/place entities, explanations and verification notices
are assembled and validated by deterministic code, not by a model.

No external LLM request is sent without explicit server-side env configuration.
Never send a Qloo API key to the LLM provider. No prompt/output logging.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from decision_engine import FORMATS, PREFERENCES, parse_objective

FORMAT_NAMES = {x[0]: x[1] for x in FORMATS}


def eligible_formats(branches: dict) -> list[str]:
    """Return only formats backed by present, Qloo-originating entity IDs."""
    def supported(kind: str) -> bool:
        return any(isinstance(e, dict) and e.get("entity_id") and
                   str(e.get("source", "")).startswith("Qloo ")
                   for e in branches.get(kind, []))

    places = [p for p in branches.get("place", [])
              if isinstance(p, dict) and p.get("entity_id") and
              str(p.get("source", "")).startswith("Qloo ") and
              p.get("venue_review", {}).get("tier") != "space_requires_permits"]
    if not places:
        return []
    return [format_id for format_id, _, _, needs in FORMATS if all(supported(k) for k in needs)]


def configured() -> bool:
    return bool(os.environ.get("ATLAS_LLM_URL", "").strip() and
                os.environ.get("ATLAS_LLM_MODEL", "").strip())


def _safe_endpoint(url: str) -> bool:
    """Only HTTPS remote endpoints or HTTP on loopback hosts, configured by owner."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return bool(u.hostname and not u.username and not u.password and
                u.query == '' and u.fragment == '' and
                (u.scheme == 'https' or
                 (u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost', '::1'))))


def validate_choice(raw: object, eligible: list[str], objective: str = "") -> list[str] | None:
    """Critic contract: exactly three distinct supported format IDs, nothing else."""
    if not isinstance(raw, dict):
        return None
    selected = raw.get("formats")
    if (not isinstance(selected, list) or len(selected) != 3 or
        any(not isinstance(x, str) for x in selected) or
        len(set(selected)) != 3 or any(x not in eligible for x in selected)):
        return None
    if objective:
        intent = parse_objective(objective)["primary"]
        goal_ranking = [fmt for fmt in PREFERENCES[intent] if fmt in eligible]
        # A model can reorder formats, but cannot lead with a manifestly
        # off-objective option when goal-aligned formats are available.
        if selected[0] not in goal_ranking[:3]:
            return None
    return selected


def review_formats(anchor: dict, branches: dict, city: str, objective: str) -> tuple[list[str] | None, str]:
    """Single model call + strict critique; on any failure use deterministic fallback.

    Sends only whitelisted context fields and Qloo entity names, no credentials.
    """
    if not configured():
        return None, "not_configured"
    endpoint = os.environ.get("ATLAS_LLM_URL", "").strip()
    if not _safe_endpoint(endpoint):
        return None, "invalid_endpoint"
    elig = eligible_formats(branches)
    if len(elig) < 3:
        return None, "insufficient_evidence"
    user_data = {
        "artist": str(anchor.get("name", ""))[:80],
        "city": city[:80],
        "programming_objective": objective[:180],
        "supported_format_ids": elig,
        "formats": [{"id": fid, "title": FORMAT_NAMES[fid]} for fid in elig],
        "evidence_names": {kind: [str(x.get("name", ""))[:100] for x in branches.get(kind, [])[:5]]
                           for kind in ("movie", "brand", "place")},
        "venue_status": [{"name": str(x.get("name", ""))[:100],
                          "tier": x.get("venue_review", {}).get("tier", "unverified")}
                         for x in branches.get("place", [])[:5]],
    }
    system = (
        "You are a bounded editorial programme planner. Select and order exactly THREE "
        "DISTINCT format IDs from supported_format_ids that best satisfy the user's goal. "
        "Prefer diverse educational formats for educational objectives; prioritise "
        "screenings for film objectives and sound formats for audio objectives. "
        "The evidence names are independent Qloo results and do NOT establish "
        "agreements, venue suitability, availability, costs, sponsorships, or "
        "compatibility percentages. Do not invent facts or output any entity names. "
        "Your ONLY output must be a compact JSON object with exactly this shape: "
        '{"formats":["id1","id2","id3"]}. No markdown or prose.'
    )
    payload = {"model": os.environ["ATLAS_LLM_MODEL"].strip(),
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)}],
               "temperature": 0, "max_tokens": 160}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = os.environ.get("ATLAS_LLM_API_KEY", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if int(response.headers.get("Content-Length", "0") or 0) > 120000:
                return None, "oversize_response"
            body = json.loads(response.read(120001))
        if not isinstance(body, dict):
            return None, "malformed_response"
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or len(content) > 4000:
            return None, "malformed_response"
        choice = validate_choice(json.loads(content), elig, objective)
        if not choice:
            return None, "choice_rejected_by_critic"
        return choice, "validated"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "transport_error"
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None, "malformed_response"
