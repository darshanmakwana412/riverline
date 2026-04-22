#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
# ]
# ///
import json, sys, pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eval_takehome import AgentEvaluator, HandFeatures
sys.modules['__main__'].HandFeatures = HandFeatures

SAMPLE_IDS = [
  '2c75ead3-6d12-70e0-bb11-cdd543451597',
  'd34fb1b1-9b39-099b-ae48-d1948756c489',
  '032101dc-a78c-9aa9-c8e2-5f92b42f1dfa',
  'eb0ea42b-8ec5-a79e-cac0-c76e2de7d497',
  'c678fac1-392b-4657-8394-ed579b91375e',
  '1a6faadc-3a1f-90ec-51e2-bb041c8f501c',
  'ec6da404-d909-7547-0429-d9f34391b906',
  '7b64728c-cd45-c931-2c2d-f44c2a1350f2',
  'e397d8ee-63e0-aa38-db48-cdadfe54f76a',
  '71db359c-39df-11a3-eb6e-4c65e6f3a8f3'
]

convs = {}
with open('data/production_logs.jsonl') as f:
    for line in f:
        c = json.loads(line)
        if c['conversation_id'] in SAMPLE_IDS:
            convs[c['conversation_id']] = c

ev = AgentEvaluator()
results = {}
for cid in SAMPLE_IDS:
    c = convs[cid]
    r = ev.evaluate(c)
    results[cid] = r

with open('/tmp/eval_sample_results.json', 'w') as f:
    json.dump(results, f, indent=2)

with open('/tmp/eval_sample_convs.json', 'w') as f:
    json.dump(convs, f, indent=2)

print("Done. Results written to /tmp/eval_sample_results.json")
for cid in SAMPLE_IDS:
    r = results[cid]
    print(f'{cid[:16]}: q={r["quality_score"]:.3f} risk={r["risk_score"]:.3f} viols={len(r["violations"])} {r["summary"]}')
