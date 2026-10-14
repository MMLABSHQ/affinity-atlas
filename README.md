# Affinity Atlas 0.4 — Bounded Agent Review (Optional LLM)

**Status: local research prototype.** Uses Qloo live data but is **not yet a public hackathon submission**. Its optional LLM reviewer is disabled until explicitly configured, and is not a fully autonomous agent. Developed as the Persona B workstream; does not use or alter Persona A's Apertus repository.

## Run locally (Ubuntu/macOS, Python 3.10+)

```bash
python3 -m unittest discover -v
python3 app.py
```

Open http://127.0.0.1:8765. Provide your own Qloo key in the local form **only**, or start with a server-side `QLOO_API_KEY` environment variable. The key is not stored in files, browser storage, or API logs. If the key was exposed in a conversation, **rotate it before any public deployment**. Do not publish keys in Git, screenshots or frontend code.

If a previous version is running on port 8765, stop it with **Ctrl+C** before starting this version. You should see `Affinity Atlas / Demo 0.3` in the footer; reload Firefox with Ctrl+Shift+R if necessary.

## Real Qloo calls per request

1. `GET /search` resolves the cultural artist to its canonical Qloo entity ID.
2. Three read-only `GET /v2/insights` branches: films, brands, places (filtered to city).
3. Qloo entities and any explainability links are preserved as source-traceable evidence.

The `feature.explainability` input signal `score` is **not a percentage indicating that an artist and venue are compatible**, and event formats are **our editorial hypotheses**, not Qloo recommendations. Each venue remains unconfirmed.

## What changed in 0.4

- **Optional bounded AI reviewer** chooses which **three of five predefined programme formats** to use, based on the brief and names of verified Qloo results.
- **Strict critic/verification gate:** accepts only three distinct IDs from the allowed list, rejects unsupported formats, does not trust model-generated facts, and **allocates all entities from Qloo in deterministic code**. If review fails or the model is unavailable, the application automatically uses the proven 0.3 editorial policy and clearly identifies it in the UI.
- **Server-side configuration only**; the Qloo API key is **never** sent to the optional LLM provider. User-entered brief, artist, city and a small set of Qloo entity names **are** transmitted if the reviewer is enabled. Do not activate an outside provider unless comfortable with that data transfer.
- New **Agent review** panel shows which reasoning mode actually ran, avoiding false claims of AI operation.
- Diversity, citation/signal caution and the independently verified 0.3 fallback are unchanged.

### Enable an external AI model later (optional)

By default this v0.4 needs **no extra key, no pip installation and no subscription**. It uses the reliable rule-based mode. To activate a compatible chat-completions model, configure these **server-side** environment variables **without storing credentials in the source or shell history**:

- `ATLAS_LLM_URL`: complete HTTPS endpoint (for example, `https://api.openai.com/v1/chat/completions`); or a localhost HTTP endpoint you control.
- `ATLAS_LLM_MODEL`: model name supported by that endpoint.
- `ATLAS_LLM_API_KEY`: provider key where required (server only; not sent to frontend).

The optional model receives **one bounded request per live research execution**, after the existing Qloo lookup. Failure is fail-closed to verified deterministic editorial rules. An incompatible model may fall back safely. The API call is optional and may incur provider costs. This is **not** a full autonomous research agent or a production security model. Live provider integration must be tested explicitly before describing it as functioning.

## Features inherited from 0.2

- **Goal-aware decision layer** (`decision_engine.py`): intent routing for cinema, immersive audio, workshops, community and interdisciplinary programmes. The *same* artist and city can produce a different first-ranked programme when the user changes their objective.
- **Bounded critique and selection**: candidate event formats must refer to returned Qloo entities and at least a location; obvious public/open spaces are kept in the evidence ledger but rejected from the automatic venue shortlist. Candidates are selected based on declared editorial preferences, never fabricated affinity scores.
- **Decision audit**: UI displays inferred goal category, formats considered, options not selected and reasons for choosing each recommendation.
- **Explicit verification needs**: cost/budget and accessibility remain unverified even if the goal mentions them; no suggestion asserts venue availability, rights, brand sponsorship or price.
- **Three one-click example goals**, tests of goal-dependent ranking, missing evidence, Spanish intent and local HTTP behaviour.

**Important limitation:** the LLM can only select/reorder formats when enabled; it is not an unrestricted autonomous planner, and no independent external venue facts are verified. Objective matching is only keyword-based and can misclassify nuanced briefs. The venue screen is heuristic and must not be mistaken for site validation.

## Demo walkthrough

Keep artist `Nils Frahm`, city `Madrid` and click each preset in turn. The top proposal should differ:

- **Film programme** → *Cinema in Resonance*.
- **Sound installation** → *Architecture of Listening*.
- **Educational workshop** → *Listening Lab*.

Each run makes **four real Qloo API calls** if your key is provided. This is a comparison of editorial priorities, not an A/B causal experiment or scientific suitability ranking. Record only sanitized outputs.

## Offline tests

```bash
python3 -m unittest discover -v
```

No third-party Python dependencies. `test_agent_reviewer.py`, `test_engine.py`, `test_decision_engine.py`, and `test_http.py` cover the workflow and safeguards without contacting Qloo.

## Security and publication readiness

The HTTP server is for **local use** (`127.0.0.1` default). **Do not bind it to a public address as-is.** A public deployment needs verified authentication, per-user quotas and abuse controls (to protect the paid/private Qloo key), rate limiting, monitoring and safe secret provisioning. It also needs a free live demo, a public open-source repository, an accessible English submission, and reliability tests through judging.

The repository includes an MIT `LICENSE` as a proposed open-source license; the team should confirm ownership/attribution before publishing.

## Qloo Hackathon

- Official rules: https://qloo.devpost.com/rules
- Deadline: **October 30, 2026, 11:45 PM EDT**.
- Demo must be externally hosted and available to judges at no charge.
- Public source repo with clearly visible open-source license.
- **No mandatory video** under the 2026 rules.
- Scored equally on Technological Implementation, Design, Potential Impact and Quality of the Idea.

## Files

- `app.py`: local HTTP server, validation and key isolation.
- `qloo_client.py`: narrowly scoped Qloo API requests.
- `engine.py`: real Qloo discovery and end-to-end trace.
- `decision_engine.py`: evidence-grounded selection and critique.
- `agent_reviewer.py`: strictly scoped optional LLM call, format-choice validation and fallback.
- `index.html`, `style.css`, `app.js`: interface.
- `test_*.py`: offline tests.
- `PERSONA_B_CHECKPOINT.md`: goal, sources, DONE criteria and next gate.
