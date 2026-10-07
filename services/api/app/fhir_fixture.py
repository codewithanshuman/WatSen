"""Export a reproducible WatSen bundle for the official HL7 validator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.fhir import bundle_from_store, validate_bundle
from app.store import get_store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", default="PT-CBR-01")
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--out", default="../../artifacts/watsen-oah-bundle.json")
    args = parser.parse_args()

    store = get_store()
    if args.segment not in store.segments:
        raise SystemExit(f"Unknown segment: {args.segment}")
    bundle = bundle_from_store(
        store.segment_summary(args.segment, "none"),
        store.history(args.segment, max(args.hours, 24), "none"),
        hours=args.hours,
    )
    preflight = validate_bundle(bundle)
    if preflight["status"] != "pass":
        raise SystemExit("Local preflight failed: " + "; ".join(preflight["errors"]))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(bundle['entry'])} entries; local preflight passed)")


if __name__ == "__main__":
    main()
