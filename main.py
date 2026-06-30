"""
Test runner for the Bureau Agent.

Loads each fixture in fixtures/, runs it through the graph,
prints a summary of the result, and saves full output to outputs/.

Usage:
  uv run python main.py              # runs all fixtures
  uv run python main.py clean        # runs only fixtures matching "clean"
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from bureau_agent.agent import create_bureau_agent

load_dotenv()

FIXTURES_DIR = Path("fixtures")
OUTPUTS_DIR = Path("outputs")


def run_fixture(agent, fixture_path: Path) -> dict:
    with open(fixture_path, "r") as f:
        raw_input = json.load(f)

    result = agent.invoke({"raw_input": raw_input})
    return result["final_output"]


def print_result_summary(fixture_name: str, output: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"FIXTURE: {fixture_name}")
    print(f"{'=' * 60}")

    if not output.get("success"):
        print(f"VALIDATION FAILED: {output.get('errors')}")
        return

    print(f"Applicant:        {output['applicant_name']}")
    print(f"Bureau:           {output['bureau_name']}")
    print(f"Credit Score:     {output['credit_score']}")
    print(f"Total Accounts:   {output['total_accounts']} (active: {output['active_accounts']})")
    print(f"Total Outstanding: {output['total_outstanding']}")
    print(f"Total Overdue:    {output['total_overdue']}")
    print(f"EMI Burden:       {output['total_emi_burden']}")
    print(f"Utilization:      {output['credit_utilization_pct']}%")
    print(f"DPD Severity:     {output['dpd_severity']}")
    print(f"Vintage (months): {output['credit_vintage_months']}")
    print(f"Enquiries (6mo):  {output['enquiries_last_6_months']}")

    print("\nRisk Flags:")
    for flag_name, flag in output["risk_flags"].items():
        marker = "[X]" if flag["flagged"] else "[ ]"
        print(f"  {marker} {flag_name}: {flag['reason']}")

    print(f"\nConsistency Notes: {len(output.get('consistency_notes', []))}")
    for note in output.get("consistency_notes", []):
        print(f"  - [{note['type']}] ({note['related_to']}): {note['observation']}")

    print(f"\nSummary:\n{output.get('summary', '')}")


def main():
    OUTPUTS_DIR.mkdir(exist_ok=True)

    filter_str = sys.argv[1] if len(sys.argv) > 1 else None
    fixture_files = sorted(FIXTURES_DIR.glob("*.json"))

    if filter_str:
        fixture_files = [f for f in fixture_files if filter_str in f.name]

    if not fixture_files:
        print("No matching fixtures found.")
        return

    agent = create_bureau_agent()

    for fixture_path in fixture_files:
        try:
            output = run_fixture(agent, fixture_path)
            print_result_summary(fixture_path.stem, output)

            out_file = OUTPUTS_DIR / f"{fixture_path.stem}_output.json"
            with open(out_file, "w") as f:
                json.dump(output, f, indent=2)

        except Exception as e:
            print(f"\nERROR running {fixture_path.name}: {e}")


if __name__ == "__main__":
    main()