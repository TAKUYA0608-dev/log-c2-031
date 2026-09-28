"""LOG-C2-031 — inner domain workflow graph (Cat 2).

Instantiated by LogisticsComplianceWorkflowGraphNode.get_subgraph() in graph.py.
Linear topology with per-node skip guards (the established Cat 2 pattern — a static
backbone plus `if error_code / retrieval_hit_count == 0: return {}` guards, rather than
conditional edges, which are the portable form across the framework subgraph boundary):

    START → obligation_type_classify → hybrid_retrieve → threshold_calc
              → compliance_answer_generate → END

On rejected input / 0 hits, hybrid_retrieve sets retrieval_hit_count=0 (+error_code);
threshold_calc no-ops and compliance_answer_generate emits the safe "insufficient data"
answer — no fabrication.
"""

from __future__ import annotations
from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState

from src.nodes.compliance_answer_generate_node import ComplianceAnswerGenerateNode
from src.nodes.hybrid_retrieve_node import HybridRetrieveNode
from src.nodes.obligation_type_classify_node import ObligationTypeClassifyNode
from src.nodes.threshold_calc_node import ThresholdCalcNode
from src.schemas.state import State


class LogisticsComplianceWorkflow(BaseGraph):
    """Inner graph: classify → retrieve → threshold → answer."""

    @property
    def name(self) -> str:
        return "LogisticsComplianceWorkflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        # No super() — BaseGraph.register_nodes() is abstract.
        self._nodes["obligation_type_classify"] = ObligationTypeClassifyNode()
        self._nodes["hybrid_retrieve"] = HybridRetrieveNode()
        self._nodes["threshold_calc"] = ThresholdCalcNode()
        self._nodes["compliance_answer_generate"] = ComplianceAnswerGenerateNode()

    def add_edges(self) -> None:
        # Static linear backbone; the 0-hit / rejected skip is handled by per-node guards.
        self._sg.add_edge(START, "obligation_type_classify")
        self._sg.add_edge("obligation_type_classify", "hybrid_retrieve")
        self._sg.add_edge("hybrid_retrieve", "threshold_calc")
        self._sg.add_edge("threshold_calc", "compliance_answer_generate")
        self._sg.add_edge("compliance_answer_generate", END)

    def route(self, state: AgentState) -> str:
        """Required by the BaseGraph ABC. Linear topology → not wired to a conditional edge."""
        if state.get("error_code") or state.get("retrieval_hit_count", 0) == 0:
            return "compliance_answer_generate"
        return "hybrid_retrieve"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "output": state.get("result"),
            "status": state.get("status"),
            "retrieval_hit_count": state.get("retrieval_hit_count", 0),
            "error_code": state.get("error_code"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
