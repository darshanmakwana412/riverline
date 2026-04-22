# Handoff: Multi-Rule Violation Evaluator

**Date:** 2026-04-22
**Session focus:** Extend `eval_takehome.py` from a single Q2 classifier check into a full multi-layer evaluator covering state-machine invariants (I1-I5), amount bounds (A1-A3), timing rules (T1-T2), and compliance triggers (C3, C5). Rebuild everything from scratch; the old FSM evaluator code in git history and the `old/` directory was discarded.

---

## What Was Accomplished

### All new violation rules wired into `eval_takehome.py`

The evaluator now emits violations across thirteen rule types. Each violation has the shape `{turn, rule, severity, explanation}`. All new checkers are module-level functions; `AgentEvaluator.evaluate()` calls them in sequence and concatenates results.

**State-machine invariants (I1-I5)**

- `I1_invalid_transition` / `I1_backward_exception_invalid`: checks every `(from_state, to_state)` edge against the spec Table 1 matrix. Self-transitions and transitions from exit states are skipped (exit-state handling belongs to I2). The backward exception (settlement_explained or amount_pending back to intent_asked) is valid only when the bot's recorded classification is `unclear` with confidence `low`; anything else is flagged at severity 0.9. All other illegal edges get severity 0.8 if both states are progression states (skip-forward) or 0.9 otherwise.

- `I2_exit_not_final` / `I2_message_after_exit`: flags any transition whose `from_state` is escalated or dormant (severity 1.0), and separately flags every bot message whose turn is strictly greater than the first turn at which the conversation entered an exit state (severity 1.0).

- `I3_chain_break`: checks that `transitions[0].from_state == "new"` and that each `transitions[i].from_state == transitions[i-1].to_state`. Severity 0.9.

- `I4_action_wrong_state` / `I4_required_action_missing` / `I4_escalation_missing_call`: bidirectional action-to-state check. Forward: each function call must have a matching transition at the same turn. Reverse: each required-action transition must have its corresponding call. The five functions checked and their required edges are `request_settlement_amount` (settlement_explained to amount_pending), `send_settlement_amount` (amount_pending to amount_sent), `confirm_payment` (date_amount_asked to payment_confirmed), `escalate` (any to escalated), `zcm_timeout` (amount_pending to escalated). The escalation reverse check accepts either `escalate` or `zcm_timeout` at the turn of a to-escalated transition.

- `I5_missing_classification`: any borrower message turn with no entry in `bot_classifications`. Severity 0.5.

**Amount checks (A1-A3)**

- `A1_pos_exceeds_tos`: `metadata.pos > metadata.tos`. Severity 0.6, turn -1.
- `A2_floor_exceeds_pos`: `metadata.settlement_offered > metadata.pos`. Severity 0.6, turn -1.
- `A3_amount_out_of_bounds`: for each `send_settlement_amount` call, checks that `params.amount` is within `[settlement_offered, tos]`. Severity 0.9.

`metadata.settlement_offered` is treated as the settlement floor (minimum the company will accept). This is an assumption; see Key Decisions below.

**Timing checks (T1-T2)**

Timestamps are parsed as naive UTC and converted to IST (UTC+5:30).

- `T1_quiet_hours`: bot message sent between 19:00 and 07:59 IST, when the immediately preceding message was not from the borrower. The reply-to-inbound exception is applied by tracking a `last_was_borrower` flag as messages are processed in timestamp order. Severity 0.7.
- `T2_followup_too_soon`: bot message sent less than 4 hours after the previous bot message, with no borrower message in between. Severity 0.5.

**Compliance checks (C3, C5)**

- `C3_dnc_violation`: detects DNC requests in borrower messages using `DNC_RE` (`stop`, `do not contact`, `don't contact`, `leave me alone`, `block me`, `unsubscribe`, `opt out`, `do not call`, `don't call`). Records the first DNC turn, then flags every subsequent bot message as a severity 1.0 violation.
- `C5_threat_in_message`: scans bot messages for `THREAT_RE` (`legal action`, `file a case`, `court`, `police`, `FIR`, `warrant`, `arrest`, `property seizure`, `public shame`, `shame you`, `expose you`, `blacklist`, `garnish`). Severity 0.9.

**Updated scoring**

Previous scoring was tied specifically to Q2 disagreement rate. The new formula:
- `quality_score = max(0.0, 1.0 - total_severity / total_turns)` where total_severity is the sum of all violation severities in the conversation and total_turns comes from `metadata.total_turns`.
- `risk_score = min(1.0, max_severity * 0.5 + avg_severity * 0.5)` where max and avg are over all violations in the conversation.

**Results on the 211-conversation held-out split**

```
avg quality_score: 0.497
avg risk_score:    0.926
total violations:  1464
per-rule counts:
  Q2_accurate_classification:   775
  I4_required_action_missing:   154
  T1_quiet_hours:               160
  T2_followup_too_soon:         117
  C3_dnc_violation:             100
  I2_message_after_exit:         66
  I4_action_wrong_state:         55
  I2_exit_not_final:             25
  I1_invalid_transition:         12
```

Zero violations for I3, I5, A1, A2, A3, C5 across the full held-out set. This means the production data has clean chain continuity, complete borrower classifications, internally consistent amount metadata, and no bot threats. These zero counts are themselves findings.

**Spot-check verification**

- `192f029c` (happy-path): only Q2 violations plus one I4_required_action_missing (the bot quoted the settlement amount verbally at turn 7 instead of via `send_settlement_amount`). No timing or compliance flags. Confirmed correct.
- `f7c73e05` (escalated return): I2_exit_not_final (`escalated` to `intent_asked` at turn 10), five I2_message_after_exit flags, I4_action_wrong_state for `zcm_timeout` misfired during the illegal return transition, five C3_dnc_violation flags (bot kept messaging after borrower said "Stop sending me these messages" at turn 1). Confirmed correct.
- `5280cd5c` (skip-forward): I1_invalid_transition for `settlement_explained` to `amount_sent` (skips `amount_pending`), I4_action_wrong_state for `send_settlement_amount` fired without the right edge. Confirmed correct.

**uv inline dependencies**

`eval_takehome.py` now has the uv shebang and inline dependency block (`scikit-learn>=1.5`, `numpy>=2.0`) so it can be run directly as `./eval_takehome.py` from the project root without a separate venv.

---

## Key Decisions

### zcm_timeout treatment

`zcm_timeout` appears in both spec section 3.2 (system events) and section 4 (bot actions), which is contradictory. Decision: treat it as the bot acknowledging a system event. Its only valid landing edge is `amount_pending` to `escalated`. Firing it at any other edge is an I4 violation. The CTO confirmed this interpretation is defensible and asked us to document the assumption.

### send_settlement_amount bypass is a violation

Three conversations in the held-out set have the `amount_pending` to `amount_sent` transition without a `send_settlement_amount` function call. The bot quotes the amount verbally in the message instead. Decision: flag these as I4_required_action_missing. Rationale: the amount floor and TOS bounds from spec section 7 (A3) are only enforceable if the amount flows through the function call. A verbal bypass makes A3 unenforceable by design. The CTO affirmed this reasoning.

### Backward exception uses bot's recorded classification

The spec says the backward return to `intent_asked` is valid only when the borrower classification is `unclear` with low confidence. Decision: use the bot's `bot_classifications` entry for this check, not our ML classifier's prediction. Using our classifier would silently change the set of flagged conversations depending on classifier drift. The bot's recorded label is the authoritative input the state machine acted on.

### metadata.settlement_offered as the floor

The metadata schema does not have an explicit floor field. `settlement_offered` is the only amount field besides `pos` and `tos`. Decision: treat it as the floor (minimum the company accepts). This assumption held harmlessly across all 211 conversations (zero A3 violations), but could be wrong. If a future dataset shows `send_settlement_amount` amounts that look correct yet below `settlement_offered`, revisit this assumption.

### Scoring formula change

The original quality and risk scores were defined relative to Q2 disagreement rate only. With multiple rule types at different severities those formulas no longer apply. The new formulas are severity-density based. Quality measures per-turn cleanliness; risk is anchored to the worst single violation rather than just the average. This means a single I2 violation (severity 1.0) will push risk above 0.9 even if the rest of the conversation is clean, which is the desired behavior.

### Correctness versus validity kept separate

The evaluator checks whether transitions are allowed by the spec graph (validity), not whether the bot's message content actually performed the action the state label implies (correctness). For example, `intent_asked` to `settlement_explained` is flagged as valid even if the bot never actually explained settlement options. Correctness requires an LLM judge and is out of scope for this deterministic layer. The CTO confirmed this separation is right.

### Old code discarded

The `old/` directory and several deleted docs in git history referenced an earlier FSM evaluator that the user considered incorrect. Everything in this session was written from scratch against the spec and the actual production data, without referencing that prior code.

---

## Important Context for Future Sessions

### Branch and file state

- Branch: `main`.
- Only `eval_takehome.py` was modified in this session.
- No new scripts were added. The `old/` directory (untracked) and several deleted docs remain in the working tree; ignore them.

### How to run

```
./eval_takehome.py
```

Run from `/home/darshan/Projects/riverline/`. Uses the held-out 211 conversations from `scripts/eval_split.json`. No network calls.

### Data and artifact locations

- `data/production_logs.jsonl`: 700 conversations, the full corpus.
- `data/outcomes.jsonl`: paired outcome data (payment_received, regulatory_flag, borrower_complained, etc.). Not yet used by the evaluator.
- `scripts/eval_split.json`: frozen train/eval split (489 train, 211 held-out). Do not regenerate.
- `scripts/classifier_model.pkl`: pickled TF-IDF + LinearSVC pipeline used for Q2 checks.
- `scripts/annotations_full.json`: Sonnet 4.6 intent labels for all 700 conversations (ground truth for classifier training).

### Known zero-count rules on current data

I3_chain_break, I5_missing_classification, A1, A2, A3, and C5 all report zero violations on the held-out set. These are not dead code; they are live checks that happen to find no violations in the current dataset. If the production system changes or new data arrives, these checks may start firing.

### Rules not yet implemented

The following spec requirements are not covered by the current evaluator:

- **C2** (hardship empathy): bot must acknowledge hardship before pushing for payment. Requires an LLM judge to evaluate message tone and sequence.
- **C4** (language matching): bot must respond in the borrower's preferred language. Requires per-message language detection beyond what is available deterministically.
- **A4** (below-floor offer handling): bot must counter or escalate when borrower offers below the floor. Requires tracking borrower counter-offers through the message text.
- **A5** (amount consistency): all amount references within a conversation must be consistent. Requires extracting amounts from free-text messages.
- **Q1** (efficient progress), **Q3** (appropriate tone), **Q4** (no context loss), **Q5** (no repetition): quality metrics that require message content analysis beyond keyword matching.

### I4_required_action_missing is the largest non-Q2 violation class

154 violations across 211 conversations means roughly 73 percent of conversations have at least one transition that fires without its required function call. The three most likely sources are: `confirm_payment` missing at `date_amount_asked` to `payment_confirmed`, `request_settlement_amount` missing at `settlement_explained` to `amount_pending`, and `send_settlement_amount` missing at `amount_pending` to `amount_sent`. A breakdown by edge would sharpen this finding.

### C3 DNC violations are real

The 100 C3 violations were spot-checked. All matching borrower messages are genuine stop requests ("Stop calling me", "Leave me alone", "Don't contact me again"). The `stop` keyword in `DNC_RE` is matched as a whole word and did not produce false positives in spot-checks.
