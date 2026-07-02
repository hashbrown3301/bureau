"""
Bureau Agent -- Streamlit UI
Run with: uv run streamlit run app.py
"""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from bureau_agent.agent import create_bureau_agent

# --- Page config ---
st.set_page_config(
    page_title="Bureau Agent",
    layout="wide"
)

# --- Header ---
st.title("Bureau Analysis Agent")
st.caption("AI-powered credit bureau report analyzer for Loan Origination")

# --- Load fixtures ---
FIXTURES_DIR = Path("fixtures")
fixture_files = {f.stem: f for f in sorted(FIXTURES_DIR.glob("*.json"))}

# --- Sidebar ---
with st.sidebar:
    st.header("Input")

    input_method = st.radio(
        "Input method",
        ["Select a fixture", "Paste JSON", "Upload JSON file"],
        index=0
    )

    raw_json = None

    if input_method == "Select a fixture":
        selected = st.selectbox(
            "Choose a test fixture",
            list(fixture_files.keys()),
            format_func=lambda x: x.replace("_", " ").title()
        )
        if selected:
            with open(fixture_files[selected]) as f:
                raw_json = f.read()
            st.code(raw_json, language="json")

    elif input_method == "Paste JSON":
        raw_json = st.text_area(
            "Paste bureau JSON here",
            height=400,
            placeholder='{"bureau_name": "CIBIL", ...}'
        )

    elif input_method == "Upload JSON file":
        uploaded = st.file_uploader("Upload bureau JSON", type=["json"])
        if uploaded:
            raw_json = uploaded.read().decode("utf-8")
            st.code(raw_json, language="json")

    st.divider()
    run_button = st.button("Run Analysis", type="primary", use_container_width=True)

# --- Run agent ---
if run_button:
    if not raw_json or not raw_json.strip():
        st.error("Please provide a bureau JSON report first.")
        st.stop()

    try:
        parsed_input = json.loads(raw_json)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
        st.stop()

    with st.spinner("Running bureau analysis..."):
        try:
            agent = create_bureau_agent()
            result = agent.invoke({"raw_input": parsed_input})
            output = result["final_output"]
        except Exception as e:
            st.error(f"Agent error: {e}")
            st.stop()

    # --- Validation failure ---
    if not output.get("success"):
        st.error("Validation Failed")
        for err in output.get("errors", []):
            st.warning(err)
        st.stop()

    # --- Success ---
    st.success("Analysis complete")

    # --- Top metrics row ---
    st.subheader("Credit Profile")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Credit Score", output["credit_score"] or "N/A")
    col2.metric("DPD Severity", output["dpd_severity"].upper())
    col3.metric("Credit Vintage", f"{output['credit_vintage_months']} months")
    col4.metric("Enquiries (6mo)", output["enquiries_last_6_months"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Accounts", output["total_accounts"])
    col2.metric("Active Accounts", output["active_accounts"])
    col3.metric("Total Outstanding", f"Rs. {output['total_outstanding']:,.0f}")
    col4.metric("Total Overdue", f"Rs. {output['total_overdue']:,.0f}")

    col1, col2 = st.columns(2)
    col1.metric("EMI Burden", f"Rs. {output['total_emi_burden']:,.0f}/month")
    col2.metric(
        "Credit Utilization",
        f"{output['credit_utilization_pct']}%" if output['credit_utilization_pct'] is not None else "N/A"
    )

    st.divider()

    # --- Risk flags ---
    st.subheader("Risk Flags")
    flags = output.get("risk_flags", {})
    flagged = {k: v for k, v in flags.items() if v["flagged"]}
    clean = {k: v for k, v in flags.items() if not v["flagged"]}

    if flagged:
        for flag_name, flag in flagged.items():
            st.error(f"**{flag_name.replace('_', ' ').upper()}** -- {flag['reason']}")
    else:
        st.success("No risk flags triggered")

    with st.expander("View all flags including clean ones"):
        for flag_name, flag in clean.items():
            st.success(f"**{flag_name.replace('_', ' ').upper()}** -- {flag['reason']}")

    st.divider()

    # --- Consistency notes ---
    st.subheader("AI Consistency Check")
    notes = output.get("consistency_notes", [])
    if notes:
        for note in notes:
            note_type = note.get("type", "context").upper()
            related_to = note.get("related_to", "overall")
            observation = note.get("observation", "")
            if note.get("type") == "contradiction":
                st.warning(f"**{note_type}** ({related_to}) -- {observation}")
            elif note.get("type") == "pattern":
                st.info(f"**{note_type}** ({related_to}) -- {observation}")
            else:
                st.info(f"**{note_type}** ({related_to}) -- {observation}")
    else:
        st.info("No consistency observations -- profile appears straightforward.")

    st.divider()

    # --- Summary ---
    st.subheader("Underwriter Summary")
    st.write(output.get("summary", "No summary generated."))

    st.divider()

    # --- Raw output ---
    with st.expander("View raw JSON output"):
        st.json(output)