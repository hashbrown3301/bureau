# Bureau Agent

A LangGraph-based AI agent that analyzes credit bureau reports (CIBIL, Experian, CRIF) and produces structured risk insights for use in a Loan Origination System (LOS).

---

## What It Does

The Bureau Agent takes a structured bureau JSON report as input and runs it through a deterministic pipeline to extract, validate, normalize, and analyze the applicant's credit history. It then uses an LLM (Groq/Llama 3.3-70b) to add judgment-level observations that rule-based engines cannot produce, and generates a plain English summary for underwriters.

The agent never makes or implies a lending decision. It produces facts, metrics, risk flags, and observations — the lending decision happens downstream.

---

## Architecture

```
Raw Bureau JSON
      ↓
[validate_input]          — checks JSON structure, field types, value ranges
      ↓
[normalize_and_compute]   — maps bureau codes to canonical schema,
                            computes all metrics and risk flags
      ↓
[run_consistency_check]   — LLM reads the full picture, flags patterns
                            and contradictions rules cannot catch
      ↓
[generate_summary]        — LLM writes a plain English summary
                            for an underwriter
      ↓
[finalize_output]         — assembles final JSON output
```

**LLM is used exactly twice:** consistency check and summary generation. Everything else is deterministic Python.

---

## Project Structure

```
bureau-agent/
  main.py                        -- test runner (CLI)
  .env                           -- GROQ_API_KEY goes here
  fixtures/                      -- synthetic test JSON reports
    clean_profile.json
    writeoff_profile.json
    high_dpd_profile.json
    thin_file_profile.json
    high_utilization_profile.json
    same_lender_enquiry_profile.json
  outputs/                       -- agent writes results here
  bureau_agent/
    __init__.py
    agent.py                     -- LangGraph graph definition
    state.py                     -- BureauAgentState TypedDict
    prompts.py                   -- LLM prompt constants
    tools.py                     -- Groq API calls
    services/
      schema.py                  -- canonical Pydantic models
      validator.py               -- raw input validation
      normalizer.py              -- bureau codes → canonical schema
      metrics.py                 -- deterministic calculations
      risk.py                    -- risk flag engine
```

---

## Setup

**Requirements:** Python 3.11+, uv

**1. Install dependencies**
```bash
uv init
uv add langchain langgraph langchain-groq pydantic python-dotenv
```

**2. Get a Groq API key**

Go to [console.groq.com](https://console.groq.com), sign in, and create a free API key. No credit card required.

**3. Add your key to .env**
```
GROQ_API_KEY=your_key_here
```

---

## How to Run

**Run all fixtures:**
```bash
uv run python main.py
```

**Run a specific fixture:**
```bash
uv run python main.py clean_profile
uv run python main.py writeoff_profile
uv run python main.py high_dpd_profile
uv run python main.py thin_file_profile
uv run python main.py high_utilization_profile
uv run python main.py same_lender_enquiry_profile
```

Results are printed to console and saved as JSON to `outputs/<fixture_name>_output.json`.

---

## Input Format

The agent accepts a bureau JSON report with the following structure:

```json
{
  "bureau_name": "CIBIL",
  "report_date": "2026-06-15",
  "applicant": {
    "name": "Rohan Mehta",
    "pan": "ABCDE1234F",
    "dob": "1990-04-12"
  },
  "credit_score": 742,
  "accounts": [
    {
      "account_id": "ACC001",
      "lender": "HDFC Bank",
      "account_type": "personal_loan",
      "sanctioned_amount": 500000,
      "current_outstanding": 320000,
      "overdue_amount": 0,
      "emi_amount": 12500,
      "status_code": "STD",
      "opened_date": "2023-01-10",
      "closed_date": null,
      "dpd_current": 0,
      "dpd_history": [0,0,0,0,0,0,0,0,0,0,0,0],
      "credit_limit": null
    }
  ],
  "enquiries": [
    {
      "enquiry_date": "2026-05-01",
      "lender": "ICICI Bank",
      "purpose": "personal_loan",
      "amount": 200000
    }
  ]
}
```

**Supported `account_type` values:**
`personal_loan`, `home_loan`, `auto_loan`, `credit_card`, `overdraft`, `business_loan`, `consumer_loan`, `gold_loan`, `education_loan`, `two_wheeler_loan`

**Supported `status_code` values:**

| Code | Meaning | Maps To |
|------|---------|---------|
| STD | Standard — performing | active |
| SUB | Sub-standard — delinquent but active | active |
| DBT | Doubtful — RBI NPA classification | npa |
| LSS | Loss asset — written off | written_off |
| XXX | No data reported that month | active |
| WRITTEN_OFF | Written off | written_off |
| SETTLED | Settled for less than full amount | settled |
| NPA | Non-performing asset | npa |
| CLOSED | Fully repaid and closed | closed |
| ACTIVE | Active and performing | active |

**`dpd_history` convention:** list of integers, most recent month first, up to 36 months. Each value is the number of days past due for that month. Use 0 for on-time payments.

---

## Output Format

```json
{
  "success": true,
  "bureau_name": "CIBIL",
  "applicant_name": "Rohan Mehta",
  "credit_score": 782,
  "total_accounts": 3,
  "active_accounts": 2,
  "total_outstanding": 325000.0,
  "total_overdue": 0.0,
  "total_emi_burden": 12500.0,
  "credit_utilization_pct": 22.5,
  "dpd_severity": "clean",
  "credit_vintage_months": 99,
  "enquiries_last_6_months": 1,
  "risk_flags": {
    "has_writeoff": { "flagged": false, "reason": "No written-off accounts" },
    "has_settlement": { "flagged": false, "reason": "No settled accounts" },
    "has_npa": { "flagged": false, "reason": "No NPA accounts" },
    "high_utilization": { "flagged": false, "reason": "Credit utilization at 22.5%, within acceptable range" },
    "recent_dpd": { "flagged": false, "reason": "No DPD in last 3 months" },
    "enquiry_surge": { "flagged": false, "reason": "1 enquiries in last 6 months, within threshold." },
    "thin_file": { "flagged": false, "reason": "2 active account(s), sufficient credit history" },
    "high_overdue": { "flagged": false, "reason": "No overdue amount across any account" }
  },
  "consistency_notes": [
    {
      "observation": "...",
      "related_to": "overall",
      "type": "context"
    }
  ],
  "summary": "Plain English summary for underwriter..."
}
```

**On validation failure:**
```json
{
  "success": false,
  "errors": [
    "credit_score must be an integer between 300-900, got: 950",
    "accounts[0] has invalid status_code: XYZ"
  ]
}
```

---

## Risk Flags

| Flag | Triggers When | Why It Matters |
|------|--------------|----------------|
| `has_writeoff` | Any account status is written_off | Lender gave up recovering the debt — strongest negative signal |
| `has_settlement` | Any account status is settled | Debt closed for less than full amount owed |
| `has_npa` | Any account status is npa | RBI non-performing asset classification (DBT accounts) |
| `high_utilization` | Credit utilization > 80% | Heavy reliance on revolving credit, signals financial stress |
| `recent_dpd` | Any DPD > 0 in last 3 months | Currently missing payments |
| `enquiry_surge` | More than 3 enquiries from more than 2 unique lenders in 6 months | Active credit seeking across multiple lenders — possible rejections |
| `thin_file` | Fewer than 2 active accounts | Insufficient credit history to assess risk reliably |
| `high_overdue` | Total overdue > 0 | Money currently owed past its due date |

**Note on `enquiry_surge`:** multiple enquiries from the same lender are treated as a single application being processed, not a surge. The flag only fires when enquiries are spread across more than 2 unique lenders.

---

## AI Layer

The LLM adds two things the deterministic rules engine cannot:

**1. Consistency Check**
Reads the full bureau picture — score, accounts, DPD history, enquiries, risk flags — and surfaces patterns, contradictions, and context that threshold rules miss. Examples:
- A write-off that is old and small vs. recent and large (same flag, different risk story)
- DPD that is steadily worsening month over month vs. an isolated historical spike
- Multiple loans opened within a short window (possible loan stacking)
- Credit score that appears inconsistent with current account-level reality
- Enquiry pattern suggesting repeated rejections vs. one application in process

The LLM does not have access to income data and will never comment on whether monetary amounts are "high" or "low" — those judgments require income context that lives in a separate agent.

**2. Summary**
150-200 word plain English summary covering credit profile, active obligations, flagged risk items, and consistency observations. Written for a loan underwriter, not a data engineer.

Neither output ever recommends approval, rejection, or eligibility.

---

## Adding New Test Fixtures

1. Create a new JSON file in `fixtures/` following the input format above
2. Name it descriptively: `<scenario>_profile.json`
3. Run it: `uv run python main.py <scenario>_profile`
4. Check `outputs/<scenario>_profile_output.json` for the full result

When designing fixtures, target specific flag combinations so you can verify expected behavior. Each fixture should ideally isolate one or two risk signals to make assertions clear.

---

## Limitations

- **No income data** — EMI burden is reported as a fact only; affordability assessment (FOIR) requires income data from a separate agent
- **Synthetic data only** — built and tested against hand-crafted fixtures; real bureau API integration is a future step
- **Status code coverage** — normalizer handles the most common CIBIL/RBI codes; additional bureau-specific codes may need to be added for Experian/CRIF formats
- **Report staleness** — agent does not currently flag reports older than 30 days; stale data may not reflect current account status
