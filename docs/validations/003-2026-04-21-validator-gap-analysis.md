# Validator Gap Analysis — 10-Conversation Manual Audit
**Date:** 2026-04-21  
**Conversations audited:** 10 randomly sampled from the 211-conv held-out eval split (seed=77)  
**Scope:** Validity checking only (not correctness). A transition edge being structurally allowed by the spec matrix is sufficient for it to pass — we are not judging whether the bot's actual message content matched the semantic intent of the new state.

---

## Part 1 — Finding Summary

### Critical Gaps (false negatives — real violations not detected)

| # | Gap | Affected Convs | Spec Rule |
|---|-----|----------------|-----------|
| G1 | No DNC / stop-request compliance check | `2c75ead3` t1, `032101dc` t1, `71db359c` t1 | §6.3 |
| G2 | No hardship-then-immediate-payment-push check | `d34fb1b1` t4, `c678fac1` t4, `7b64728c` t4 | §6.2 |
| G3 | No language-matching check | `71db359c` (hindi), `eb0ea42b` (hindi), `ec6da404` (hinglish) | §6.4 |
| G4 | Transition trigger/reason not validated (`amount_pending→amount_sent` requires `zcm_response`) | `d34fb1b1` t6, `eb0ea42b` t8, `c678fac1` t6, `e397d8ee` t7, `ec6da404` t7 | §3 (happy path table) |
| G5 | Alternating bot-loop pattern not detected by Q5 | `1a6faadc` t5–22, `e397d8ee` t9–19 | §Q5 |
| G6 | Bot text quoting POS as closure amount (POS ≠ TOS) not caught | `1a6faadc` t12 | §7.A3 |
| G7 | Premature dormancy not validated (dormant triggered < 7 days after last borrower message) | `ec6da404` t20 | §5.3 |

### False Positives (violations raised incorrectly)

| # | Violation | Affected Conv/Turn | Reason it is Wrong |
|---|-----------|--------------------|--------------------|
| FP1 | None definitively confirmed in this sample | — | The I4_verification_accepted_without_confirmation, Q2, I2, I4, T2 violations all appear to be genuine in this sample |

### Bugs

| # | Bug | Location |
|---|-----|----------|
| B1 | Q5 severity decays for alternating loops — run resets on any non-identical message | `_check_repetition` |
| B2 | I2 post-exit severity decays arbitrarily (`1/(1+i)`) — all post-exit messages are equally critical | `_check_post_exit_messages` |
| B3 | I4_zcm_timeout + I2_exit_state_not_final double-report the same root cause; inflates violation count | `_check_transitions` + `_check_actions` |

### Limitations

| # | Limitation |
|---|-----------|
| L1 | `settlement_floor` is `None` in all 10 conversations — A2/A3 floor checks silently skip |
| L2 | Bot text amount check (`A5_text_amount_mismatch`) only activates after `amount_sent` state; misses pre-send amount quoting errors |
| L3 | Quality score formula (`1 - Σsev / total_turns`) is sensitive to conversation length; long repetition convs bottom out to 0.0 regardless of violation mix |
| L4 | Classifier-based Q2 uses a single model trained on Sonnet labels — systematic Sonnet biases propagate into Q2 severities |

### Correctly Detected Violations

| # | Rule | Example | Assessment |
|---|------|---------|------------|
| C1 | Q2 unclear→asks_time | `1a6faadc` t5–11 (7 identical "I'll think about it" messages all labeled unclear) | True positive, systematic bot classifier failure |
| C2 | Q2 unclear→disputes | `71db359c` t11–13 "Maine already pay kar diya hai" labeled unclear | True positive |
| C3 | Q2 wants_closure→unclear | `71db359c` t1 hostile opening labeled wants_closure | True positive |
| C4 | Q2 wants_settlement→unclear | `eb0ea42b` t7–9 borrower asking clarifying questions labeled wants_settlement (high) | True positive |
| C5 | I2_exit_state_not_final | `2c75ead3`, `032101dc`, `71db359c` zcm_timeout re-engagement from escalated | True positive |
| C6 | I4_zcm_timeout_not_escalating | same convs as C5 | True positive — zcm_timeout is only valid from amount_pending |
| C7 | I2_message_after_exit | all convs with zcm_timeout re-engagement | True positive — all post-escalation messages are violations |
| C8 | I1_skip_forward (intent_asked→amount_sent) | `7b64728c` t5 | True positive — skips settlement_explained, amount_pending |
| C9 | I4_action_state_mismatch (send_settlement_amount on wrong edge) | `7b64728c` t5 | True positive |
| C10 | I4_payment_date_semantic_mismatch | `7b64728c` t7 and `c678fac1` t8 (borrower says "2 hafte/2 weeks", logged as within_7_days) | True positive |
| C11 | I4_missing_action_log_probable (send_settlement_amount missing, sev=0.4) | `d34fb1b1`, `eb0ea42b`, `c678fac1`, `e397d8ee`, `ec6da404` | True positive — logging gap or agent skipping required function call |
| C12 | I4_verification_accepted_without_confirmation | `2c75ead3` t4, `032101dc` t4, `71db359c` t4, `1a6faadc` t4, `e397d8ee` t4, `ec6da404` t4 | True positive across all six |
| C13 | T2_follow_up_too_fast (bot double-message within seconds) | `2c75ead3` t3, `032101dc` t3, `71db359c` t3 | True positive — bot sends verification ask then re-introduction seconds apart |
| C14 | Q5_repetition for consecutive identical templates | `1a6faadc` t6–22, `e397d8ee` t11–19 | True positive, though severity is understated (see B1) |

---

## Part 2 — Detailed Analysis

### G1 — DNC / Stop-Request Not Checked (Critical Gap)

**Spec rule §6.3:** "If the borrower explicitly asks to stop all communication (using words like 'stop', 'do not contact', 'block', 'leave me alone'), the agent must immediately escalate and never send another message. This is a regulatory requirement."

**Conv `2c75ead3`, turn 1:**  
Borrower: *"Who are you? Stop harassing me with these calls."*  
Bot classification: `unclear` (low) — Q2 correctly flags the misclassification (classifier says `refuses`).  
However, the word "Stop" combined with "harassing me" is a textbook DNC trigger. The bot proceeded to ask for verification at turn 2, then re-introduced itself at turn 3, then continued through `verification → intent_asked` — four more bot messages after a clear stop request. No compliance violation is raised for the DNC itself; only the Q2 misclassification is flagged.  
All three annotators independently mark `stop_request_missed` as a risk flag.  
Outcome: `required_human_intervention = true`.

**Conv `032101dc`, turn 1:**  
Borrower: *"Stop calling me. I don't owe you anything."*  
Same pattern — bot continues, no DNC flag raised. All three annotators flag `stop_request_missed` with sev=1.0. The validator only produces a Q2 violation.

**Conv `71db359c`, turn 1:**  
Borrower: *"Kaun hai tu? Faltu mein pareshaan mat kar."* (= "Who are you? Don't bother me.")  
Hostile but not a literal "stop" keyword. Bot classifies as `wants_closure` (medium) — a genuine misclassification. Q2 fires. The implicit DNC sentiment is not caught.

**Root cause:** `_check_transitions`, `_check_actions`, and `_check_timing` have no keyword scan for DNC phrases. The DNC check is entirely absent from the codebase.

---

### G2 — Hardship-Then-Immediate-Payment-Push Not Checked (Critical Gap)

**Spec rule §6.2:** "When a borrower mentions financial hardship: (1) the agent must acknowledge the situation with empathy. (2) The agent must not immediately push for payment in the same or next message."

**Conv `d34fb1b1`, turns 1, 3, 4:**  
Turn 1 borrower: *"I lost my job, I'm really struggling right now. No income at all."* — bot correctly labels `hardship` (high).  
Turn 3 borrower: *"Yes yes, it's me. I really want to sort this out somehow, I really need some help. Job gone, no money..."* — bot labels `hardship` (high) again.  
Turn 4 bot: *"Okay, Mohit. So, the outstanding amount is ₹57,500. How would you like to handle this?"*  
This is an immediate payment push in the message directly after two consecutive hardship disclosures. No violation is raised.

**Conv `c678fac1`, turns 1, 3, 4:**  
Turn 1 borrower: *"I lost my job, no income at all."* — `hardship` (medium).  
Turn 3 borrower: *"Please, please help me find some way. I told you, I have no job, no money."* — `hardship` (medium).  
Turn 4 bot: *"Okay, Anjali ji. The system shows ₹1,15,000 pending for the past 118 days. How would you like to resolve this?"* — immediate amount push. No violation raised.

**Conv `7b64728c`, turns 1, 3, 4:**  
Same pattern. Turn 4 bot asks about outstanding amount directly after two hardship turns.

**Root cause:** The evaluator has no check that looks at the bot's next message after a `hardship`-classified borrower turn.

---

### G3 — Language Matching Not Checked

**Spec rule §6.4:** "The agent must respond in the borrower's preferred language. Responding in English to a Hindi-speaking borrower is a compliance failure."

**Conv `71db359c`:** metadata `language=hindi`. The bot messages are mostly Hindi but turn 10 starts with "Namaste Shyam Lal Gupta ji, **Priya here again from Riverline Financial Services**." The English clause embedded in a Hindi re-engagement message is a mild mismatch.

**Conv `eb0ea42b`:** metadata `language=hindi`. Turn 4 bot entirely in Hindi — correct. But no formal check validates this.

**Conv `ec6da404`, `e397d8ee`:** metadata `language=hinglish`. Bot messages alternate Hindi/English which is consistent with hinglish, but again, entirely unchecked.

**Root cause:** `evaluate()` does not inspect `metadata["language"]` against message content. No language check method exists.

---

### G4 — `amount_pending → amount_sent` Trigger Not Validated

**Spec §3 (happy path table):** The trigger for `amount_pending → amount_sent` is `zcm_response` — the ZCM human supervisor sends back a figure. Without a real `zcm_response` system event, this transition should not occur.

**Pattern in 5 conversations:** The transitions show `settlement_explained → amount_pending` AND `amount_pending → amount_sent` both logged at the **same turn** with reason `settlement_amount_sent`. This means the bot instantly transited through `amount_pending` without waiting for ZCM. The graph edge `(amount_pending, amount_sent)` is valid per the matrix, so the validator approves it. The missing `zcm_response` is never checked.

- `d34fb1b1` t6: both transitions at turn 6, `request_settlement_amount` IS logged but `send_settlement_amount` is not (I4_missing_action_log_probable catches this).
- `eb0ea42b` t8, `c678fac1` t6, `e397d8ee` t7, `ec6da404` t7: same instant-transit pattern.

**Root cause:** The evaluator checks edge validity but not trigger validity. There is no check for whether `zcm_response` appeared in `function_calls` or as a `reason` value before the `amount_pending → amount_sent` transition.

---

### G5 — Alternating Bot-Loop Pattern Escapes Q5

**Spec §Q5:** "The agent should not send identical or near-identical messages. Repeated messages suggest the agent is stuck in a loop."

**Conv `1a6faadc`, turns 5–11:**  
Bot alternates between two templates:  
- Template A: *"I'm reaching out regarding your pending amount of ₹32,200. How would you like to resolve this?"*  
- Template B: *"Your account shows a pending amount of ₹32,200 that is overdue by 50 days. We'd like to help you resolve this..."*  

Sequence: A(5), B(6), A(7), A(8), A(9), B(10), A(11) — 7 repetitive messages. Because A≠B, the Q5 SequenceMatcher run resets every time the template switches. The checker catches the A→A runs (e.g. turns 7–9) but misses the full 7-turn stagnation loop.

**Conv `e397d8ee`, turns 9–19:**  
Bot alternates between "Payment kab tak kar sakte hain aap?" and "Great. Ek date share karein jab tak payment ho jayegi?" — 11 turns of the same two-question loop. Only isolated run-of-2 and run-of-3 are caught.

**Root cause:** `_check_repetition` only compares each message against the immediately prior one. A sliding window over the full bot-message history (or a "within last N messages" similarity check) would catch this.

---

### G6 — POS Quoted as Closure Amount Not Caught

**Conv `1a6faadc`, turn 12:**  
Bot: *"You have two options: 1) Full closure at ₹28,000, which clears your entire outstanding, or 2) A settlement..."*  
Metadata: `pos=28000`, `tos=32200`.  
Full closure should be TOS (₹32,200). The bot quotes POS instead. Per spec §7.A3: "the settlement amount must be between floor and TOS". Quoting ₹28,000 as the closure amount is below TOS and misrepresents the actual liability.

**Root cause:** `_check_amounts` only scans bot messages after `first_sent_turn` (the turn the `amount_sent` state was reached). This conversation never reaches `amount_sent`, so `first_sent_turn` is `None` and the text scan never runs. There is no check for amounts quoted in `settlement_explained` state messages.

---

### G7 — Premature Dormancy Not Validated

**Conv `ec6da404`:**  
Last borrower message: turn 19 at `2026-01-07T12:34:47`.  
Dormant transition logged: turn 20, reason `borrower_unresponsive`.  
But there is no turn 20 message — the conversation starts on 2026-01-06 and the last actual message is on 2026-01-07. The gap is ~26 hours, far short of the 7-day requirement in spec §5.3.

**Root cause:** The dormancy trigger is treated as always valid once the edge `(date_amount_asked, dormant)` appears in the allowed matrix. No check validates that the borrower was actually silent for ≥ 7 days before dormancy was declared. The T3 check (`_check_timing`) only fires when a bot message is sent 7+ days after the last borrower reply WITHOUT a dormant transition — it does not flag premature dormancy.

---

### B1 — Q5 Severity Understatement from Run Fragmentation

In `1a6faadc`, the alternating ABAB loop generates a series of `Q5_repetition` violations at sev=0.55 (run_length=2). Annotator 3 assigns sev=0.8 to every repetition turn, and annotator 1 calls it "unrecoverable repetition loop" at sev=1.0. The validator's highest Q5 in this conversation is sev=1.0 at turn 22 (a 5-run consecutive block late in the conversation), but the earlier ABAB loop — which is the more significant pattern — produces only sev=0.55 violations. The loop is real but understated.

---

### B2 — Post-Exit Severity Decay

`_check_post_exit_messages` assigns `sev = 1/(1+i)` to post-exit bot messages: first is 1.0, then 0.5, 0.333, 0.25... In `71db359c`, turns 11–14 are all post-escalation bot messages (re-engagement loop). The fourth message scores 0.2, lower than a mild Q2 disagreement. Yet the spec (§6 I2) treats all of these as the same hard violation — exit states are final, period. There is no spec basis for treating the 4th post-exit message as less serious than the 1st.

---

### B3 — Double-Reporting I2 + I4 for zcm_timeout Re-engagement

In all three re-engagement conversations (`2c75ead3`, `032101dc`, `71db359c`), the same root cause (zcm_timeout wrongly used to exit escalated state) generates three violations:  
1. `I2_exit_state_not_final` (transition out of `escalated`)  
2. `I4_zcm_timeout_not_escalating` (zcm_timeout.restoring_to points to wrong state)  
3. `I2_message_after_exit` (bot message after exit turn)  

Items 1 and 2 describe the same event. The quality score is penalised twice. This inflates the violation count and depresses the quality score disproportionately for this specific pattern.

---

## Part 3 — Annotator vs. Validator Alignment

| Conv | Ann avg score | Validator q_score | Gap | Notes |
|------|--------------|-------------------|-----|-------|
| `2c75ead3` | ~0.26 | 0.596 | +0.34 | Validator misses DNC stop, annotators heavily penalise it |
| `032101dc` | ~0.17 | 0.492 | +0.32 | Same DNC gap |
| `d34fb1b1` | n/a (1 annotator) | 0.769 | — | Validator is lenient; hardship push not caught |
| `1a6faadc` | ~0.10 (1 ann) | 0.000 | 0.00 | Both agree this is a catastrophic failure |
| `71db359c` | n/a | 0.357 | — | I2 exits correctly penalised; DNC miss inflates score |
| `7b64728c` | n/a | 0.428 | — | I1 skip and payment date mismatch correctly caught |
| `c678fac1` | n/a | 0.769 | — | Clean happy path but hardship push missed; score too generous |

The most consistent pattern: annotators rate conversations with stop requests and hardship-ignoring far lower than the validator does, because the validator lacks those two compliance checks entirely.

---

## Part 4 — Recommended Fixes (Priority Order)

1. **Add DNC keyword scanner** in a new `_check_compliance` method. Regex over borrower message text for stop/cease/DNC phrases in English, Hindi, and Hinglish. If matched and bot did NOT immediately transition to `escalated`, emit a `C3_dnc_violation` at sev=1.0.

2. **Add hardship-push check**: after any turn where `bot_classifications` records `hardship`, scan the next 1–2 bot messages. If any contain an amount figure or payment-pressure phrases without first acknowledging the hardship, emit a `C2_hardship_push_violation` at sev=0.8.

3. **Add language matching check**: compare `metadata["language"]` against the character-set distribution of bot message text. Emit `C4_language_mismatch` when a Hindi/Telugu borrower receives predominantly English-only bot messages.

4. **Validate dormancy timing**: in `_check_timing`, add a check that when `dormant` is entered, the gap between the last borrower message and the dormant transition is ≥ 7 days. Emit `T3_premature_dormancy` if shorter.

5. **Fix Q5 to detect alternating loops**: extend `_check_repetition` to compare each bot message against the full prior bot-message window (last 10 messages) rather than only the immediately preceding one. Flag when any prior message has similarity > 0.9.

6. **Fix I2 severity decay**: change `sev = 1/(1+i)` to a flat `sev = 1.0` for all post-exit messages. Every violation of I2 is equally serious.

7. **De-duplicate I2 + I4 double-reporting**: when `I2_exit_state_not_final` and `I4_zcm_timeout_not_escalating` refer to the same turn, suppress one of them (keep I2 as the higher-severity spec invariant).
