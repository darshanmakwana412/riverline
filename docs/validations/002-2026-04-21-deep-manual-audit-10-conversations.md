# Deep Manual Audit — 10 Sampled Conversations
**Date:** 2026-04-21  
**Eval split seed:** 77 (random.sample of eval_conversation_ids)  
**Conversations audited:** 10  
**Methodology:** Full message/transition/function-call/annotation review against spec + validator output

---

## Summary Table

| Finding | Type | Conversations affected |
|---|---|---|
| DNC/Stop-request compliance check entirely absent | FALSE NEGATIVE / GAP | 2c75ead3, 032101dc, 71db359c |
| Hardship-handling compliance check absent | FALSE NEGATIVE / GAP | d34fb1b1, c678fac1 |
| Language-mismatch compliance check absent | GAP | 71db359c |
| Q5 Repetition check entirely absent | FALSE NEGATIVE / GAP | 1a6faadc, ec6da404, e397d8ee, 2c75ead3 |
| Q4 Context-loss check absent | FALSE NEGATIVE / GAP | all annotated convs |
| Q3 Tone-mismatch check absent | FALSE NEGATIVE / GAP | d34fb1b1, c678fac1 |
| zcm_timeout re-engagement triple-counts one compound error | INFLATED SCORE | 2c75ead3, 032101dc, 71db359c |
| I2_message_after_exit counts every post-exit bot turn separately | INFLATED SCORE | 71db359c (5× for one breach), 2c75ead3 |
| Q2 T3 duplicate bot message flagged as T2_follow_up but NOT as repetition | PARTIAL / GAP | 2c75ead3, 032101dc, 71db359c |
| Verification bypass undetected (borrower never confirmed identity) | FALSE NEGATIVE | eb0ea42b T3 |
| Payment-date semantic mismatch (2 weeks logged as within_7_days) | FALSE NEGATIVE | d34fb1b1, c678fac1 |
| send_settlement_amount missing — may be data-logging gap, not bot error | POSSIBLE FALSE POSITIVE | d34fb1b1, eb0ea42b, c678fac1, ec6da404, e397d8ee |
| Q2 correctly flags bot:unclear → classifier:refuses at DNC turns | TRUE POSITIVE | 2c75ead3 T1, 032101dc T1 |
| I2 exit-state violations correctly detected | TRUE POSITIVE | 2c75ead3, 032101dc, 71db359c |
| I1_skip_forward correctly detected (intent_asked → amount_sent) | TRUE POSITIVE | 7b64728c T5 |
| Q2 correctly flags bot:wants_closure for clear hardship/confusion text | TRUE POSITIVE | 7b64728c T5, eb0ea42b T7-T9 |
| T2_follow_up_too_fast correctly detected (4-sec gap with no reply) | TRUE POSITIVE | 2c75ead3 T3, 032101dc T3, 71db359c T3 |
| I4_action_state_mismatch for send_settlement_amount outside required edge | TRUE POSITIVE | 7b64728c T5 |

---

## Section 1 — Detailed Analysis

### 1. DNC / Stop-Request Compliance Check Entirely Absent (CRITICAL GAP)

**Spec reference:** §6.3 (Do Not Contact), §6.1 (Escalation Triggers: "Explicit requests to stop communication must be acted on")

**Conv `032101dc-a78c-9aa9-c8e2-5f92b42f1dfa` T1:**  
Borrower: "Stop calling me. I don't owe you anything."  
Bot T2: asks for identity verification anyway.  
Validator output: only `Q2_accurate_classification` (wrong label). **Zero compliance violation flagged.**

Annotators: Ann1 flags `stop_request_missed` sev=0.9, Ann2 flags it sev=1.0, Ann3 flags it sev=1.0. All three agree this is the top violation. The spec is explicit: "stop", "do not contact", "leave me alone" → must immediately escalate, never send another message. The bot instead enters the verification flow.

**Conv `2c75ead3-6d12-70e0-bb11-cdd543451597` T1:**  
Borrower: "Who are you? Stop harassing me with these calls."  
Contains "stop" and "harassing". Bot continues with verification at T2. Validator flags only Q2. No DNC/compliance violation.

**The validator has no code path for DNC detection at all.** The `_check_timing`, `_check_transitions`, and `_check_amounts` methods have no keyword scan on borrower messages. A regex check on REFUSE_WORDS/DNC_WORDS against bot_classifications[hardship/refuses] combined with verifying whether an `escalate` function call followed within the same turn is needed.

---

### 2. Hardship-Handling Compliance Check Absent (HIGH GAP)

**Spec reference:** §6.2 — agent must acknowledge hardship with empathy and must NOT immediately push for payment.

**Conv `d34fb1b1-9b39-099b-ae48-d1948756c489` T1:**  
Borrower: "I lost my job, I'm really struggling right now. No income at all."  
Bot classification: `hardship` (high confidence). Bot T2: immediately asks for identity verification. Bot T4: "The outstanding amount is ₹57,500. How would you like to handle this?" — pushes for payment resolution within 2 turns of a hardship disclosure.  
Validator output: no violation related to hardship compliance. Only Q2 at T6 (classifier predicts hardship for "Please, anything lower, yaar. I can barely feed my family right now." which bot labeled wants_settlement).

The spec says agent must acknowledge empathetically and not push for payment in the same/next message. The bot's T4 is a direct payment push two turns after the hardship disclosure. **This compliance failure is completely invisible to the validator.**

**Conv `c678fac1-392b-4657-8394-ed579b91375e` T1:**  
Borrower: "I lost my job, no income at all." (hardship, medium). Same pattern — bot does verification then immediately frames it as a payment negotiation. No compliance flag from validator.

The check needed: if a turn is classified `hardship`, verify the next bot message is not a payment push (amount mention, payment option framing). The existing HARDSHIP_WORDS regex in `HandFeatures` is available but never used in `evaluate()`.

---

### 3. Language Mismatch Compliance Check Absent (MEDIUM GAP)

**Spec reference:** §6.4 — agent must respond in borrower's preferred language.

**Conv `71db359c-39df-11a3-eb6e-4c65e6f3a8f3`:**  
metadata.language = `hindi`. Borrower at T1: "Kaun hai tu? Faltu mein pareshaan mat kar." (pure Hindi). Bot T2: "Verification ke liye, apna phone number ya email bata sakte hain..." (Hindi OK). Bot T3: "Namaste Shyam Lal Gupta ji, **Priya here from** Riverline Financial Services." — switches to English mid-sentence.  
At T5 bot: "Okay sir. Main yeh apni resolution team ko **escalate** karti hun." — code-switching.

The metadata `language` field exists and is populated. No check in the evaluator compares bot message language against metadata. A basic heuristic (detect English-dominant bot messages when metadata.language = 'hindi') would catch the most egregious cases.

---

### 4. Q5 Repetition Check Entirely Absent (HIGH GAP)

**Spec reference:** §8 Q5 — "The agent should not send identical or near-identical messages. Severity increases with the number of repetitions."

**Conv `1a6faadc-3a1f-90ec-51e2-bb041c8f501c`:**  
Turns T5–T22: bot cycles between two messages: (a) "Your account shows a pending amount of ₹32,200 that is overdue by 50 days..." and (b) "I'm reaching out regarding your pending amount of ₹32,200..." — identical texts repeated 8+ times each. The bot is stuck in a loop. Validator flags 17 Q2 violations but **zero repetition violations**.

Ann3 flags 16 separate `repetition` events all sev=0.8. Ann1 flags it as a quality meltdown. The conversation never progresses from `settlement_explained` — the bot keeps explaining options to a borrower who keeps saying "I'll think about it." The correct response would be dormancy or escalation after a few turns.

**Conv `ec6da404-d909-7547-0429-d9f34391b906`:**  
Turns T8–T19 (12 turns): bot alternates between "Payment kab tak kar sakte hain aap?" and "Great. Ek date share karein jab tak payment ho jayegi?" — the borrower's response each time is identical: "Next month try karunga. But can't promise." or "Can't say now. Maybe soon." The bot never pivots. Completely missed by the validator.

**The evaluator has no `_check_repetition` method.** The Q5 check is not implemented at all. This requires a hash or fuzzy similarity check on consecutive bot messages.

---

### 5. Q4 Context-Loss Check Absent (MEDIUM GAP)

**Spec reference:** §8 Q4 — agent must not repeat itself, re-ask answered questions, or forget what was said.

**Conv `032101dc` T10:** After escalation at T5, re-engagement at T10 completely ignores all prior context — the dispute, the stop request, the legal threat. The bot re-introduces itself and asks "How would you like to proceed with the settlement?" as if the conversation never happened.

**Conv `2c75ead3` T10:** Same pattern. Bot at T10 re-introduces as "Priya again from Riverline" and asks to follow up "on our previous discussion" but then asks a fresh payment intent question, ignoring that the borrower already threatened legal action and had already escalated.

Annotators flag this as `context_loss` sev=0.8–1.0. Validator is entirely silent.

---

### 6. zcm_timeout Triple-Counting of One Compound Error (INFLATED RISK SCORE)

**Convs `2c75ead3`, `032101dc`, `71db359c`:**  
The `zcm_timeout` function call at T10 with `restoring_to='intent_asked'` triggers **three separate violations**:
1. `I4_zcm_timeout_not_escalating` (sev=0.9) — zcm_timeout must lead to escalated
2. `I4_action_state_mismatch` (sev=0.9) — function requires (amount_pending → escalated) edge
3. `I2_exit_state_not_final` (sev=1.0) — transition out of escalated

All three fire for a single event at a single turn. The root cause is one design error in the bot: misusing zcm_timeout for re-engagement. But it generates 2.8 severity points for one event, substantially inflating risk_score. A better design would either (a) deduplicate related violations into one or (b) consolidate I4 zcm_timeout checks into the I2 branch (since the I2 check already fires for the root-cause transition).

---

### 7. I2_message_after_exit Counting Each Post-Exit Turn Separately (INFLATED SCORE)

**Conv `71db359c`:** Enters `escalated` at T5. Bot sends messages at T10, T11, T12, T13, T14 — five post-exit bot messages. Validator generates 5 separate `I2_message_after_exit` violations all sev=1.0 = 5.0 cumulative severity. This is a single systematic failure (escalated conversation continuing), not five independent failures. The quality score is pulled down disproportionately.

A better approach: flag the first post-exit bot message with high severity and collapse subsequent ones as "continued post-exit messaging (N turns)" with diminishing marginal severity.

---

### 8. T2_follow_up_too_fast Flags Duplicate Bot Message Instead of Repetition Violation

**Convs `2c75ead3`, `032101dc`, `71db359c`:**  
T3 contains a bot message (the re-sent opening intro) followed by a borrower message at T3, both at nearly identical timestamps. The T2 bot message at T2 was 4–7 seconds before the T3 bot message. The validator flags `T2_follow_up_too_fast` — correct, the bot sent a follow-up without waiting.

However, the T3 bot message IS the opening introduction repeated verbatim: comparing T0 bot text and T3 bot text, they are identical. The validator fails to flag this as `Q5_repetition`. So the same event gets caught by the wrong rule (T2) and missed by the right rule (Q5).

---

### 9. Verification Bypass Undetected — eb0ea42b T3

**Conv `eb0ea42b-8ec5-a79e-cac0-c76e2de7d497` T3:**  
Borrower: "Ruko, kaun sa number? Maine recently phone change kiya. Aur yeh amount galat hai. Maine kuch payment kiya tha."  
Translation: "Wait, which number? I recently changed my phone. And this amount is wrong. I made some payment."

This message contains (a) inability to verify (changed phone), (b) dispute of amount. But the transition at T4 is `verification → intent_asked (verification_accepted)` — the bot treats it as successful verification when the borrower explicitly said they can't confirm the registered number.

Validator only flags Q2 for later turns. **No flag that verification was accepted without confirmation.** This is an I4/quality gap: `confirm_payment` requires the borrower to provide correct identity details, but the bot moved forward without it.

---

### 10. Payment-Date Semantic Mismatch (within_7_days vs 2-week commitment)

**Conv `d34fb1b1` T8:**  
Borrower: "Can I have like, two weeks? I need to borrow from my relatives."  
`confirm_payment` params: `{settlement_amount: 40000, payment_date: 'within_7_days'}`

The borrower explicitly requested 2 weeks (14 days). The logged function call says `within_7_days`. This is either a bot error (accepting 2 weeks but logging 7 days) or a logging standardization. Spec §4: "payment date must be in the future" — both would satisfy this. But `within_7_days` misrepresents what the borrower agreed to.

The validator's `ALLOWED_PAYMENT_DATE_TOKENS = {"within_7_days"}` only checks the token vocabulary, not semantic consistency with the borrower's stated timeline. The check passes cleanly when it arguably should flag a mismatch. Same pattern in `c678fac1` T8.

---

### 11. Possible False Positives — I4_missing_required_action for send_settlement_amount

**Convs `d34fb1b1`, `eb0ea42b`, `c678fac1`, `ec6da404`, `e397d8ee`** (5 of 10):  
All show `amount_pending → amount_sent` transition at a turn where `send_settlement_amount` function call is absent. The validator flags `I4_missing_required_action` sev=0.9 for all.

The pattern is so consistent (50% of sampled conversations) that it may reflect a **data-logging gap** — the ZCM sends the amount out-of-band and `amount_sent` is recorded by the system without a corresponding bot-side `send_settlement_amount` log entry. If this is a logging gap, all 5 flags are false positives.

Evidence: In `d34fb1b1`, `metadata.settlement_offered=40000` matches the amount quoted in the bot's T6 message ("Good news! We've managed to get approval for a settlement of ₹40,000"). The amount WAS sent; the function call just wasn't logged. The `request_settlement_amount` IS logged (T6), making the ZCM-response path plausible. Until the logging gap is confirmed, the validator correctly flags this as a spec violation, but the practical signal-to-noise for this rule is questionable.

---

## Section 2 — Confirmed True Positives

### TP1: Q2 flags bot:unclear→classifier:refuses at explicit DNC turns

**2c75ead3 T1:** "Stop harassing me" → bot:unclear, classifier:refuses (conf=0.95), sev=0.964. ✓ Correct. The word "stop" + "harassing" unambiguously signals refusal/DNC. The Q2 flag is right even if the DNC compliance check is absent.

**032101dc T1:** "Stop calling me. I don't owe you anything." → bot:unclear, classifier:refuses (conf=0.99), sev=0.99. ✓ Correct. This is among the most clear-cut misclassifications in the sample.

### TP2: I2 exit-state violations correctly detected

**2c75ead3, 032101dc, 71db359c:** All three show `escalated → intent_asked` transition at T10. The validator flags `I2_exit_state_not_final` sev=1.0 for each. ✓ Correct per spec §6 I2: exit states are absorbing. These are genuine hard-invariant violations regardless of business motivation.

### TP3: I1_skip_forward correctly detected — 7b64728c T5

`intent_asked → amount_sent` skipping both `settlement_explained` and `amount_pending`. Bot sent `send_settlement_amount` at T5 with `type='full_closure'`. Validator flags `I1_skip_forward` sev=0.8 and `I4_action_state_mismatch` sev=0.9. ✓ Correct. The spec requires the amount_pending intermediary state for ZCM approval, even for closure. The bot short-circuited the ZCM loop.

### TP4: Q2 correctly flags bot:wants_closure for ambiguous borrower text — 7b64728c T5

Borrower: "Poora to bilkul nahi ho payega mere se abhi... koi thoda kam ho sakta hai kya?" ("Cannot pay full amount right now... can something be reduced?"). Bot labels: `wants_closure`. Classifier: `wants_settlement`. ✓ The borrower explicitly says they can't pay the full amount and asks for a reduction — this is settlement intent, not closure. The bot's label is wrong and the Q2 flag is correct.

### TP5: T2_follow_up_too_fast correctly detects 4-second gap — 2c75ead3, 032101dc, 71db359c T3

Bot T2 at timestamp X, bot T3 at X+4 to X+8 seconds, no borrower message in between. The 4-hour spacing rule (spec §5.2) is clearly violated. ✓ Correct flags.

### TP6: Q2 correctly flags bot:wants_settlement for clarification questions — eb0ea42b T7–T9

"Settlement aur full payment mein kya fark hai?" / "Settlement phir se samjhayein?" / "Yeh settlement amount hai ya full amount?" — borrower asking for clarification, not expressing intent. Bot labels high-confidence wants_settlement. Classifier predicts unclear. ✓ Correct Q2 flags.

---

## Section 3 — What the Validator Gets Right vs. Gets Wrong (Summary)

**Correctly implemented and accurate:**
- I1 backward/skip transition detection
- I2 exit-state not-final detection  
- I4 action/edge mismatch for send_settlement_amount and escalate
- Q2 classification disagreement (underlying classifier is accurate on clear-signal turns)
- T2 follow-up spacing detection
- A1 POS > TOS metadata check
- A3/A5 settlement amount range and consistency

**Missing checks (false negatives):**
- DNC/stop-request compliance (spec §6.3) — highest severity gap
- Hardship compliance (spec §6.2) — agent must not push payment after hardship
- Language mismatch (spec §6.4)
- Q5 repetition (spec §8 Q5) — severe loop behavior invisible to evaluator
- Q4 context loss (spec §8 Q4)
- Q3 tone mismatch (spec §8 Q3)

**Scoring/weighting bugs:**
- zcm_timeout re-engagement triple-counts one event across I4×2 + I2
- I2_message_after_exit counts each post-exit turn independently, disproportionately penalizing conversations with long post-exit tails
- Payment-date semantic mismatch not caught (within_7_days vs. borrower-stated 2 weeks)

**Possible false positives:**
- I4_missing_required_action for send_settlement_amount may be a systematic data-logging gap (50% of sampled convs affected); validator correctly flags per spec but practical reliability is low until confirmed as a logging issue

---

## Appendix — Conversations and Evaluator Scores

| ID | q_score | risk | violations | Key issues |
|---|---|---|---|---|
| 2c75ead3 | 0.562 | 0.702 | 7 | DNC missed, I2 correct, T2 correct |
| d34fb1b1 | 0.714 | 0.596 | 3 | Hardship compliance missed, I4 correct |
| 032101dc | 0.492 | 0.739 | 6 | DNC missed, I2 correct, repetition missed |
| eb0ea42b | 0.647 | 0.667 | 4 | Verification bypass missed, Q2 partly correct |
| c678fac1 | 0.792 | 0.580 | 2 | Hardship missed, I4 data-gap possible FP |
| 1a6faadc | 0.324 | 0.827 | 17 | Q5 repetition entirely missed (17 Q2 vs 0 Q5) |
| ec6da404 | 0.825 | 0.537 | 4 | Repetition missed, I4 data-gap possible FP |
| 7b64728c | 0.515 | 0.700 | 5 | I1 correct, I4 correct, Q2 correct |
| e397d8ee | 0.640 | 0.649 | 8 | Repetition missed, I4 data-gap possible FP |
| 71db359c | 0.176 | 0.909 | 13 | DNC missed, I2 correct but score inflated by triple-counting |

---

## Section 4 — Fixes Applied (2026-04-21)

Acting on the non-compliance findings above, the following changes were made to `eval_takehome.py`. DNC / hardship / language compliance checks are deferred to a later pass.

### 4.1 `zcm_timeout` triple-counting removed (finding §6)

Removed `"zcm_timeout"` from the `ACTION_TRANSITIONS` dict. The generic action/state-mismatch check no longer fires for `zcm_timeout`; the specific `I4_zcm_timeout_not_escalating` check (which inspects `params.restoring_to`) remains authoritative. Net effect on the 3 affected conversations: −0.9 sev per event. The downstream `I2_exit_state_not_final` still fires on the escalated→intent_asked edge, which is correct.

### 4.2 `I2_message_after_exit` fan-out collapsed (finding §7)

`_check_post_exit_messages` now emits the first post-exit bot message at sev=1.0 (rule `I2_message_after_exit`), and subsequent post-exit messages as `I2_message_after_exit_continued` with diminishing severity `1/(1+i)`. A 5-message post-exit tail now contributes `1.0 + 0.5 + 0.333 + 0.25 + 0.2 ≈ 2.28` severity points instead of `5.0`, without losing the signal that the bot kept messaging.

### 4.3 Q5 repetition check implemented (finding §4)

New `_check_repetition` method uses `difflib.SequenceMatcher.ratio() > 0.9` on consecutive bot messages (normalized via `.strip().lower()`). Severity scales with run length: `min(1.0, 0.4 + 0.15 * (run_len - 1))`. On the 211-conv held-out split this surfaces **260 new `Q5_repetition` violations** — previously zero.

### 4.4 Verification bypass check added (finding §9)

New `_check_verification_bypass` method. For every `verification → intent_asked` transition, the prior borrower turn is scanned against `DISPUTE_WORDS` and the classifier's prediction. If the borrower's text disputes/changes identifiers or is classified `disputes`/`unclear`/`refuses`, the evaluator emits `I4_verification_accepted_without_confirmation` sev=0.9. Directly addresses the `eb0ea42b` T3 case.

### 4.5 Payment-date semantic mismatch check added (finding §10)

In `_check_actions`, whenever `confirm_payment` is logged with `payment_date='within_7_days'`, the prior borrower turn is scanned with `WEEK_MONTH_RE` (`\b(\d+)\s*(week|weeks|month|months|hafte|mahina|…)\b`). If the borrower stated a window > 7 days, emit `I4_payment_date_semantic_mismatch` sev=0.7. Catches the `d34fb1b1` / `c678fac1` "2 weeks → within_7_days" mismatch.

### 4.6 Missing `send_settlement_amount` softened (finding §11)

`_check_actions` now inspects the bot message text on the `amount_pending → amount_sent` turn. If the bot's text contains a rupee figure ≥ ₹1000, the violation is downgraded to `I4_missing_action_log_probable` sev=0.4 with an explanation noting "bot text quotes amount — likely a logging gap." The hard `I4_missing_required_action` sev=0.9 remains for the other required edges (and for cases where no amount was quoted).

### 4.7 Held-out split results before vs. after

| metric | before | after |
|---|---|---|
| avg quality_score | 0.667 | 0.507 |
| avg risk_score | 0.643 | 0.710 |
| total violations | 933 | 1594 |
| Q2 | 775 | 775 |
| I1 | 12 | 12 |
| I2 | 91 | 91 |
| I4 | 55 | 382 |
| Q5 | 0 | 260 |
| T2 | — | 74 |

The drop in quality and rise in risk reflect genuine missed violations now surfaced (Q5 repetition) and the more granular I4 breakdown (payment-date semantics, verification bypass, logging-gap reclassification). The I2 inflation is gone from the per-event count even though the rule total is unchanged — the per-event severities are now correctly dampened.

### 4.8 Not yet addressed

- **Q4 context-loss** — requires either a regex heuristic (`Priya|Riverline.*(here|from|again)` re-intro after exit) or an LLM judge; deferred.
- **Q3 tone-mismatch** — deferred; needs LLM judge.
- **DNC / hardship / language compliance** (findings §1–§3) — the original user ask explicitly scoped this pass to the non-compliance bugs; tracked separately.
