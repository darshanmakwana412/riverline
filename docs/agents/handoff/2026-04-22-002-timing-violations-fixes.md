# Handoff: Timing Violation Fixes and Dormancy Check

**Date:** 2026-04-22
**Session focus:** Audit the timing violation checks in `eval_takehome.py` against the spec, fix two bugs in T1 and the timestamp sort, add missing timestamp flagging (T0), implement the dormancy timing check in both directions (T3_early_dormancy and T3_missed_dormancy), and fix missing-timestamp handling to use forward-fill instead of dropping messages.

---

## What Was Accomplished

### All changes are in `eval_takehome.py`

**Bug 1 -- T1 reply exception was too broad (fixed)**

The spec states: "No outbound messages between 7 PM and 8 AM IST. However, if the borrower sends a message during quiet hours, the agent may reply."

The previous implementation used `not last_was_borrower` as the exception gate, which exempted any bot message that followed a borrower message regardless of when the borrower sent theirs. A borrower sending at 17:00 and the bot replying at 21:00 was wrongly exempted.

Fix: track a second flag `last_borrower_in_quiet` alongside `last_was_borrower`. The T1 exception now fires only when both flags are true -- the borrower's message itself was sent during quiet hours.

```python
if in_quiet and not (last_was_borrower and last_borrower_in_quiet):
    # flag T1
```

**Bug 2 -- Timestamp sort was string-based (fixed)**

The previous sort was `sorted(messages, key=lambda m: m.get("timestamp", ""))`. Messages without timestamps received `""` which sorted before all real timestamps, corrupting the sequential `last_bot_ts` and `last_was_borrower` tracking for both T1 and T2.

Fix: replaced with a pre-processing pass described below.

**New check -- Missing bot timestamps flagged as T0**

Bot messages with missing or unparseable timestamps are flagged as `T0_missing_timestamp` at severity 0.4. Borrower messages with missing timestamps are not flagged (only outbound bot timing is subject to spec rules).

**Missing-timestamp handling changed from drop to forward-fill**

Previously, any message without a timestamp was dropped entirely from processing, which broke role tracking (`last_was_borrower`) for subsequent messages and could cause false T1/T2 suppression or false fires.

New approach: sort all messages by turn, then walk forward keeping `last_known_dt`. A message with no timestamp inherits `last_known_dt`. If no prior message has a timestamp yet (i.e. the very first messages lack timestamps), `dt` remains `None` and the message is skipped for timing checks only -- role tracking still updates. This preserves the sequential state machine correctly while still flagging T0 for bot messages.

```python
for m in sorted(messages, key=lambda m: m["turn"]):
    dt = _parse_ts(m.get("timestamp"))
    if dt is None:
        if m["role"] == "bot":
            # flag T0
        dt = last_known_dt   # inherit; may still be None if no prior timestamp exists
    else:
        last_known_dt = dt
    resolved.append((dt, m))
```

**New check -- Dormancy timing (T3), both directions**

The spec requires (Section 6.3): "If the borrower has not responded for 7 days, the conversation should be marked as dormant." There were two missing checks.

`_check_dormancy(messages, transitions)` now handles both:

1. `T3_early_dormancy` (severity 0.7): a dormant transition exists but the gap between the last borrower message and the transition is less than 7 days. 17 violations on the current eval split.

2. `T3_missed_dormancy` (severity 0.8): the bot sent a message more than 7 days after the last borrower reply, and no dormant transition had occurred at or before that turn. Flags only the first bot message per silence gap (`gap_flagged` resets on each new borrower message). 0 violations on the current eval split -- every conversation with a 7+ day gap correctly transitioned to dormant before the bot sent another message. This check is live for the hidden test set.

`T3_missed_dormancy` is severity 0.8 (higher than `T3_early_dormancy` at 0.7) because messaging a non-responding borrower violates the spec more directly than triggering dormancy a day early.

**Final results on the 211-conversation held-out split**

```
avg quality_score: 0.494
avg risk_score:    0.924
total violations:  1481
per-rule counts:
  Q2_accurate_classification:   775
  I4_required_action_missing:   154
  T1_quiet_hours:               160
  T2_followup_too_soon:         117
  C3_dnc_violation:             100
  I2_message_after_exit:         66
  I4_action_wrong_state:         55
  I2_exit_not_final:             25
  T3_early_dormancy:             17
  I1_invalid_transition:         12
```

T0 and T3_missed_dormancy are both zero on this split. All messages in the current dataset have timestamps, so forward-fill has no effect here. Both checks are defensive measures for the hidden test set.

---

## Key Decisions

### T1 exception scope

The spec's wording is unambiguous: the exception applies only when the borrower sends during quiet hours. The previous "last message was borrower" heuristic introduced false negatives regardless of when the borrower sent.

### Forward-fill over drop for missing timestamps

Dropping a message from processing breaks the role-tracking state machine. A borrower message with no timestamp followed by two bot messages would make the second bot message appear to follow a borrower reply, suppressing T1 and T2 incorrectly. Forward-fill preserves sequencing while still flagging T0. The first-message edge case (no prior timestamp to inherit) falls back to skipping timing checks only.

### T3 uses message timestamps, not transition metadata

State transitions do not carry timestamps in the data schema. The dormancy trigger turn is resolved by walking backward from the transition turn to find the nearest message with a valid timestamp. If no such message exists, the early-dormancy check is skipped rather than flagging spuriously.

### T3_missed_dormancy flags once per silence gap

The check resets `gap_flagged` on each new borrower message. This means a single silence gap of 7+ days produces at most one `T3_missed_dormancy` violation (at the first offending bot message), rather than one per subsequent bot message in the same gap.

### _parse_ts extracted as a shared helper

The timestamp parsing logic is shared between `_check_timing` and `_check_dormancy`.

---

## Important Context for Future Sessions

### Branch and file state

- Branch: `main`.
- Only `eval_takehome.py` was modified in this session.
- The module docstring at the top lists all rule codes including T0, T3_early_dormancy, and T3_missed_dormancy.

### How to run

```
./eval_takehome.py
```

Run from `/home/darshan/Projects/riverline/`. Uses the 211-conversation held-out split from `scripts/eval_split.json`.

### All messages in the current dataset have timestamps

Verified across all 12,179 messages in `data/production_logs.jsonl`. T0 and the forward-fill are purely defensive for the hidden test set.

### T3_missed_dormancy and T0 are canaries for the hidden test set

Zero on the current split does not mean the hidden set is clean. Do not remove or lower the priority of either check.

### Rules still not implemented

Unchanged from the previous handoff. The following spec requirements have no coverage:

- **C2** (hardship empathy): requires LLM judge for tone and message sequencing.
- **C4** (language matching): requires per-message language detection.
- **A4** (below-floor offer handling): requires extracting borrower counter-offer amounts from free text.
- **A5** (amount consistency): requires amount extraction across multiple messages.
- **Q1, Q3, Q4, Q5**: quality metrics requiring message content analysis.
