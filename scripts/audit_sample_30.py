#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["scikit-learn>=1.5", "numpy>=2.0", "fire>=0.7.1"]
# ///
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from eval_takehome import AgentEvaluator

def main(seed: int = 2026, n: int = 30):
    root = Path(__file__).parent.parent
    convs = [json.loads(l) for l in open(root / "data/production_logs.jsonl") if l.strip()]
    outcomes = {json.loads(l)["conversation_id"]: json.loads(l) for l in open(root / "data/outcomes.jsonl") if l.strip()}
    annotations = {}
    for i in (1, 2, 3):
        for line in open(root / f"data/annotations/annotator_{i}.jsonl"):
            if not line.strip(): continue
            a = json.loads(line)
            annotations.setdefault(a["conversation_id"], {})[f"ann{i}"] = a

    random.seed(seed)
    sample = random.sample(convs, n)

    ev = AgentEvaluator()
    out = []
    for c in sample:
        r = ev.evaluate(c)
        cid = c["conversation_id"]
        out.append({
            "conversation_id": cid,
            "metadata": c.get("metadata", {}),
            "n_messages": len(c.get("messages", [])),
            "transitions": c.get("state_transitions", []),
            "function_calls": c.get("function_calls", []),
            "bot_classifications": c.get("bot_classifications", []),
            "messages": c.get("messages", []),
            "quality_score": r["quality_score"],
            "risk_score": r["risk_score"],
            "violations": r["violations"],
            "outcome": outcomes.get(cid),
            "annotations": annotations.get(cid, {}),
        })
    (root / "docs/validations/_audit_30_seed2026.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {len(out)} convs; total violations={sum(len(x['violations']) for x in out)}")
    print(f"Annotated: {sum(1 for x in out if x['annotations'])}")

if __name__ == "__main__":
    import fire
    fire.Fire(main)
