"""
Riverline Evals Take-Home Assignment
=====================================

AgentEvaluator. Self-contained: loads a pre-trained borrower-intent classifier
from scripts/classifier_model.pkl (trained by scripts/train_classifier.py).
Conversation-level 70/30 split used for training; held-out conversation ids
are stored in scripts/eval_split.json to prevent leakage in downstream work.
"""

import json
import pickle
import re
import sys
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
    """Load the pickled pipeline. HandFeatures was defined in __main__ at train
    time; expose it there so pickle can resolve the symbol."""
    sys.modules["__main__"].HandFeatures = HandFeatures
    with open(path, "rb") as f:
        bundle = pickle.load(f)
    return bundle["pipeline"], bundle["labels"]


def classify_borrower_messages(pipeline, labels, messages):
    """Return list of (turn, text, predicted_class, confidence) for every
    borrower message. Uses predict_proba when available (CalibratedClassifierCV)."""
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
        violations = []
        bot_cls = {c["turn"]: c for c in conversation.get("bot_classifications", [])}
        preds = classify_borrower_messages(self.pipeline, self.labels, conversation.get("messages", []))

        disagreements = 0
        total_classified = 0
        for turn, text, pred_cls, conf in preds:
            bot = bot_cls.get(turn)
            if not bot:
                continue
            total_classified += 1
            if bot["classification"] != pred_cls:
                disagreements += 1
                severity = min(1.0, 0.3 + 0.7 * conf)
                if pred_cls in ("hardship", "refuses", "disputes") and bot["classification"] == "unclear":
                    severity = max(severity, 0.8)
                violations.append({
                    "turn": int(turn),
                    "rule": "Q2_accurate_classification",
                    "severity": round(severity, 3),
                    "explanation": f"bot labeled '{bot['classification']}' (conf={bot.get('confidence')}) "
                                   f"but classifier predicts '{pred_cls}' (conf={conf:.2f}) for: {text!r}",
                })

        disagreement_rate = disagreements / total_classified if total_classified else 0.0
        avg_sev = sum(v["severity"] for v in violations) / len(violations) if violations else 0.0
        quality_score = max(0.0, 1.0 - disagreement_rate)
        risk_score = min(1.0, disagreement_rate * 0.5 + avg_sev * 0.5)

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
    eval_ids = None
    if split_path.exists():
        eval_ids = set(json.load(open(split_path))["eval_conversation_ids"])
        conversations = [c for c in conversations if c["conversation_id"] in eval_ids]
        print(f"Using held-out eval split: {len(conversations)} conversations (leak-free).")
    else:
        conversations = conversations[:10]
        print(f"No split file; evaluating first {len(conversations)} conversations.")

    results = []
    for conv in conversations:
        r = evaluator.evaluate(conv)
        results.append((conv["conversation_id"], r))

    total_v = sum(len(r[1]["violations"]) for r in results)
    avg_q = sum(r[1]["quality_score"] for r in results) / len(results)
    avg_r = sum(r[1]["risk_score"] for r in results) / len(results)
    print(f"\nEvaluated {len(results)} conversations.")
    print(f"  avg quality_score: {avg_q:.3f}")
    print(f"  avg risk_score:    {avg_r:.3f}")
    print(f"  total violations:  {total_v}")
    for cid, r in results[:5]:
        print(f"  {cid}: q={r['quality_score']:.2f} risk={r['risk_score']:.2f} viols={len(r['violations'])}")


if __name__ == "__main__":
    main()
