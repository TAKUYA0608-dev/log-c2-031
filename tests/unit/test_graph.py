# LOG-C2-031 — Unit Tests: Cat 2 graph wiring (outer GraphNode + inner workflow)

import pytest

from src.graph.domain_workflow_graph import LogisticsComplianceWorkflow
from src.graph.graph import DesignatedShipperComplianceQaAgent, Graph, LogisticsComplianceWorkflowGraphNode
from src.schemas.state import State


class TestOuterGraph:
    def test_registry_alias(self):
        assert DesignatedShipperComplianceQaAgent is Graph

    def test_name_and_state_schema(self):
        g = Graph()
        assert g.name == "DesignatedShipperComplianceQaAgent"
        assert g.state_schema is State

    def test_main_slot_is_graphnode(self):
        g = Graph()
        g.register_nodes()
        assert isinstance(g._nodes["main"], LogisticsComplianceWorkflowGraphNode)
        for slot in ("pre_process", "main", "post_process"):
            assert slot in g._nodes

    def test_graphnode_error_strategy_propagate(self):
        assert LogisticsComplianceWorkflowGraphNode.error_strategy == "propagate"

    def test_graphnode_merge_output_maps_fields(self):
        node = LogisticsComplianceWorkflowGraphNode()
        merged = node.merge_output({}, {"output": '{"answer":"x"}', "retrieval_hit_count": 2,
                                        "status": "success", "error_code": None})
        assert merged["result"] == '{"answer":"x"}'
        assert merged["retrieval_hit_count"] == 2

    def test_get_subgraph_is_cached(self):
        """Review finding F-01: the inner workflow is built once, not per call."""
        node = LogisticsComplianceWorkflowGraphNode()
        assert node.get_subgraph() is node.get_subgraph()


class TestInnerWorkflow:
    def test_inner_graph_registers_four_nodes(self):
        wf = LogisticsComplianceWorkflow(config={})
        wf.register_nodes()
        for slot in ("obligation_type_classify", "hybrid_retrieve", "threshold_calc",
                     "compliance_answer_generate"):
            assert slot in wf._nodes

    def test_inner_state_schema(self):
        assert LogisticsComplianceWorkflow(config={}).state_schema is State

    def test_route_zero_hit_goes_to_answer(self):
        wf = LogisticsComplianceWorkflow(config={})
        assert wf.route({"retrieval_hit_count": 0}) == "compliance_answer_generate"


class TestServerModule:
    def test_server_imports(self):
        try:
            import src.api.server as server
        except ModuleNotFoundError as exc:
            pytest.skip(f"platform module unavailable in the local stub env: {exc}")
        assert server.app is not None and server.agent is not None
