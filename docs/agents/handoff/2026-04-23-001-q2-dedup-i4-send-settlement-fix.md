# Handoff: Q2 Duplicate Deduplication and I4 send_settlement_amount Fix

**Date:** 2026-04-23
**Session focus:** Two evaluator bugs identified in the state-transition invariant audit (`docs/validations/2026-04-22-003-state-transition-invariant-audit.md`) were fixed in `eval_takehome.py`. Bug 1 (BUG-1) caused Q2 violation counts to inflate by 7-16x due to shared turn numbers. Bug 2 (BUG-2) caused the `I4_required_action_missing` rule to fire identically regardless of whether the missing function call existed elsewhere in the conversation or was truly absent.

---

## What Was Accomplished

All changes are in `/home/darshan/Projects/riverline/eval_takehome.py`. No other files touched.

### Bug 1: Q2 duplicate inflation fix

**Root cause:** The data has a known quality issue (documented in `CLAUDE.md`) where bot and borrower share the same turn number from turn 5 onward. The same borrower text appears verbatim at multiple consecutive turns, each with a separate `bot_classifications` entry. `_check_q2` was iterating over every turn independently, firing one `Q2_accurate_classification` violation per turn for what is a single underlying misclassification. In affected conversations (`d70454f9`, `698ced97`, `fe67f506`) this produced 7-16 identical violations from a single bad label.

**Fix:** Rewrote `_check_q2` to group violations by `(text, bot_classification, predicted_class)` key before emitting. Within each group, the maximum classifier confidence is used as the base severity and a log-scale multiplier `(1 + 0.1 * log(count))` is applied to scale severity upward with repetition count without capping unfairly. A single violation is emitted at the first turn of the group with an explanation that includes `x{count}` and the full list of turns. Severity is capped at 1.0.

Before: a conversation with 16 identical misclassifications produced 16 violations with total severity ~9.6.
After: one violation with severity slightly above the single-occurrence baseline, roughly 1.1x-1.3x depending on count.

### Bug 2: I4 send_settlement_amount conversation-wide check

**Root cause:** The I4 `REQUIRED_ACTION` check compared function call presence at the exact same turn as the state transition. `send_settlement_amount` was required at the turn of `amount_pending -> amount_sent`. In the production data, this call is systematically absent from the normal flow (460 conversations have the transition, zero have the call at the same turn), making this a 100% fire rate. Separately, 41 conversations have `send_settlement_amount` calls but no `amount_pending -> amount_sent` transition (they skip `amount_pending` via an I1 invalid transition). These two failure modes were independent and correctly caught. However, the check gave no distinction between a call that was genuinely absent from the entire conversation versus one that existed but was logged at the wrong turn.

**Fix:** Added a module-level set `CONV_WIDE_ACTIONS = {"send_settlement_amount"}`. When the required action is not found at the transition turn, the check now falls back to searching `all_call_fns` (the set of all function names in the conversation). If the call exists somewhere else in the conversation, a lower-severity `I4_required_action_wrong_turn` violation (severity 0.6) is emitted instead of `I4_required_action_missing` (severity 0.9). If the call is absent from the entire conversation, the original `I4_required_action_missing` fires unchanged. The `CONV_WIDE_ACTIONS` set is intentionally limited to `send_settlement_amount` for now; other required actions (`request_settlement_amount`, `confirm_payment`) are not candidates because the data does not exhibit the same turn-alignment issue for them.

---

## Key Decisions

- **Q2 grouping key uses text, not just classification pair.** If two different borrower messages both have the same `(bot_class, pred_class)` mismatch, they represent distinct classification errors and should not be merged. The text is included in the key to keep semantically distinct errors separate.
- **Log-scale severity multiplier, not linear.** A linear multiplier would make a conversation with 16 repetitions 16x worse than one with 1, reintroducing the inflation problem in a different form. `log(count)` grows slowly and reflects diminishing marginal information from each additional duplicate.
- **`CONV_WIDE_ACTIONS` as an explicit set, not a general policy.** Making all required-action checks conversation-wide would suppress true per-turn violations for `request_settlement_amount` and `confirm_payment`. The set makes the relaxation opt-in per action.
- **`I4_required_action_wrong_turn` at 0.6, not silenced.** A misaligned call is still a data integrity concern. Dropping it entirely would hide turn-logging bugs. The lower severity reflects that the intent was present, just mis-attributed in the log.
- **No changes to scoring formulas or other rules.** `quality_score` and `risk_score` computations are unchanged.

---

## Important Context for Future Sessions

### Results on the eval split after fixes (211 conversations)

```
avg quality_score: 0.519
avg risk_score:    0.896
total violations:  1397

per-rule counts:
  A3_full_closure_not_tos:    12
  A4_closure_not_tos:        153
  C3_dnc_violation:          100
  I1_invalid_transition:      12
  I2_exit_not_final:          25
  I2_message_after_exit:      66
  I4_action_wrong_state:      55
  I4_required_action_missing: 154
  I4_required_action_wrong_turn: 0  (none in eval split -- all 41 misaligned conversations lack the transition)
  Q2_accurate_classification: 526
  T1_quiet_hours:            160
  T2_followup_too_soon:      117
  T3_early_dormancy:          17
```

The `Q2_accurate_classification` count (526 after dedup) was previously in the thousands due to duplicate inflation. The `I4_required_action_wrong_turn` count is zero on this split because the 41 conversations with misaligned `send_settlement_amount` calls skip `amount_pending` entirely via an I1 violation, so the `amount_pending -> amount_sent` edge never fires in those conversations and the fallback branch is not reached. It will likely fire on the hidden test set if a conversation has both the transition and the call at a different turn.

### Remaining open gaps from the audit doc

The following gaps from `docs/validations/2026-04-22-003-state-transition-invariant-audit.md` are not yet addressed:

- **GAP-1:** Semantic verification bypass (bot transitions `verification -> intent_asked` before the borrower actually confirms identity). Requires NLP-based check on the borrower message preceding the transition.
- **GAP-3:** Bot re-introduction repetition (Q4/Q5). Bot resends verbatim opening message at turn 3 in multiple conversations. No repetition checker exists yet.
- **GAP-4:** Hardship-response sequencing (bot pushes payment in the same message as empathy). Requires tracking empathy acknowledgement then checking the next message from the bot.

### Files and data

- Production logs: `data/production_logs.jsonl`
- Eval split: `scripts/eval_split.json` (211 IDs)
- Classifier bundle: `scripts/classifier_model.pkl`
- Spec: `spec.tex`
- Audit doc this session addressed: `docs/validations/2026-04-22-003-state-transition-invariant-audit.md`

### Running the evaluator

The script is a uv executable. Run with `./eval_takehome.py`. Direct `python3 eval_takehome.py` will fail; sklearn is not in the global interpreter.

### Branch status

Working on `main`. No commits made this session. Changes confined to `eval_takehome.py` and this handoff document.
