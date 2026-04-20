#!/usr/bin/env -S uv run --with scikit-learn --with numpy --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
import json
from pathlib import Path
from collections import defaultdict

conversations = [json.loads(l) for l in open("data/production_logs.jsonl") if l.strip()]

total_cls = 0
missing_input_text = 0
turn_not_found = 0
text_mismatch = 0
no_borrower_msg = 0

mismatch_examples = []
missing_examples = []

for conv in conversations:
    cid = conv["conversation_id"]
    msg_by_turn = {}
    for m in conv.get("messages", []):
        if m["role"] == "borrower" and m.get("text"):
            msg_by_turn[m["turn"]] = m["text"]

    for bc in conv.get("bot_classifications", []):
        total_cls += 1
        turn = bc["turn"]
        input_text = bc.get("input_text")

        if input_text is None:
            missing_input_text += 1
            if len(missing_examples) < 3:
                missing_examples.append({"conv": cid, "turn": turn, "bc": bc})
            continue

        actual = msg_by_turn.get(turn)
        if actual is None:
            no_borrower_msg += 1
            continue

        if input_text.strip() != actual.strip():
            text_mismatch += 1
            if len(mismatch_examples) < 10:
                mismatch_examples.append({
                    "conv": cid,
                    "turn": turn,
                    "input_text": input_text,
                    "actual_text": actual,
                    "classification": bc["classification"],
                    "confidence": bc["confidence"],
                })

print(f"Total bot_classifications: {total_cls}")
print(f"Missing input_text field:  {missing_input_text}")
print(f"Turn has no borrower msg:  {no_borrower_msg}")
print(f"input_text != actual text: {text_mismatch}")
print()

if missing_examples:
    print("=== Missing input_text examples ===")
    for e in missing_examples:
        print(f"  conv={e['conv']} turn={e['turn']} bc={e['bc']}")
    print()

if mismatch_examples:
    print(f"=== Text mismatch examples (first {len(mismatch_examples)}) ===")
    for e in mismatch_examples:
        print(f"  conv={e['conv']} turn={e['turn']} cls={e['classification']}({e['confidence']})")
        print(f"    input_text : {e['input_text'][:120]!r}")
        print(f"    actual_text: {e['actual_text'][:120]!r}")
        print()
