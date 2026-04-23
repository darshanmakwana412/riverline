# Validator Audit — 30 Conversations (seed=2026, Full Spec Coverage)

**Date:** 2026-04-23
**Sample:** 30 conversations randomly drawn (seed=2026) from full `data/production_logs.jsonl` (700 convs, train+eval combined).
**Script:** `scripts/audit_sample_30.py` → `docs/validations/_audit_30_seed2026.json`
**Checks evaluated:** Q2, I1–I5, A1–A5, T0–T3, C3, C5, Q4, Q5 (all currently implemented)
**Checks explicitly out of scope (not implemented):** Q1, Q3, C1, C2, C4

## Aggregate

| rule | count |
|---|---|
| Q2_accurate_classification | 67 |
| Q5_repetition | 22 |
| A4_closure_not_tos | 20 |
| I4_required_action_missing | 19 |
| T2_followup_too_soon | 15 |
| T1_quiet_hours | 14 |
| I2_message_after_exit | 12 |
| I4_action_wrong_state | 9 |
| I2_exit_not_final | 6 |
| C3_dnc_violation | 6 |
| Q4_reintroduction | 3 |
| I1_invalid_transition | 1 |
| A3_full_closure_not_tos | 1 |

No violations of: I3 (chain continuity), I5 (missing classification), A1/A2/A3 numeric-bounds, A5 (inconsistency), C5 (threats), T0 (bad timestamps), T3 (dormancy). 19/30 conversations had ≥1 annotator; 11 unannotated.

---

## Findings Summary (FPs, FNs, gaps, correct calls)

### Bugs / False Positives

| # | Rule | Conversations | Description |
|---|---|---|---|
| FP1 | Q2_accurate_classification | fa4453e4 t8, d03b8e7f t8, 87d6c412 t9, 30305fdd t9–18, 8baafe5a t10, 9b5396d7 t10, 56b43383 t9+, 9c22c31e t8, 97eaaa71 t9 | Payment-commitment texts ("Friday tak kar dunga", "3 din mein payment", "Next month try karunga", "Month end tak kar dunga", "Can't say now, Maybe soon") get predicted `asks_time` by our classifier because of temporal keywords. The *semantics* can be either a commitment with a timeline (→ wants_settlement/wants_closure) or a stall (→ asks_time); a single label is not well-defined. Bot's `unclear` is often a legitimate reading, so firing Q2 with severity 0.9–1.0 is an over-confident false positive driven by our classifier's keyword bias. |
| FP2 | Q2_accurate_classification | d03b8e7f t7, dbba942b t7–t8, 87d6c412 t7, 9b5396d7/8baafe5a t5–7 | Bot labels "Settlement aur full payment mein kya fark hai?" / "samjhauta karna hai. Amount check karein" as `wants_settlement`/`wants_closure` while classifier says `unclear`. Per spec these are questions/clarifications ("what is the difference?") not intent statements; `unclear` is defensible. Our validator still flags bot as wrong — disagreement is real but *either label is defensible*; firing at sev 0.9+ is mis-calibrated. |
| FP3 | A4_closure_not_tos severity | 20 conversations (every case) | The check is correct ("bot quoted POS as full-closure figure when TOS is higher") but severity is universally clamped to the 0.4 floor because `(TOS−POS)/TOS ≈ 10–15%`. Since this is a *systematic* misquote that misleads every borrower in the sample, the severity floor is too low relative to its recurrence and semantic impact. |
| FP4 | C3 severity ceiling | 0c704508, 3e63b7d2, 2c75ead3, b656cf58, bd61f339 (all cap at 1.0) | Severity formula `min(1.0, 0.7 + 0.1·(count−1))` saturates at 4+ post-DNC messages. In b656cf58 the bot sent 6 messages over 2 re-engagements after DNC — still sev 1.0, same as a 4-message case. Scaling beyond 1.0 is not possible, so we collapse distinguishable severity bands. |
| FP5 | Q5_repetition turn attribution | bd61f339 / 87d6c412 / b6bde107 (not in sample but pattern) | `Q5_repetition` records the turn of the *2nd* occurrence rather than the first. In 30305fdd the 10-message repetition is reported at turn 12 not turn 9, which makes it harder to correlate with annotations that flag the *onset*. |

### False Negatives / Detection Gaps

| # | Rule | Conversations | Description |
|---|---|---|---|
| FN1 | Delayed-escalation after DNC | 0c704508, 3e63b7d2, 2c75ead3, b656cf58, bd61f339 | Spec §7.3: DNC → *immediate* escalation. In all 5 convs the bot sends 2–4 messages (verification, repeat of amount, intent question) before escalating at turn 5. Our C3 check counts post-DNC bot messages but does not isolate "delay between DNC and escalate()" as a specific, higher-severity violation. Annotators uniformly flag `stop_request_missed` at turn 1–2, while our first C3 entry is at turn 2 with the same lenient flat severity. |
| FN2 | Escalation-trigger keywords (legal threats) | 2c75ead3 t5 "I'll talk to my lawyer", b656cf58 t5/t11, bd61f339 t5 "Mere lawyer se baat karo", a5f2726d t5 "mere lawyer se baat karo", 3e63b7d2 t5 "Apne vakil se baat karke dekhta hun" | Spec §7.1 requires immediate escalation for legal threats/"references to regulatory bodies". We have THREAT_RE for outbound bot threats (C5) but no inbound borrower-legal-threat detector. Annotators consistently tag these as `missed_escalation`. (Note: user asked to skip C1 — this is one implementation of that skipped check.) |
| FN3 | Hardship handling | 0c704508 (new_job), d03b8e7f (job loss), 3e63b7d2 (new_job), 2c75ead3 (family_help), a5f2726d | Borrowers disclose serious hardship ("Job chali gayi meri, koi income nahi hai"); bot pivots to verification or repeats the outstanding amount in the same or next turn. §7.2 requires empathy and *not* pushing payment. Not implemented (C2). Annotators flag `ignored_hardship` / `hardship_ignored`. |
| FN4 | Borrower commitment without real commitment (confirm_payment semantic) | dbba942b t10, 30305fdd t18+ (never confirmed), 9b5396d7, 8baafe5a | `confirm_payment` is called with `payment_date: "within_7_days"` even when the borrower said "Kab pay kar sakta hun pata nahi. Sochne do" or cycled "Can't say now. Maybe soon" 10 times. This is a state-machine/semantic issue: bot is not meeting the spec's "borrower provides a date" precondition for `date_amount_asked → payment_confirmed`. Our I4 only checks the function *exists* at the right transition, not that the confirmation is substantively valid. Could be an A/I or a Q1 issue; currently falls through. |
| FN5 | I1 infinite date-ask loop w/o progression | 30305fdd (t8–t18), 9c22c31e, 56b43383, 97eaaa71 | Bot loops in `date_amount_asked` for 10+ turns asking the same question. Self-transitions are always valid per spec so no I1 fires, and Q5 covers the repetition surface. But there's no explicit check for "stuck in a state beyond N self-transitions" (part of Q1 — out of scope). Worth noting because annotators label this as `state_machine_error`. |
| FN6 | Amount-text parser misses Hindi closure phrasing | Not observed in this sample | Known from prior audit (seed=42, b6bde107 t6: "poora ₹3,80,000 ek baar mein dekar account close kar sakte hain"). CLOSURE_KW lacks `account close kar`, `poora.*deke`. Flagged for completeness; this sample didn't hit it. |
| FN7 | 1d72c76b regulatory_flag without any spec violation surfaced | 1d72c76b | Outcome has `regulatory_flag=True` but validator only fires 2 Q2 + 1 Q5 (total sev modest). Conv is a 9-turn loop where bot repeats the same "account shows ₹92,000 pending" line while borrower keeps asking "I want to pay. Options kya hain?". No DNC, no hardship, no amount error. The regulatory flag is plausibly from *business-side* (inaction/failure to progress), which none of our implemented rules capture. Suggests missing Q1 (efficient progress) is an important signal for regulatory risk. |

### Correct Detections (True Positives)

| # | Rule | Example conv / turn | Why correct |
|---|---|---|---|
| TP1 | Q2_accurate_classification | 3e63b7d2 t1 "Band karo ye sab. Mujhe kuch nahi dena. Dobara phone mat karna" → bot said `wants_closure`, classifier `refuses` | Clear bot misclassification; borrower refuses + DNC. Annotators all tag this. |
| TP2 | Q2 | 0c704508 t1 "Stop messaging me. I don't owe you people anything" → bot `unclear`, classifier `refuses` | Text is unambiguously refuses+DNC; bot's `unclear` is wrong. |
| TP3 | Q2 | b656cf58 t1, 2c75ead3 t1, bd61f339 t1, dbba942b t7, 87d6c412 t5 | All clear-intent messages labelled `unclear` by bot. Matches spec I5's definition of misclassification. |
| TP4 | I2_message_after_exit + I2_exit_not_final | 3e63b7d2 t10, 2c75ead3 t10/11, b656cf58 t10/16, bd61f339 t10/11, a5f2726d t10, 0c704508 t10 | Systemic `zcm_timeout_reengagement` pattern: 5 turns after `escalate`, bot synthesises `escalated → intent_asked` and sends a follow-up. Clearly violates spec §4, Invariant I2, and uses `zcm_timeout` outside its only legal transition (`amount_pending → escalated`). |
| TP5 | I4_action_wrong_state for zcm_timeout | Same convs as TP4 | Spec §5: `zcm_timeout` only valid from `amount_pending`. Here it fires from `escalated`. |
| TP6 | I4_required_action_missing for send_settlement_amount | dbba942b t8, d03b8e7f t6, 30305fdd t6, 9b5396d7 t6, 8baafe5a t6, 53f043a8 t6, 9c22c31e t7, 97eaaa71 t6, 66263e7c, 56b43383 t6, 00d924eb, 1cd0f4fb, cff8ad9c, e04bbd3e, fa4453e4 t6, 81c4761 t6, 201a9fdc, d305f19e, 92f60be8 | Every happy-path conv that transitions `amount_pending → amount_sent` is missing the `send_settlement_amount` function call. The amount is only in bot text; no structured action is recorded. Systemic agent bug; correctly flagged 19/30. |
| TP7 | A4_closure_not_tos | 20 convs | Bot consistently offers "full closure = POS" instead of TOS. E.g., dbba942b: quoted 25,000, TOS=28,750. Strict spec violation (§8, A3 note). |
| TP8 | A3_full_closure_not_tos | 87d6c412 t7 | `send_settlement_amount(amount=95000, type=full_closure)` but TOS=109,250. Strict numeric violation. |
| TP9 | C3_dnc_violation | 0c704508 t1 "Stop messaging", 3e63b7d2 t1 "Dobara phone mat karna", 2c75ead3 t1 "Stop harassing me", b656cf58 t1 "Stop messaging", bd61f339 t1 "Stop calling me. Mujhe kuch nahi dena" | DNC_RE correctly fires in English and Hinglish ("phone mat", "band karo") phrasings. Post-DNC bot turns are enumerated. |
| TP10 | T1_quiet_hours | dbba942b t0 (20:45 IST), 3e63b7d2 t0/t3/t10 (23:32 IST), 9b5396d7 t0 (20:35 IST), 8baafe5a t0 (21:09 IST), 30305fdd t0 (23:11 IST), 56b43383 t0 (21:45 IST), 9c22c31e (21:47 IST), fa4453e4 (20:34 IST) | First outbound messages in the forbidden 19:00–08:00 IST window. Matches spec §6.1 exactly. |
| TP11 | T2_followup_too_soon | 0c704508 t3, 2c75ead3 t3/t10, bd61f339 t10, 3e63b7d2 t3/t10, a5f2726d t3/t10, b656cf58 t10/t16, 53f043a8 t5 | All < 4h gaps between consecutive bot messages with no borrower reply in between. |
| TP12 | Q4_reintroduction | 0c704508 t3, 2c75ead3 t3, a5f2726d t3 | "Priya here again from Riverline" after intro at t0. Matches INTRO_RE and the "only at turn 0" rule. |
| TP13 | Q5_repetition | dbba942b t5 (3×), 30305fdd (two loops 4× and 10×), 1d72c76b (4× at t4–t8), 97eaaa71, 9c22c31e, 56b43383, 53f043a8, 9b5396d7, 8baafe5a | Bot loops identical strings; thresholding on 2+ occurrences is clearly meeting the spec's Q5 intent. |
| TP14 | I1_invalid_transition | 87d6c412 t7 (`settlement_explained → amount_sent`) | Skipped `amount_pending` entirely. Clear spec violation; correctly flagged with sev 0.8. |

---

## Conversation-level deep dives

### dbba942b (hindi, DPD=120, regulatory_flag=True)
- Agent path is textbook on paper: `new → message_received → verification → intent_asked → settlement_explained → amount_pending → amount_sent → date_amount_asked → payment_confirmed`, and `confirm_payment(settlement_amount=22000)` is called.
- **But** borrower at t9 says "Ruko, yeh pay karna hai? Interest ka kya hua?" and at t10 "Kab pay kar sakta hun pata nahi. Sochne do." — i.e. the borrower *never agreed to a date*. Bot pushes through with `payment_date: "within_7_days"`. Validator does not catch this semantic failure (FN4). Regulatory flag is plausibly due to the bot fabricating a PTP.
- Validator correctly flags: Q2 at t7/t8/t9/t10, I4 missing `send_settlement_amount`, A4 closure-not-TOS (25,000 vs 28,750), T1 (20:45 IST at t0), Q5 (repeated restate-amount at t4/5/6).
- Annotator #3 rates q=0.85 (!) and only notes t5 repetition — annotator under-scored this conversation relative to the semantics; validator's risk=0.91 is more consistent with the regulatory outcome.

### 0c704508 (english, DPD=80, borrower_complained=True)
- Borrower says "Stop messaging me" at t1, bot does verification → repeats amount → escalates at t5 only. Then at t10 `zcm_timeout_reengagement` resurrects the conversation.
- Validator correctly flags Q2, I2 (message after exit), I4 (zcm_timeout wrong state), C3 (5 messages after DNC), Q4 (reintro), T2.
- Annotator #3 at q=0.3 with flags `compliance_concern / stop_request_missed / tone_inappropriate / amount_error`; exactly aligned with what we caught — strong agreement that this conversation is a compliance failure. Validator missed: (a) the *immediate* escalation requirement (delay between t1 DNC and t5 escalate), (b) the amount_error surfaced by annotator (bot asserts 149,500 despite borrower's "I already paid" — this would need an A* semantic check we don't have).

### 3e63b7d2 (hindi, DPD=105, 3 annotators)
- Triple-annotated with consensus quality≈0.15–0.6, all flagging `stop_request_missed`, `escalation_missed`.
- Validator caught all of the structural issues (DNC→post-DNC messages, T1 quiet hours 23:32, I2 exit-not-final for t10 reengagement, I4 wrong-state zcm_timeout, T2 0h follow-ups, Q2 misclassification of t1 as wants_closure instead of refuses).
- **Missed:** legal-threat escalation trigger at t5 ("Apne vakil se baat karke dekhta hun") — no C1 implementation. Annotator #1 flags this as `missed_escalation` 0.6.

### 87d6c412 (hindi, DPD=115, unannotated)
- Unique case in the sample: `settlement_explained → amount_sent` directly at t7 (skipped amount_pending) + `send_settlement_amount(amount=95000, type=full_closure)` with TOS=109,250.
- Validator correctly caught the only I1 in the sample plus I4_action_wrong_state and A3_full_closure_not_tos. Good coverage for an atypical path.
- Q2 has 4 flags — 3 are solid misclassifications (bot said `unclear` to "Main pay karna chahta hun. Options batayein?", "Haan, yeh theek hai. Main pay karunga", "3 din mein payment kar dunga"). One (t7 "Mujhe samjhauta karna hai. Amount check karein." — classifier `wants_settlement`, bot `wants_closure`) is a judgment call — borrower literally says *samjhauta* = settlement, so bot is wrong; classifier correct.

### 30305fdd (hinglish, DPD=85, borrower_complained=True)
- 33 messages, bot stuck in `date_amount_asked` for turns 8–18, asking the same date question to borrower saying "Can't say now. Maybe soon." ~10 times. Classic Q1 failure → manifests as Q5 (two repetition groups: 4× and 6×/10×) and one Q2.
- Validator's q=0.75 is *too high* here — the conversation is structurally fine but experientially broken. This is the scenario where Q1 would push the score down. Annotator #1 rates q=0.15 (validator 5× higher).
- Validator correctly catches T1 (23:11 IST t0) and A4 (POS quoted for closure).
- **Missed:** bot at t6 reveals the settlement amount (`₹2,34,000 approved`) *before* getting consent to check it; ann #1 calls this `state_machine_error 0.6`. Our rules allow the sequence because the FSM does `settlement_explained → amount_pending → amount_sent` as valid edges regardless of borrower consent to check.

### 1d72c76b (hinglish, DPD=125, regulatory_flag=True)
- 9-turn loop where borrower says "I want to pay. Options kya hain?" 4 times and bot keeps restating the amount. No DNC, no hardship, no amount error.
- Validator fires only 3 violations (Q2 x2, Q5 x1). Risk=0.96 (dominated by Q2 severity), but quality=0.69 is likely too lenient given the outcome is regulatory-flagged.
- **Missed:** The structural "bot cannot make progress from `intent_asked`" problem. This is Q1 (efficient progress) territory — skipped by scope but it's the load-bearing signal here.

### d03b8e7f (hinglish, DPD=285, 3 annotators, life_event=family_help)
- Hardship-adjacent conversation: borrower at t1 "Job chali gayi meri, koi income nahi hai 😔", t3 "please koi raasta nikalo yaar... job gayi hai". Bot classifies hardship/medium but *proceeds straight to verification and payment options without empathy acknowledgement*.
- Annotator #1 q=0.22 flags `hardship_ignored`, `tone_inappropriate`, `escalation_missed`, `state_machine_error`. Our validator q=0.61, risk=0.85.
- **Missed:** C2 hardship-handling check. Annotators overwhelmingly agree this is the core failure.
- Validator correctly flags: T2 (0h follow-up t3), Q2 (misclassifying "Month end tak kar dunga" as asks_time vs bot `unclear`), I4 missing send_settlement_amount, A4 POS-vs-TOS.

### a5f2726d (english, DPD=80, 3 annotators)
- Similar DNC+legal pattern. Validator caught I2, I4 wrong-state, T2, Q4 reintro. **Missed** the DNC detection at t1 — wait: borrower t1 says "Who are you? Why are you bothering me?" — this is not explicitly a DNC phrase (no "stop", "band", etc.). Ann #1 thinks it's a stop request. This is a FN of DNC_RE being too strict, or a TP of DNC_RE being appropriately strict — arguable. Given spec §7.3 lists the trigger words as "stop / do not contact / block / leave me alone", "Why are you bothering me" doesn't satisfy the lexical spec. Validator's stricter reading is defensible.

### b656cf58 (english, DPD=240)
- Two escalation cycles (t5 and t11) with two `zcm_timeout_reengagements` at t10/t16. Six bot messages after DNC at t1. Validator fires 11 violations — captures everything structurally relevant (I2×3 exit-not-final, I2×3 message-after-exit, I4×2 wrong-state, T2×2, Q2, C3).

---

## Recommendations

1. **FP1 / FP2 (Q2 over-firing):** Either downweight severity when the classifier's prediction is itself `asks_time`/`unclear` (ambiguous-by-nature classes), or gate Q2 on `max_conf ≥ 0.8` *and* text ≥ 5 tokens to reduce keyword-bias flags on short commitments with timelines.
2. **FP3 (A4 severity floor):** Since the POS-as-closure misquote is *systematic* in this agent (20/30), either raise the floor to 0.6 or track it as an `agent-level` violation (one per conv) with explicit severity reflecting misinformation risk regardless of relative gap.
3. **FN1 (delayed escalation after DNC):** Add a sub-check that measures `turns between DNC trigger and first escalate()`. If > 1, fire a stronger `C3_delayed_escalation` at sev 0.9 separate from the per-message C3.
4. **FN2 / FN3 (legal triggers + hardship):** Prioritised next checks; both map cleanly to spec §7.1 and §7.2 and are evidenced by annotator consensus.
5. **FN4 (semantic confirm_payment):** Consider a minimal check that `date_amount_asked → payment_confirmed` requires the last borrower message to contain at least a date/time reference *or* an affirmation keyword.
6. **Score calibration:** `quality_score` uses `1 − total_sev/total_turns` which rewards long conversations (more turns → more forgiveness) and is why 30305fdd and 1d72c76b score higher than annotator truth. Consider normalising by unique *violation types* or severity-weighted turns.
