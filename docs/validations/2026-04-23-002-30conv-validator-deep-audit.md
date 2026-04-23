# Validator Deep Audit — 30 Conversations (Full Spec Coverage)

**Date:** 2026-04-23  
**Scope:** 30 randomly sampled conversations (seed=42) from full production_logs.jsonl (700 convs)  
**Checks evaluated:** All implemented checks — Q2, I1–I5, A1–A5, T0–T3, C3, C5, Q4, Q5  
**Checks explicitly skipped (not yet implemented):** Q1, Q3, C1, C2, C4

---

## Summary of Findings

### Bugs / False Positives

| # | Type | Rule | Conversation(s) | Description |
|---|------|------|-----------------|-------------|
| B1 | False Positive | Q2_accurate_classification | 9f4cad57 turn 8, b6bde107 turn 9 | Payment commitment messages misclassified as `asks_time` because time-related keywords ("Friday", "3 days", "within") trigger classifier. Semantic meaning is a commitment, not a time request. |
| B2 | False Positive | Q2_accurate_classification | 9f4cad57 turn 5 | "I'd definitely like to sort this out. What options do I have?" — both `wants_settlement` and `wants_closure` are plausible. Bot said `wants_settlement`, classifier says `wants_closure`. Neither is wrong. |
| B3 | False Positive (borderline) | Q2_accurate_classification | 91faad79 turn 1 | "Piss off. Wrong number." — classifier detects "wrong" keyword → `disputes` (0.53 confidence), but "Wrong number" semantically means wrong contact, not amount dispute. Low confidence makes this a borderline false positive. |
| B4 | Severity too low | A4_closure_not_tos | Appears in ~20/30 conversations | Severity clamped to minimum 0.4 for all closure misquotes. The relative deviation is ~13% (POS vs TOS), but this is a systematic agent bug affecting every conversation — severity should be 0.7+. |

### False Negatives / Missed Violations

| # | Type | Rule | Conversation(s) | Description |
|---|------|------|-----------------|-------------|
| F1 | Missed | A4_closure_not_tos | b6bde107 turn 6 | Hindi/Hinglish: "poora ₹3,80,000 ek baar mein dekar account close kar sakte hain" — CLOSURE_KW regex misses `account close kar` pattern. Only matched English and some Hindi phrases. |
| F2 | Missed | (C1 not impl.) | 91faad79 turn 1, 18047863 turn 5 | "Piss off." and "I'll talk to my lawyer." are mandatory escalation triggers (abusive language, legal threat) per spec §7.1. Agent should immediately escalate but does not at turn 1. Only escalation at turn 5 is detected via I2. |
| F3 | Missed | (C2 not impl.) | bd080e56 (job loss), eaa4c64e (job+medical), 01d2bc92 | Borrowers disclose severe hardship. Spec §7.2 requires empathy acknowledgement and no immediate payment push. Bot pivots to payment options in same/next turn. Not detected. |
| F4 | Missed | C3 delayed escalation | 032101dc, 7d118cdb, 18047863 | C3_dnc_violation correctly fires for messages AFTER DNC trigger, but does not flag that escalation was DELAYED. Spec requires IMMEDIATE escalation when DNC is triggered. Bot sent 2–3 messages before escalating at turn 5. |
| F5 | Missed | (Q1 not impl.) | 698ced97 (14 turns), a0a868e2 (5 turns), d70454f9 (8 turns) | Conversations stuck in `settlement_explained` or `intent_asked` for many turns with borrower repeatedly expressing clear payment intent. Q1 (efficiency) not implemented. |
| F6 | Missed | semantic confirm_payment | 01d2bc92 turn 9 | Borrower says "Honestly nahi pata kab ho payega 😞 Thoda time chahiye mujhe sochne ke liye..." — explicitly uncertain. Bot confirms payment with `payment_date: 'within_7_days'`. No semantic validation of whether borrower actually committed. |
| F7 | Regex gap | A4_closure_not_tos | b6bde107 turn 6, various Hindi convs | CLOSURE_KW regex lacks: `\b(account close|close kar)\b`, `\bpoora\b.{0,20}\b(dekar|deke)\b`. Systematically under-detects closure amount misquotes in Hindi/Hinglish conversations. |

### Correctly Detected (True Positives — Key Patterns)

| # | Rule | Pattern | Example |
|---|------|---------|---------|
| TP1 | A4_closure_not_tos | Bot consistently quotes POS instead of TOS for "full payment/closure" option | bd080e56 turn 5: "full payment ₹1,00,000" but TOS=115000, POS=100000. Appears in ~20/30 conversations. |
| TP2 | I4_required_action_missing | Bot skips `send_settlement_amount` when transitioning amount_pending→amount_sent | Nearly all conversations with that transition path. Function call absent; amount only mentioned in text. |
| TP3 | I2_exit_not_final + I4_action_wrong_state | `zcm_timeout_reengagement` pattern: after escalation, bot re-engages via `escalated→intent_asked` with `zcm_timeout` function call | 032101dc, c1cffa15, 91faad79, 7d118cdb, 18047863 all turn 10. |
| TP4 | C3_dnc_violation | DNC signals correctly detected and post-DNC bot messages flagged | 032101dc: "Stop calling me. I don't owe you anything." turn 1 → 5 subsequent bot messages. |
| TP5 | Q2_accurate_classification | Bot classifies clear intents as `unclear` — particularly wants_settlement, wants_closure, asks_time, refuses | d70454f9 turns 5-11: "Main pay karna chahta hun. Options batayein?" classified as unclear 7 times. |
| TP6 | Q5_repetition | Bot sends identical messages repeatedly | 698ced97: 2 alternating messages for 14 turns; d70454f9: same message 8x. |
| TP7 | Q4_reintroduction | Bot re-introduces itself after escalation+reengagement | 032101dc, 91faad79, 7d118cdb all turn 3. |
| TP8 | I1_invalid_transition | settlement_explained→amount_sent (skipping amount_pending) | d70454f9 turn 13, b6bde107 turn 7. |
| TP9 | A3_full_closure_not_tos | `send_settlement_amount` with type=full_closure and amount≠TOS | d70454f9 turn 13: amount=200000 type=full_closure but TOS=230000; b6bde107 turn 7: amount=380000 but TOS=437000. |
| TP10 | T1_quiet_hours | Initial outbound bot messages late at night IST | d70454f9 turn 0: 14:37 UTC = 20:07 IST; 7d118cdb turn 0: 18:36 UTC = 00:06 IST. |
| TP11 | T2_followup_too_soon | Rapid follow-up bot messages (< 4h) with no borrower reply | 032101dc turns 2-3: 0h gap; eaa4c64e turns 2-3: 5 second gap. |
| TP12 | Q2 for DNC/refusal misclassified as wants_closure | Bot classifies DNC request as payment intent | 18047863 turn 1: "Mujhe baar baar message karna band karo" → bot says wants_closure. |

---

## Detailed Analysis

### Systemic Bug 1: POS Quoted Instead of TOS for Full Closure (A4_closure_not_tos)

**Conversations:** bd080e56, 03f02884, eaa4c64e, 59147cd2, 55d0c883, 698ced97, 2c55a668, 9a367ccb, 9f4cad57, 01d2bc92 and ~10 more  
**Spec ref:** §8.A3: Settlement amount must be between floor and TOS. For full closure, amount = TOS.

In every conversation with a full payment/closure option presented, the bot quotes POS instead of TOS:
- `bd080e56`: "full payment ₹1,00,000" but POS=100000, TOS=115000 (diff: ₹15,000)
- `9f4cad57`: "full closure at ₹1,50,000" but POS=150000, TOS=165000 (diff: ₹15,000)
- `698ced97`: "full payment of ₹28,000" but POS=28000, TOS=32200 (diff: ₹4,200)

The validator correctly detects these but severity is clamped to 0.4 (because relative deviation ~13% gives `0.3 + 0.7*0.13 = 0.39`, clamped to 0.4 minimum). This severity is too low given the violation is systematic and misleads borrowers about what full payment means. Recommended minimum severity: 0.7.

**A4 text check gap for Hindi/Hinglish:**  
`b6bde107` turn 6: "poora ₹3,80,000 ek baar mein dekar account close kar sakte hain" — TOS=437000, bot quotes 380000 (=POS). The CLOSURE_KW regex does not match "account close kar sakte" or "poora ... dekar account close". The English pattern "close the account" and Hindi pattern "account band karna" are present but "account close" variant is missing.

### Systemic Bug 2: send_settlement_amount Function Never Called (I4_required_action_missing)

**Conversations:** bd080e56, 03f02884, eaa4c64e, 59147cd2, 55d0c883, 2c55a668, 9a367ccb, b4e40ff4, 01d2bc92, cef7d0f9 and others  
**Spec ref:** §5, Actions table: `send_settlement_amount` only during transition from `amount_pending` to `amount_sent`.

In every conversation where `amount_pending→amount_sent` transition occurs, `request_settlement_amount` is called but `send_settlement_amount` is never called. The amount is quoted in bot text but the formal function call is absent. Pattern:
```
Function calls: [(6, 'request_settlement_amount'), (8, 'confirm_payment')]
State transitions: [..., (6, 'settlement_explained', 'amount_pending'), (6, 'amount_pending', 'amount_sent'), ...]
```
Both transitions at same turn 6, with only `request_settlement_amount` present. The validator correctly flags I4_required_action_missing consistently.

### Systemic Bug 3: zcm_timeout Reengagement After Escalation (I2_exit_not_final)

**Conversations:** 032101dc, c1cffa15, 91faad79, 7d118cdb, 18047863  
**Spec ref:** §6.I2: Once escalated, conversation is over. §5, zcm_timeout valid only from `amount_pending`.

All 5 conversations follow the same pattern:
1. Escalation triggered at turn 5 (`intent_asked → escalated`)
2. `escalate` function called with `reason: 'borrower_requested'`
3. 5 turns later (turn 10): `escalated → intent_asked` with `reason: 'zcm_timeout_reengagement'`
4. `zcm_timeout` function called with `params: {waited_turns: 5, restoring_to: 'intent_asked'}`
5. Bot sends another message at turn 10

This violates I2 (exit state not final), uses `zcm_timeout` at wrong transition (should only be `amount_pending → escalated`), and triggers T2 (0h gap between turn 5 and 10 bot messages). All correctly detected.

Note: The `zcm_timeout` misuse is particularly problematic — the function is designed for amount timeout, not for reengagement logic.

### False Positive Pattern: Payment Commitment → asks_time (Q2)

**Conversations:** b6bde107 turn 9, 9f4cad57 turn 8, bd080e56 turn 8  
**Issue:** ML classifier systematically classifies payment commitment texts as `asks_time` because they contain temporal keywords.

Examples:
- `b6bde107` turn 9: "Main is Friday tak kar dunga payment, pakka." (I WILL pay by Friday, definitely) → classifier says `asks_time` (0.97 confidence). This is a firm commitment, not a time request. Bot says `unclear` (also wrong).
- `9f4cad57` turn 8: "I should be able to make the payment within the next 3 days." → classifier says `asks_time` (0.98). This is a payment timeline, not asking for delay.
- `bd080e56` turn 8: "2 weeks mil sakte hain kya? Relatives se lena padega..." → this one IS genuinely `asks_time` (requesting 2 weeks). Correctly classified.

The feature `TIME_WORDS` regex matches "Friday", "days", "within" etc. which are present in both asking-for-time AND providing-a-timeline messages. The classifier cannot distinguish direction of time reference (requesting vs providing). This is a known limitation of keyword-based features.

### Missed: Hindi/Hinglish CLOSURE_KW Coverage

**Conversation:** b6bde107 turn 6  
**Bot text:** "Aapke paas basically 2 options hain — ek toh poora ₹3,80,000 ek baar mein dekar account close kar sakte hain..."  
**TOS=437000, POS=380000**

The CLOSURE_KW regex in `_check_amount_text` includes:
```
"account band karna|deke account band|band karne ke liye"
```
But NOT `"account close kar"` or the pattern `poora ... dekar ... close`. The amount 380000 would be tagged as "generic" not "closure", so A4_closure_not_tos doesn't fire for this text mention.

Suggested fix: Add `\b(account close|close kar|close karne)\b` and `\b(ek baar mein)\b` with surrounding context to CLOSURE_KW.

### Missed: Delayed DNC Escalation

**Conversations:** 032101dc, 7d118cdb, 18047863  
**Spec ref:** §7.3 DNC: "must immediately escalate and NEVER send another message"

In all three conversations, the DNC signal occurs at turn 1 (e.g., "Stop calling me", "Mujhe baar baar message karna band karo"). The bot escalates at turn 5, not turn 1. The C3_dnc_violation check correctly fires for post-DNC messages, but does not flag the 4-turn delay in escalation itself.

A stricter check would verify: if DNC is detected at turn N, the next state transition must be to `escalated`. The current check only counts messages after DNC, not the delayed escalation.

### Annotator Agreement vs Validator

For `032101dc` (DNC + I2 violations): All 3 annotators gave scores 0.10–0.30 with multiple risk flags including `stop_request_missed`, `compliance_concern`. Validator's C3 and I2 violations align with annotator concerns, though annotators additionally flagged `hardship_ignored` and `context_loss` at turns not caught by the validator (C2 not implemented).

For `01d2bc92`: Annotator scores ranged 0.28–0.80 (high inter-annotator variance). Annotator 1 flagged `state_machine_error` at turn 4 (bot disclosed balance before completing verification) and `amount_error` at turn 8 (amount inconsistency ₹55,000→₹54,500). Validator caught neither of these. The A5_settlement_inconsistent check only looks at `settlement`-tagged mentions; ₹55,000 was tagged as `closure` so the cross-type inconsistency was missed.

### Interesting Edge: Multi-Message Same Turn

**Conversation:** eaa4c64e turn 5  
Two distinct bot messages exist at turn 5:
1. `ts=16:38:16`: "Mujhe sunke bura laga aapki situation. Hum aapka saath dene ko tayyar hain." (empathy)
2. `ts=16:38:18`: "Aapke paas options hain — full payment ₹60,000 ya reduced settlement..." (payment push)

The T2 check correctly fires for the second message (2-second gap, no borrower reply). The T1 check correctly exempts the first message (borrower was in quiet hours) but fires for the second (last_was_borrower=False after first bot msg). Both are correctly handled.

The spec compliance issue (C2: immediate payment push after hardship) is not caught because C2 is not implemented.

---

## Summary Statistics

- **Conversations analyzed:** 30
- **Violations found:** 182 total across 30 conversations
- **Confirmed true positives:** ~165 (90.7%)
- **Confirmed false positives:** ~8 (4.4%) — primarily Q2 payment commitment misclassifications
- **Missed violations (false negatives) in-scope:** ~4–6 (A4 Hindi regex gap, C3 delayed-escalation precision)
- **Missed violations out-of-scope (C1, C2, C4, Q1, Q3 not implemented):** ~30+ estimated

## Recommendations

1. **Increase A4_closure_not_tos severity minimum from 0.4 to 0.7** — systematic agent bug.
2. **Add Hindi/Hinglish closure variants to CLOSURE_KW**: `account close kar`, `close karne`, `ek baar mein deke`.
3. **Q2 classifier improvement**: Add contextual features distinguishing time-requesting vs time-providing (e.g., future tense markers, "kar dunga", "able to pay by").
4. **Add C3 sub-check for delayed escalation**: Flag when DNC is detected but next transition is NOT to `escalated`.
5. **Implement C1 (abusive language escalation trigger)**: Pattern-match abusive language like "Piss off", "shut up", "stop calling" → must immediately escalate.
6. **Implement Q1 (efficiency)**: Flag conversations stuck in same state for >3 turns with forward-intent borrower messages.
