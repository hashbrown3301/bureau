"""
Canonical schema for normalized bureau reports.
This is the single internal representation that all bureau formats
(CIBIL, Experian, Equifax, CRIF) normalize into.

LLM never populates derived fields. Only the metrics/risk engines do.
"""

from __future__ import annotations
from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class AccountStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    WRITTEN_OFF = "written_off"
    SETTLED = "settled"
    NPA = "npa"


class DPDSeverity(str, Enum):
    CLEAN = "clean"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class Account(BaseModel):
    account_id: str
    lender: str
    account_type: str  # e.g. "personal_loan", "credit_card", "auto_loan", "overdraft"
    sanctioned_amount: float
    current_outstanding: float
    overdue_amount: float
    emi_amount: Optional[float] = None
    status: AccountStatus
    opened_date: Optional[date] = None
    closed_date: Optional[date] = None
    dpd_current: int = 0
    dpd_history: list[int] = Field(default_factory=list)  # most recent first
    credit_limit: Optional[float] = None  # only for revolving accounts


class Enquiry(BaseModel):
    enquiry_date: date
    lender: str
    purpose: str
    amount: float


class RiskFlag(BaseModel):
    flagged: bool
    reason: str


class CanonicalBureauReport(BaseModel):
    bureau_name: str
    report_date: date
    applicant_name: str
    pan: str
    credit_score: Optional[int] = None

    accounts: list[Account] = Field(default_factory=list)
    enquiries: list[Enquiry] = Field(default_factory=list)

    # --- Derived fields: populated by metrics engine, NEVER by LLM ---
    total_accounts: int = 0
    active_accounts: int = 0
    closed_accounts: int = 0
    total_outstanding: float = 0.0
    total_overdue: float = 0.0
    total_credit_limit: float = 0.0
    total_emi_burden: float = 0.0
    credit_utilization_pct: Optional[float] = None
    dpd_severity: DPDSeverity = DPDSeverity.CLEAN
    credit_vintage_months: Optional[int] = None
    enquiries_last_6_months: int = 0

    # --- Risk flags: populated by risk engine, NEVER by LLM ---
    risk_flags: dict[str, RiskFlag] = Field(default_factory=dict)

    # --- Summary: populated by LLM, prose only, no decisions ---
    summary: str = ""  