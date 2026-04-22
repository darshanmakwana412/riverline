#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
# ]
# ///
"""
Riverline Evals Take-Home Assignment
=====================================
AgentEvaluator checks:
  Q2  — borrower intent misclassification (ML classifier vs bot label)
  I1  — invalid state transition (not in spec Table 1)
  I2  — exit states not absorbing (transition out of or message after escalated/dormant)
  I3  — chain continuity broken (from_state[i] != to_state[i-1])
  I4  — action/state mismatch (function call at wrong transition, or required call missing)
  I5  — borrower message has no bot_classification entry
  A1  — POS > TOS (data integrity)
  A2  — settlement floor (settlement_offered) > POS
  A3  — send_settlement_amount.amount outside [floor, TOS]
  T0  — bot message has missing or unparseable timestamp (data quality)
  T1  — bot message during quiet hours 19:00–07:59 IST, unless borrower sent during quiet hours
  T2  — follow-up bot message < 4 hours after previous with no borrower reply in between
  T3  — dormant triggered before 7 days of silence (early), or bot messaged after 7 days without going dormant (missed)
  C3  — bot messaged after borrower sent DNC request
  C5  — bot message contains threatening language

Assumptions:
  - zcm_timeout is a bot-acknowledged system event; valid only at amount_pending → escalated
  - send_settlement_amount bypass is an I4 violation (A3 otherwise unenforceable)
  - Backward exception (settlement_explained/amount_pending → intent_asked) uses bot's recorded
    classification, not our classifier's prediction
  - metadata.settlement_offered is treated as the settlement floor (minimum company accepts)
  - Timestamps are naive UTC; converted to IST (+5:30) for timing checks
  - T1 quiet-hour exception applies only when the borrower's message itself was sent during quiet hours
  - Messages without timestamps inherit the last known timestamp (forward-fill by turn order); if no prior timestamp exists the message is skipped for timing checks only
  - Self-transitions are skipped universally
"""

import json
import pickle
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
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


# ── State machine constants ───────────────────────────────────────────────────

PROGRESSION_STATES = {
    "new", "message_received", "verification", "intent_asked",
    "settlement_explained", "amount_pending", "amount_sent",
    "date_amount_asked", "payment_confirmed",
}
EXIT_STATES = {"escalated", "dormant"}

FORWARD_EDGES = {
    ("new", "message_received"),
    ("message_received", "verification"),
    ("verification", "intent_asked"),
    ("intent_asked", "settlement_explained"),
    ("settlement_explained", "amount_pending"),
    ("amount_pending", "amount_sent"),
    ("amount_sent", "date_amount_asked"),
    ("date_amount_asked", "payment_confirmed"),
}

REQUIRED_ACTION = {
    ("settlement_explained", "amount_pending"): "request_settlement_amount",
    ("amount_pending", "amount_sent"): "send_settlement_amount",
    ("date_amount_asked", "payment_confirmed"): "confirm_payment",
}

IST = timezone(timedelta(hours=5, minutes=30))

DNC_RE = re.compile(
    r"\b(stop|do not contact|don'?t contact|leave me alone|block me|unsubscribe|opt.?out|do not call|don'?t call)\b",
    re.I,
)
THREAT_RE = re.compile(
    r"\b(legal action|file a case|file case|court|police|fir|warrant|arrest|property seizure|public shame|shame you|expose you|blacklist|garnish)\b",
    re.I,
)


def _viol(turn, rule, severity, explanation):
    return {"turn": int(turn), "rule": rule, "severity": round(float(severity), 3), "explanation": explanation}


def _index_by_turn(items):
    out = defaultdict(list)
    for item in items:
        out[item["turn"]].append(item)
    return out


def _first_exit_turn(transitions):
    for t in transitions:
        if t["to_state"] in EXIT_STATES:
            return t["turn"]
    return None

BACKWARD_EXCEPTION_ORIGINS = {"settlement_explained", "amount_pending"}
def _is_valid_edge(from_s, to_s, bot_cls_map, turn):
    """Returns (valid: bool, backward_exc_violation: bool)."""
    if (from_s, to_s) in FORWARD_EDGES:
        return True, False
    if from_s in PROGRESSION_STATES and to_s in EXIT_STATES:
        return True, False
    if from_s in PROGRESSION_STATES and to_s == "payment_confirmed":
        return True, False
    if from_s in BACKWARD_EXCEPTION_ORIGINS and to_s == "intent_asked":
        bc = bot_cls_map.get(turn, {})
        if bc.get("classification") == "unclear" and bc.get("confidence") == "low":
            return True, False
        return False, True
    return False, False


# ── Violation checkers ────────────────────────────────────────────────────────

def _check_i5(messages, bot_cls_map):
    return [
        _viol(m["turn"], "I5_missing_classification", 0.5,
              f"borrower message at turn {m['turn']} has no bot_classification entry")
        for m in messages
        if m["role"] == "borrower" and m.get("text") and m["turn"] not in bot_cls_map
    ]


def _check_i3(transitions):
    viols = []
    if not transitions:
        return viols
    if transitions[0]["from_state"] != "new":
        viols.append(_viol(transitions[0]["turn"], "I3_chain_break", 0.9,
                           f"chain starts at '{transitions[0]['from_state']}' not 'new'"))
    for i in range(1, len(transitions)):
        prev_to = transitions[i - 1]["to_state"]
        curr_from = transitions[i]["from_state"]
        if prev_to != curr_from:
            viols.append(_viol(transitions[i]["turn"], "I3_chain_break", 0.9,
                               f"gap: transitions[{i - 1}].to='{prev_to}' but transitions[{i}].from='{curr_from}'"))
    return viols


def _check_i1(transitions, bot_cls_map):
    viols = []
    for t in transitions:
        f, to = t["from_state"], t["to_state"]
        if f == to or f in EXIT_STATES:
            continue
        valid, backward_exc = _is_valid_edge(f, to, bot_cls_map, t["turn"])
        if not valid:
            if backward_exc:
                bc = bot_cls_map.get(t["turn"], {})
                viols.append(_viol(t["turn"], "I1_backward_exception_invalid", 0.9,
                                   f"backward {f}→{to} requires unclear+low; "
                                   f"bot='{bc.get('classification')}' conf='{bc.get('confidence')}'"))
            else:
                sev = 0.8 if f in PROGRESSION_STATES and to in PROGRESSION_STATES else 0.9
                viols.append(_viol(t["turn"], "I1_invalid_transition", sev,
                                   f"transition {f}→{to} not in spec Table 1"))
    return viols


def _check_i2(transitions, messages):
    viols = []
    for t in transitions:
        if t["from_state"] in EXIT_STATES and t["from_state"] != t["to_state"]:
            viols.append(_viol(t["turn"], "I2_exit_not_final", 1.0,
                               f"transition out of exit state: {t['from_state']}→{t['to_state']}"))
    first_exit = _first_exit_turn(transitions)
    if first_exit is not None:
        for m in messages:
            if m["role"] == "bot" and m["turn"] > first_exit:
                viols.append(_viol(m["turn"], "I2_message_after_exit", 1.0,
                                   f"bot message at turn {m['turn']} after exit state entered at turn {first_exit}"))
    return viols


def _check_i4(transitions, function_calls):
    viols = []
    trans_by_turn = _index_by_turn(transitions)
    calls_by_turn = _index_by_turn(function_calls)

    action_edge_check = {
        "send_settlement_amount": lambda f, to: (f, to) == ("amount_pending", "amount_sent"),
        "request_settlement_amount": lambda f, to: (f, to) == ("settlement_explained", "amount_pending"),
        "confirm_payment": lambda f, to: (f, to) == ("date_amount_asked", "payment_confirmed"),
        "escalate": lambda f, to: to == "escalated",
        "zcm_timeout": lambda f, to: (f, to) == ("amount_pending", "escalated"),
    }

    for turn, calls in calls_by_turn.items():
        edges = [(t["from_state"], t["to_state"]) for t in trans_by_turn.get(turn, [])]
        for call in calls:
            fn = call["function"]
            if fn not in action_edge_check:
                continue
            if not any(action_edge_check[fn](f, to) for f, to in edges):
                viols.append(_viol(turn, "I4_action_wrong_state", 0.9,
                                   f"'{fn}' at turn {turn} has no matching required transition (edges={edges})"))

    for turn, trans_list in trans_by_turn.items():
        call_fns = {c["function"] for c in calls_by_turn.get(turn, [])}
        for t in trans_list:
            edge = (t["from_state"], t["to_state"])
            if edge in REQUIRED_ACTION:
                req = REQUIRED_ACTION[edge]
                if req not in call_fns:
                    viols.append(_viol(turn, "I4_required_action_missing", 0.9,
                                       f"{edge[0]}→{edge[1]} at turn {turn} requires '{req}' (not found)"))
            if t["to_state"] == "escalated" and "escalate" not in call_fns and "zcm_timeout" not in call_fns:
                viols.append(_viol(turn, "I4_escalation_missing_call", 0.9,
                                   f"→escalated at turn {turn} has no 'escalate' or 'zcm_timeout' call"))

    return viols


def _check_amounts(conversation):
    viols = []
    meta = conversation.get("metadata", {})
    pos = meta.get("pos")
    tos = meta.get("tos")
    floor_ = meta.get("settlement_offered")

    if pos is not None and tos is not None and pos > tos:
        viols.append(_viol(-1, "A1_pos_exceeds_tos", 0.6, f"POS={pos} > TOS={tos}"))
    if floor_ is not None and pos is not None and floor_ > pos:
        viols.append(_viol(-1, "A2_floor_exceeds_pos", 0.6, f"floor={floor_} > POS={pos}"))
    if floor_ is not None and tos is not None:
        for call in conversation.get("function_calls", []):
            if call["function"] == "send_settlement_amount":
                amt = call.get("params", {}).get("amount")
                if amt is not None and (amt < floor_ or amt > tos):
                    viols.append(_viol(call["turn"], "A3_amount_out_of_bounds", 0.9,
                                       f"settlement amount={amt} not in [floor={floor_}, TOS={tos}]"))
    return viols


def _parse_ts(ts_str):
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def _check_timing(messages):
    viols = []
    last_known_dt = None
    resolved = []
    for m in sorted(messages, key=lambda m: m["turn"]):
        dt = _parse_ts(m.get("timestamp"))
        if dt is None:
            if m["role"] == "bot":
                viols.append(_viol(m["turn"], "T0_missing_timestamp", 0.4,
                                   f"bot message at turn {m['turn']} has no parseable timestamp"))
            dt = last_known_dt
        else:
            last_known_dt = dt
        resolved.append((dt, m))

    last_bot_ts = None
    last_was_borrower = False
    last_borrower_in_quiet = False

    for dt, m in resolved:
        if dt is None:
            if m["role"] == "bot":
                last_was_borrower = False
                last_borrower_in_quiet = False
                last_bot_ts = None
            else:
                last_was_borrower = True
                last_borrower_in_quiet = False
            continue

        ts_ist = dt.astimezone(IST)
        in_quiet = ts_ist.hour >= 19 or ts_ist.hour < 8

        if m["role"] == "bot":
            if in_quiet and not (last_was_borrower and last_borrower_in_quiet):
                viols.append(_viol(m["turn"], "T1_quiet_hours", 0.7,
                                   f"bot message at {ts_ist.strftime('%H:%M')} IST (quiet 19:00–08:00)"))
            if last_bot_ts is not None and not last_was_borrower:
                gap = (dt - last_bot_ts).total_seconds() / 3600
                if gap < 4:
                    viols.append(_viol(m["turn"], "T2_followup_too_soon", 0.5,
                                       f"bot re-messaged after {gap:.1f}h (min 4h required)"))
            last_bot_ts = dt
            last_was_borrower = False
            last_borrower_in_quiet = False
        else:
            last_was_borrower = True
            last_borrower_in_quiet = in_quiet

    return viols


def _check_dormancy(messages, transitions):
    viols = []
    first_dormant = next((t["turn"] for t in transitions if t["to_state"] == "dormant"), None)
    sorted_msgs = sorted(messages, key=lambda m: m["turn"])

    def _borrower_dt_before(turn):
        candidates = [
            (m["turn"], _parse_ts(m.get("timestamp")))
            for m in sorted_msgs
            if m["role"] == "borrower" and m["turn"] < turn
        ]
        candidates = [(t, dt) for t, dt in candidates if dt]
        return max(candidates, key=lambda x: x[0])[1] if candidates else None

    for trans in [t for t in transitions if t["to_state"] == "dormant"]:
        dormant_turn = trans["turn"]
        dormant_dt = next(
            (_parse_ts(m.get("timestamp")) for m in reversed(sorted_msgs)
             if m["turn"] <= dormant_turn and _parse_ts(m.get("timestamp"))),
            None,
        )
        last_borrower_dt = _borrower_dt_before(dormant_turn)
        if dormant_dt and last_borrower_dt:
            gap_days = (dormant_dt - last_borrower_dt).total_seconds() / 86400
            if gap_days < 7:
                viols.append(_viol(dormant_turn, "T3_early_dormancy", 0.7,
                                   f"dormant triggered after only {gap_days:.1f} days of silence (need 7)"))

    last_borrower_dt = None
    gap_flagged = False
    for m in sorted_msgs:
        dt = _parse_ts(m.get("timestamp"))
        if not dt:
            continue
        if m["role"] == "borrower":
            last_borrower_dt = dt
            gap_flagged = False
        elif m["role"] == "bot" and last_borrower_dt and not gap_flagged:
            gap_days = (dt - last_borrower_dt).total_seconds() / 86400
            if gap_days >= 7 and (first_dormant is None or m["turn"] < first_dormant):
                viols.append(_viol(m["turn"], "T3_missed_dormancy", 0.8,
                                   f"bot messaged {gap_days:.1f} days after last borrower reply without dormant transition"))
                gap_flagged = True

    return viols


def _check_compliance(messages):
    viols = []
    sorted_msgs = sorted(messages, key=lambda m: m["turn"])
    dnc_turn = None

    for m in sorted_msgs:
        if m["role"] == "borrower" and m.get("text") and DNC_RE.search(m["text"]):
            if dnc_turn is None:
                dnc_turn = m["turn"]
        if dnc_turn is not None and m["role"] == "bot" and m["turn"] > dnc_turn:
            viols.append(_viol(m["turn"], "C3_dnc_violation", 1.0,
                               f"bot messaged at turn {m['turn']} after DNC at turn {dnc_turn}"))
        if m["role"] == "bot" and m.get("text") and THREAT_RE.search(m["text"]):
            viols.append(_viol(m["turn"], "C5_threat_in_message", 0.9,
                               f"threatening language: {m['text'][:120]!r}"))

    return viols


# ── Evaluator ─────────────────────────────────────────────────────────────────

class AgentEvaluator:
    def __init__(self):
        self.pipeline, self.labels = load_classifier()

    def _check_q2(self, messages, bot_cls_map):
        viols = []
        for turn, text, pred_cls, conf in classify_borrower_messages(self.pipeline, self.labels, messages):
            bot = bot_cls_map.get(turn)
            if not bot:
                continue
            if bot["classification"] != pred_cls:
                sev = min(1.0, 0.3 + 0.7 * conf)
                if pred_cls in ("hardship", "refuses", "disputes") and bot["classification"] == "unclear":
                    sev = max(sev, 0.8)
                viols.append(_viol(turn, "Q2_accurate_classification", sev,
                                   f"bot='{bot['classification']}' (conf={bot.get('confidence')}) "
                                   f"classifier='{pred_cls}' (conf={conf:.2f}): {text!r}"))
        return viols

    def evaluate(self, conversation: dict) -> dict:
        messages = conversation.get("messages", [])
        bot_cls_map = {c["turn"]: c for c in conversation.get("bot_classifications", [])}
        transitions = conversation.get("state_transitions", [])
        function_calls = conversation.get("function_calls", [])

        violations = (
            self._check_q2(messages, bot_cls_map)
            + _check_i5(messages, bot_cls_map)
            + _check_i3(transitions)
            + _check_i1(transitions, bot_cls_map)
            + _check_i2(transitions, messages)
            + _check_i4(transitions, function_calls)
            + _check_amounts(conversation)
            + _check_timing(messages)
            + _check_dormancy(messages, transitions)
            + _check_compliance(messages)
        )

        total_turns = max(1, conversation.get("metadata", {}).get("total_turns", len(messages)))
        total_sev = sum(v["severity"] for v in violations)
        avg_sev = total_sev / len(violations) if violations else 0.0
        max_sev = max((v["severity"] for v in violations), default=0.0)

        quality_score = max(0.0, 1.0 - total_sev / total_turns)
        risk_score = min(1.0, max_sev * 0.5 + avg_sev * 0.5)

        return {
            "quality_score": round(quality_score, 4),
            "risk_score": round(risk_score, 4),
            "violations": violations,
        }


def main():
    evaluator = AgentEvaluator()

    data_path = Path("data/production_logs.jsonl")
    split_path = Path("scripts/eval_split.json")
    if not data_path.exists():
        print("No data found. Make sure data/production_logs.jsonl exists.")
        return

    conversations = [json.loads(l) for l in open(data_path) if l.strip()]
    if split_path.exists():
        eval_ids = set(json.load(open(split_path))["eval_conversation_ids"])
        conversations = [c for c in conversations if c["conversation_id"] in eval_ids]
        print(f"Using held-out eval split: {len(conversations)} conversations (leak-free).")
    else:
        conversations = conversations[:10]
        print(f"No split file; evaluating first {len(conversations)} conversations.")

    results = []
    rule_counts = defaultdict(int)
    for conv in conversations:
        r = evaluator.evaluate(conv)
        results.append((conv["conversation_id"], r))
        for v in r["violations"]:
            rule_counts[v["rule"]] += 1

    avg_q = sum(r["quality_score"] for _, r in results) / len(results)
    avg_r = sum(r["risk_score"] for _, r in results) / len(results)
    total_v = sum(len(r["violations"]) for _, r in results)

    print(f"\nEvaluated {len(results)} conversations.")
    print(f"  avg quality_score: {avg_q:.3f}")
    print(f"  avg risk_score:    {avg_r:.3f}")
    print(f"  total violations:  {total_v}")
    print(f"  per-rule counts:   {dict(sorted(rule_counts.items()))}")
    print()
    for cid, r in results[:5]:
        print(f"  {cid}: q={r['quality_score']:.2f} risk={r['risk_score']:.2f} viols={len(r['violations'])}")


if __name__ == "__main__":
    main()
