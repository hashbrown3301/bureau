"""
Groq-calling tools for the Bureau Agent.

Two LLM touch points only:
1. run_consistency_check -- judgment pass, returns structured JSON
2. generate_summary -- plain English narrative

Both are thin: prompt formatting + API call + response parsing.
No business logic here -- that lives in services/.
"""

import json
import os

from langchain_groq import ChatGroq

from .prompts import CONSISTENCY_CHECK_PROMPT, SUMMARY_PROMPT

GROQ_MODEL = "llama-3.3-70b-versatile"  # adjust to whichever Groq model you're targeting


def _get_llm(temperature: float = 0.1) -> ChatGroq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in environment")
    return ChatGroq(model=GROQ_MODEL, api_key=api_key, temperature=temperature)


def _clean_json_response(raw_text: str) -> str:
    """Strips markdown code fences if the model wraps its JSON in them anyway."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def run_consistency_check(canonical_report_json: str) -> list[dict[str, str]]:
    """
    Calls the LLM to identify patterns/contradictions in the already-computed
    bureau report. Returns a list of observation dicts, or an empty list
    on any failure (fail-safe, never blocks the pipeline).
    """
    try:
        llm = _get_llm(temperature=0.1)
        prompt = CONSISTENCY_CHECK_PROMPT.format(
            canonical_report_json=canonical_report_json
        )
        response = llm.invoke(prompt)
        cleaned = _clean_json_response(response.content)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, list):
            return []

        # defensive: only keep well-formed entries
        valid_notes = []
        for item in parsed:
            if isinstance(item, dict) and "observation" in item:
                valid_notes.append({
                    "observation": str(item.get("observation", ""))[:500],
                    "related_to": str(item.get("related_to", "overall")),
                    "type": str(item.get("type", "context")),
                })
        return valid_notes

    except Exception:
        # Consistency check is supplementary, never block the pipeline on it
        return []


def generate_summary(report_with_flags_json: str) -> str:
    """
    Calls the LLM to write a plain-English summary of the bureau findings.
    Returns a fallback string on failure rather than raising.
    """
    try:
        llm = _get_llm(temperature=0.2)
        prompt = SUMMARY_PROMPT.format(
            report_with_flags_and_observations_json=report_with_flags_json
        )
        response = llm.invoke(prompt)
        return response.content.strip()[:2000]

    except Exception as e:
        return f"Summary generation failed: {str(e)}. Refer to structured data for full details."