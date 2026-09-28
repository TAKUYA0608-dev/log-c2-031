"""LOG-C2-031 — inner workflow step 2: hybrid_retrieve.

Deterministic (keyword/tag + obligation-type) retrieval over the 物効法 KB via the DI
`ButsurikoKB`. Sets `retrieval_hit_count`; **0 hits (rejected input or no corpus match)
routes to the safe-answer branch** — the agent never fabricates compliance guidance.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import ButsurikoKB
from src.utils.audit import emit_trace_event


class HybridRetrieveNode(FunctionNode):
    """Retrieve grounded 物効法 passages for the query + obligation type."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code"):
            emit_trace_event("hybrid_retrieve.skip", {"reason": state["error_code"]}, state)
            return {"retrieved_passages": "[]", "retrieval_hit_count": 0, "status": AgentStatus.SUCCESS.value}

        scope = json.loads(state.get("validated_input") or "{}")
        query = scope.get("query", "")
        otype = state.get("obligation_type", "general")
        passages = ButsurikoKB.retrieve(query, otype)
        emit_trace_event("hybrid_retrieve.complete", {"hit_count": len(passages), "obligation_type": otype}, state)
        out = {
            "retrieved_passages": json.dumps(passages, ensure_ascii=False),
            "retrieval_hit_count": len(passages),
            "status": AgentStatus.SUCCESS.value,
        }
        if not passages:
            out["error_code"] = "NO_PASSAGES_FOUND"
        return out
