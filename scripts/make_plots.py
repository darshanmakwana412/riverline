#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fire>=0.7.1",
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
#     "scipy>=1.14",
#     "matplotlib>=3.9",
# ]
# ///
import json
import pickle
import sys
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "plots"
OUT.mkdir(parents=True, exist_ok=True)


def load_sonnet():
    return json.load(open(ROOT / "scripts" / "annotations_full.json"))


def load_model():
    sys.path.insert(0, str(ROOT))
    import eval_takehome  # registers HandFeatures in __main__
    eval_takehome.load_classifier  # noqa
    sys.modules["__main__"].HandFeatures = eval_takehome.HandFeatures
    with open(ROOT / "scripts" / "classifier_model.pkl", "rb") as f:
        b = pickle.load(f)
    return b["pipeline"], b["labels"]


def plot_class_distribution(d):
    c = Counter()
    for r in d["results"]:
        for a in r["sonnet"]["annotations"]:
            c[a["classification"]] += 1
    labels, counts = zip(*c.most_common())
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(labels, counts, color="#4a7abc")
        ax.set_title("sonnet label distribution across 700 conversations")
        ax.set_ylabel("borrower messages")
        for i, v in enumerate(counts):
            ax.text(i, v + 20, str(v), ha="center")
        plt.xticks(rotation=20)
        plt.tight_layout()
        plt.savefig(OUT / "class_distribution.png", dpi=120)
        plt.close()


def plot_bot_vs_sonnet(d):
    agree = disagree = 0
    swaps = Counter()
    for r in d["results"]:
        bot = {c["turn"]: c["classification"] for c in r["bot"]}
        for a in r["sonnet"]["annotations"]:
            if a["turn"] not in bot:
                continue
            if bot[a["turn"]] == a["classification"]:
                agree += 1
            else:
                disagree += 1
                swaps[(bot[a["turn"]], a["classification"])] += 1
    with plt.xkcd():
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].bar(["agree", "disagree"], [agree, disagree], color=["#4caf50", "#e74c3c"])
        axes[0].set_title(f"bot vs sonnet agreement\n{agree/(agree+disagree):.1%} on {agree+disagree} turns")
        for i, v in enumerate([agree, disagree]):
            axes[0].text(i, v + 40, str(v), ha="center")

        top = swaps.most_common(8)
        labels = [f"{b}\n→ {s}" for (b, s), _ in top]
        counts = [n for _, n in top]
        axes[1].barh(range(len(top)), counts, color="#e74c3c")
        axes[1].set_yticks(range(len(top)))
        axes[1].set_yticklabels(labels)
        axes[1].invert_yaxis()
        axes[1].set_title("top bot → sonnet disagreements")
        axes[1].set_xlabel("count")
        plt.tight_layout()
        plt.savefig(OUT / "bot_vs_sonnet.png", dpi=120)
        plt.close()


def plot_confusion_and_f1(d, pipeline, labels):
    split = json.load(open(ROOT / "scripts" / "eval_split.json"))
    eval_ids = set(split["eval_conversation_ids"])
    X, y = [], []
    for r in d["results"]:
        if r["conversation_id"] not in eval_ids:
            continue
        for a in r["sonnet"]["annotations"]:
            if a.get("text"):
                X.append(a["text"])
                y.append(a["classification"])
    pred = pipeline.predict(X)
    cm = confusion_matrix(y, pred, labels=labels)
    f1_per = f1_score(y, pred, labels=labels, average=None)
    macro = f1_score(y, pred, average="macro")

    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(9, 7))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_yticklabels(labels)
        ax.set_xlabel("predicted")
        ax.set_ylabel("sonnet (ground truth)")
        ax.set_title(f"held-out confusion matrix  macro_f1={macro:.3f}")
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, cm[i, j], ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
        fig.colorbar(im, ax=ax)
        plt.tight_layout()
        plt.savefig(OUT / "confusion_matrix.png", dpi=120)
        plt.close()

        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(labels, f1_per, color="#4a7abc")
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("f1 score")
        ax.set_title(f"per-class f1 on held-out conversations (n={len(X)})")
        for i, v in enumerate(f1_per):
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
        plt.xticks(rotation=20)
        plt.tight_layout()
        plt.savefig(OUT / "per_class_f1.png", dpi=120)
        plt.close()


def plot_pipeline_diagram():
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(13, 7))
        ax.set_xlim(0, 14)
        ax.set_ylim(0, 8)
        ax.axis("off")

        def box(x, y, w, h, text, color="#fdf6e3"):
            ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, facecolor=color, edgecolor="black", linewidth=2))
            ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=11)

        def arrow(x1, y1, x2, y2):
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="->", lw=2))

        box(0.2, 3.2, 2.3, 1.6, "borrower\nmessage", "#c8e6c9")
        box(3.2, 5.5, 3, 1.3, "TF-IDF word\n1–3 grams", "#bbdefb")
        box(3.2, 3.2, 3, 1.3, "TF-IDF char_wb\n2–5 grams", "#bbdefb")
        box(3.2, 0.9, 3, 1.3, "hand-crafted\n14 features", "#bbdefb")
        box(7.2, 3.2, 2.6, 1.6, "concat\n+ scaler", "#ffe0b2")
        box(10.3, 3.2, 2.6, 1.6, "LinearSVC\n(calibrated)\nC=4", "#f8bbd0")

        arrow(2.5, 4.0, 3.2, 6.1)
        arrow(2.5, 4.0, 3.2, 3.85)
        arrow(2.5, 4.0, 3.2, 1.55)
        arrow(6.2, 6.1, 7.2, 4.2)
        arrow(6.2, 3.85, 7.2, 4.0)
        arrow(6.2, 1.55, 7.2, 3.8)
        arrow(9.8, 4.0, 10.3, 4.0)

        ax.text(13.0, 4.0, "→ 7-class\nintent", fontsize=12, va="center")
        ax.set_title("borrower-intent classifier pipeline  (macro f1 = 0.94, cpu)", fontsize=13)
        plt.tight_layout()
        plt.savefig(OUT / "pipeline.png", dpi=120)
        plt.close()


def plot_eval_scores():
    import subprocess
    # run eval_takehome evaluate over held-out, capture per-conv scores
    sys.path.insert(0, str(ROOT))
    from eval_takehome import AgentEvaluator
    split = json.load(open(ROOT / "scripts" / "eval_split.json"))
    eval_ids = set(split["eval_conversation_ids"])
    convs = [json.loads(l) for l in open(ROOT / "data" / "production_logs.jsonl") if l.strip()]
    convs = [c for c in convs if c["conversation_id"] in eval_ids]
    ev = AgentEvaluator()
    qs, rs, vs = [], [], []
    for c in convs:
        r = ev.evaluate(c)
        qs.append(r["quality_score"]); rs.append(r["risk_score"]); vs.append(len(r["violations"]))
    with plt.xkcd():
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
        axes[0].hist(qs, bins=15, color="#4caf50", edgecolor="black")
        axes[0].set_title(f"quality_score  mean={np.mean(qs):.2f}")
        axes[0].set_xlabel("quality_score")
        axes[1].hist(rs, bins=15, color="#e74c3c", edgecolor="black")
        axes[1].set_title(f"risk_score  mean={np.mean(rs):.2f}")
        axes[1].set_xlabel("risk_score")
        axes[2].hist(vs, bins=range(0, max(vs) + 2), color="#4a7abc", edgecolor="black")
        axes[2].set_title(f"#violations per conv  mean={np.mean(vs):.1f}")
        axes[2].set_xlabel("# Q2 violations")
        fig.suptitle(f"AgentEvaluator on {len(qs)} held-out conversations")
        plt.tight_layout()
        plt.savefig(OUT / "eval_scores.png", dpi=120)
        plt.close()


def main():
    d = load_sonnet()
    pipeline, labels = load_model()
    plot_class_distribution(d)
    plot_bot_vs_sonnet(d)
    plot_confusion_and_f1(d, pipeline, labels)
    plot_pipeline_diagram()
    plot_eval_scores()
    for p in sorted(OUT.iterdir()):
        print(p.relative_to(ROOT))


if __name__ == "__main__":
    import fire
    fire.Fire(main)
