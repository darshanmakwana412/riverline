#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
# ]
# ///
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval_takehome import AgentEvaluator


def main(out_path: str = "violations.jsonl", data_path: str = "data/production_logs.jsonl"):
    evaluator = AgentEvaluator()
    convs = [json.loads(l) for l in open(ROOT / data_path) if l.strip()]
    outcomes = {}
    op = ROOT / "data/outcomes.jsonl"
    if op.exists():
        for l in open(op):
            if l.strip():
                o = json.loads(l)
                outcomes[o["conversation_id"]] = o

    with open(ROOT / out_path, "w") as f:
        for c in convs:
            r = evaluator.evaluate(c)
            f.write(json.dumps({
                "conversation_id": c["conversation_id"],
                "metadata": c.get("metadata", {}),
                "outcome": outcomes.get(c["conversation_id"]),
                "quality_score": r["quality_score"],
                "risk_score": r["risk_score"],
                "violations": r["violations"],
            }) + "\n")
    print(f"wrote {len(convs)} rows to {out_path}")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
