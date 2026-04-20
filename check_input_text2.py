#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
import json
from difflib import SequenceMatcher

conversations = [json.loads(l) for l in open("data/production_logs.jsonl") if l.strip()]

total_mismatch = 0
cross_turn = 0        # input_text matches a DIFFERENT turn in same conv
cross_conv = 0        # input_text matches no turn in this conv at all
input_shorter = 0     # input_text is shorter (possible truncation/paraphrase)
input_longer = 0
same_length_diff = 0

# build a global index of all borrower texts → (conv_id, turn)
all_texts = {}
for conv in conversations:
    for m in conv.get("messages", []):
        if m["role"] == "borrower" and m.get("text"):
            all_texts[m["text"].strip()] = (conv["conversation_id"], m["turn"])

similarity_buckets = {">=0.9": 0, "0.7-0.9": 0, "0.5-0.7": 0, "<0.5": 0}
wrong_turn_examples = []
no_match_examples = []

for conv in conversations:
    cid = conv["conversation_id"]
    msg_by_turn = {m["turn"]: m["text"] for m in conv.get("messages", [])
                   if m["role"] == "borrower" and m.get("text")}

    for bc in conv.get("bot_classifications", []):
        turn = bc["turn"]
        input_text = (bc.get("input_text") or "").strip()
        actual = (msg_by_turn.get(turn) or "").strip()

        if input_text == actual:
            continue
        total_mismatch += 1

        ratio = SequenceMatcher(None, input_text, actual).ratio()
        if ratio >= 0.9:
            similarity_buckets[">=0.9"] += 1
        elif ratio >= 0.7:
            similarity_buckets["0.7-0.9"] += 1
        elif ratio >= 0.5:
            similarity_buckets["0.5-0.7"] += 1
        else:
            similarity_buckets["<0.5"] += 1

        if len(input_text) < len(actual):
            input_shorter += 1
        elif len(input_text) > len(actual):
            input_longer += 1
        else:
            same_length_diff += 1

        # check if input_text matches some OTHER turn in this conv
        matched_turn = None
        for t, txt in msg_by_turn.items():
            if txt.strip() == input_text:
                matched_turn = t
                break
        if matched_turn is not None and matched_turn != turn:
            cross_turn += 1
            if len(wrong_turn_examples) < 3:
                wrong_turn_examples.append({
                    "conv": cid, "bc_turn": turn, "matched_turn": matched_turn,
                    "input_text": input_text, "actual": actual,
                    "cls": bc["classification"]
                })
        elif matched_turn is None:
            # check if it matches ANY conv
            if input_text not in all_texts:
                cross_conv += 1
                if len(no_match_examples) < 5:
                    no_match_examples.append({
                        "conv": cid, "turn": turn, "input_text": input_text,
                        "actual": actual, "cls": bc["classification"],
                        "sim": round(ratio, 2)
                    })

print(f"Total mismatches: {total_mismatch}")
print(f"  input_text shorter than actual: {input_shorter} ({100*input_shorter//total_mismatch}%)")
print(f"  input_text longer than actual:  {input_longer} ({100*input_longer//total_mismatch}%)")
print(f"  same length, different content: {same_length_diff}")
print()
print("Similarity distribution:")
for k, v in similarity_buckets.items():
    print(f"  {k}: {v} ({100*v//total_mismatch}%)")
print()
print(f"input_text exactly matches a DIFFERENT turn in same conv: {cross_turn}")
print(f"input_text matches NO borrower message anywhere:          {cross_conv}")
print()

if wrong_turn_examples:
    print("=== Wrong-turn examples ===")
    for e in wrong_turn_examples:
        print(f"  conv={e['conv']} bc_turn={e['bc_turn']} matched_turn={e['matched_turn']} cls={e['cls']}")
        print(f"    input_text: {e['input_text'][:100]!r}")
        print(f"    actual:     {e['actual'][:100]!r}")
        print()

if no_match_examples:
    print("=== No-match examples (input_text not found anywhere) ===")
    for e in no_match_examples:
        print(f"  conv={e['conv']} turn={e['turn']} cls={e['cls']} sim={e['sim']}")
        print(f"    input_text: {e['input_text'][:120]!r}")
        print(f"    actual:     {e['actual'][:120]!r}")
        print()
