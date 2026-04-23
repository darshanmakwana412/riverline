#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["fire>=0.7.1"]
# ///
import json, sys
from pathlib import Path

def main(cid_prefix: str):
    p = Path(__file__).parent.parent / "docs/validations/_audit_30_seed2026.json"
    data = json.loads(p.read_text())
    for x in data:
        if not x["conversation_id"].startswith(cid_prefix):
            continue
        m = x["metadata"]
        print(f"=== {x['conversation_id']} ===")
        print(f"lang={m.get('language')} dpd={m.get('dpd')} pos={m.get('pos')} tos={m.get('tos')} floor={m.get('settlement_offered')} temp={m.get('temperament')}")
        print(f"q={x['quality_score']} r={x['risk_score']}")
        print(f"outcome: {json.dumps(x['outcome'], default=str)}")
        print(f"\n--- MESSAGES ---")
        for msg in sorted(x["messages"], key=lambda z: z["turn"]):
            bc = next((c for c in x["bot_classifications"] if c["turn"] == msg["turn"]), None) if msg["role"] == "borrower" else None
            bc_s = f" [{bc['classification']}/{bc.get('confidence','?')}]" if bc else ""
            txt = (msg.get("text") or "")[:200]
            print(f"  t{msg['turn']:2d} [{msg['role'][:3]}] {msg.get('timestamp','')}{bc_s}: {txt}")
        print(f"\n--- TRANSITIONS ---")
        for t in x["transitions"]:
            print(f"  t{t['turn']:2d}: {t['from_state']} → {t['to_state']} ({t.get('reason','')})")
        print(f"\n--- FUNCTION CALLS ---")
        for fc in x["function_calls"]:
            print(f"  t{fc['turn']:2d}: {fc['function']} {json.dumps(fc.get('params',{}),default=str)}")
        print(f"\n--- VIOLATIONS ({len(x['violations'])}) ---")
        for v in x["violations"]:
            print(f"  t{v['turn']:3d} [{v['severity']:.2f}] {v['rule']}: {v['explanation'][:250]}")
        print(f"\n--- ANNOTATIONS ---")
        for k, a in x["annotations"].items():
            print(f"  [{k}] q={a.get('quality_score')} flags={a.get('risk_flags')} assess={a.get('overall_assessment','')[:120]}")
            for fp in a.get("failure_points", []):
                print(f"    t{fp.get('turn')} [{fp.get('severity')}] {fp.get('category')}: {fp.get('note','')[:180]}")
        print()

if __name__ == "__main__":
    import fire
    fire.Fire(main)
