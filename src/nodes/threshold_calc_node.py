"""LOG-C2-031 — inner workflow step 3: threshold_calc.

Deterministic 特定荷主 eligibility computation (no LLM): compares the caller-supplied
annual transport volume (トンキロ) against the designated-shipper threshold and records an
auditable calc trace. Skips (no-op) on rejected input or 0-hit retrieval.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.services.service import ThresholdCalculator
from src.utils.audit import emit_trace_event


class ThresholdCalcNode(FunctionNode):
    """Compute the designated-shipper threshold result deterministically."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error_code") or state.get("retrieval_hit_count", 0) == 0:
            return {}  # skip guard — safe-answer branch handles the rest

        scope = json.loads(state.get("validated_input") or "{}")
        calc = ThresholdCalculator.evaluate(scope.get("transport_ton_km"))
        emit_trace_event(
            "threshold_calc.complete", {"computable": calc["computable"], "qualifies": calc["qualifies"]}, state
        )
        out: dict[str, Any] = {"calc_trace": json.dumps(calc, ensure_ascii=False), "status": AgentStatus.SUCCESS.value}
        if calc["computable"]:
            out["qualifies"] = bool(calc["qualifies"])
        return out
