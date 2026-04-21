# Evaluator Assumptions

Documents every assumption, scope decision, and ambiguity resolution made while
implementing the timing, action/event, and amount-validation checks in
`eval_takehome.py`. Each entry cites the spec section it interprets and the data
observation that motivated the call.

---

## 1. Amount validation (spec §7)

### A1.1 — `settlement_floor` is absent from the dataset
**Observation:** A full scan of all 700 conversations shows metadata keys
`{language, zone, dpd, pos, tos, settlement_offered, total_turns}`. No conversation
carries a `settlement_floor` field, and no `function_calls.params` exposes it.

**Decision (1a):** Implement only floor-independent rules:
- `A1_pos_exceeds_tos` — POS ≤ TOS (spec §7.A1).
- `A3_amount_above_tos` — settlement amount ≤ TOS (upper half of §7.A3).
- `A3_amount_nonpositive` — amount > 0 (implicit guard).
- `A5_amount_inconsistent` — consistency across function calls (§7.A5).
- `A5_text_amount_mismatch` — bot-quoted ₹ figures agree with approved amount (§7.A5).

**Skipped with note:** §7.A2 (floor ≤ POS), §7.A3 lower bound (floor ≤ amount),
§7.A4 (counter with floor). All three require floor data the dataset does not
expose. Flagged in the writeup, not silently dropped.

### A1.2 — "Approved settlement amount" source of truth
**Priority order for A5 text-vs-amount check:**
1. The latest `send_settlement_amount.params.amount` function call, else
2. the latest `confirm_payment.params.settlement_amount`, else
3. `metadata.settlement_offered` as a final fallback.

**Why:** The §7.A5 rule is "once the agent quotes a settlement amount, all
subsequent references must be consistent". Function-call params are the machine-
authoritative record of what the bot quoted; metadata is the system's stored
answer. Both are used.

### A1.3 — Rupee parsing from bot text (3b)
- Regex: `(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)`.
- Only figures ≥ ₹1,000 are compared, to suppress noise from non-monetary
  numbers (e.g. "3 days", "office at 9").
- Check only runs on bot messages at or after the first
  `amount_sent`-landing transition, so POS/TOS mentions during the
  `settlement_explained` phase (e.g. "full closure at ₹1,50,000") don't
  trigger false A5 flags.
- A mismatch is flagged only when **none** of the parsed figures ≥ ₹1,000 in a
  single message matches the approved amount. A message that quotes both POS
  and the settlement amount is not flagged.

### A1.4 — A5 consistency across function calls
A new `send_settlement_amount.amount` or `confirm_payment.settlement_amount`
that differs from the previously-quoted amount is flagged as
`A5_amount_inconsistent`. Spec §7.A5 permits ZCM re-approval to replace the
previous amount, but no `zcm_response` function call exists in the dataset to
signal this, so every change is flagged. Treated as a conservative flag, not a
hard error.

---

## 2. Timing (spec §5)

### A2.1 — T2 sort key (bug fix)
**Previous bug:** Messages were sorted by `(turn, role_bias)`. When a bot
follow-up and the borrower's next reply shared the same turn number, the
borrower message was placed first, updating `last_borrower_ts` before the bot
follow-up was evaluated — silently skipping T2 entirely.

**Fix:** Sort by `(timestamp, turn)` so wall-clock order drives the state
machine in `_check_timing`. This matches the intent of §5.2 (at least 4 hours
between consecutive bot messages with no borrower reply in between).

### A2.2 — T1 "replying to a quiet-hours borrower" rule
**Spec §5.1:** "If the borrower sends a message during quiet hours, the agent
may reply." Interpreted as: the bot is exempted only if the **most recent**
borrower message (anywhere in the conversation, not only immediately prior)
arrived during quiet hours and has not yet been replied to.

**Implication:** A bot-initiated follow-up chain entirely within the quiet
window still trips T1 on messages after the first — consistent with "the agent
must not initiate messages during this window."

### A2.3 — Quiet window boundaries
`QUIET_START_HOUR = 19`, `QUIET_END_HOUR = 8`. "Between 7 PM and 8 AM IST" is
read as `[19:00, 08:00)`. Timestamps in the dataset are treated as IST as-is;
no timezone offset is applied (the spec is IST-only and no timestamps carry
offsets).

### A2.4 — T3 dormancy check (4b)
**Spec §5.3 / §3.6:** 7-day borrower silence must transition to `dormant`.

**Added check:** If a borrower reply is followed, anywhere in the message
stream, by a bot message ≥ 7 days later, and the conversation never entered
`dormant`, flag `T3_missed_dormancy_transition`.

**Not flagged:** A 7-day gap with no subsequent bot message (there is no
compliance harm — the conversation simply stalled). Also not flagged:
conversations that correctly transitioned to `dormant` on the expected turn.

### A2.5 — Messages after the exit turn are ignored for timing
If the conversation reaches `escalated` or `dormant`, timing checks stop at
the exit turn. Post-exit bot messages are already covered by
`I2_message_after_exit` and should not generate duplicate T1/T2 flags.

---

## 3. Actions, function calls, and system events (spec §4, §3.2)

### A3.1 — Bidirectional I4
`_check_actions` now enforces both directions:
1. **Action → transition** (already existed): a function call must coincide
   with its required edge.
2. **Transition → action** (new): a transition that requires an action must
   have that action recorded.

The second direction is driven by `REQUIRED_ACTION_FOR_EDGE`:

| Edge | Required function |
|------|-------------------|
| `settlement_explained → amount_pending` | `request_settlement_amount` |
| `amount_pending → amount_sent` | `send_settlement_amount` |
| `date_amount_asked → payment_confirmed` | `confirm_payment` |

**`escalate`** is deliberately excluded from the reverse check: §3.3 lists
many trigger conditions for escalation (DNC, refusal, dispute, hardship,
keywords, zcm_timeout), and not all of them require the bot to call
`escalate` itself — the CTO guidance is to treat action/state direction as
the primary enforcement ("escalate must always lead to `escalated`") and
leave the reverse implication as scope-bounded.

### A3.2 — `zcm_timeout` treated as a system event, not a bot action (5)
**Ambiguity:** `zcm_timeout` appears in both spec §3.2 (system events) and
§4 (actions).

**Decision:** Treat as a system event whose required landing edge is
`amount_pending → escalated`. This is the earlier `fsm_evaluator.md` ruling
and is kept unchanged.

**New sub-check:** `zcm_timeout.params.restoring_to` must equal `"escalated"`.
108 calls in the full dataset set `restoring_to: "intent_asked"` — these
now fire `I4_zcm_timeout_not_escalating` in addition to the existing
`I4_action_state_mismatch`.

### A3.3 — `confirm_payment.payment_date` token vocabulary (2a)
**Observation:** All 384 `confirm_payment` calls in the dataset carry
`payment_date = "within_7_days"` — a window token, not a parseable date.

**Decision:** Instead of the spec-literal "date must be in the future"
check, validate that `payment_date` ∈ an allowed vocabulary
(`ALLOWED_PAYMENT_DATE_TOKENS = {"within_7_days"}`). Anything outside
the vocabulary fires `I4_invalid_payment_date`. This preserves the spec's
intent ("the agent commits to a real future payment window") while
matching the data's shape.

**Not implemented:** Parsing the token into an absolute date and comparing
to the conversation timestamp. The spec defines no mapping from
`"within_7_days"` to a concrete date and the dataset does not carry one.

---

## 4. Scope decisions carried over from earlier iterations (kept unchanged)

### A4.1 — Validity vs. correctness
The evaluator checks whether transitions are **allowed** by the matrix, not
whether the bot's message content actually fulfils the semantic claim of
the new state (e.g. did the bot actually explain settlement before moving to
`settlement_explained`?). Correctness belongs to an LLM-judge layer and is
explicitly out of scope. CTO-endorsed.

### A4.2 — Self-transitions are always valid
`from_state == to_state` rows are skipped entirely in `_check_transitions`,
per spec §3.2 ("staying in the current state is always valid").

### A4.3 — Q2 trusts the classifier's label
`_check_q2` treats any classifier-vs-bot disagreement as a Q2 violation.
Known false-positive class (audit finding): classifier mislabels payment
commitments like "I'll take care of it within 3 days" as `asks_time`. Scope-
excluded from this iteration (user direction: "leave false positive and
DNC/compliance detection for now").

### A4.4 — `bot_classifications.input_text` mismatch (data integrity)
39.7% of `input_text` entries do not match the actual borrower message at
the same turn. The evaluator runs its own classifier on the real message
text, so the resulting Q2 signal is "classifier on real text" vs "bot label
on paraphrased text". This is acknowledged as a data-integrity artefact per
the audit and is not a bug in the evaluator. Out of scope for this pass.

---

## 5. Out of scope for this iteration

Per user direction:
- DNC / compliance keyword detection (spec §6.1, §6.3).
- Q2 false-positive filtering.
- Q5 repetition detection (spec §Q5).
- Language-matching compliance (spec §6.4).
- "No threats" content check (spec §6.5).
- Hardship empathy / "don't immediately push for payment" check (spec §6.2).
- Correctness checks on whether bot messages semantically fulfil state claims.

Each will need its own pass; most require either a keyword/regex layer
(DNC, threats, language) or an LLM judge (empathy, repetition severity,
correctness).
