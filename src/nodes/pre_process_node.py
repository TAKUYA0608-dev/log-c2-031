"""LOG-C2-031 — pre_process node (S-1 input validation + scope extraction).

Accepts a structured JSON request or a natural-language query, normalizes it (NFKC),
enforces S-1/S-2 (size cap + prompt-injection markers via `_extra_security_gate_input`),
and extracts `{query, obligation_hint, transport_ton_km, fiscal_year}` into validated_input.

Hard rejects (empty / injection / oversize) return `status=SUCCESS + error_code` (degraded,
not ERROR) so the safe-answer path still flows through main → post_process (S-3/S-4).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import ButsurikoKB
from src.utils.audit import emit_trace_event

_MAX_INPUT = 200_000
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "###system",
    "<|im_start|>",
)
_TON_KM_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:トンキロ|ton[\s-]?km|tkm)", re.I)
_FY_RE = re.compile(r"(20\d{2})\s*年度")


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


class PreProcessNode(FunctionNode):
    """Validate the request and extract the compliance-query scope.

    Validation is split by intent: **injection markers + size cap are handled in
    the S-2 `_extra_security_gate_input` hook** (which returns status=ERROR and short-circuits
    before `execute()` — these inputs never reach `execute()`); **empty input is handled in
    `execute()` as a degraded SUCCESS + error_code** (an empty query is a valid-but-unanswerable
    request, not an S-2 security rejection, so it must flow through main → post_process for audit).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2 domain checks: size cap + prompt-injection markers.

        SDK 1.0.0 contract: this hook MUST NOT raise — it surfaces a rejection by
        returning the state with `status=ERROR` (+error_log), which makes `__call__`
        short-circuit before `execute()`. Always return the (possibly modified) state.
        """
        raw = state.get("user_input", "") or ""
        reject = None
        if len(raw) > _MAX_INPUT:
            reject = f"input exceeds size cap ({_MAX_INPUT} chars)"
        elif any(marker in _nfkc(raw).lower() for marker in _INJECTION_MARKERS):
            reject = "prompt-injection marker detected"
        if reject:
            out = dict(state)
            out["status"] = AgentStatus.ERROR.value
            out["error_log"] = [f"PreProcessNode S-2: {reject}"]
            return out
        return dict(state)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "") or ""
        input_context = state.get("input_context", {})  # read-only [C1]
        enriched = json.dumps(  # ADR-005: complex State fields are JSON strings, never bare dict
            {"source": "DesignatedShipperComplianceQaAgent", "channel": input_context.get("channel", "unknown")},
            ensure_ascii=False,
        )

        if not raw.strip():
            emit_trace_event("pre_process.rejected", {"reason": "empty_input"}, state)
            return {
                "validated_input": "{}",
                "input_format": "empty",
                "enriched_context": enriched,
                "error_code": "INPUT_REJECTED",
                "status": AgentStatus.SUCCESS.value,
            }

        text = _nfkc(raw).strip()
        scope, fmt = self._parse_scope(text)
        emit_trace_event(
            "pre_process.validated",
            {
                "input_format": fmt,
                "obligation_hint": scope.get("obligation_hint"),
                "has_tonnage": scope.get("transport_ton_km") is not None,
            },
            state,
        )
        return {
            "validated_input": json.dumps(scope, ensure_ascii=False),
            "input_format": fmt,
            "enriched_context": enriched,
            "status": AgentStatus.SUCCESS.value,
        }

    def _parse_scope(self, text: str) -> tuple[dict[str, Any], str]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return self._normalize_scope(obj), "json"
        except (ValueError, TypeError):
            pass
        return self._extract_from_text(text), "text"

    def _normalize_scope(self, obj: dict[str, Any]) -> dict[str, Any]:
        query = str(obj.get("query") or obj.get("question") or "")
        tonnage = obj.get("transport_ton_km", obj.get("tonnage"))
        try:
            tonnage = float(tonnage) if tonnage is not None else None
        except (ValueError, TypeError):
            tonnage = None
        return {
            "query": query,
            "obligation_hint": ButsurikoKB.classify_obligation(query),
            "transport_ton_km": tonnage,
            "fiscal_year": obj.get("fiscal_year"),
        }

    def _extract_from_text(self, text: str) -> dict[str, Any]:
        tonnage = None
        m = _TON_KM_RE.search(text)
        if m:
            try:
                tonnage = float(m.group(1).replace(",", ""))
            except ValueError:
                tonnage = None
        fy = _FY_RE.search(text)
        return {
            "query": text,
            "obligation_hint": ButsurikoKB.classify_obligation(text),
            "transport_ton_km": tonnage,
            "fiscal_year": fy.group(1) if fy else None,
        }
