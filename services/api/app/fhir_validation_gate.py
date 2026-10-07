"""Fail CI when an HL7 validator OperationOutcome contains errors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("outcome")
    args = parser.parse_args()
    outcome = json.loads(Path(args.outcome).read_text(encoding="utf-8"))
    issues = outcome.get("issue", [])
    errors = [issue for issue in issues if issue.get("severity") in {"fatal", "error"}]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    print(f"HL7 validator: {len(errors)} errors, {len(warnings)} warnings, {len(issues)} total issues")
    for issue in errors:
        location = ", ".join(issue.get("location", []))
        detail = issue.get("diagnostics") or issue.get("details", {}).get("text") or "validation error"
        print(f"ERROR {location}: {detail}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
