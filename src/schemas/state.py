"""LOG-C2-031 — Agent state (特定荷主 物効法 Compliance Q&A, Cat 2).

ADR-005: State is a flat TypedDict — never a validation/BaseModel instance.
LangGraph checkpoints use msgpack serialization; model objects cause silent
corruption. Complex fields are stored as JSON strings (``NotRequired[str]`` +
``# JSON:``); nodes ``json.dumps`` on write / ``json.loads`` on read.

S-5 / State Safety: no credentials, secrets, or PII in State. The agent answers
物効法 compliance questions with citations; it never emits legal determinations,
only grounded guidance with a mandatory disclaimer.

All agent-specific fields are NotRequired (populated progressively; absent at
empty-start invoke — only user_input is caller-provided).
"""

from __future__ import annotations


from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for the designated-shipper compliance Q&A workflow."""

    # ── pre_process (S-1 validated request) ─────────────────────────────────
    validated_input: str  # JSON: {query, obligation_hint, transport_tonnage, fiscal_year, ...}
    input_format: str  # "json" | "text" | "empty"
    enriched_context: str  # JSON: {source, channel} (read-only caller context)

    # ── inner workflow (classify → retrieve → threshold → answer) ────────────
    obligation_type: str  # eligibility | threshold | obligation | deadline | general
    retrieved_passages: str  # JSON: [{doc_ref, source, article, text, score}]
    retrieval_hit_count: int  # KB passages retrieved (0 → out-of-scope safe answer)
    qualifies: bool  # designated-shipper threshold result (when computable)
    calc_trace: str  # JSON: deterministic threshold computation trace
    result: str  # JSON: assembled report {answer, citations, threshold, ...}

    # ── post_process (S-3 gate + S-4 audit) ──────────────────────────────────
    formatted_output: str  # JSON: final response envelope (answer + citations + disclaimer)
    disclaimer: str  # legal disclaimer text
    audit_logged: bool  # True once the terminal audit event is emitted

    # ── degraded-path signalling (SUCCESS + error_code, never status=ERROR) ──
    error_code: str  # INPUT_REJECTED | INPUT_TOO_LONG | NO_PASSAGES_FOUND
    error_message: str  # operator-facing detail
