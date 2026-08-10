"""
Bureau Agent -- LangGraph pipeline.

Flow:
  validate_input -> normalize_and_compute -> generate_pd_questions
  -> rewrite_pd_questions -> run_consistency_check
  -> generate_supplementary_pd_questions -> generate_summary -> finalize_output

If validation fails, the graph short-circuits straight to finalize_output
with an error populated.

Factory pattern: create_bureau_agent() returns a compiled graph.
No I/O, no prints -- this file only defines the graph.
"""

import json

from langgraph.graph import StateGraph, END

from .state import BureauAgentState
from .services.validator import validate_bureau_input
from .services.normalizer import normalize_bureau_report
from .services.metrics import compute_metrics
from .services.risk import compute_risk_indicators
from .services.pd_questions import generate_pd_questions
from .services.schema import CanonicalBureauReport
from .tools import (
    run_consistency_check,
    generate_summary,
    rewrite_pd_questions,
    generate_supplementary_pd_questions,
)


def _node_validate_input(state: BureauAgentState) -> BureauAgentState:
    is_valid, errors = validate_bureau_input(state["raw_input"])
    return {
        **state,
        "is_valid": is_valid,
        "validation_errors": errors,
    }


def _node_normalize_and_compute(state: BureauAgentState) -> BureauAgentState:
    report = normalize_bureau_report(state["raw_input"])
    report = compute_metrics(report)
    report = compute_risk_indicators(report)
    return {
        **state,
        "canonical_report": report.model_dump(mode="json"),
    }


def _node_generate_pd_questions(state: BureauAgentState) -> BureauAgentState:
    report = CanonicalBureauReport.model_validate(state["canonical_report"])
    questions = generate_pd_questions(report)
    return {
        **state,
        "pd_questionnaire": [q.model_dump() for q in questions],
    }


def _node_rewrite_pd_questions(state: BureauAgentState) -> BureauAgentState:
    questions = state.get("pd_questionnaire", [])
    rewritten = rewrite_pd_questions(questions)
    return {
        **state,
        "pd_questionnaire": rewritten,
    }


def _node_run_consistency_check(state: BureauAgentState) -> BureauAgentState:
    report_json = json.dumps(state["canonical_report"])
    notes = run_consistency_check(report_json)
    return {
        **state,
        "consistency_notes": notes,
    }


def _node_generate_supplementary_pd_questions(state: BureauAgentState) -> BureauAgentState:
    report_json = json.dumps(state["canonical_report"])
    existing = state.get("pd_questionnaire", [])
    supplementary = generate_supplementary_pd_questions(
        report_json,
        state.get("consistency_notes", []),
        existing,
    )
    combined = sorted(existing + supplementary, key=lambda q: q["priority"])
    return {
        **state,
        "pd_questionnaire": combined,
    }


def _node_generate_summary(state: BureauAgentState) -> BureauAgentState:
    payload = {
        **state["canonical_report"],
        "consistency_notes": state.get("consistency_notes", []),
    }
    summary = generate_summary(json.dumps(payload))
    return {
        **state,
        "summary": summary,
    }


def _node_finalize_output(state: BureauAgentState) -> BureauAgentState:
    if not state.get("is_valid", False):
        return {
            **state,
            "error": "Validation failed",
            "final_output": {
                "success": False,
                "errors": state.get("validation_errors", []),
            },
        }

    report = state["canonical_report"]
    final_output = {
        "success": True,
        "bureau_name": report["bureau_name"],
        "applicant_name": report["applicant_name"],
        "credit_score": report["credit_score"],
        "total_accounts": report["total_accounts"],
        "active_accounts": report["active_accounts"],
        "total_outstanding": report["total_outstanding"],
        "total_overdue": report["total_overdue"],
        "total_emi_burden": report["total_emi_burden"],
        "credit_utilization_pct": report["credit_utilization_pct"],
        "dpd_severity": report["dpd_severity"],
        "credit_vintage_months": report["credit_vintage_months"],
        "enquiries_last_6_months": report["enquiries_last_6_months"],
        "risk_flags": report["risk_flags"],
        "consistency_notes": state.get("consistency_notes", []),
        "pd_questionnaire": state.get("pd_questionnaire", []),
        "summary": state.get("summary", ""),
    }
    return {**state, "final_output": final_output}


def _route_after_validation(state: BureauAgentState) -> str:
    return "normalize_and_compute" if state.get("is_valid") else "finalize_output"


def create_bureau_agent():
    """
    Factory: builds and compiles the Bureau Agent graph.
    Returns a compiled LangGraph app, ready to .invoke({"raw_input": ...}).
    """
    workflow = StateGraph(BureauAgentState)

    workflow.add_node("validate_input", _node_validate_input)
    workflow.add_node("normalize_and_compute", _node_normalize_and_compute)
    workflow.add_node("generate_pd_questions", _node_generate_pd_questions)
    workflow.add_node("rewrite_pd_questions", _node_rewrite_pd_questions)
    workflow.add_node("run_consistency_check", _node_run_consistency_check)
    workflow.add_node("generate_supplementary_pd_questions", _node_generate_supplementary_pd_questions)
    workflow.add_node("generate_summary", _node_generate_summary)
    workflow.add_node("finalize_output", _node_finalize_output)

    workflow.set_entry_point("validate_input")
    workflow.add_conditional_edges(
        "validate_input",
        _route_after_validation,
        {"normalize_and_compute": "normalize_and_compute", "finalize_output": "finalize_output"},
    )

    workflow.add_edge("normalize_and_compute", "generate_pd_questions")
    workflow.add_edge("generate_pd_questions", "rewrite_pd_questions")
    workflow.add_edge("rewrite_pd_questions", "run_consistency_check")
    workflow.add_edge("run_consistency_check", "generate_supplementary_pd_questions")
    workflow.add_edge("generate_supplementary_pd_questions", "generate_summary")
    workflow.add_edge("generate_summary", "finalize_output")
    workflow.add_edge("finalize_output", END)

    return workflow.compile()