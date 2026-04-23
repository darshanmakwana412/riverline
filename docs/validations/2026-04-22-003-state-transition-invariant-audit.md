# State Transition & Invariant Violations Audit
**Date:** 2026-04-22  
**Scope:** I1, I2, I3, I4, Q2 (state transitions, invariants, action/state match, classification)  
**Sample:** 20 random conversations from production_logs.jsonl (seed=42)

---

## Summary of Findings

| Category | Count | Status |
|----------|-------|--------|
| TRUE POSITIVES correctly flagged | 7 types | ✅ Correct |
| FALSE POSITIVES (incorrect flags) | 0 | — |
| GAPS (missed violations) | 4 | ❌ Not detected |
| VALIDATOR BUGS | 2 | 🐛 Fix needed |

---

## Issues List

### 🐛 Bugs / False Positives / False Negatives

#### BUG-1: Q2 Duplicate Violation Inflation from Shared Turn Numbers
**Type:** Inflation (not false positive per se, but misleading count)  
**Conversations affected:** `d70454f9`, `698ced97`, `fe67f506`  
**Description:** The data quality bug described in CLAUDE.md (bot and borrower sharing the same turn number from turn 5 onward) causes the same borrower text to appear on multiple consecutive turns with separate `bot_classifications` entries. Q2 generates a separate violation for each turn, multiplying the count for a single underlying misclassification.

In `d70454f9`: borrower text "Main pay karna chahta hun. Options batayein?" appears verbatim at turns 5, 6, 7, 8, 9, 10, 11 — all classified `unclear low` by the bot. Our classifier predicts `wants_closure` (0.92) on all 7. Q2 fires **7 violations** for what is one classification error.

In `698ced97`: "Let me check. I'll get back to you on this." at 8 turns, "Maybe. I need to think about it first." at 6 turns → 14 Q2 violations. In `fe67f506`: same texts at 16 turns → 16 Q2 violations.

**Why it matters:** These inflate the violation count significantly and will amplify risk/quality score distortion on the hidden test set. A conversation with 16 identical misclassifications should not be 16× worse than one with 1. Should deduplicate Q2 violations by `(text, predicted_class, bot_class)` per conversation.

---

#### BUG-2: I4 `send_settlement_amount` Missing — Fires on 100% of `amount_pending → amount_sent` transitions
**Type:** True positive firing but requires data-context caveat  
**Conversations affected:** All 460 conversations with `amount_pending → amount_sent` transition (100%)  
**Description:** `send_settlement_amount` never appears at the same turn as `amount_pending → amount_sent` in any of the 460 qualifying conversations. The 41 conversations that DO contain a `send_settlement_amount` call have no corresponding `amount_pending → amount_sent` transition — instead they skip `amount_pending` entirely via an `I1_invalid_transition`.

The I4_required_action_missing for `send_settlement_amount` is therefore a **true positive** — the action is genuinely missing from the transition. However, the 100% rate across all conversations is a strong signal that this is a systematic injected bug in the dataset (the function call is simply never logged in the normal flow). On the hidden test set this same pattern may continue.

**Evidence:** `01d2bc92`, `bd080e56`, `eaa4c64e`, `b4e40ff4`, `2c55a668` all show `request_settlement_amount` at turn T, transitions `settlement_explained→amount_pending` AND `amount_pending→amount_sent` at turn T, `confirm_payment` at turn T+2, but zero `send_settlement_amount` in function_calls.

**Action:** Keep the check as-is (it IS a real violation), but note in documentation that it fires at 100% rate.

---

#### GAP-1: Verification Bypass (Disclosure Before Verification Complete)
**Type:** Missed violation  
**Conversation:** `01d2bc92` (also noted by all 3 annotators)  
**Description:** At turn 3, borrower says "Hmm wait which number? Maine recently phone change kiya tha toh confuse ho rahi hun" — this does NOT constitute successful verification. Yet at turn 4 the bot transitions `verification → intent_asked` and immediately discloses "₹63,250 pending hai". Annotator 1 notes: "Bot disclosed account balance without completing identity verification" (sev=0.9).

The state machine correctly records `verification → intent_asked` (structurally valid), but the verification condition was not semantically satisfied. Our validator checks structural validity only — it has no mechanism to detect premature disclosure.

**Fix required:** Would need NLP-based check: if the transition `verification → intent_asked` occurs but the preceding borrower message contains confusion/non-confirmation signals, flag it.

---

#### GAP-2: Post-Escalation Re-contact Pattern Not Fully Caught
**Type:** Partial miss  
**Conversations:** `032101dc`, `c1cffa15`, `91faad79`, `18047863`, `7d118cdb`  
**Description:** I2_exit_not_final correctly catches the `escalated → intent_asked` structural violation. BUT the transition is labeled with reason `zcm_timeout_reengagement`, suggesting the data injects a fake ZCM-timeout mechanism to justify re-entering after escalation. The I4 for `zcm_timeout` at the wrong state is correctly caught too. 

What's missed: the COMPLIANCE aspect. In all 5 conversations, the initial escalation trigger was a DNC/stop request at turn 1 ("Stop calling me. I don't owe you anything." in `032101dc`/`7d118cdb`, "Mujhe baar baar message karna band karo" in `18047863`). Re-contacting after a DNC escalation is not just an I2 violation — it's a C3 (DNC) violation. The C3 check would catch this, but we're told to check C3 separately. The current analysis scope excludes it.

---

#### GAP-3: Bot Re-Introduction Repetition Not Detected (Q5 Quality Check Missing)
**Type:** Missed quality violation  
**Conversations:** `032101dc` (turn 3), `7d118cdb` (turn 3), `59147cd2` (turn 3), `eaa4c64e` (turn 3)  
**Description:** In each of these, the bot re-sends its verbatim opening introduction ("Hi [Name], this is Priya from Riverline Financial Services...") at turn 3 as if no conversation had occurred. This is a Q5 (no repetition) and Q4 (remembering context) violation. Our evaluator does not implement Q4/Q5 repetition checks — these were intentionally excluded from the current evaluator scope.

**Evidence:**
- `032101dc` turn 3 bot: "Hello Manish Tiwari, my name is Priya and I'm calling from Riverline Financial Services..." (identical to turn 0)
- `7d118cdb` turn 3 bot: "Hi Padmini Chandrasekaran, this is Priya from Riverline Financial Services..." (identical to turn 0)

All 3 annotators flag this as `repetition sev=0.7-0.8` for these conversations.

---

#### GAP-4: `eaa4c64e` Hardship Handling — Double Bot Message at Same Turn
**Type:** Missed compliance issue  
**Conversation:** `eaa4c64e`  
**Description:** At turn 5, borrower says "Mujhe medical emergency ka samna karna pada. Thoda time ya lower amount ho sakta hai?" (hardship high). The data has TWO bot messages at turn 5: 
1. "Mujhe sunke bura laga aapki situation. Hum aapka saath dene ko tayyar hain." (empathy ✓)
2. "Aapke paas options hain — full payment ₹60,000 ya reduced settlement..." (immediate payment push ✗)

Spec section 7.2: "agent must not immediately push for payment in the same or next message" after hardship. The second message at the same turn violates this. Our evaluator has no hardship-response sequencing check.

---

## Detailed Analysis of Each Conversation

### `bd080e56` — Happy path, valid transitions
**Transitions:** new→new→msg_rcvd→verification→intent_asked→settlement_explained→amount_pending→amount_sent→date_amount_asked→payment_confirmed (all at consecutive turns 0-8)  
**Violations detected:** 2  
- I4_required_action_missing t=6: `send_settlement_amount` missing (TRUE POSITIVE — see BUG-2)  
- Q2 t=7: bot=`unclear` (low) but text "Theek hai, try karungi arrange karne ki. Par ek baar mein..." → classifier=`asks_time` (0.95). The borrower is clearly trying to arrange payment (time-based commitment). Bot should have classified `asks_time`. TRUE POSITIVE.

---

### `032101dc` — I2: escalated → intent_asked re-entry
**Transitions:** new→msg_rcvd→verification→intent_asked→escalated (t=5) → **intent_asked (t=10)**  
**Violations detected:** 4  
- I2_exit_not_final t=10: TRUE POSITIVE — exit state `escalated` is final per spec I2.  
- I2_message_after_exit t=10: TRUE POSITIVE — bot message after exit state.  
- I4_action_wrong_state t=10: `zcm_timeout` called during `escalated→intent_asked`. TRUE POSITIVE — `zcm_timeout` is only valid at `amount_pending→escalated`.  
- Q2 t=1: bot=`unclear low`, text "Stop calling me. I don't owe you anything." → classifier=`refuses` (0.99). Egregious misclassification — this is a DNC + refuses signal. TRUE POSITIVE.

**Missed:** C3 DNC violation (out of scope for this pass), Q4/Q5 bot re-introduction at t=3 (GAP-3).

---

### `d70454f9` — I1: skips amount_pending state entirely
**Transitions:** ...intent_asked→settlement_explained (t=12) → **amount_sent (t=13)** → date_amount_asked (t=14)  
**Violations detected:** 11 (7 are Q2 duplicates from BUG-1)  
- I1_invalid_transition t=13: `settlement_explained → amount_sent` not in spec. TRUE POSITIVE — `amount_pending` state was skipped entirely.  
- I4_action_wrong_state t=13: `send_settlement_amount` called during `settlement_explained→amount_sent`. TRUE POSITIVE.  
- Q2 turns 5-11: 7× same text "Main pay karna chahta hun. Options batayein?" → classifier=`wants_closure`. TRUE POSITIVES but inflated by BUG-1.  
- Q2 t=13: bot=`wants_closure` (medium) but "Mujhe samjhauta karna hai. Amount check karein" → classifier=`wants_settlement` (0.91). "samjhauta" = compromise/settlement, not full closure. TRUE POSITIVE.  
- Q2 t=14: bot=`unclear` (low) but "Haan, yeh theek hai. Main pay karunga." → classifier=`wants_settlement` (0.92). Clear agreement. TRUE POSITIVE.

---

### `698ced97` — Stuck in loop, no progress, no escalation
**Transitions:** ...intent_asked→settlement_explained (t=5), then NO further transitions across 15 more turns.  
**Violations detected:** 14 (all Q2, same 2 texts repeated)  
- Q2 turns 6-19: bot classifies "Let me check. I'll get back to you" and "Maybe. I need to think about it first." as `unclear` repeatedly. Classifier predicts `asks_time`. The borrower IS asking for time — bot should have handled this differently (T2 follow-up spacing would also apply). These are TRUE POSITIVES but inflated per BUG-1.

**Missed:** The conversation loops for 15 turns with no progression and no escalation or dormancy trigger. Q1 (efficient progress) violation — gap not checked. T2 (follow-up spacing) may apply — excluded from this pass. Missing `dormant` transition despite prolonged stagnation — T3 missed dormancy — excluded from this pass.

---

### `c1cffa15` / `91faad79` / `18047863` / `7d118cdb` — Pattern: escalated → intent_asked via zcm_timeout
**Identical structural pattern across 5 conversations in the 20-sample.** Suggests a batch of injected bugs.  
All correctly flagged: I2_exit_not_final, I2_message_after_exit, I4_action_wrong_state. TRUE POSITIVES.

`18047863` specific: bot=`wants_closure` (medium) for "Kaun Priya? Aur kaunsi company? Mujhe baar baar message karna band karo." → classifier=`refuses` (0.98). Bot classifying a stop-message as `wants_closure` is a critical misclassification. TRUE POSITIVE.

`91faad79` specific: bot=`unclear` (low) for "Piss off. Wrong number." → classifier=`disputes` (0.53). Lower confidence but correct direction. TRUE POSITIVE (marginal).

---

### `01d2bc92` — Over-confident bot classification in wrong direction
**Transitions:** Happy path, all valid.  
**Violations detected:** 6  
- I4_required_action_missing: TRUE POSITIVE (BUG-2)  
- Q2 t=3: bot=`asks_time` (medium), text "Hmm wait which number? Maine recently phone change kiya tha" → classifier=`unclear` (0.97). Bot assigned `asks_time` to a verification confusion response. Our classifier (`unclear`) is actually MORE correct here. This is a case where the bot is wrong AND our classifier agrees with the human interpretation. TRUE POSITIVE — bot mislabeled.  
- Q2 t=6: bot=`wants_settlement` (high), text "Ek cheez samajhni thi — settlement aur full payment mein actually kya fark hota hai?" → classifier=`unclear` (0.99). Bot labeled a question about options as `wants_settlement high`. Completely wrong. TRUE POSITIVE.  
- Q2 t=7: bot=`wants_settlement` (high), text "Agar settlement le liya toh credit score pe kitna asar padega?" → classifier=`unclear` (0.98). Again, a question. TRUE POSITIVE.  
- Q2 t=8: bot=`asks_time` (medium), text "Ruko ruko — toh yeh ₹54,500 abhi bharna padega? Koi interest wagera toh nahi lagega?" → classifier=`unclear` (0.80). Bot labeled a question as `asks_time`. Our classifier `unclear` is more accurate. TRUE POSITIVE.  
- Q2 t=9: bot=`unclear` (low), text "Honestly nahi pata kab ho payega 😞 Thoda time chahiye mujhe sochne ke liye..." → classifier=`asks_time` (0.91). Bot labeled hardship + time request as `unclear`. Our classifier correctly gets `asks_time`. TRUE POSITIVE.

---

### `55d0c883` / `eaa4c64e` / `b4e40ff4` / `59147cd2` / `0ff9571e` / `9a367ccb` / `1c271c17` — Happy path variants
All follow normal flow. All correctly catch I4 `send_settlement_amount` missing (BUG-2). Q2 violations are primarily:
- bot=`unclear` for "Theek hai, yeh amount sahi hai. Main pay kar dungi." → `wants_settlement`
- bot=`unclear` for "Main Friday tak pay kar dungi." → `asks_time`
- bot=`unclear` for "Hi, haan mujhe pending amount ka pata hai. Chalo isse sort karte hain." → `wants_closure`

All are TRUE POSITIVES — the bot systematically under-classifies cooperative borrower intent as `unclear`.

---

### `2c55a668` — payment_confirmed → dormant
**Notable:** transition `payment_confirmed → dormant` at t=9. Our validator does NOT flag this as I1 — CORRECT. The spec transition matrix shows `pay_conf → dormant = Yes`. The validator correctly allows this. ✓

---

## Summary Table: What the Validator Correctly Catches

| Rule | Correctly Detected? | Notes |
|------|---------------------|-------|
| I1: invalid forward skip (settlement_explained→amount_sent) | ✅ Yes | d70454f9 |
| I1: backward exception requires unclear+low | ✅ Yes | correctly absent from these 20 |
| I2: escalated→intent_asked re-entry | ✅ Yes | 5 conversations |
| I2: message after exit state | ✅ Yes | 5 conversations |
| I3: chain continuity | ✅ Yes | zero breaks in these 20 |
| I4: zcm_timeout wrong state | ✅ Yes | 5 conversations |
| I4: send_settlement_amount missing | ✅ Yes (real) | 100% rate — BUG-2 caveat |
| I4: required confirm_payment | ✅ Yes | none missing in these 20 |
| Q2: bot=unclear for clear refuses/disputes/hardship | ✅ Yes | multiple conversations |
| Q2: bot=wants_closure/settlement for questions | ✅ Yes | 01d2bc92 |
| payment_confirmed→dormant valid transition | ✅ Correctly not flagged | 2c55a668 |

---

## Key Data Quality Observations

1. **Shared turn numbers** (CLAUDE.md bug #1): Same text on turns 5+ for both bot and borrower inflates Q2 violation counts. Most visible in `d70454f9`, `698ced97`, `fe67f506`.

2. **5 conversations share the exact same escalated→intent_asked bug pattern** (`032101dc`, `c1cffa15`, `91faad79`, `18047863`, `7d118cdb`) — likely a batch of injected test cases.

3. **`send_settlement_amount` call is in 41 conversations that DON'T have `amount_pending→amount_sent` transition**, while 460 conversations WITH that transition have zero `send_settlement_amount` calls. Two separate injected failure modes.

4. **Bot consistently over-classifies `unclear`** for messages that are clearly `asks_time`, `wants_settlement`, or `wants_closure` — particularly after the settlement amount is presented (turns 7-9 in happy path).

5. **Bot re-introduction at turn 3** appears in multiple conversations as a known data artifact (off-turn text bug from CLAUDE.md bug #2).
