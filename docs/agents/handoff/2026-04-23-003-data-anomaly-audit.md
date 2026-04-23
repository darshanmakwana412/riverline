# Handoff: Data Anomaly Audit

**Date:** 2026-04-23
**Session focus:** Ran a fresh structural audit of everything under `data/` (`production_logs.jsonl`, `outcomes.jsonl`, `annotations/annotator_{1,2,3}.jsonl`) to catalogue anomalies and data-quality issues. No code in the repo was changed. Audit scripts live at `/tmp/audit_data.py` and `/tmp/audit2.py` (outside the repo, reproducible by rerunning).

---

## What Was Accomplished

Produced a complete anomaly inventory across the three data files. Counts below are from 700 conversations, 700 outcome rows, and 3 x 200 annotation rows (100 conversations triple-annotated).

### Bot classifier input drift (confirmed and quantified)

The `bot_classifications[*].input_text` field is often not the borrower message at that turn:

- 3,343 entries match the borrower message at the same turn.
- 2,166 entries match a borrower message from a different turn in the same or another conversation (off-turn drift).
- 33 entries do not appear anywhere in the borrower corpus (fabricated text).
- Off-corpus entries by class: 21 `unclear`, 12 `wants_settlement`.
- Dominant fabricated string: `"Please, anything lower. I barely have enough to feed my family."` labeled `wants_settlement` across many conversations despite being textbook `hardship`.

This matches the CLAUDE.md note but the counts are larger than previously documented.

### Turn-numbering structure

- 4,256 turns contain one borrower and one bot message (the shared-turn pattern from turn 5 onward).
- 56 turns contain one borrower and two bot messages (same-turn bot double-send). This is a new finding and is not currently detected by any rule in `eval_takehome.py`.
- One case of a bot message that is a verbatim echo of the borrower text at the same turn: conversation `192f029c-2626-7e25-7fee-3fff275530b7`, turn 5.

### State machine anomalies present in the data

- 61 self-loops where `from_state == to_state == "escalated"`. Exit states are supposed to be absorbing per I2.
- 272 bot messages occur at turns after a transition into `escalated` or `dormant` has already been recorded. I2 already catches these.
- 700 `new to new` self-loops exist as initialization markers and are benign.

### Function-call anomalies

- `confirm_payment.payment_date` is the literal string `"within_7_days"` in all 384 confirmations. It is never a concrete date, which makes the spec rule "payment date must be in the future" structurally unverifiable against this data. Any future check on payment-date recency should treat this as an opaque token rather than parse it.
- `send_settlement_amount.amount` is always within `[settlement_offered, tos]`. The A3 numeric check will fire zero times on numeric amounts alone, which is why the text-extraction path `_check_amount_text` is the one that surfaces A3 and A4 issues.

### Outcomes vs. final state (label noise)

- 179 conversations end in `payment_confirmed` but `outcomes.payment_received == False`.
- 12 end in `dormant` and 9 end in `intent_asked` yet `payment_received == True` (plausible back-channel payments, or injected label noise).
- All 215 rows with `payment_received == True` have `payment_amount != expected_amount`. Every single one. Either by design or systematic mismatch.
- Outcome label counts: `payment_received` 215 true / 485 false, `required_human_intervention` 288 true, `borrower_complained` 78 true, `regulatory_flag` 22 true.
- `channel_attribution` is `None` for 485 rows (exactly the `payment_received=False` rows) and one of `certain/uncertain/likely/unlikely` for the remaining 215.

### Metadata integrity

Clean. Across all 700 conversations: 0 `pos > tos`, 0 `settlement_offered > pos`, 0 missing pos/tos/floor, 0 negative TOS, 0 duplicate conversation IDs, 0 timestamp inversions, 0 missing texts, 0 missing timestamps, 0 unsorted turn arrays, 0 `bot_classifications` rows pointing at a turn with no borrower message.

### Annotations

- Fields per row: `conversation_id, quality_score, failure_points, risk_flags, overall_assessment, _annotator, _model`.
- The `_model` field on every row indicates the annotators are themselves LLM-generated, not human. Treat agreement or disagreement accordingly.
- 100 conversations are annotated by 2 or more annotators. Trivial key-based disagreement scan reported 0 disagreements, but that used a simple equality over `quality` fields and did not examine `failure_points` or `risk_flags` contents, so inter-annotator agreement on the substantive fields is still open.

### Classification confidence distribution

Heavily skewed toward `(unclear, low)` at 3,122 of roughly 5,500 total classifications. Next largest are `(asks_time, medium)` 800, `(wants_settlement, high)` 540, `(wants_settlement, medium)` 272. The `unclear+low` dominance is what unlocks the allowed backward transition in the FSM, so any classifier-replacement experiment needs to preserve that distribution or the I1 backward-exception check will flip.

---

## Key Decisions

- Scope limited to anomaly discovery. No evaluator rules added or modified this session. Two candidates identified for future work: (a) a new check for same-turn double bot messages (56 cases) and (b) an outcome-vs-final-state consistency check that would flag the 179 `payment_confirmed` + `payment_received=False` rows as suspected label noise rather than real evaluator failures.
- Audit scripts were deliberately kept in `/tmp` rather than committed, since they are one-shot exploratory and the findings are what gets preserved.

---

## Important Context for Future Sessions

- Data locations: `data/production_logs.jsonl` (700 convs), `data/outcomes.jsonl` (700 rows, one per conversation, keyed by `conversation_id`), `data/annotations/annotator_{1,2,3}.jsonl` (200 rows each, 100 of which overlap across all three annotators).
- The top-level README was renamed to `INFO.md` this session (the CLAUDE.md was updated to reflect this). The file itself was not modified.
- The correct field name on `bot_classifications` entries is `input_text`, not `message`. An earlier version of the audit used the wrong key and reported zero drift before being corrected.
- The correct field on `outcomes` is `payment_received` (boolean), not `final_outcome`. Use `final_outcome` only for state-machine end state via the last `state_transitions` entry.
- `confirm_payment.payment_date` being the literal `within_7_days` token is intentional data shape, not corruption. Do not add a future-date parser.
- Branch status at session start: `main`, clean tree. No commits made this session. The CLAUDE.md edit arrived mid-session via an external linter or user action and is unrelated to this audit.
- Prior handoffs `2026-04-23-001` and `2026-04-23-002` already address Q2 dedup, I4 `send_settlement_amount`, and Q4/Q5/C3. This handoff does not overlap with those.
