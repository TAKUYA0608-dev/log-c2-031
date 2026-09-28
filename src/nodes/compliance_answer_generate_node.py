"""LOG-C2-031 — inner workflow step 4: compliance_answer_generate.

Assembles the cited compliance answer from retrieved passages + the deterministic threshold
result. Every claim is grounded in a passage with an inline ``[<doc_ref>]`` marker. On the
0-hit / rejected branch it emits the safe "out-of-scope / insufficient data" answer.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.utils.audit import emit_trace_event

_OUT_OF_SCOPE = (
    "ご質問は特定荷主・物効法コンプライアンスの参照 KB(該当判定 / 閾値 / 義務 / 期限)の範囲外か、"
    "根拠となる条文が見つかりませんでした。物効法(2024 改正)・特定荷主指定・中長期計画・定期報告 "
    "などの観点で質問を具体化いただくか、所管部門にご確認ください。"
)


class ComplianceAnswerGenerateNode(FunctionNode):
    """Synthesize the cited compliance answer (or safe answer on 0-hit)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        passages = json.loads(state.get("retrieved_passages") or "[]")
        if state.get("error_code") or not passages:
            emit_trace_event("answer_generate.safe", {"reason": state.get("error_code") or "no_passages"}, state)
            report: dict[str, Any] = {
                "status_kind": "insufficient_data",
                "message": _OUT_OF_SCOPE,
                "answer": _OUT_OF_SCOPE,
                "citations": [],
                "threshold": None,
            }
            return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}

        lines: list[str] = []
        citations: list[dict[str, str]] = []
        for p in passages:
            lines.append(f"- {p['text']} [{p['doc_ref']}]（{p['source']} {p['article']}）")
            citations.append({"marker": p["doc_ref"], "source": p["source"], "article": p["article"]})

        threshold: dict[str, Any] | None = None
        calc_raw = state.get("calc_trace")
        if calc_raw:
            calc = json.loads(calc_raw)
            threshold = {"computable": calc["computable"], "qualifies": calc["qualifies"], "trace": calc["trace"]}
            verdict = ("**該当判定**: " + calc["trace"]) if calc["computable"] else ("**該当判定**: " + calc["trace"])
            lines.insert(0, verdict)

        report = {
            "status_kind": "answer",
            "answer": "\n".join(lines),
            "obligation_type": state.get("obligation_type"),
            "citations": citations,
            "threshold": threshold,
        }
        emit_trace_event(
            "answer_generate.complete",
            {"citation_count": len(citations), "has_threshold": threshold is not None},
            state,
        )
        return {"result": json.dumps(report, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
