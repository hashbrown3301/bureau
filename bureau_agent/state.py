"""
State definition for the Bureau Agent's LangGraph pipeline.

Each node reads from and writes to this state. Fields are populated
progressively as the report moves through validate -> normalize ->
metrics -> risk -> consistency_check -> summary -> finalize.
"""

from typing import Any, TypedDict


class BureauAgentState(TypedDict, total=False):
    # --- Input ---
    raw_input: dict[str, Any]            # raw bureau JSON as received

    # --- Validation ---
    is_valid: bool
    validation_errors: list[str]

    # --- Pipeline artifacts ---
    canonical_report: dict[str, Any]     # CanonicalBureauReport.model_dump() after normalize+metrics+risk

    # --- AI outputs ---
    consistency_notes: list[dict[str, str]]  # list of {observation, related_to, type}
    summary: str

    # --- PD Question Engine (BRE, deterministic) ---
    pd_questionnaire: list[dict[str, Any]]   # list of PDQuestion.model_dump()

    # --- Final output ---
    final_output: dict[str, Any]
    error: str | None