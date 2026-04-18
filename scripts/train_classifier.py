#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fire>=0.7.1",
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
#     "scipy>=1.14",
# ]
# ///
import json
import pickle
import random
import re
from pathlib import Path
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent

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


def load_dataset(path):
    d = json.load(open(path))
    per_conv = {}
    for r in d["results"]:
        per_conv[r["conversation_id"]] = [(a.get("text", ""), a["classification"]) for a in r["sonnet"]["annotations"] if a.get("text")]
    return per_conv


def split_by_conversation(per_conv, test_size, seed):
    ids = sorted(per_conv.keys())
    rng = random.Random(seed)
    rng.shuffle(ids)
    cut = int(len(ids) * (1 - test_size))
    return ids[:cut], ids[cut:]


def build_pipeline(model: str):
    feats = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 3), min_df=2, sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True, lowercase=True)),
        ("hand", Pipeline([("h", HandFeatures()), ("s", StandardScaler(with_mean=False))])),
    ])
    if model == "lr":
        clf = LogisticRegression(max_iter=3000, class_weight="balanced", solver="lbfgs")
        grid = {"clf__C": [0.5, 1.0, 2.0, 4.0, 8.0]}
    elif model == "svm":
        base = LinearSVC(class_weight="balanced", max_iter=5000)
        clf = CalibratedClassifierCV(base, cv=3)
        grid = {"clf__estimator__C": [0.25, 0.5, 1.0, 2.0, 4.0]}
    else:
        raise ValueError(model)
    return Pipeline([("feats", feats), ("clf", clf)]), grid


def main(
    src: str = "scripts/annotations_full.json",
    seed: int = 42,
    test_size: float = 0.30,
    model: str = "svm",
    tune: bool = True,
    model_out: str = "scripts/classifier_model.pkl",
    split_out: str = "scripts/eval_split.json",
    report_out: str = "scripts/classifier_report.txt",
):
    per_conv = load_dataset(ROOT / src)
    train_ids, test_ids = split_by_conversation(per_conv, test_size, seed)
    X_tr, y_tr = [], []
    for cid in train_ids:
        for t, l in per_conv[cid]:
            X_tr.append(t); y_tr.append(l)
    X_te, y_te = [], []
    for cid in test_ids:
        for t, l in per_conv[cid]:
            X_te.append(t); y_te.append(l)
    print(f"Conversations: {len(train_ids)} train / {len(test_ids)} test")
    print(f"Messages:      {len(X_tr)} train / {len(X_te)} test")

    pipe, grid = build_pipeline(model)
    if tune:
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        search = GridSearchCV(pipe, grid, scoring="f1_macro", cv=cv, n_jobs=-1, verbose=1)
        search.fit(X_tr, y_tr)
        print(f"Best CV macro_f1: {search.best_score_:.4f}  params: {search.best_params_}")
        clf = search.best_estimator_
    else:
        pipe.fit(X_tr, y_tr)
        clf = pipe

    pred = clf.predict(X_te)
    labels = sorted(set(y_tr) | set(y_te))
    macro = f1_score(y_te, pred, average="macro")
    weighted = f1_score(y_te, pred, average="weighted")
    report = classification_report(y_te, pred, labels=labels, digits=3)
    cm = confusion_matrix(y_te, pred, labels=labels)

    lines = [
        f"model: {model}  tune: {tune}  conversation-level split",
        f"conversations: {len(train_ids)} train / {len(test_ids)} test (seed={seed}, test_size={test_size})",
        f"messages: {len(X_tr)} train / {len(X_te)} test",
        f"macro_f1: {macro:.4f}   weighted_f1: {weighted:.4f}",
        "",
        report,
        "confusion matrix (rows=true, cols=pred):",
        "          " + "".join(f"{l[:9]:>10}" for l in labels),
    ]
    for i, lbl in enumerate(labels):
        lines.append(f"{lbl[:9]:>9} " + "".join(f"{cm[i,j]:>10d}" for j in range(len(labels))))
    txt = "\n".join(lines)
    print("\n" + txt)
    (ROOT / report_out).write_text(txt)

    with open(ROOT / model_out, "wb") as f:
        pickle.dump({"pipeline": clf, "labels": labels, "hand_features_src": __file__}, f)
    with open(ROOT / split_out, "w") as f:
        json.dump({"seed": seed, "test_size": test_size, "train_conversation_ids": train_ids, "eval_conversation_ids": test_ids}, f, indent=2)
    print(f"\nSaved model → {model_out}")
    print(f"Saved split → {split_out}")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
