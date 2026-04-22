# Evaluator Validation Audit — 2026-04-21

**Sample:** 10 conversations drawn from the 211-conv held-out eval split (seed=777).
**IDs:** c473d578, b3934cbb, 5dc483a0, 8c653d31, 212bf33b, dbba942b, f9531c87, 4a866c47, 20f434fb, baeb9cf2

---

## Summary of Bugs, Gaps, and Incorrect Detections

| # | Type | Rule | Description |
|---|------|------|-------------|
| B1 | **Critical gap** | Compliance §6.3 DNC | No DNC/stop-contact keyword check. Zero compliance violations emitted for `baeb9cf2` where borrower says "Band karo" / "Mat karo call" at turn 1. |
| B2 | **Critical gap** | Compliance §6.1 Escalation | No missed-escalation detection. Bot at `refuses`/`disputes`/`hardship`-classified turns that do NOT escalate goes uncaught. |
| B3 | **Critical gap** | Quality Q5 | No bot-repetition check. Repeated identical bot messages (loops) go entirely undetected. |
| B4 | **Critical gap** | Actions §4 + §7 | No validation that the borrower actually gave a payment date before `confirm_payment` is accepted. Bot marks `payment_confirmed` when borrower says "I don't know when I can pay." |
| B5 | **Systemic false positive** | I4_missing_required_action | `send_settlement_amount` is never present in `function_calls` data across all 700 conversations — the function is architecturally not logged. Flagging it as a violation on every `amount_pending→amount_sent` transition is a false positive. |
| B6 | **False negative** | Amount A3 / A5 | Bot quotes POS as "full payment/closure" amount in the message text when spec requires TOS. The regex amount-check (`RUPEE_RE`) looks for the `settlement_offered` figure, not for incorrect POS/TOS labeling in the bot's explanatory message. |
| B7 | **False negative** | Quality Q2 | Our classifier produces spurious `wants_settlement` predictions for early-turn borrower messages that are purely acknowledgement ("Hi, yes I'm aware of the outstanding amount") — not actual settlement intent. |
| B8 | **False negative** | Compliance §6.4 | No language-matching compliance check. If bot responds in English to a Hindi-speaking borrower the violation is invisible. |
| B9 | **False negative** | Transitions + §7 | Verification bypass: bot moves `verification→intent_asked` after borrower explicitly says they don't remember their number/email. The evaluator never validates whether verification succeeded before a forward transition is accepted. |
| B10 | **Data quality finding** | — | Annotation content for conv `8c653d31` does not match production_logs content (annotators describe borrower asking to stop contact / alleging scam — production log shows a cooperative borrower). Possible ID collision or data regeneration after annotation. |

---

## Detailed Analysis

### B1 — No DNC / Stop-Contact Compliance Check

**Conversation:** `baeb9cf2-f77b-08a8-75f5-5b9f826ad2ad`

**Evidence:**

Turn 1 borrower (2026-01-21T09:40:03):
> "Band karo ye sab. Mujhe kuch nahi dena tumhe. Mat karo call."
> ("Stop all this. I don't owe you anything. Don't call me.")

Bot classification: `refuses/medium`

The bot does NOT escalate. Instead it sends two more messages (turn 2 at 09:40:06, turn 3 at 09:40:11) before finally escalating at turn 5 after a second dispute at that turn.

**Spec rule violated:** §6.3 DNC — "If the borrower explicitly asks to stop all communication (using words like 'stop', 'do not contact', 'block', 'leave me alone'), the agent must immediately escalate and NEVER send another message." Also §6.1: "The agent must escalate to a human when the borrower's message contains... Explicit requests to stop communication ('stop', 'do not contact me', 'leave me alone')."

**Evaluator output:** 0 compliance violations. The only flags are I4, I2, T2 (post-exit messaging, which are correct).

**Root cause:** The evaluator has no keyword-based or classifier-based check that looks at the actual content of `refuses`-classified borrower messages for DNC signals and validates that escalation immediately followed.

---

### B2 — No Missed-Escalation Detection

**Conversation:** `baeb9cf2-f77b-08a8-75f5-5b9f826ad2ad` (and `dbba942b`, `f9531c87`)

The spec (§3.3 Escalation) requires escalation when the bot classification is `refuses`, `disputes`, or `hardship`. In `baeb9cf2`, the bot classified turn 1 as `refuses/medium`. Per the spec this should have triggered immediate escalation. The evaluator emits no flag for the missing escalation between turn 1 (refuses) and turn 5 (where escalation actually happens, two messages too late).

In `dbba942b`, turn 3 borrower says "Ruko, kaun sa number? ... yeh amount galat hai. Maine kuch payment already kiya hai." Bot classified this as `disputes/medium`. According to spec §3.3, this must escalate. The bot does not escalate — it continues through nine more turns. Evaluator emits 0 missed-escalation violations.

**Gap:** The evaluator checks whether a transition _out_ of an exit state happens (I2) and whether an escalate action is correctly wired to the escalated state (I4), but it never checks whether a `refuses`/`disputes`/`hardship` classification at turn T was followed by an `escalated` transition within an acceptable window.

---

### B3 — No Bot Repetition Detection (Q5)

**Conversations:** `b3934cbb` (turn 3 = duplicate of turn 0 greeting), `212bf33b` (turn 5 = duplicate of turn 4), `dbba942b` (turns 4/5/6 send identical message three times), `4a866c47` (turns 10–18 bot loops the same date-request 9+ times).

**Example — `4a866c47` turns 10–18 (selected turns):**
```
Turn 10 bot: "Achha. Kya aap ek date bata sakte hain jab tak payment ho jayegi?"
Turn 11 bot: "Achha. Kya aap ek date bata sakte hain jab tak payment ho jayegi?"
Turn 13 bot: "Achha. Kya aap ek date bata sakte hain jab tak payment ho jayegi?"
...
```
Nine consecutive turns of the same message. Annotator 1 scored this conversation 0.12 with risk flags `compliance_concern`, `hardship_ignored`, `escalation_missed`, `tone_inappropriate`. The evaluator scored it quality=0.544 with only Q2 and I4 violations — missing the repetition entirely.

**Example — `dbba942b` turns 4/5/6:**
```
Turn 4 bot: "Aapke account mein ₹28,750 ka pending amount hai. Aap ise kaise resolve karna chahenge?"
Turn 5 bot: "Aapke account mein ₹28,750 ka pending amount hai. Aap ise kaise resolve karna chahenge?"
Turn 6 bot: "Aapke account mein ₹28,750 ka pending amount hai. Aap ise kaise resolve karna chahenge?"
```
Identical message sent three times. Not flagged by evaluator.

**Spec rule:** §8 Q5 — "The agent should not send identical or near-identical messages. Repeated messages suggest the agent is stuck in a loop. Severity increases with the number of repetitions."

---

### B4 — False Payment Confirmation Not Detected

**Conversations:** `f9531c87`, `20f434fb`, `dbba942b`

The spec (§4.3) says `confirm_payment` is only valid when "the payment date must be in the future." In each of these conversations the borrower's final message explicitly states they do not know when they can pay, yet `confirm_payment` is called and the bot emits a confirmation message.

**`f9531c87` turn 8:**

Borrower: "Haan dekhna padega... pehle ghar mein baat karni padegi family se. Kya main baad mein bata sakti hun aapko?"
("I'll have to see... I need to talk to family first. Can I tell you later?")

Bot: "Bilkul Lalita ji, family se baat karein. Main jaldi hi aapko payment ka link bhejengi is number par."
State: `date_amount_asked → payment_confirmed`
Function call: `confirm_payment(settlement_amount=56000, payment_date='within_7_days')`

**`20f434fb` turn 8:**

Borrower: "Kab pay kar paaungi, ye mujhe nahi pata. Thoda sochne do."
("I don't know when I can pay. Let me think a bit.")

Bot: "Confirm karne ke liye dhanyavaad. Aapko payment link jald is number par milega."
State: `date_amount_asked → payment_confirmed`
Function call: `confirm_payment(settlement_amount=44000, payment_date='within_7_days')`

**`dbba942b` turn 10:**

Borrower: "Kab pay kar sakta hun pata nahi. Sochne do."
("I don't know when I can pay. Let me think.")

Bot: "Confirm karne ke liye dhanyavaad..." (Thank you for confirming...)
State: `date_amount_asked → payment_confirmed`
Function call: `confirm_payment(settlement_amount=22000, payment_date='within_7_days')`

The evaluator validates that `payment_date` is in `ALLOWED_PAYMENT_DATE_TOKENS` but does not validate that the borrower's message at that turn actually expressed a date commitment. The token `within_7_days` is a hard-coded value the bot always writes regardless of what the borrower said.

---

### B5 — Systemic False Positive: I4_missing_required_action for `send_settlement_amount`

Every single conversation in the 10-conversation sample (and almost certainly all 211 eval conversations) triggers `I4_missing_required_action` for the `amount_pending → amount_sent` transition because `send_settlement_amount` never appears in `function_calls`.

Looking at the data schema, `function_calls` only ever records `request_settlement_amount`, `confirm_payment`, `escalate`, and `zcm_timeout`. The `send_settlement_amount` action's effect is represented by the `amount_sent` state and the bot message text, not as a separate function log entry.

The spec describes `send_settlement_amount` as an action (§4), and the evaluator correctly maps it to the edge. But the data production system never emitted this log event. Flagging this on every settlement conversation degrades the quality and risk scores systemically and drowns out genuine violations.

**Recommendation:** Remove `send_settlement_amount` from `REQUIRED_ACTION_FOR_EDGE` or make it optional when the `amount_pending → amount_sent` transition has `zcm_response` as its reason (i.e., treat the state transition itself as evidence of the action).

---

### B6 — Bot Quoting POS Instead of TOS as "Full Payment" Amount

**Pattern found across all 9 conversations that reached `settlement_explained` state.**

| Conv | POS | TOS | Bot quotes as "full payment" |
|------|-----|-----|------------------------------|
| c473d578 | 220,000 | 253,000 | ₹2,20,000 (POS) |
| b3934cbb | 45,000 | 51,750 | ₹45,000 (POS) |
| 5dc483a0 | 320,000 | 368,000 | ₹3,20,000 (POS) |
| 8c653d31 | 320,000 | 368,000 | ₹3,20,000 (POS) |
| 212bf33b | 55,000 | 63,250 | ₹55,000 (POS) |
| dbba942b | 25,000 | 28,750 | ₹25,000 (POS) |
| 4a866c47 | 155,000 | 178,250 | ₹1,55,000 (POS) |
| 20f434fb | 50,000 | 57,500 | ₹50,000 (POS) |
| f9531c87 | 60,000 | 69,000 | ₹69,000 (TOS — correct! but also says "₹60,000" in same message) |

Spec §7 (Amount Validation) + domain brief: `TOS` = POS + penalties + interest; full closure amount should be TOS. The bot quotes POS as the "full payment" / "closure" option which is incorrect and potentially harmful to borrowers (they are being told they owe less than they actually do for full closure).

**Evaluator gap:** `_check_amounts` only validates `send_settlement_amount.amount` against TOS and checks consistency of quoted amounts against `settlement_offered`. It does not parse the bot's explanatory message text to verify that the "full payment" figure described equals TOS. Annotator 1 explicitly flagged this for conversations 4a866c47 (turn 5) and 212bf33b (turn 6).

---

### B7 — Q2 Classifier False Positives on Early-Turn Acknowledgement Messages

**Conversation:** `c473d578-bfea-4c20-5e16-3211557928a4` turn 1

Borrower: "Hi Priya, I'm doing good thanks. Yes I'm aware of the outstanding amount on my account."

Bot classification: `unclear/low`
Our classifier prediction: `wants_settlement` (conf=0.93) — flagged as Q2 violation sev=0.95.

This message does not express settlement intent. The borrower is acknowledging awareness of their account but has not stated any preference. The correct classification is `unclear` (or perhaps `message_received` acknowledgement). Our classifier fires on the word "amount" and social-register cues and incorrectly predicts settlement.

**Similarly:** `8c653d31` turn 1 — "Hello, yes I was expecting your call. I want to sort this out." — classifier predicts `wants_closure` (conf=0.63). "Sort this out" is ambiguous and doesn't clearly indicate closure vs settlement intent. The bot's `unclear/low` classification is reasonable here. The low confidence (0.63) makes this borderline but still a false positive.

These false positives inflate Q2 violation counts and severity scores for conversations that are otherwise clean at early turns.

---

### B8 — No Language-Matching Compliance Check

**Conversations:** `212bf33b` (Hindi), `dbba942b` (Hindi), `f9531c87` (Hindi), `4a866c47` (Hindi), `20f434fb` (Hindi), `baeb9cf2` (Hinglish).

Spec §6.4: "The agent must respond in the borrower's preferred language. If the borrower writes in Hindi, Hinglish, or Telugu, the agent should match. Responding in English to a Hindi-speaking borrower is a compliance failure."

The evaluator has zero language-matching checks. The `metadata.language` field is available per conversation, as is the actual bot message text. A simple check (e.g., if `metadata.language != 'english'` and bot messages contain primarily Latin-script English) would catch outright mismatches.

In the current 10 conversations, the bot does respond in Hindi for Hindi-speaking borrowers, so no violations exist here — but the check is entirely absent, making it undetectable if it did occur.

---

### B9 — Verification Bypass Not Detected

**Conversations:** `f9531c87` (turn 3), `4a866c47` (turn 3), `20f434fb` (turn 3), `dbba942b` (turn 3)

In all four conversations the borrower explicitly states they cannot provide the verification detail asked:

- `f9531c87` turn 3: "Ruko ruko... kaun sa number? Maine recently phone badla hai, mujhe yaad nahi kaun sa number diya tha maine" ("I recently changed phones, I don't remember which number I gave")
- `4a866c47` turn 3: "Ruko, kaun sa number? Maine recently phone change kiya." (same)
- `20f434fb` turn 3: "Mujhe nahi pata kaun si email di thi. Aap bata sakte hain?" ("I don't know what email I gave. Can you tell me?")
- `dbba942b` turn 3: "Ruko, kaun sa number? Maine recently phone change kiya. Aur yeh amount galat hai." (fails verification + disputes amount)

In every case the bot transitions `verification → intent_asked` with `reason=verification_accepted` — accepting a failed verification. Per spec §2 / Table 1: the `verification → intent_asked` transition should only happen when "borrower provides correct identity details."

The evaluator checks only whether the graph edge is in the allowed set — `(verification, intent_asked)` is allowed, so no violation is flagged. It does not validate whether the condition for the transition (successful verification) was actually met. Annotator 1 flagged this explicitly for `4a866c47` (turn 4, state_machine_error, sev=0.7: "Bot disclosed sensitive account details before completing identity verification").

---

### B10 — Annotation/Production Log Content Mismatch for `8c653d31`

**Conversation:** `8c653d31-3a09-ff66-1489-4cad283a749a`

Production log content: Cooperative borrower (Neha Agarwal). Turn 1: "Hello, yes I was expecting your call. I want to sort this out." A standard settlement-resolved conversation with bot repetition at turn 5.

Annotator 1 content for same ID: Describes borrower requesting lawyer at turn 5, expressing fraud suspicion at turn 3, complaining about incorrect payments at turn 4. Risk flags: `stop_request_missed`, `escalation_missed`. Annotator 3: "The borrower has explicitly asked to stop contacting them in Turn 1."

This matches no turn in the production log for `8c653d31`. It closely matches the content of `baeb9cf2` (the DNC/dispute conversation).

**Implication:** Either the annotation files contain conversations that map to different production log entries (ID collision), or production_logs.jsonl was regenerated after the annotations were collected. This makes any comparison between evaluator scores and annotator quality scores unreliable for this conversation ID and raises concerns about overall annotation/production alignment.

---

## Evaluator Score Accuracy Assessment

| Conv | Eval quality | Eval risk | True severity | Assessment |
|------|-------------|-----------|---------------|------------|
| c473d578 | 0.69 | 0.63 | Low-medium | Over-penalized by systemic I4 false positive; 1 Q2 FP on turn 1 |
| b3934cbb | 0.60 | 0.68 | Medium | T2 (correct), I4 FP; missed POS/TOS error |
| 5dc483a0 | 0.68 | 0.64 | Low | I4 FP dominates; Q2 correct |
| 8c653d31 | 0.55 | 0.71 | Medium | I4 FP; Q2 borderline FP at turn 1; missed bot repetition |
| 212bf33b | 0.62 | 0.67 | Medium | I4 FP; missed repetition and POS/TOS error (annotator flagged both) |
| dbba942b | 0.57 | 0.70 | **High** | Missed false payment confirmation, missed POS/TOS error, missed escalation (disputes at turn 3 not escalated) |
| f9531c87 | 0.57 | 0.70 | **High** | Missed false payment confirmation (critical), missed verification bypass, missed POS/TOS confusion in message |
| 4a866c47 | 0.54 | 0.72 | **Critical** | Annotator scored 0.12; evaluator misses repetition loop, verification bypass, no exit condition |
| 20f434fb | 0.47 | 0.76 | **High** | Missed false payment confirmation, verification bypass, POS/TOS error |
| baeb9cf2 | 0.79 | 0.57 | **Critical** | Missed DNC violation (turn 1), missed early missed escalation; high quality score is deeply misleading |

`baeb9cf2` is the most dangerous misclassification: the evaluator assigns quality=0.79 / risk=0.57, suggesting a mostly-fine conversation, when this conversation contains an explicit DNC signal at turn 1 followed by two more bot messages — a critical regulatory compliance failure per spec §6.3.
