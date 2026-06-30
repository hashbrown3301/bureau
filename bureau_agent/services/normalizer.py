"""
Normalizes raw bureau JSON into the canonical schema.
Pure deterministic mapping -- no LLM involved.

Assumes input has already passed validator.py checks.
"""

from datetime import date, datetime
from .schema import Account, AccountStatus, CanonicalBureauReport, Enquiry

# Based on RBI/CIBIL asset classification convention:
# STD = Standard, SUB = Sub-standard, DBT = Doubtful, LSS = Loss, XXX = no data reported that month
STATUS_CODE_MAP: dict[str, AccountStatus] = {
    "STD": AccountStatus.ACTIVE,
    "SUB": AccountStatus.ACTIVE,        # delinquent but still being serviced; DPD captures severity
    "DBT": AccountStatus.NPA,           # doubtful asset = RBI NPA classification
    "LSS": AccountStatus.WRITTEN_OFF,   # loss asset = functionally a write-off
    "XXX": AccountStatus.ACTIVE,        # no data reported that month, not a real status change
    "WRITTEN_OFF": AccountStatus.WRITTEN_OFF,
    "SETTLED": AccountStatus.SETTLED,
    "NPA": AccountStatus.NPA,
    "CLOSED": AccountStatus.CLOSED,
    "ACTIVE": AccountStatus.ACTIVE,
}

REVOLVING_ACCOUNT_TYPES = {"credit_card", "overdraft"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _normalize_account(raw_acc: dict) -> Account:
    status = STATUS_CODE_MAP.get(raw_acc["status_code"], AccountStatus.ACTIVE)
    account_type = raw_acc["account_type"]

    credit_limit = raw_acc.get("credit_limit")
    if account_type not in REVOLVING_ACCOUNT_TYPES:
        credit_limit = None

    return Account(
        account_id=raw_acc["account_id"],
        lender=raw_acc["lender"],
        account_type=account_type,
        sanctioned_amount=float(raw_acc["sanctioned_amount"]),
        current_outstanding=float(raw_acc["current_outstanding"]),
        overdue_amount=float(raw_acc["overdue_amount"]),
        emi_amount=float(raw_acc["emi_amount"]) if raw_acc.get("emi_amount") is not None else None,
        status=status,
        opened_date=_parse_date(raw_acc.get("opened_date")),
        closed_date=_parse_date(raw_acc.get("closed_date")),
        dpd_current=int(raw_acc.get("dpd_current", 0)),
        dpd_history=list(raw_acc.get("dpd_history", [])),
        credit_limit=float(credit_limit) if credit_limit is not None else None,
    )


def _normalize_enquiry(raw_enq: dict) -> Enquiry:
    return Enquiry(
        enquiry_date=_parse_date(raw_enq["enquiry_date"]),
        lender=raw_enq["lender"],
        purpose=raw_enq["purpose"],
        amount=float(raw_enq["amount"]),
    )


def normalize_bureau_report(raw: dict) -> CanonicalBureauReport:
    """
    Maps validated raw bureau JSON into the canonical schema.
    Does NOT compute derived fields (totals, metrics, risk flags) --
    that's the job of metrics.py and risk.py, run after this.
    """
    accounts = [_normalize_account(a) for a in raw.get("accounts", [])]
    enquiries = [_normalize_enquiry(e) for e in raw.get("enquiries", [])]

    return CanonicalBureauReport(
        bureau_name=raw["bureau_name"],
        report_date=_parse_date(raw["report_date"]),
        applicant_name=raw["applicant"]["name"],
        pan=raw["applicant"]["pan"],
        credit_score=raw.get("credit_score"),
        accounts=accounts,
        enquiries=enquiries,
    )