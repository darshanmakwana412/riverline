#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fire>=0.7.1",
#     "scikit-learn>=1.5",
#     "numpy>=2.0",
#     "matplotlib>=3.9",
# ]
# ///
import json
import sys
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "plots"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

from eval_takehome import AgentEvaluator, ALLOWED_EDGES, PROGRESSION, EXIT  # noqa: E402


def load_eval_convs():
    eval_ids = set(json.load(open(ROOT / "scripts" / "eval_split.json"))["eval_conversation_ids"])
    return [
        json.loads(l)
        for l in open(ROOT / "data" / "production_logs.jsonl")
        if l.strip() and json.loads(l)["conversation_id"] in eval_ids
    ]


def run_eval(convs):
    ev = AgentEvaluator()
    return [(c, ev.evaluate(c)) for c in convs]


def plot_violations_by_rule(results):
    rules = Counter()
    for _, r in results:
        for v in r["violations"]:
            rules[v["rule"]] += 1
    items = sorted(rules.items(), key=lambda kv: -kv[1])
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color="#d97757")
        ax.set_xlabel("violations")
        ax.set_title("Violations by rule (211 held-out conversations)")
        for i, (_, v) in enumerate(items[::-1]):
            ax.text(v + 4, i, str(v), va="center")
        fig.tight_layout()
        fig.savefig(OUT / "fsm_violations_by_rule.png", dpi=120)
    plt.close(fig)


def plot_illegal_edges(convs):
    pair_counts = Counter()
    for c in convs:
        for t in c["state_transitions"]:
            f, to = t["from_state"], t["to_state"]
            if f == to:
                continue
            if (f, to) in ALLOWED_EDGES:
                continue
            pair_counts[(f, to)] += 1
    items = sorted(pair_counts.items(), key=lambda kv: -kv[1])[:10]
    labels = [f"{f} → {t}" for (f, t), _ in items]
    counts = [c for _, c in items]
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(labels[::-1], counts[::-1], color="#c96442")
        ax.set_xlabel("count on held-out set")
        ax.set_title("Top illegal state transitions")
        for i, c in enumerate(counts[::-1]):
            ax.text(c + 0.4, i, str(c), va="center")
        fig.tight_layout()
        fig.savefig(OUT / "fsm_illegal_edges.png", dpi=120)
    plt.close(fig)


def plot_quality_risk(results):
    qs = [r["quality_score"] for _, r in results]
    rs = [r["risk_score"] for _, r in results]
    with plt.xkcd():
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
        a1.hist(qs, bins=20, color="#4a7c4a", edgecolor="black")
        a1.set_title(f"Quality score (avg={np.mean(qs):.2f})")
        a1.set_xlabel("quality_score")
        a2.hist(rs, bins=20, color="#7c4a4a", edgecolor="black")
        a2.set_title(f"Risk score (avg={np.mean(rs):.2f})")
        a2.set_xlabel("risk_score")
        fig.tight_layout()
        fig.savefig(OUT / "fsm_quality_risk.png", dpi=120)
    plt.close(fig)


def plot_heatmap(convs):
    states = PROGRESSION + list(EXIT)
    idx = {s: i for i, s in enumerate(states)}
    M = np.zeros((len(states), len(states)), dtype=int)
    for c in convs:
        for t in c["state_transitions"]:
            f, to = t["from_state"], t["to_state"]
            if f == to:
                continue
            M[idx[f], idx[to]] += 1
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(9, 8))
        im = ax.imshow(np.log1p(M), cmap="Oranges")
        ax.set_xticks(range(len(states)))
        ax.set_yticks(range(len(states)))
        ax.set_xticklabels(states, rotation=45, ha="right")
        ax.set_yticklabels(states)
        ax.set_xlabel("to_state")
        ax.set_ylabel("from_state")
        ax.set_title("State transition frequency (log-scale)\nred box = illegal per spec")
        for i in range(len(states)):
            for j in range(len(states)):
                if M[i, j]:
                    ax.text(j, i, str(M[i, j]), ha="center", va="center", fontsize=7)
                if i != j and (states[i], states[j]) not in ALLOWED_EDGES and M[i, j] > 0:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="red", lw=2))
        fig.colorbar(im, ax=ax, fraction=0.046)
        fig.tight_layout()
        fig.savefig(OUT / "fsm_transition_heatmap.png", dpi=120)
    plt.close(fig)


def main():
    convs = load_eval_convs()
    print(f"loaded {len(convs)} held-out conversations")
    results = run_eval(convs)
    plot_violations_by_rule(results)
    plot_illegal_edges(convs)
    plot_quality_risk(results)
    plot_heatmap(convs)
    print(f"wrote plots to {OUT}")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
