"""LOG-C2-031 — inner workflow step 1: obligation_type_classify.

Rule-based classification of the compliance question into an obligation type
(eligibility / threshold / obligation / deadline / general). Also canonicalizes the
scope for downstream inner nodes. On rejected input it no-ops (skip guard).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import ButsurikoKB
from src.utils.audit import emit_trace_event


class ObligationTypeClassifyNode(FunctionNode):
    """Classify the obligation type of the query (rule-based primary)."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # The inner graph receives the scope as `user_input` (GraphNode.extract_input);
        # `validated_input` is the outer-state name — accept either.
        scope = json.loads(state.get("validated_input") or state.get("user_input") or "{}")
        canonical = json.dumps(scope, ensure_ascii=False)
        if state.get("error_code") or not scope.get("query"):
            emit_trace_event("obligation_classify.skip", {"reason": state.get("error_code") or "empty_query"}, state)
            return {"validated_input": canonical, "obligation_type": "general", "status": AgentStatus.SUCCESS.value}

        otype = scope.get("obligation_hint") or ButsurikoKB.classify_obligation(scope["query"])
        emit_trace_event("obligation_classify.complete", {"obligation_type": otype}, state)
        return {"validated_input": canonical, "obligation_type": otype, "status": AgentStatus.SUCCESS.value}
