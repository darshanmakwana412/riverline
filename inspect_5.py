#!/usr/bin/env -S uv run --with scikit-learn --with numpy --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["scikit-learn>=1.4", "numpy>=1.26"]
# ///
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eval_takehome import AgentEvaluator

evaluator = AgentEvaluator()
conversations = [json.loads(l) for l in open("data/production_logs.jsonl") if l.strip()]
eval_ids = set(json.load(open("scripts/eval_split.json"))["eval_conversation_ids"])
conversations = [c for c in conversations if c["conversation_id"] in eval_ids]

random.seed(7)
sample = random.sample(conversations, 5)

for conv in sample:
    cid = conv["conversation_id"]
    result = evaluator.evaluate(conv)
    meta = conv.get("metadata", {})

    print(f"\n{'='*70}")
    print(f"CONV: {cid}")
    print(f"meta: lang={meta.get('language')} zone={meta.get('zone')} dpd={meta.get('dpd')} pos={meta.get('pos')} tos={meta.get('tos')} floor={meta.get('settlement_floor')} offered={meta.get('settlement_offered')} turns={meta.get('total_turns')}")
    print(f"score: quality={result['quality_score']} risk={result['risk_score']} violations={len(result['violations'])}")

    print("\n--- MESSAGES ---")
    for m in conv.get("messages", []):
        bc = {c["turn"]: c for c in conv.get("bot_classifications", [])}
        cls_info = ""
        if m["role"] == "borrower":
            bc_entry = bc.get(m["turn"])
            cls_info = f" [bot_cls={bc_entry['classification'] if bc_entry else 'NONE'}, conf={bc_entry.get('confidence','?') if bc_entry else '?'}]"
        ts = m.get("timestamp", "")
        print(f"  t{m['turn']:02d} [{m['role'][:3]}]{cls_info} {ts} | {m.get('text','')[:120]}")

    print("\n--- STATE TRANSITIONS ---")
    for tr in conv.get("state_transitions", []):
        print(f"  t{tr['turn']:02d} {tr['from_state']:25s} -> {tr['to_state']:25s} reason={tr.get('reason','')}")

    print("\n--- FUNCTION CALLS ---")
    for fc in conv.get("function_calls", []):
        print(f"  t{fc['turn']:02d} {fc['function']} params={fc.get('params',{})}")

    print("\n--- VIOLATIONS ---")
    for v in sorted(result["violations"], key=lambda x: x["turn"]):
        print(f"  t{v['turn']:02d} [{v['rule']}] sev={v['severity']} | {v['explanation'][:120]}")
