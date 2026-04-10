from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seller_client_app.bootstrap.phase1 import build_phase1_plan
from seller_client_app.contracts.phase1 import JoinMaterialEnvelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Seller_Client phase-1 bootstrap plan as JSON.")
    parser.add_argument(
        "input_path",
        nargs="?",
        default=Path(__file__).with_name("phase1-bootstrap-input.example.json"),
        help="Path to a JSON file shaped like JoinMaterialEnvelope.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    join_input = JoinMaterialEnvelope.from_dict(payload)
    plan = build_phase1_plan(join_input)
    print(plan.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
