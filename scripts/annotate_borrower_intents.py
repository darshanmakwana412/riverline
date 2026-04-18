#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fire>=0.7.1",
#     "anthropic>=0.40.0",
# ]
# ///
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["unclear", "wants_settlement", "wants_closure", "refuses", "disputes", "hardship", "asks_time"]
MODEL = "claude-sonnet-4-6"
PRICE = {"input": 3.0, "cache_write_5m": 3.75, "cache_write_1h": 6.0, "cache_read": 0.30, "output": 15.0}

SYSTEM = """You are a ground-truth annotator for a WhatsApp debt collection agent.
For every borrower message in the given conversation, classify the borrower's intent into EXACTLY one of:
  {classes}
Also assign a confidence: high, medium, or low.

Use the attached specification, README, and domain brief as the authoritative definition of each class.
You are given ONLY the raw conversation and account metadata. You are NOT given the bot's own classifications or
state transitions - do not ask for them and do not try to infer them. Base your decision purely on what the borrower
actually said in context.

Return a single JSON object (no prose, no markdown fences) of the form:
{{
  "annotations": [
    {{"turn": <int>, "text": "<borrower text>", "classification": "<one of the classes>", "confidence": "high|medium|low", "reasoning": "<one short sentence>"}},
    ...
  ]
}}
Include one entry per borrower message, in order.""".format(classes=", ".join(CLASSES))


def load_context():
    return (ROOT / "spec.tex").read_text(), (ROOT / "README.md").read_text(), (ROOT / "docs" / "domain.md").read_text()


def build_user_message(conv):
    meta = conv.get("metadata", {})
    msgs = [{"turn": m["turn"], "role": m["role"], "text": m["text"], "timestamp": m["timestamp"]} for m in conv["messages"]]
    return (
        f"Conversation ID: {conv['conversation_id']}\n\n"
        f"Metadata:\n{json.dumps(meta, indent=2)}\n\n"
        f"Messages (bot and borrower turns, in order):\n{json.dumps(msgs, indent=2, ensure_ascii=False)}\n\n"
        "Classify every borrower message. Output JSON only."
    )


def usage_to_dict(u):
    cw_details = getattr(u, "cache_creation", None)
    cw_5m = getattr(cw_details, "ephemeral_5m_input_tokens", None) if cw_details else None
    cw_1h = getattr(cw_details, "ephemeral_1h_input_tokens", None) if cw_details else None
    cw_total = getattr(u, "cache_creation_input_tokens", 0) or 0
    if cw_5m is None and cw_1h is None:
        cw_5m, cw_1h = cw_total, 0
    return {
        "input": getattr(u, "input_tokens", 0) or 0,
        "output": getattr(u, "output_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write_5m": cw_5m or 0,
        "cache_write_1h": cw_1h or 0,
    }


def cost_usd(t):
    return (t["input"] * PRICE["input"] + t["output"] * PRICE["output"]
            + t["cache_write_5m"] * PRICE["cache_write_5m"]
            + t["cache_write_1h"] * PRICE["cache_write_1h"]
            + t["cache_read"] * PRICE["cache_read"]) / 1_000_000


def annotate(conv, client, spec, readme, domain):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": f"=== SPECIFICATION (spec.tex) ===\n{spec}"},
            {"type": "text", "text": f"=== README.md ===\n{readme}\n\n=== docs/domain.md ===\n{domain}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": build_user_message(conv)}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    tokens = usage_to_dict(resp.usage)
    return json.loads(text), tokens


def render_comparison(conv, sonnet_ann):
    bot_by_turn = {c["turn"]: c for c in conv.get("bot_classifications", [])}
    son_by_turn = {a["turn"]: a for a in sonnet_ann["annotations"]}
    lines = [f"\n{'='*100}\nConversation: {conv['conversation_id']}\n{'='*100}"]
    for m in conv["messages"]:
        if m["role"] != "borrower":
            continue
        t = m["turn"]
        bot = bot_by_turn.get(t, {})
        son = son_by_turn.get(t, {})
        lines.append(f"\nturn {t}: {m['text']}")
        lines.append(f"  bot    : {bot.get('classification','-'):<18} ({bot.get('confidence','-')})")
        lines.append(f"  sonnet : {son.get('classification','-'):<18} ({son.get('confidence','-')})  -- {son.get('reasoning','')}")
        if bot.get("classification") != son.get("classification"):
            lines.append(f"  *** DISAGREE ***")
    return "\n".join(lines)


def main(n: int = 3, seed: int = 42, parallel: int = 1, out: str = "scripts/annotations_sample.json"):
    random.seed(seed)
    spec, readme, domain = load_context()
    convs = [json.loads(l) for l in (ROOT / "data" / "production_logs.jsonl").read_text().splitlines() if l.strip()]
    picked = random.sample(convs, n)
    client = Anthropic()
    results = [None] * len(picked)
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}
    per_req = []

    def worker(idx, conv):
        t0 = time.time()
        ann, tokens = annotate(conv, client, spec, readme, domain)
        return idx, conv, ann, tokens, time.time() - t0

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(worker, i, c) for i, c in enumerate(picked)]
        for fut in as_completed(futures):
            idx, conv, ann, tokens, dt = fut.result()
            for k in totals:
                totals[k] += tokens[k]
            req_cost = cost_usd(tokens)
            per_req.append({"conversation_id": conv["conversation_id"], "tokens": tokens, "usd": req_cost, "seconds": dt})
            print(f"[{idx+1}/{len(picked)}] {conv['conversation_id']} ({dt:.1f}s) "
                  f"in={tokens['input']} out={tokens['output']} "
                  f"cr={tokens['cache_read']} cw5m={tokens['cache_write_5m']} "
                  f"cw1h={tokens['cache_write_1h']} ${req_cost:.4f}", flush=True)
            results[idx] = {"conversation_id": conv["conversation_id"], "sonnet": ann, "bot": conv.get("bot_classifications", []), "tokens": tokens, "usd": req_cost}
    wall = time.time() - t_start
    for conv, r in zip(picked, results):
        print(render_comparison(conv, r["sonnet"]))

    total_cost = cost_usd(totals)
    print(f"\n{'='*100}\nUSAGE SUMMARY ({MODEL}, {len(picked)} requests, parallel={parallel}, wall={wall:.1f}s)\n{'='*100}")
    print(f"  input tokens         : {totals['input']:>10,}  @ ${PRICE['input']}/MTok  = ${totals['input']*PRICE['input']/1e6:.6f}")
    print(f"  output tokens        : {totals['output']:>10,}  @ ${PRICE['output']}/MTok = ${totals['output']*PRICE['output']/1e6:.6f}")
    print(f"  cache read tokens    : {totals['cache_read']:>10,}  @ ${PRICE['cache_read']}/MTok  = ${totals['cache_read']*PRICE['cache_read']/1e6:.6f}")
    print(f"  cache write 5m tokens: {totals['cache_write_5m']:>10,}  @ ${PRICE['cache_write_5m']}/MTok = ${totals['cache_write_5m']*PRICE['cache_write_5m']/1e6:.6f}")
    print(f"  cache write 1h tokens: {totals['cache_write_1h']:>10,}  @ ${PRICE['cache_write_1h']}/MTok  = ${totals['cache_write_1h']*PRICE['cache_write_1h']/1e6:.6f}")
    print(f"  TOTAL                : ${total_cost:.6f}  (avg ${total_cost/len(picked):.6f}/conv)")

    (ROOT / out).write_text(json.dumps({"model": MODEL, "totals": totals, "total_usd": total_cost, "per_request": per_req, "results": results}, indent=2, ensure_ascii=False))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
