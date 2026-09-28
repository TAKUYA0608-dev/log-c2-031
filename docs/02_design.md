# Template Design Specification — LOG-C2-031

特定荷主 物効法 Compliance Q&A Agent (Cat 2).

## Position in AgentCore Architecture

- **Agent Class**: `DesignatedShipperComplianceQaAgent` (module-level alias of `Graph`)
- **L1 Base**: **AgentBaseGraph** (Cat 2 — outer 5-node backbone; direct L1 inheritance, no L2)
- **Category**: Cat 2 — a multi-step domain workflow (classify → retrieve → threshold → answer) for a
  specific business outcome (特定荷主 compliance guidance); LOG industry
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (`execute(self, state: dict) -> dict` override only)
  - Graph: outer `AgentBaseGraph` + **`GraphNode` in the `main` slot** wrapping an inner `BaseGraph`

## Architecture Overview

Cat 2 pattern — the `main` slot is a **`GraphNode`** (`LogisticsComplianceWorkflowGraphNode`) that
wraps the inner `LogisticsComplianceWorkflow` (`BaseGraph`). The inner graph is a **static linear
backbone with per-node skip guards** (the portable Cat 2 form; conditional edges do not propagate
across the subgraph boundary).

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | user_input | (framework) | InitializeNode (default) |
| pre_process | `PreProcessNode` — S-1/S-2 (`_extra_security_gate_input`), scope extraction | user_input | validated_input, input_format, enriched_context | FunctionNode.execute |
| main | `LogisticsComplianceWorkflowGraphNode` (GraphNode) → inner workflow | validated_input | result, retrieval_hit_count | GraphNode |
| post_process | `PostProcessNode` — S-3 citation gate (`_extra_security_gate_output`) + disclaimer + S-4 audit | result | formatted_output, disclaimer, audit_logged | FunctionNode.execute |
| finalize | response_metadata, total_time_ms | | (framework) | FinalizeNode (default) |

**Inner workflow (`LogisticsComplianceWorkflow` : BaseGraph):**

```
START → obligation_type_classify → hybrid_retrieve → threshold_calc → compliance_answer_generate → END
```

| Inner node | Responsibility |
|---|---|
| ObligationTypeClassify | rule-based obligation type (eligibility/threshold/obligation/deadline/general) |
| HybridRetrieve | deterministic KB retrieval (物効法/特定荷主/MLIT); 0-hit → safe-answer branch |
| ThresholdCalc | **deterministic** 特定荷主 threshold judgement (トンキロ vs 政令基準); skips on 0-hit |
| ComplianceAnswerGenerate | cited answer (every claim ends `[<doc_ref>]`) + threshold verdict; safe answer on 0-hit |

### Data Flow

```
START → initialize → pre_process → main(GraphNode → inner linear workflow) → post_process → finalize → END
                                     ↓ (retry, max 3)
                                   pre_process
```

Rejected input / 0-hit sets `error_code` + `retrieval_hit_count=0`; the threshold node no-ops and
the answer node emits the safe "insufficient data" answer — no fabrication.

### State Definition

| Field | Type | Purpose |
|-------|------|---------|
| validated_input | str (JSON) | `{query, obligation_hint, transport_ton_km, fiscal_year}` |
| obligation_type | str | eligibility/threshold/obligation/deadline/general |
| retrieved_passages | str (JSON) | `[{doc_ref, source, article, text, score}]` |
| retrieval_hit_count | int | 0 → out-of-scope safe answer |
| qualifies | bool | designated-shipper threshold result (when computable) |
| calc_trace | str (JSON) | deterministic threshold computation trace |
| result / formatted_output | str (JSON) | inner report / final envelope |
| disclaimer / audit_logged | str/bool | post_process outputs |
| error_code / error_message | str | degraded path (SUCCESS + error_code, never status=ERROR) |

**State Constraints:** flat TypedDict; JSON strings for complex fields; no credentials/PII;
`enriched_context` is a JSON string (ADR-005); InvocationContext via `from_state()` only.

## Framework Utilization

- [x] **GraphNode-in-main** (Cat 2 composition, criterion #9) — `error_strategy="propagate"`, `propagate_hitl=False`
- [x] S-1 `required_trust_level=VERIFIED_EXTERNAL` on all nodes
- [x] S-2 `_extra_security_gate_input()` (pre) — size cap + injection markers; **returns state w/ status=ERROR, never raises** (SDK 1.0.0)
- [x] S-3 `_extra_security_gate_output()` (post) — disclaimer preservation; **may raise** (SDK 1.0.0)
- [x] S-4 `emit_trace_event()` in every `execute()`; terminal audit always fires (incl. degraded)

## Import Isolation Confirmation
- [x] No `agenticstar` SDK (Level 0) import — PB-4
- [x] Import targets: `framework/`, `langgraph`, and `src.` only

## Design Decision Record

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| L1 base type | AgentBaseGraph | Fixed pipeline, no autonomous loop |
| Composition | **GraphNode-in-main + inner BaseGraph** | Cat 2 multi-step domain workflow |
| Inner topology | **Linear + per-node skip guards** | Conditional edges don't propagate across the subgraph boundary (shipped Cat 2 pattern). **`LogisticsComplianceWorkflow.route()` is implemented only to satisfy the `BaseGraph` ABC — it is NOT wired to a conditional edge; the static linear backbone (`add_edges`) is the real topology, and the 0-hit / rejected skip is handled by per-node `if error_code / retrieval_hit_count == 0: return {}` guards.** |
| Threshold judgement | **Deterministic (no LLM)** | Auditable eligibility computation |
| Rejection signalling | SUCCESS + error_code | Guarantees post_process S-3/S-4 always run (SDK 1.0.0) |

## Open Items (Stage ③ implementation MR)
- Node implementations + inner workflow graph (shipped in the implementation MR).
- Seeded `ButsurikoKB` (6 records) + `ThresholdCalculator`.
- Unit + integration + PB tests; coverage ≥ 80%.
