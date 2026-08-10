"""
BRE-style Preset Question Engine for PD (Personal Discussion) Underwriting.

Pure rule-based mapping from risk_flags -> underwriter interview questions.
No LLM involved -- this must stay explainable and auditable, since PD
questions can end up referenced in compliance/audit trails.

Mirrors the structure of risk.py: one flag -> one deterministic outcome.
Add new rules by adding a new `if` block; keep the priority scale in
one place (lower number = more urgent / ask first).
"""

from .schema import AccountStatus, CanonicalBureauReport, PDQuestion

# --- Priority scale (lower = higher urgency, asked first) ---
PRIORITY_CRITICAL = 1   # write-off, NPA -- most serious credit history signals
PRIORITY_HIGH = 2       # active repayment problems (recent DPD, overdue)
PRIORITY_MEDIUM = 3     # settlement, enquiry surge -- past/recent credit-seeking behavior
PRIORITY_LOW = 4        # utilization -- self-contained, less severe
PRIORITY_INFO = 5       # thin file -- informational, not a red flag per se


def _lenders(report: CanonicalBureauReport, status: AccountStatus) -> str:
    matching = sorted({a.lender for a in report.accounts if a.status == status})
    return ", ".join(matching) if matching else "the relevant lender"


def generate_pd_questions(report: CanonicalBureauReport) -> list[PDQuestion]:
    """
    Maps report.risk_flags -> a prioritized list of PD interview questions.
    Assumes compute_risk_indicators() has already populated report.risk_flags.
    Returns questions sorted by priority (most urgent first).
    """
    flags = report.risk_flags
    questions: list[PDQuestion] = []

    def flagged(name: str) -> bool:
        f = flags.get(name)
        return f is not None and f.flagged

    if flagged("has_writeoff"):
        lenders = _lenders(report, AccountStatus.WRITTEN_OFF)
        questions.append(PDQuestion(
            question=f"Can you walk me through the circumstances of the written-off account with {lenders}?",
            category="credit_history",
            reason=flags["has_writeoff"].reason,
            priority=PRIORITY_CRITICAL,
            source_flag="has_writeoff",
        ))

    if flagged("has_npa"):
        lenders = _lenders(report, AccountStatus.NPA)
        questions.append(PDQuestion(
            question=f"Your account with {lenders} is classified as a non-performing asset. What led to this, and what's the current status?",
            category="credit_history",
            reason=flags["has_npa"].reason,
            priority=PRIORITY_CRITICAL,
            source_flag="has_npa",
        ))

    if flagged("recent_dpd"):
        questions.append(PDQuestion(
            question="You've had delayed payments in the last few months. What caused this, and is repayment on track now?",
            category="repayment_behavior",
            reason=flags["recent_dpd"].reason,
            priority=PRIORITY_HIGH,
            source_flag="recent_dpd",
        ))

    if flagged("high_overdue"):
        questions.append(PDQuestion(
            question=f"You currently show an overdue amount of {report.total_overdue}. When do you plan to clear this?",
            category="repayment_behavior",
            reason=flags["high_overdue"].reason,
            priority=PRIORITY_HIGH,
            source_flag="high_overdue",
        ))

    if flagged("has_settlement"):
        lenders = _lenders(report, AccountStatus.SETTLED)
        questions.append(PDQuestion(
            question=f"Your account with {lenders} was settled for less than the full amount owed. Can you explain what happened?",
            category="credit_history",
            reason=flags["has_settlement"].reason,
            priority=PRIORITY_MEDIUM,
            source_flag="has_settlement",
        ))

    if flagged("enquiry_surge"):
        questions.append(PDQuestion(
            question="You've applied for credit with several different lenders recently. What was the purpose, and were any applications declined?",
            category="credit_seeking",
            reason=flags["enquiry_surge"].reason,
            priority=PRIORITY_MEDIUM,
            source_flag="enquiry_surge",
        ))

    if flagged("high_utilization"):
        questions.append(PDQuestion(
            question=f"Your credit utilization is at {report.credit_utilization_pct}%. Is this a temporary spike or an ongoing pattern?",
            category="utilization",
            reason=flags["high_utilization"].reason,
            priority=PRIORITY_LOW,
            source_flag="high_utilization",
        ))

    if flagged("thin_file"):
        questions.append(PDQuestion(
            question="You have limited active credit history on record. Do you have any informal or undisclosed borrowing not reflected in this report?",
            category="file_thickness",
            reason=flags["thin_file"].reason,
            priority=PRIORITY_INFO,
            source_flag="thin_file",
        ))

    questions.sort(key=lambda q: q.priority)
    return questions