# LOG-C2-031 — Integration: end-to-end through pre → inner workflow (linear) → post

import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.compliance_answer_generate_node import ComplianceAnswerGenerateNode
from src.nodes.hybrid_retrieve_node import HybridRetrieveNode
from src.nodes.obligation_type_classify_node import ObligationTypeClassifyNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.nodes.threshold_calc_node import ThresholdCalcNode


def _run(user_input: str) -> dict:
    """Drive outer pre → inner workflow (linear, skip-guarded) → outer post."""
    state: dict = {"user_input": user_input, "input_context": {}, "node_history": [], "error_log": []}
    state.update(PreProcessNode().execute(state) or {})
    for node in (ObligationTypeClassifyNode(), HybridRetrieveNode(), ThresholdCalcNode(),
                 ComplianceAnswerGenerateNode()):
        state.update(node.execute(state) or {})
    state.update(PostProcessNode().execute(state) or {})
    return state


class TestEndToEnd:
    def test_eligibility_with_tonnage_computes_threshold(self):
        state = _run("当社は特定荷主に該当しますか。年間輸送量は 12,000,000 トンキロです。")
        assert state["status"] == AgentStatus.SUCCESS
        assert state["audit_logged"] is True
        env = json.loads(state["formatted_output"])
        assert env["status_kind"] == "answer"
        assert env["citations"]
        assert env["threshold"]["qualifies"] is True

    def test_obligation_question_cited(self):
        state = _run("特定荷主に指定されたら、どんな義務がありますか？")
        env = json.loads(state["formatted_output"])
        assert env["citation_complete"] is True
        assert any(c["marker"].startswith("BUTSURIKO") or c["marker"].startswith("MLIT")
                   for c in env["citations"])

    def test_out_of_scope_safe(self):
        state = _run("おすすめの引っ越し業者を教えて")
        env = json.loads(state["formatted_output"])
        assert env["status_kind"] == "insufficient_data"
        assert env["citations"] == []

    def test_empty_degrades_but_audits(self):
        state = _run("   ")
        assert state["status"] == AgentStatus.SUCCESS
        assert state["audit_logged"] is True
        assert json.loads(state["formatted_output"])["status_kind"] == "insufficient_data"
