#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fire>=0.7.1",
#     "matplotlib>=3.9",
#     "numpy>=2.0",
# ]
# ///
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "plots"
OUT.mkdir(parents=True, exist_ok=True)

PROG = {
    "new": (0, 9),
    "message_received": (0, 8),
    "verification": (0, 7),
    "intent_asked": (0, 6),
    "settlement_explained": (0, 5),
    "amount_pending": (0, 4),
    "amount_sent": (0, 3),
    "date_amount_asked": (0, 2),
    "payment_confirmed": (0, 1),
}
EXIT = {"escalated": (5.5, 5), "dormant": (5.5, 1)}

C_PROG = "#e8e8e8"
C_EXIT = "#d9b38c"
C_INTENT = "#b8e6b8"
C_EVENT = "#a8c8e8"
C_ACTION = "#fff2a8"


def node(ax, xy, text, color, w=2.2, h=0.55, fontsize=9):
    x, y = xy
    box = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.04",
                         linewidth=1.2, edgecolor="black", facecolor=color)
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, fontweight="bold")


def chip(ax, xy, text, color, w=1.9, h=0.38, fontsize=7):
    x, y = xy
    box = FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02",
                         linewidth=0.8, edgecolor="black", facecolor=color)
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize)


def arrow(ax, p1, p2, color="black", style="-|>", lw=1.2, rad=0.0, ls="-"):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, color=color, lw=lw,
                        mutation_scale=12, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)


def draw_main():
    fig, ax = plt.subplots(figsize=(14, 12))
    ax.set_xlim(-4, 9)
    ax.set_ylim(0, 10.2)
    ax.axis("off")
    ax.set_title("Debt-collection FSM — states, triggers, actions", fontsize=14, pad=20)

    for name, (x, y) in PROG.items():
        node(ax, (x, y), name, C_PROG)
    for name, (x, y) in EXIT.items():
        node(ax, (x, y), name, C_EXIT)

    happy = [
        ("new", "message_received", "borrower msg"),
        ("message_received", "verification", "borrower msg"),
        ("verification", "intent_asked", "verification_accepted"),
        ("intent_asked", "settlement_explained", "wants_settlement / wants_closure"),
        ("settlement_explained", "amount_pending", "borrower agrees\n+ request_settlement_amount"),
        ("amount_pending", "amount_sent", "zcm_response\n+ send_settlement_amount"),
        ("amount_sent", "date_amount_asked", "borrower agrees"),
        ("date_amount_asked", "payment_confirmed", "borrower gives date\n+ confirm_payment"),
    ]
    for f, t, label in happy:
        x1, y1 = PROG[f]; x2, y2 = PROG[t]
        arrow(ax, (x1, y1 - 0.28), (x2, y2 + 0.28), lw=1.6)
        color = C_EVENT if "zcm" in label or "verification" in label or "payment_received" in label else C_INTENT
        if "borrower msg" in label:
            color = C_INTENT
        if "+ " in label:
            color = C_ACTION
        chip(ax, (-2.3, (y1 + y2) / 2), label, color, w=2.6, h=0.55, fontsize=6.5)
        arrow(ax, (-1.05, (y1 + y2) / 2), (-0.1 - 1.05, (y1 + y2) / 2 - 0.01), style="-", lw=0.4, ls=":")

    for name, (x, y) in PROG.items():
        if name in ("payment_confirmed",):
            continue
        arrow(ax, (x + 1.1, y), (5.5 - 1.1, 5), color="#b23b3b", rad=0.05, lw=1.1)
    chip(ax, (3, 6.7), "refuses / disputes / hardship /\nDNC kw / zcm_timeout\n+ escalate",
         C_ACTION, w=3.0, h=0.85, fontsize=7)

    for name, (x, y) in PROG.items():
        arrow(ax, (x + 1.1, y), (5.5 - 1.1, 1), color="#806040", rad=-0.15, lw=0.9, ls="--")
    chip(ax, (3, 2.3), "7-day timeout (system)", C_EVENT, w=2.4, h=0.4, fontsize=7)

    for f in ("settlement_explained", "amount_pending"):
        x, y = PROG[f]
        xt, yt = PROG["intent_asked"]
        arrow(ax, (x - 1.1, y - 0.1), (xt - 1.1, yt + 0.1), color="#6060a0", rad=-0.35, lw=1.1, ls="-.")
    chip(ax, (-2.9, 5.5), "unclear + low conf\n(only backward allowed)", C_INTENT, w=2.6, h=0.55, fontsize=6.5)

    chip(ax, (7.8, 9), "payment_received\n(system event →\npayment_confirmed\nfrom any state)",
         C_EVENT, w=2.6, h=1.0, fontsize=7)

    legend_items = [
        ("Progression state", C_PROG),
        ("Exit state (final)", C_EXIT),
        ("Borrower intent", C_INTENT),
        ("System event", C_EVENT),
        ("Bot action", C_ACTION),
    ]
    for i, (label, color) in enumerate(legend_items):
        y0 = 0.5 - i * 0.35
        ax.add_patch(Rectangle((6.8, y0 - 0.12), 0.35, 0.25, facecolor=color, edgecolor="black"))
        ax.text(7.3, y0, label, va="center", fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT / "fsm_diagram.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def draw_trigger_taxonomy():
    intents = [
        ("unclear", "intent could not be determined"),
        ("wants_settlement", "reduced payment to close"),
        ("wants_closure", "full payment to close"),
        ("refuses", "will not pay → escalate"),
        ("disputes", "contests debt → escalate"),
        ("hardship", "job loss / medical → escalate"),
        ("asks_time", "wants more time (stay in state)"),
    ]
    events = [
        ("timeout / 7-day", "→ dormant from any progression state"),
        ("payment_received", "→ payment_confirmed from any state"),
        ("zcm_response", "amount_pending → amount_sent"),
        ("zcm_timeout", "amount_pending → escalated"),
    ]
    actions = [
        ("request_settlement_amount", "settlement_explained → amount_pending"),
        ("send_settlement_amount", "amount_pending → amount_sent (floor ≤ amt ≤ TOS)"),
        ("confirm_payment", "date_amount_asked → payment_confirmed (date > now)"),
        ("escalate", "any progression → escalated"),
        ("zcm_timeout", "amount_pending → escalated"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    for ax, (title, rows, color) in zip(
        axes,
        [("Borrower Intents (§3.1)", intents, C_INTENT),
         ("System Events (§3.2)", events, C_EVENT),
         ("Bot Actions (§4)", actions, C_ACTION)],
    ):
        ax.set_xlim(0, 10)
        ax.set_ylim(-len(rows) - 0.5, 0.5)
        ax.axis("off")
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
        for i, (name, desc) in enumerate(rows):
            y = -i - 0.5
            ax.add_patch(FancyBboxPatch((0.2, y - 0.35), 3.8, 0.7,
                                        boxstyle="round,pad=0.03",
                                        facecolor=color, edgecolor="black", linewidth=1))
            ax.text(2.1, y, name, ha="center", va="center", fontsize=9, fontweight="bold")
            ax.text(4.3, y, desc, ha="left", va="center", fontsize=8)
    fig.suptitle("Trigger taxonomy — what causes state changes", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "fsm_triggers.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    draw_main()
    draw_trigger_taxonomy()
    print(f"wrote FSM diagrams to {OUT}")


if __name__ == "__main__":
    import fire
    fire.Fire(main)
