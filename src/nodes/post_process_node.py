"""LOG-C2-031 — post_process node (S-3 output gate + S-4 audit).

S-3: verify citation completeness (a grounded answer must cite its 物効法 sources) and append
the mandatory legal disclaimer (this is guidance, not a legal determination). S-4: emit an
audit event (counts / obligation type / verdict only — never the caller's raw query). Runs on
both the full answer and the safe-answer branch.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_DISCLAIMER = (
    "本回答は物流効率化促進法(物効法)および国交省ガイドラインに基づく参考情報であり、"
    "特定荷主該当性・義務内容の最終的な法的判断ではありません。確定判断は最新の政省令・"
    "所管当局への確認および法務・専門家のレビューを要します。"
)


class PostProcessNode(FunctionNode):
    """Verify citations, append disclaimer, emit audit."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation check: disclaimer present in the output envelope.

        SDK 1.0.0 contract: this hook receives the **result dict returned by `execute()`**
        (not the full state) and returns the (possibly filtered) result. It MAY raise to
        signal the output cannot be safely emitted — `__call__` catches it → ERROR status.
        """
        out = result.get("formatted_output", "")
        if out and "物効法" not in out and "免責" not in out and _DISCLAIMER[:12] not in out:
            raise ValueError("S-3: legal disclaimer missing from output")
        return dict(result)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        report: dict[str, Any] = json.loads(state.get("result", "{}") or "{}")

        citations = report.get("citations", [])
        grounded = report.get("status_kind") == "answer"
        citation_complete = (not grounded) or bool(citations)

        formatted = {
            "answer": report.get("answer", ""),
            "status_kind": report.get("status_kind"),
            "obligation_type": report.get("obligation_type"),
            "citations": citations,
            "threshold": report.get("threshold"),
            "citation_complete": citation_complete,
            "disclaimer": _DISCLAIMER,
        }
        emit_trace_event(
            "post_process.complete",
            {
                "status_kind": report.get("status_kind"),
                "citation_count": len(citations),
                "citation_complete": citation_complete,
                "obligation_type": report.get("obligation_type"),
                "error_code": state.get("error_code"),
            },
            state,
        )
        return {
            "formatted_output": json.dumps(formatted, ensure_ascii=False),
            "disclaimer": _DISCLAIMER,
            "audit_logged": True,
            "status": AgentStatus.SUCCESS.value,
        }
