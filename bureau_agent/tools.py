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

from .prompts import (
    CONSISTENCY_CHECK_PROMPT, SUMMARY_PROMPT,
    PD_QUESTION_REWRITE_PROMPT, SUPPLEMENTARY_PD_QUESTIONS_PROMPT,
)


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


def rewrite_pd_questions(questions: list[dict]) -> list[dict]:
    """
    Calls the LLM to rephrase each PD question conversationally.
    Returns the same list with `display_question` populated on each item.
    Fail-safe: on any failure (API error, malformed JSON, count mismatch),
    falls back to using the original `question` text as `display_question`
    for every item -- the pipeline never breaks on this step.
    """
    if not questions:
        return questions

    # fallback default: display_question = question, in case rewrite fails
    for q in questions:
        q["display_question"] = q["question"]

    try:
        payload = [
            {"index": i, "question": q["question"]}
            for i, q in enumerate(questions)
        ]
        llm = _get_llm(temperature=0.3)
        prompt = PD_QUESTION_REWRITE_PROMPT.format(
            questions_json=json.dumps(payload)
        )
        response = llm.invoke(prompt)
        cleaned = _clean_json_response(response.content)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, list) or len(parsed) != len(questions):
            return questions  # fallback already applied above

        for item in parsed:
            idx = item.get("index")
            rewritten = item.get("rewritten")
            if isinstance(idx, int) and 0 <= idx < len(questions) and rewritten:
                questions[idx]["display_question"] = str(rewritten)[:500]

        return questions

    except Exception:
        # rewrite is cosmetic -- never block the pipeline on it
        return questions


def generate_supplementary_pd_questions(
    canonical_report_json: str,
    consistency_notes: list[dict],
    already_asked: list[dict],
) -> list[dict]:
    """
    LLM gap-filler: suggests PD questions for anything the fixed BRE rules
    didn't cover. Fail-safe -- returns [] on any error, never blocks the
    pipeline. Every returned question is tagged is_llm_generated=True
    downstream so it's never confused with a policy-mandated question.
    """
    try:
        llm = _get_llm(temperature=0.2)
        already_asked_summary = [
            {"question": q["question"], "category": q["category"]}
            for q in already_asked
        ]
        prompt = SUPPLEMENTARY_PD_QUESTIONS_PROMPT.format(
            already_asked_json=json.dumps(already_asked_summary),
            canonical_report_json=canonical_report_json,
            consistency_notes_json=json.dumps(consistency_notes),
        )
        response = llm.invoke(prompt)
        cleaned = _clean_json_response(response.content)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, list):
            return []

        valid = []
        for item in parsed[:4]:  # hard cap, even if the model ignores the instruction
            if isinstance(item, dict) and "question" in item:
                valid.append({
                    "question": str(item.get("question", ""))[:500],
                    "display_question": str(item.get("question", ""))[:500],
                    "category": str(item.get("category", "other")),
                    "reason": str(item.get("reason", ""))[:300],
                    "priority": 3,  # supplementary questions default to medium priority
                    "source_flag": "llm_supplementary",
                    "is_llm_generated": True,
                })
        return valid

    except Exception:
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