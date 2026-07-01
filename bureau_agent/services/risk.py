"""
Computes risk indicators from a normalized + metrics-computed bureau report.
Pure rule-based flagging -- no LLM.

Each flag is a boolean with a short reason string, stored in
report.risk_flags as a dict[str, RiskFlag].

Thresholds are constants here -- update in one place, never hardcode
magic numbers inside the flagging logic itself.
"""

from .schema import AccountStatus, CanonicalBureauReport, DPDSeverity, RiskFlag

# --- Thresholds (NBFC-standard placeholder defaults --
# confirm against actual lending policy before production use) ---
HIGH_UTILIZATION_THRESHOLD_PCT = 80.0
ENQUIRY_SURGE_THRESHOLD = 3          # more than this many enquiries in 6 months
ENQUIRY_SURGE_UNIQUE_LENDER_THRESHOLD = 2  # more than this = genuinely spread across lenders
THIN_FILE_MIN_ACTIVE_ACCOUNTS = 2    # fewer than this = thin file
RECENT_DPD_LOOKBACK_MONTHS = 3       # any DPD > 0 within this many months = recent


def _has_status(report: CanonicalBureauReport, *statuses: AccountStatus) -> tuple[bool, list[str]]:
    """Returns (flagged, list of account_ids matching any of the given statuses)."""
    matches = [a.account_id for a in report.accounts if a.status in statuses]
    return len(matches) > 0, matches


def _has_recent_dpd(report: CanonicalBureauReport, lookback_months: int) -> tuple[bool, list[str]]:
    """
    Checks the first `lookback_months` entries of dpd_history (most recent first)
    plus dpd_current, across all accounts, for any DPD > 0.
    """
    flagged_accounts = []
    for acc in report.accounts:
        if acc.dpd_current > 0:
            flagged_accounts.append(acc.account_id)
            continue
        recent_window = acc.dpd_history[:lookback_months]
        if any(d > 0 for d in recent_window):
            flagged_accounts.append(acc.account_id)
    return len(flagged_accounts) > 0, flagged_accounts


def compute_risk_indicators(report: CanonicalBureauReport) -> CanonicalBureauReport:
    """
    Computes all risk flags and populates report.risk_flags.
    Assumes compute_metrics() has already run -- relies on derived fields.
    Returns the same report object with risk_flags filled in.
    """
    flags: dict[str, RiskFlag] = {}

    # --- Write-off ---
    has_writeoff, writeoff_ids = _has_status(report, AccountStatus.WRITTEN_OFF)
    flags["has_writeoff"] = RiskFlag(
        flagged=has_writeoff,
        reason=(
            f"{len(writeoff_ids)} account(s) written off: {writeoff_ids}"
            if has_writeoff else "No written-off accounts"
        ),
    )

    # --- Settlement ---
    has_settlement, settlement_ids = _has_status(report, AccountStatus.SETTLED)
    flags["has_settlement"] = RiskFlag(
        flagged=has_settlement,
        reason=(
            f"{len(settlement_ids)} account(s) settled: {settlement_ids}"
            if has_settlement else "No settled accounts"
        ),
    )

    # --- NPA ---
    has_npa, npa_ids = _has_status(report, AccountStatus.NPA)
    flags["has_npa"] = RiskFlag(
        flagged=has_npa,
        reason=(
            f"{len(npa_ids)} account(s) classified NPA: {npa_ids}"
            if has_npa else "No NPA accounts"
        ),
    )

    # --- High utilization ---
    util = report.credit_utilization_pct
    high_util = util is not None and util > HIGH_UTILIZATION_THRESHOLD_PCT
    flags["high_utilization"] = RiskFlag(
        flagged=high_util,
        reason=(
            f"Credit utilization at {util}%, exceeds {HIGH_UTILIZATION_THRESHOLD_PCT}% threshold"
            if high_util else f"Credit utilization at {util}%, within acceptable range"
        ),
    )

    # --- Recent DPD ---
    recent_dpd, dpd_ids = _has_recent_dpd(report, RECENT_DPD_LOOKBACK_MONTHS)
    flags["recent_dpd"] = RiskFlag(
        flagged=recent_dpd,
        reason=(
            f"DPD reported in last {RECENT_DPD_LOOKBACK_MONTHS} months on: {dpd_ids}"
            if recent_dpd else f"No DPD in last {RECENT_DPD_LOOKBACK_MONTHS} months"
        ),
    )

    # --- Enquiry surge (smarter: considers unique lenders + purpose concentration) ---
    # Same lender multiple times = likely one application being processed (low risk)
    # Multiple lenders = actively seeking credit from different sources (higher risk)
    raw_count = report.enquiries_last_6_months
    unique_lenders = report.unique_lenders_last_6_months
    purposes = report.enquiry_purposes_last_6_months

    spread = raw_count > ENQUIRY_SURGE_THRESHOLD and unique_lenders > ENQUIRY_SURGE_UNIQUE_LENDER_THRESHOLD
    concentrated = raw_count > ENQUIRY_SURGE_THRESHOLD and unique_lenders <= ENQUIRY_SURGE_UNIQUE_LENDER_THRESHOLD

    if spread:
        enquiry_surge = True
        reason = (
            f"{raw_count} enquiries from {unique_lenders} different lenders "
            f"in last 6 months, purposes: {purposes}. "
            f"Spread across multiple lenders suggests active credit seeking."
        )
    elif concentrated:
        enquiry_surge = False
        reason = (
            f"{raw_count} enquiries in last 6 months but only from "
            f"{unique_lenders} lender(s) -- likely one application being processed, "
            f"not active credit seeking."
        )
    else:
        enquiry_surge = False
        reason = f"{raw_count} enquiries in last 6 months, within threshold."

    flags["enquiry_surge"] = RiskFlag(flagged=enquiry_surge, reason=reason)

    # --- Thin file ---
    thin_file = report.active_accounts < THIN_FILE_MIN_ACTIVE_ACCOUNTS
    flags["thin_file"] = RiskFlag(
        flagged=thin_file,
        reason=(
            f"Only {report.active_accounts} active account(s), "
            f"below minimum of {THIN_FILE_MIN_ACTIVE_ACCOUNTS}"
            if thin_file
            else f"{report.active_accounts} active account(s), sufficient credit history"
        ),
    )

    # --- High overdue ---
    high_overdue = report.total_overdue > 0
    flags["high_overdue"] = RiskFlag(
        flagged=high_overdue,
        reason=(
            f"Total overdue amount: {report.total_overdue}"
            if high_overdue else "No overdue amount across any account"
        ),
    )

    report.risk_flags = flags
    return report