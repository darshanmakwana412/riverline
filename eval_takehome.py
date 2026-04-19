"""
Riverline Evals Take-Home Assignment
=====================================

AgentEvaluator. Self-contained: loads a pre-trained borrower-intent classifier
from scripts/classifier_model.pkl (trained by scripts/train_classifier.py).
Conversation-level 70/30 split used for training; held-out conversation ids
are stored in scripts/eval_split.json to prevent leakage in downstream work.

Checks performed per conversation:
  Q2  classifier vs. bot classification disagreement
  I1  state transition in spec matrix (§3, Table 1) — incl. backward-exception
  I2  exit states final (escalated/dormant) and no bot messages after entry
  I3  state_transitions chain coherence (one state at a time)
  I4  function_calls must happen during the correct transition
  I5  every borrower message has a classification
"""

import json
import pickle
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


TIME_WORDS = r"\b(tomorrow|today|tonight|yesterday|week|weeks|day|days|month|months|friday|monday|tuesday|wednesday|thursday|saturday|sunday|hour|hours|minute|minutes|kal|aaj|parso|abhi|baad|raat|subah|shaam|din|hafte|hafta|mahina|mahine|salary|paisa|vetan|tankhwah|time|saal|jald)\b"
REFUSE_WORDS = r"\b(not pay|won'?t pay|no way|refuse|stop|leave me|lawyer|legal|court|police|never|cannot pay|can'?t pay|nahi dunga|nahi doongi|nahi doonga|mat karo|band karo|lawyer se|vakeel)\b"
DISPUTE_WORDS = r"\b(don'?t owe|not my|wrong|incorrect|already paid|dispute|mistake|fraud|scam|verify|verification|ye amount|galat)\b"
HARDSHIP_WORDS = r"\b(lost my job|no job|no income|medical|hospital|emergency|death|family|sick|illness|cancer|accident|jobless|naukri chali|job chal|job chali|bimari|beemar|hospital mein|father|mother|wife|husband|beta|beti)\b"
SETTLE_WORDS = r"\b(settle|settlement|reduce|reduced|lower|lesser|kam amount|kam karo|discount|waiver)\b"
CLOSURE_WORDS = r"\b(full amount|full payment|close|closure|foreclose|foreclosure|complete payment|pura|poora|entire)\b"


class HandFeatures(BaseEstimator, TransformerMixin):
    patterns = {
        "time": re.compile(TIME_WORDS, re.I),
        "refuse": re.compile(REFUSE_WORDS, re.I),
        "dispute": re.compile(DISPUTE_WORDS, re.I),
        "hardship": re.compile(HARDSHIP_WORDS, re.I),
        "settle": re.compile(SETTLE_WORDS, re.I),
        "closure": re.compile(CLOSURE_WORDS, re.I),
    }
    digit_re = re.compile(r"\d")
    date_re = re.compile(r"\b\d{1,2}\s*(day|days|week|weeks|month|months|din|hafta|hafte|mahina|mahine)\b", re.I)
    emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for t in X:
            f = [
                len(t), len(t.split()),
                int(bool(self.digit_re.search(t))),
                int(bool(self.date_re.search(t))),
                len(self.emoji_re.findall(t)),
                int("?" in t), int("!" in t),
                int(bool(re.search(r"\bplease\b|\bplz\b|🙏", t, re.I))),
            ]
            for _, pat in self.patterns.items():
                f.append(len(pat.findall(t)))
            rows.append(f)
        return np.asarray(rows, dtype=np.float32)


MODEL_PATH = Path(__file__).parent / "scripts" / "classifier_model.pkl"


PROGRESSION = [
    "new", "message_received", "verification", "intent_asked",
    "settlement_explained", "amount_pending", "amount_sent",
    "date_amount_asked", "payment_confirmed",
]
PROG_SET = set(PROGRESSION)
EXIT = {"escalated", "dormant"}

QUIET_START_HOUR = 19
QUIET_END_HOUR = 8
MIN_SPACING_SEC = 4 * 3600

_HAPPY_PATH = [
    ("new", "message_received"),
    ("message_received", "verification"),
    ("verification", "intent_asked"),
    ("intent_asked", "settlement_explained"),
    ("settlement_explained", "amount_pending"),
    ("amount_pending", "amount_sent"),
    ("amount_sent", "date_amount_asked"),
    ("date_amount_asked", "payment_confirmed"),
]
ALLOWED_EDGES = set(_HAPPY_PATH)
for _s in PROGRESSION:
    ALLOWED_EDGES |= {(_s, "escalated"), (_s, "dormant"), (_s, "payment_confirmed")}
ALLOWED_EDGES.discard(("payment_confirmed", "payment_confirmed"))

BACKWARD_EXCEPTIONS = {
    ("settlement_explained", "intent_asked"),
    ("amount_pending", "intent_asked"),
}

ACTION_TRANSITIONS = {
    "request_settlement_amount": ("settlement_explained", "amount_pending"),
    "send_settlement_amount": ("amount_pending", "amount_sent"),
    "confirm_payment": ("date_amount_asked", "payment_confirmed"),
    "zcm_timeout": ("amount_pending", "escalated"),
}


def load_classifier(path: Path = MODEL_PATH):
    sys.modules["__main__"].HandFeatures = HandFeatures
    with open(path, "rb") as f:
        bundle = pickle.load(f)
    return bundle["pipeline"], bundle["labels"]


def classify_borrower_messages(pipeline, labels, messages):
    borrower = [(m["turn"], m["text"]) for m in messages if m["role"] == "borrower" and m.get("text")]
    if not borrower:
        return []
    texts = [t for _, t in borrower]
    preds = pipeline.predict(texts)
    if hasattr(pipeline, "predict_proba"):
        probs = pipeline.predict_proba(texts)
        confs = probs.max(axis=1)
    else:
        confs = np.ones(len(texts))
    return [(turn, text, str(p), float(c)) for (turn, text), p, c in zip(borrower, preds, confs)]


class AgentEvaluator:
    """Evaluate WhatsApp debt collection conversations against the agent spec."""

    def __init__(self):
        self.pipeline, self.labels = load_classifier()

    def evaluate(self, conversation: dict) -> dict:
        messages = conversation.get("messages", [])
        bot_cls_list = conversation.get("bot_classifications", [])
        bot_cls = {c["turn"]: c for c in bot_cls_list}
        transitions = conversation.get("state_transitions", [])
        function_calls = conversation.get("function_calls", [])

        preds = classify_borrower_messages(self.pipeline, self.labels, messages)
        preds_by_turn = {t: (p, c) for t, _, p, c in preds}

        violations = []
        violations += self._check_q2(preds, bot_cls)
        violations += self._check_transitions(transitions, preds_by_turn, bot_cls)
        violations += self._check_chain_coherence(transitions)
        violations += self._check_actions(function_calls, transitions)
        violations += self._check_post_exit_messages(messages, transitions)
        violations += self._check_all_classified(messages, bot_cls)
        violations += self._check_timing(messages, transitions)

        summary = Counter(v["rule"].split("_", 1)[0] for v in violations)
        total_turns = max(1, conversation.get("metadata", {}).get("total_turns", len(messages)))
        weighted = sum(v["severity"] for v in violations)
        quality_score = max(0.0, 1.0 - weighted / total_turns)
        avg_sev = weighted / len(violations) if violations else 0.0
        risk_score = min(1.0, 0.5 * (len(violations) / total_turns) + 0.5 * avg_sev)

        return {
            "quality_score": round(quality_score, 4),
            "risk_score": round(risk_score, 4),
            "violations": violations,
            "summary": dict(summary),
        }

    def _check_q2(self, preds, bot_cls):
        out = []
        for turn, text, pred_cls, conf in preds:
            bot = bot_cls.get(turn)
            if not bot or bot["classification"] == pred_cls:
                continue
            severity = min(1.0, 0.3 + 0.7 * conf)
            if pred_cls in ("hardship", "refuses", "disputes") and bot["classification"] == "unclear":
                severity = max(severity, 0.8)
            out.append({
                "turn": int(turn),
                "rule": "Q2_accurate_classification",
                "severity": round(severity, 3),
                "explanation": f"bot labeled '{bot['classification']}' (conf={bot.get('confidence')}) "
                               f"but classifier predicts '{pred_cls}' (conf={conf:.2f}) for: {text!r}",
            })
        return out

    def _check_transitions(self, transitions, preds_by_turn, bot_cls):
        out = []
        for tr in transitions:
            frm, to, turn = tr["from_state"], tr["to_state"], tr["turn"]
            if frm == to:
                continue
            if frm in EXIT:
                out.append({
                    "turn": int(turn),
                    "rule": "I2_exit_state_not_final",
                    "severity": 1.0,
                    "explanation": f"transition out of exit state '{frm}' → '{to}' (reason={tr.get('reason')!r})",
                })
                continue
            if (frm, to) in ALLOWED_EDGES:
                continue
            if (frm, to) in BACKWARD_EXCEPTIONS:
                pred = preds_by_turn.get(turn) or preds_by_turn.get(turn - 1)
                bot = bot_cls.get(turn) or bot_cls.get(turn - 1)
                intent_ok = pred and pred[0] == "unclear"
                conf_ok = bot and bot.get("confidence") == "low"
                if intent_ok and conf_ok:
                    continue
                out.append({
                    "turn": int(turn),
                    "rule": "I1_backward_exception_unmet",
                    "severity": 0.9,
                    "explanation": f"backward '{frm}' → '{to}' requires borrower intent=unclear+confidence=low; "
                                   f"got pred={pred}, bot={bot and (bot['classification'], bot.get('confidence'))}",
                })
                continue
            if to in PROG_SET and frm in PROG_SET and PROGRESSION.index(to) < PROGRESSION.index(frm):
                sev, rule = 0.9, "I1_backward_transition"
            elif to in PROG_SET and frm in PROG_SET and PROGRESSION.index(to) > PROGRESSION.index(frm) + 1:
                sev, rule = 0.8, "I1_skip_forward"
            else:
                sev, rule = 0.8, "I1_invalid_transition"
            out.append({
                "turn": int(turn),
                "rule": rule,
                "severity": sev,
                "explanation": f"'{frm}' → '{to}' not in spec matrix (reason={tr.get('reason')!r})",
            })
        return out

    def _check_chain_coherence(self, transitions):
        out = []
        if not transitions:
            return out
        ordered = sorted(transitions, key=lambda t: (t["turn"], 0))
        if ordered[0]["from_state"] != "new":
            out.append({
                "turn": int(ordered[0]["turn"]),
                "rule": "I3_chain_does_not_start_at_new",
                "severity": 0.9,
                "explanation": f"first transition starts at '{ordered[0]['from_state']}', expected 'new'",
            })
        for prev, cur in zip(ordered, ordered[1:]):
            if prev["to_state"] != cur["from_state"]:
                out.append({
                    "turn": int(cur["turn"]),
                    "rule": "I3_state_discontinuity",
                    "severity": 0.9,
                    "explanation": f"previous to_state='{prev['to_state']}' but next from_state='{cur['from_state']}'",
                })
        return out

    def _check_actions(self, function_calls, transitions):
        out = []
        trans_by_turn = {}
        for tr in transitions:
            trans_by_turn.setdefault(tr["turn"], []).append((tr["from_state"], tr["to_state"]))
        for fc in function_calls:
            fn, turn = fc["function"], fc["turn"]
            edges = trans_by_turn.get(turn, [])
            if fn == "escalate":
                if not any(to == "escalated" for _, to in edges):
                    out.append({
                        "turn": int(turn),
                        "rule": "I4_action_state_mismatch",
                        "severity": 0.9,
                        "explanation": f"function 'escalate' did not produce a transition to 'escalated' at turn {turn}",
                    })
                continue
            expected = ACTION_TRANSITIONS.get(fn)
            if expected is None:
                continue
            if expected not in edges:
                out.append({
                    "turn": int(turn),
                    "rule": "I4_action_state_mismatch",
                    "severity": 0.9,
                    "explanation": f"function '{fn}' requires transition {expected} at turn {turn}; got {edges or 'none'}",
                })
        return out

    def _check_post_exit_messages(self, messages, transitions):
        out = []
        exit_turn = None
        for tr in sorted(transitions, key=lambda t: t["turn"]):
            if tr["to_state"] in EXIT and tr["from_state"] not in EXIT:
                exit_turn = tr["turn"]
                break
        if exit_turn is None:
            return out
        for m in messages:
            if m["role"] == "bot" and m["turn"] > exit_turn:
                out.append({
                    "turn": int(m["turn"]),
                    "rule": "I2_message_after_exit",
                    "severity": 1.0,
                    "explanation": f"bot message at turn {m['turn']} after conversation entered exit state at turn {exit_turn}",
                })
        return out

    def _check_timing(self, messages, transitions):
        out = []
        exit_turn = None
        for tr in sorted(transitions, key=lambda t: t["turn"]):
            if tr["to_state"] in EXIT and tr["from_state"] not in EXIT:
                exit_turn = tr["turn"]
                break

        ordered = sorted(
            [m for m in messages if m.get("timestamp")],
            key=lambda m: (m["turn"], 0 if m["role"] == "borrower" else 1),
        )
        last_bot_ts = None
        last_borrower_ts = None
        prev_msg = None
        for m in ordered:
            if exit_turn is not None and m["turn"] > exit_turn:
                break
            ts = datetime.fromisoformat(m["timestamp"])
            if m["role"] == "bot":
                in_quiet = ts.hour >= QUIET_START_HOUR or ts.hour < QUIET_END_HOUR
                prev_in_quiet = False
                if prev_msg and prev_msg["role"] == "borrower":
                    pts = datetime.fromisoformat(prev_msg["timestamp"])
                    prev_in_quiet = pts.hour >= QUIET_START_HOUR or pts.hour < QUIET_END_HOUR
                if in_quiet and not prev_in_quiet:
                    out.append({
                        "turn": int(m["turn"]),
                        "rule": "T1_quiet_hours_outbound",
                        "severity": 0.8,
                        "explanation": f"outbound bot message at {ts.isoformat()} falls in quiet hours "
                                       f"(19:00–08:00 IST) without a borrower message initiating contact",
                    })
                if last_bot_ts is not None and (last_borrower_ts is None or last_borrower_ts <= last_bot_ts):
                    gap = (ts - last_bot_ts).total_seconds()
                    if gap < MIN_SPACING_SEC:
                        sev = round(min(0.8, max(0.5, 0.5 + 0.3 * (1 - gap / MIN_SPACING_SEC))), 3)
                        out.append({
                            "turn": int(m["turn"]),
                            "rule": "T2_follow_up_too_fast",
                            "severity": sev,
                            "explanation": f"bot follow-up {gap/60:.1f} min after previous bot message "
                                           f"with no borrower reply in between (min 240 min required)",
                        })
                last_bot_ts = ts
            else:
                last_borrower_ts = ts
            prev_msg = m
        return out

    def _check_all_classified(self, messages, bot_cls):
        out = []
        for m in messages:
            if m["role"] != "borrower" or not m.get("text"):
                continue
            if m["turn"] not in bot_cls:
                out.append({
                    "turn": int(m["turn"]),
                    "rule": "I5_missing_classification",
                    "severity": 0.5,
                    "explanation": f"borrower message at turn {m['turn']} has no bot_classifications entry",
                })
        return out


def main():
    evaluator = AgentEvaluator()

    data_path = Path("data/production_logs.jsonl")
    split_path = Path("scripts/eval_split.json")
    if not data_path.exists():
        print("No data found. Make sure data/production_logs.jsonl exists.")
        return

    conversations = [json.loads(l) for l in open(data_path) if l.strip()]
    eval_ids = None
    if split_path.exists():
        eval_ids = set(json.load(open(split_path))["eval_conversation_ids"])
        conversations = [c for c in conversations if c["conversation_id"] in eval_ids]
        print(f"Using held-out eval split: {len(conversations)} conversations (leak-free).")
    else:
        conversations = conversations[:10]
        print(f"No split file; evaluating first {len(conversations)} conversations.")

    results = []
    rule_totals = Counter()
    for conv in conversations:
        r = evaluator.evaluate(conv)
        results.append((conv["conversation_id"], r))
        for rule, n in r["summary"].items():
            rule_totals[rule] += n

    total_v = sum(len(r[1]["violations"]) for r in results)
    avg_q = sum(r[1]["quality_score"] for r in results) / len(results)
    avg_r = sum(r[1]["risk_score"] for r in results) / len(results)
    print(f"\nEvaluated {len(results)} conversations.")
    print(f"  avg quality_score: {avg_q:.3f}")
    print(f"  avg risk_score:    {avg_r:.3f}")
    print(f"  total violations:  {total_v}")
    print(f"  per-rule totals:   {dict(rule_totals)}")
    for cid, r in results[:5]:
        print(f"  {cid}: q={r['quality_score']:.2f} risk={r['risk_score']:.2f} "
              f"viols={len(r['violations'])} summary={r['summary']}")


if __name__ == "__main__":
    main()
