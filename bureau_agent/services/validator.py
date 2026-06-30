"""
Validates raw bureau input JSON before normalization.
Pure deterministic checks -- no LLM involved.

Operates on the RAW dict structure (matching the bureau API/synthetic
JSON format), not the canonical schema. This is intentional: we want
to catch malformed input before we even attempt to normalize it.
"""

from datetime import datetime

VALID_STATUS_CODES = {
    "STD", "SUB", "DBT", "LSS", "XXX",
    "WRITTEN_OFF", "SETTLED", "NPA", "CLOSED", "ACTIVE"
}

VALID_ACCOUNT_TYPES = {
    "personal_loan", "home_loan", "auto_loan", "credit_card",
    "overdraft", "business_loan", "consumer_loan", "gold_loan",
    "education_loan", "two_wheeler_loan"
}

REQUIRED_TOP_LEVEL_FIELDS = {
    "bureau_name", "report_date", "applicant", "credit_score",
    "accounts", "enquiries"
}

REQUIRED_APPLICANT_FIELDS = {"name", "pan"}

REQUIRED_ACCOUNT_FIELDS = {
    "account_id", "lender", "account_type", "sanctioned_amount",
    "current_outstanding", "overdue_amount", "status_code"
}

REQUIRED_ENQUIRY_FIELDS = {"enquiry_date", "lender", "purpose", "amount"}


def _is_valid_date(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def validate_bureau_input(raw: dict) -> tuple[bool, list[str]]:
    """
    Validates the raw bureau JSON structure.

    Returns (is_valid, list_of_error_strings).
    PII rule: never include full PAN or applicant name in error strings --
    reference by account_id or index only.
    """
    errors: list[str] = []

    # --- Top-level fields ---
    missing_top = REQUIRED_TOP_LEVEL_FIELDS - raw.keys()
    if missing_top:
        errors.append(f"Missing top-level fields: {sorted(missing_top)}")
        return False, errors  # can't proceed further without these

    if not _is_valid_date(raw.get("report_date")):
        errors.append("report_date is missing or not in YYYY-MM-DD format")

    score = raw.get("credit_score")
    if score is not None:
        if not isinstance(score, int) or not (300 <= score <= 900):
            errors.append(f"credit_score must be an integer between 300-900, got: {score}")

    # --- Applicant ---
    applicant = raw.get("applicant", {})
    if not isinstance(applicant, dict):
        errors.append("applicant must be an object")
    else:
        missing_applicant = REQUIRED_APPLICANT_FIELDS - applicant.keys()
        if missing_applicant:
            errors.append(f"applicant missing fields: {sorted(missing_applicant)}")
        elif not applicant.get("pan"):
            errors.append("applicant.pan is empty")

    # --- Accounts ---
    accounts = raw.get("accounts")
    if not isinstance(accounts, list):
        errors.append("accounts must be a list")
        accounts = []

    for i, acc in enumerate(accounts):
        if not isinstance(acc, dict):
            errors.append(f"accounts[{i}] is not an object")
            continue

        missing = REQUIRED_ACCOUNT_FIELDS - acc.keys()
        if missing:
            errors.append(f"accounts[{i}] missing fields: {sorted(missing)}")
            continue  # skip further checks on this malformed account

        if not acc.get("lender"):
            errors.append(f"accounts[{i}] has empty lender")

        if not acc.get("account_type"):
            errors.append(f"accounts[{i}] has empty account_type")

        status = acc.get("status_code")
        if status not in VALID_STATUS_CODES:
            errors.append(f"accounts[{i}] has invalid status_code: {status}")

        if acc.get("overdue_amount", 0) < 0:
            errors.append(f"accounts[{i}] has negative overdue_amount")

        if acc.get("sanctioned_amount", 0) < 0:
            errors.append(f"accounts[{i}] has negative sanctioned_amount")

        dpd_history = acc.get("dpd_history")
        if dpd_history is not None:
            if not isinstance(dpd_history, list):
                errors.append(f"accounts[{i}] dpd_history must be a list")
            elif len(dpd_history) > 36:
                errors.append(f"accounts[{i}] dpd_history exceeds 36 months")
            elif not all(isinstance(d, int) and d >= 0 for d in dpd_history):
                errors.append(f"accounts[{i}] dpd_history must contain non-negative integers")

        opened = acc.get("opened_date")
        if opened is not None and not _is_valid_date(opened):
            errors.append(f"accounts[{i}] opened_date is not in YYYY-MM-DD format")

    # --- Enquiries ---
    enquiries = raw.get("enquiries")
    if not isinstance(enquiries, list):
        errors.append("enquiries must be a list")
        enquiries = []

    for i, enq in enumerate(enquiries):
        if not isinstance(enq, dict):
            errors.append(f"enquiries[{i}] is not an object")
            continue

        missing = REQUIRED_ENQUIRY_FIELDS - enq.keys()
        if missing:
            errors.append(f"enquiries[{i}] missing fields: {sorted(missing)}")
            continue

        if not _is_valid_date(enq.get("enquiry_date")):
            errors.append(f"enquiries[{i}] enquiry_date is not in YYYY-MM-DD format")

        if enq.get("amount", 0) < 0:
            errors.append(f"enquiries[{i}] has negative amount")

    return len(errors) == 0, errors