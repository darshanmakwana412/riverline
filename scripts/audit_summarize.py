#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# ///
import json
from pathlib import Path
from collections import Counter

p = Path(__file__).parent.parent / "docs/validations/_audit_30_seed2026.json"
data = json.loads(p.read_text())
rule_counts = Counter()
for x in data:
    for v in x["violations"]:
        rule_counts[v["rule"]] += 1
print("=== RULE COUNTS ===")
for r, c in sorted(rule_counts.items(), key=lambda x: -x[1]):
    print(f"  {r}: {c}")
print(f"\n=== CONVERSATIONS ({len(data)}) ===")
for x in data:
    m = x["metadata"]
    o = x["outcome"] or {}
    n_ann = len(x["annotations"])
    print(f"{x['conversation_id'][:8]} msgs={x['n_messages']:3d} lang={str(m.get('language','?')):8s} dpd={str(m.get('dpd','?')):>3} pos={str(m.get('pos','?')):>7} tos={str(m.get('tos','?')):>7} fl={str(m.get('settlement_offered','?')):>7} viols={len(x['violations']):2d} q={x['quality_score']:.2f} r={x['risk_score']:.2f} paid={o.get('payment_received','?')} cmpl={o.get('borrower_complained','?')} reg={o.get('regulatory_flag','?')} ann={n_ann}")
