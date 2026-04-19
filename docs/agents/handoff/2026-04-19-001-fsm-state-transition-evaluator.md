# Handoff: FSM State-Transition Evaluator

**Date:** 2026-04-19
**Session focus:** Clarify the validity vs correctness framing of the spec, then extend `eval_takehome.py` from a Q2-only classifier check into a full state-machine evaluator covering invariants I1 through I5. Produce FSM diagrams and writeup under `docs/`.

---

## What Was Accomplished

### Clarified the spec's ambiguities before coding

Four framing questions drove this session before any implementation. Their resolutions are baked into the evaluator:

1. **Validity vs correctness.** Validity is a pure graph check against the spec Table 1 edge set. Correctness (did the bot actually explain settlement before claiming `settlement_explained`) is a separate semantic axis best handled by an LLM judge later. This pass implements validity only.
2. **Misclassified intent interacting with transitions.** Kept orthogonal. Q2 covers the label disagreement; I1 evaluates the graph edge regardless of which label drove it. No double-counting.
3. **`zcm_timeout` is event or action.** Spec is inconsistent (listed in both section 3.2 and section 5). Evaluator treats it as a system event whose required landing edge is `amount_pending -> escalated`. Any other landing trips I4.
4. **`zcm_response`.** System event emitted when the ZCM supervisor replies with a settlement amount. Required landing edge is `amount_pending -> amount_sent`. Not a borrower message, not a bot action.

### FSM-validity layer in `eval_takehome.py`

The file is now a single-file, self-contained evaluator. Augmented `AgentEvaluator` with five private helpers, all called from `evaluate()` and merged with the pre-existing Q2 block:

| Rule | Helper | What it flags |
|---|---|---|
| I1 | `_check_transitions` | `(from, to)` edge not in spec matrix. Backward exception `settlement_explained`/`amount_pending -> intent_asked` only valid when classifier-predicted intent is `unclear` and bot-reported confidence is `low`. |
| I2 (entry) | `_check_transitions` | Any transition out of `escalated` or `dormant`. Severity 1.0. |
| I2 (tail) | `_check_post_exit_messages` | Any bot message at a turn strictly greater than the first entry into an exit state. Severity 1.0. |
| I3 | `_check_chain_coherence` | `state_transitions[i].from_state != state_transitions[i-1].to_state`, or chain does not start at `new`. |
| I4 | `_check_actions` | `function_calls[*]` fired outside its required edge (e.g. `send_settlement_amount` requires `amount_pending -> amount_sent`; `escalate` must land in `escalated`; `zcm_timeout` requires `amount_pending -> escalated`). |
| I5 | `_check_all_classified` | Borrower message with no matching `bot_classifications` entry. |
| Q2 | `_check_q2` | Unchanged from the previous session. |

Module-level constants added: `PROGRESSION`, `EXIT`, `ALLOWED_EDGES`, `BACKWARD_EXCEPTIONS`, `ACTION_TRANSITIONS`. These encode spec Table 1 directly; change them here if the spec moves.

Scoring updated:
- `quality_score = max(0, 1 - sum(severity) / total_turns)`. Penalises dense violations per turn rather than absolute count, so long happy-path conversations are not unfairly deflated.
- `risk_score = min(1, 0.5 * (count / total_turns) + 0.5 * avg_severity)`.
- `summary` is a `Counter` keyed by rule prefix (`Q2`, `I1`, `I2`, `I3`, `I4`, `I5`) for quick per-conversation triage.

### Held-out eval numbers

Running `python eval_takehome.py` on the 211-conv held-out split:

```
avg quality_score: 0.667
avg risk_score:    0.643
total violations:  933
per-rule totals:   {'Q2': 775, 'I2': 91, 'I4': 55, 'I1': 12}
```

The I2/I4 counts match expected dataset-wide signals. `escalated -> intent_asked` (108 dataset-wide) and `escalated -> escalated` (61 dataset-wide) dominate the I2 column. `settlement_explained -> amount_sent` (23) and `intent_asked -> amount_sent` (18) dominate I1 skip-forwards.

### Manual spot-check on 5 conversations

Picked one conversation per archetype and confirmed every flag matches the spec:

| Archetype | Conversation | Expected | Evaluator output |
|---|---|---|---|
| Happy path | `192f029c-2626-7e25-7fee-3fff275530b7` | no I-violations | Q2 only |
| Escalated return | `f7c73e05-d9bd-5c83-2532-468b5c7c8c5e` | I2 return plus I2 post-exit messages plus I4 `zcm_timeout` mismatch | all three flagged |
| Skip forward | `5280cd5c-173d-7120-2480-1a56683a58e0` | I1 for `settlement_explained -> amount_sent`, I4 for `send_settlement_amount` outside its edge | both flagged |
| Dormant after success | `51924834-04e7-1f5d-33ba-3884b928b8db` | no I-violations (`payment_confirmed -> dormant` is allowed) | clean |
| Escalated self-loop | `63f0a960-c782-fdb5-c6dc-60074e403e42` | I2 post-exit messages, I4 `zcm_timeout` mismatch | both flagged |

### Documentation and plots

- `docs/fsm_evaluator.md`: full writeup covering framing, data shape, rule table, results, and manual verification.
- `scripts/make_fsm_plots.py`: regenerator for `fsm_violations_by_rule.png`, `fsm_illegal_edges.png`, `fsm_transition_heatmap.png` (illegal cells red-bordered), and `fsm_quality_risk.png`.
- `scripts/make_fsm_diagram.py`: renders `fsm_diagram.png` (colour-coded FSM with every edge labelled by borrower intent, system event, or bot action) and `fsm_triggers.png` (three-column taxonomy of all seven intents, four events, and five actions).

Both scripts are uv executables with inline dependencies, matching the project convention.

---

## Key Decisions

1. **Validity only in this pass.** Correctness (state label matches the bot's actual message content) is deferred to a future LLM-judged layer. Rationale: validity is deterministic and produces a strong signal already; mixing in LLM judgement blurs reproducibility.
2. **Backward exception gating uses the classifier prediction, not the bot's stored label.** The bot's stored label may itself be the misclassification that produced the illegal backward move. Using the classifier is the best available ground truth inside the evaluator.
3. **Self-transitions are skipped universally.** Spec says progression self-transitions are always valid and is silent on exit self-loops. `escalated -> escalated` is therefore not directly flagged as I2, but the behavioural harm (bot continuing to message after exit) is caught by `I2_message_after_exit`, so no practical gap.
4. **Scope ruled out for this pass.** Amount validation (section 7), quiet hours (section 5.1), follow-up spacing (section 5.2), DNC keyword detection (section 6.3), language matching (section 6.4), tone (Q3), and context memory (Q4). All planned for a separate pass.
5. **No new files inside `eval_takehome.py`.** All new checks live as methods on `AgentEvaluator` so the submission script remains self-contained. Constants are module-level to keep the hot path allocation-free.
6. **`quality_score` is turn-normalised.** Earlier iteration used `1 - disagreement_rate` (Q2-only). Extending that to the full violation set would over-penalise long conversations; turn-normalised severity sum is the correct generalisation.

---

## Important Context for Future Sessions

### Where things live

```
eval_takehome.py                              # AgentEvaluator, all checks
scripts/classifier_model.pkl                  # loaded at AgentEvaluator init
scripts/eval_split.json                       # 211 held-out conversation ids
scripts/annotations_full.json                 # Sonnet ground-truth labels (700 convs)
scripts/make_fsm_plots.py                     # violation distribution plots
scripts/make_fsm_diagram.py                   # FSM state diagram plots
docs/fsm_evaluator.md                         # this session's writeup
docs/approach.md                              # previous session's writeup
docs/plots/fsm_*.png                          # all FSM plots
data/production_logs.jsonl                    # 700 production conversations
```

### Data shape (confirmed, not speculated)

Each conversation in `data/production_logs.jsonl` has:

- `messages[]`: `{turn, role in {bot, borrower}, text, timestamp}`. No `role == system`. No per-message `state` field.
- `bot_classifications[]`: `{turn, input_text, classification, confidence in {low, medium, high}}`.
- `state_transitions[]`: `{turn, from_state, to_state, reason}`. Multiple transitions per turn are allowed. Turn 0 is always `new -> new` with reason `conversation_initialized`.
- `function_calls[]`: `{turn, function, params}`. `params` includes `pos`, `tos`, `dpd`, `settlement_amount`, `payment_date` depending on the function.
- `metadata`: `{language, zone, dpd, pos, tos, settlement_offered, total_turns}`.

The `reason` field is free-text with 14 observed values mixing bot actions, borrower-intent-derived triggers, and system events. The evaluator deliberately ignores `reason` and keys off the `(from_state, to_state)` pair, because the spec matrix is pure graph.

### Observed illegal edges on the full 700-conv dataset

```
escalated -> intent_asked     108   (I2)
escalated -> escalated         61   (I2, not currently flagged, see decision 3)
settlement_explained -> amount_sent   23   (I1 skip)
intent_asked -> amount_sent           18   (I1 skip)
```

If the held-out numbers drift from roughly 211/700 of these, something in the split or the checker has changed.

### Known pre-existing behaviours (not bugs, document them)

- The production bot treats `escalated` as reversible and returns to `intent_asked` after a `zcm_timeout_reengagement`. This is a hard spec violation (I2) but is consistent with how the data was generated. Do not try to "fix" the spec to accommodate it.
- `payment_confirmed -> dormant` appears 14 times in the dataset. This is allowed per Table 1 (any progression state can go to `dormant`). It represents a borrower who committed to pay and then went silent for 7 days. The checker correctly does not flag this.
- `bot_classifications` uses `wants_full_payment` in the raw data where the spec uses `wants_closure`. The Q2 check compares against the bot's stored label verbatim, so this mismatch surfaces as Q2 disagreements. If a future iteration normalises labels, do it in one place only (the classifier or the Q2 check, not both).

### Git status

Branch `main`, clean before this session. Session produced edits to `eval_takehome.py` and new files under `scripts/` and `docs/`. Nothing committed yet. Prior commits referenced in the session:

```
0a439d1 adding the approach to claude
d26b524 borrower intent classifier handoff docs and models
f4c254b some updates in the claude doc
2ec4de0 adding the initial editor ui
d6a76e6 adding claude instruction file
```

### How to run

```bash
uv run --with scikit-learn --with numpy eval_takehome.py
./scripts/make_fsm_plots.py
./scripts/make_fsm_diagram.py
```

No shell wrapping needed beyond uv. The eval script auto-detects `scripts/eval_split.json` and restricts to the held-out set; delete or rename that file to run on all 700.

---

## What's Next

Priority order for the remaining evaluator work:

1. **Amount validation (section 7).** POS less than or equal to TOS, floor less than or equal to amount less than or equal to TOS, consistency of the quoted amount across turns. All deterministic from `function_calls[*].params` plus `metadata`. No model needed.
2. **Quiet hours and follow-up spacing (section 5.1 and 5.2).** Timestamp-only. Convert `timestamp` to IST, flag outbound bot messages between 19:00 and 08:00, and flag consecutive bot messages less than 4 hours apart with no borrower reply in between.
3. **Compliance keywords (section 6).** DNC phrases, legal-threat keywords, language mismatch against `metadata.language`. Mostly regex.
4. **Correctness layer.** LLM-judged check scoped to the handful of edges where the state label makes a semantic claim about the bot's own message (`settlement_explained`, `amount_sent`, `payment_confirmed`). Cheap because it only fires on state-change turns, not every borrower message.
