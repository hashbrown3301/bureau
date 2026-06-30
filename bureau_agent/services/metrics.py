"""
Computes deterministic financial metrics from a normalized bureau report.
Pure arithmetic -- no LLM, no business-rule flagging (that's risk.py).

All functions operate on CanonicalBureauReport and return primitive
values or update the report's derived fields directly.
"""

from datetime import date
from .schema import Account, AccountStatus, CanonicalBureauReport, DPDSeverity

REVOLVING_ACCOUNT_TYPES = {"credit_card", "overdraft"}

# DPD severity thresholds -- worst single DPD value across all accounts,
# all months in dpd_history (convention: most recent first)
DPD_SEVERITY_THRESHOLDS = [
    (0, DPDSeverity.CLEAN),
    (30, DPDSeverity.MILD),
    (90, DPDSeverity.MODERATE),
]
# anything above the last threshold = SEVERE


def _classify_dpd_severity(worst_dpd: int) -> DPDSeverity:
    if worst_dpd <= 0:
        return DPDSeverity.CLEAN
    if worst_dpd <= 30:
        return DPDSeverity.MILD
    if worst_dpd <= 90:
        return DPDSeverity.MODERATE
    return DPDSeverity.SEVERE


def _worst_dpd_across_accounts(accounts: list[Account]) -> int:
    worst = 0
    for acc in accounts:
        worst = max(worst, acc.dpd_current)
        if acc.dpd_history:
            worst = max(worst, max(acc.dpd_history))
    return worst


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _credit_vintage_months(accounts: list[Account], report_date: date) -> int | None:
    opened_dates = [a.opened_date for a in accounts if a.opened_date is not None]
    if not opened_dates:
        return None
    oldest = min(opened_dates)
    return _months_between(oldest, report_date)


def _enquiries_in_last_n_months(report, n: int) -> int:
    count = 0
    for enq in report.enquiries:
        if enq.enquiry_date is None:
            continue
        months_ago = _months_between(enq.enquiry_date, report.report_date)
        if 0 <= months_ago <= n:
            count += 1
    return count


def compute_metrics(report: CanonicalBureauReport) -> CanonicalBureauReport:
    """
    Computes and populates all derived fields on the canonical report.
    Returns the same report object with derived fields filled in.
    """
    accounts = report.accounts

    # --- Account counts ---
    report.total_accounts = len(accounts)
    report.active_accounts = sum(1 for a in accounts if a.status == AccountStatus.ACTIVE)
    report.closed_accounts = sum(
        1 for a in accounts
        if a.status in (AccountStatus.CLOSED, AccountStatus.WRITTEN_OFF, AccountStatus.SETTLED)
    )

    # --- Outstanding / overdue totals ---
    report.total_outstanding = sum(a.current_outstanding for a in accounts)
    report.total_overdue = sum(a.overdue_amount for a in accounts)

    # --- Credit limit totals (revolving accounts only) ---
    report.total_credit_limit = sum(
        a.credit_limit for a in accounts
        if a.credit_limit is not None and a.account_type in REVOLVING_ACCOUNT_TYPES
    )

    # --- EMI burden: sum of emi_amount across ACTIVE accounts only ---
    report.total_emi_burden = sum(
        a.emi_amount for a in accounts
        if a.emi_amount is not None and a.status == AccountStatus.ACTIVE
    )

    # --- Credit utilization: outstanding / limit, revolving accounts only ---
    revolving_outstanding = sum(
        a.current_outstanding for a in accounts
        if a.account_type in REVOLVING_ACCOUNT_TYPES
    )
    if report.total_credit_limit > 0:
        report.credit_utilization_pct = round(
            (revolving_outstanding / report.total_credit_limit) * 100, 2
        )
    else:
        report.credit_utilization_pct = None

    # --- DPD severity: worst single DPD across all accounts/months ---
    worst_dpd = _worst_dpd_across_accounts(accounts)
    report.dpd_severity = _classify_dpd_severity(worst_dpd)

    # --- Credit vintage ---
    report.credit_vintage_months = _credit_vintage_months(accounts, report.report_date)

    # --- Enquiries in last 6 months ---
    report.enquiries_last_6_months = _enquiries_in_last_n_months(report, n=6)

    return report