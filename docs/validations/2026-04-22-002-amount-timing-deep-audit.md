# Validation Audit: Amount + Timing Checks — Deep Audit (20 conversations)
**Date:** 2026-04-22  
**Scope:** A1–A5 (amount rules) + T0–T3 (timing rules) only  
**Sample:** 20 random conversations from `production_logs.jsonl` (seed=42, full 700-conversation pool)

---

## Section 1 — Summary Table: Bugs, Gaps, Findings

| # | Type | Rule | Status | Description |
|---|------|------|--------|-------------|
| 1 | Correct Detection | A4_closure_not_tos | ✅ TRUE POSITIVE | Bot consistently quotes POS as full closure option — detected in 12/20 convs |
| 2 | Correct Detection | A3_full_closure_not_tos | ✅ TRUE POSITIVE | Function call `send_settlement_amount(POS, full_closure)` when TOS≠POS — detected in d70454f9 |
| 3 | Correct Detection | T1_quiet_hours | ✅ TRUE POSITIVE | Initial bot message during 19:00–08:00 IST detected in 7/20 convs |
| 4 | Correct Detection | T2_followup_too_soon | ✅ TRUE POSITIVE | Dual-send pattern (bot→bot in <5 sec) and zcm_timeout resumption detected in 8/20 convs |
| 5 | Correct Detection | T3_early_dormancy | ✅ TRUE POSITIVE | Dormant transition 0.0 days after last borrower reply in 2c55a668 |
| 6 | Gap/Limitation | A4_closure_not_tos | ⚠️ SEVERITY UNDERESTIMATE | Severity locked at 0.391 for all closure errors due to POS/TOS ratio (~87-90%). Systematic error affecting 60% of conversations deserves higher baseline. |
| 7 | Gap/Limitation | A4_closure_not_tos | ⚠️ AMBIGUITY | "full payment ₹POS mein settle ho sakta hai" matches CLOSURE_KW ("full payment") but might be settlement offer at POS, not closure. Context-dependent; borderline false positive risk. |
| 8 | Gap | A5_settlement_inconsistent | ⚠️ NOT CHECKED | Text-level: bot quotes TOS as "outstanding" (turn 4) then POS as "full payment/closure" (turn 5). Semantically inconsistent for borrower but A5 only tracks "settlement"-tagged amounts — doesn't cross-check outstanding vs closure quotes |
| 9 | Gap | T2_followup_too_soon | ⚠️ SECONDARY VIOLATION | When bot messages after exit state (I2 violation), T2 also fires. T2 is technically correct but the root is I2. No false positive — both are real — but the framing in the violation list may be confusing. |
| 10 | Correct | b4e40ff4 | ✅ CORRECTLY CLEAN | Conversation with messages crossing quiet-hours boundary correctly identified as clean because every quiet-hour bot message followed a quiet-hour borrower message (exception applies). |
| 11 | Correct | cef7d0f9 | ✅ CORRECTLY PARTIAL | Only T1 flagged at turn 0. Subsequent quiet-hour bot replies (turns 2–16) all exempt because each follows a borrower message also in quiet hours. |
| 12 | Gap | NO RULE | ⚠️ NO AMOUNT MISMATCH CHECK | When bot skips `send_settlement_amount` function call and quotes amount only in text (e.g., bd080e56), A3 from function-call path doesn't fire. Text path (A3_text) does check the verbally quoted amount, but there's no check that the function-call `amount` matches verbally quoted amount when both exist. |

---

## Section 2 — Detailed Conversation Analysis

### bd080e56 — POS=100,000 TOS=115,000 floor=88,000

**Evaluator output:**
```
[A4_closure_not_tos] turn=5  sev=0.391  closure amount=100000, TOS=115000
[T1_quiet_hours]     turn=0  sev=0.7    bot message at 21:37 IST
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** Bot at turn 5 says:
  > "Bilkul, options hain aapke paas — full payment ₹1,00,000 mein settle ho sakta hai, ya ek reduced settlement bhi possible hai"
  
  "full payment" matches CLOSURE_KW. Amount=100,000=POS. TOS=115,000. Spec §8: closure = TOS. The bot is presenting POS as "full payment" option, which is wrong. Real violation.

  **Ambiguity note**: "full payment … settle ho sakta hai" could mean "settlement at POS" not "closure." But the bot frames two choices — "full payment" vs "reduced settlement" — making POS the apparent closure option. Violation is real, though the ambiguity could cause a false positive in messages where "full payment" is used loosely to mean "one lump sum settlement."

- **T1 turn=0 ✅ CORRECT.** Turn 0 bot timestamp: `2026-01-25T16:07:00 UTC` = **21:37 IST** (quiet window). No prior borrower message to trigger the reply-exception. Real violation.

- **Missing: `send_settlement_amount` call.** Turn 6 has `request_settlement_amount`, turn 8 has `confirm_payment(88000)`. No `send_settlement_amount` in between. The bot verbally quotes ₹88,000 (in range [88000, 115000]) but skips the function call. A3 from function-call path can't fire; text path shows 88000 is valid. **I4 would catch this (not in scope here).**

---

### 032101dc — POS=250,000 TOS=287,500 floor=None

**Evaluator output:**
```
[T2_followup_too_soon] turn=3   sev=0.5   gap=0.0h
[T2_followup_too_soon] turn=10  sev=0.5   gap=0.0h
```

**Manual audit:**

- **T2 turn=3 ✅ CORRECT.** Bot at turn 2 (09:28:02), bot at turn 3 (09:28:07). Gap = 5 seconds. No borrower reply in between. Spec §6.2: ≥4h required before re-messaging without borrower reply. Clear violation.

- **T2 turn=10 ✅ CORRECT.** Bot turn 5 (09:28:16) escalated; bot turn 10 (09:28:18) is the zcm_timeout re-engagement, 2 seconds later. No borrower in between. Root issue is also I2 (message after exit state — not in scope), but T2 correctly fires independently. Both violations are real.

- **No amount violations ✅ CORRECT.** floor=None, so A3/A4 skip. No function calls referencing amounts.

---

### 03f02884 — POS=220,000 TOS=253,000 floor=187,000

**Evaluator output:**
```
[A4_closure_not_tos] turn=5  sev=0.391  closure amount=220000, TOS=253000
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** Bot turn 5:
  > "Pay the full amount of ₹2,20,000 to close it, or 2) A reduced settlement amount."
  
  "full amount" matches CLOSURE_KW. Amount=220,000=POS. TOS=253,000. Real violation.

- **Settlement offer turn 6: correctly clean.** Bot offers "₹1,87,000" (=floor=187,000). floor=187,000 ≤ 187,000 ≤ 253,000=TOS. No A3_text.

- **Timing: correctly clean.** All messages between 09:03 and 09:07 IST (business hours). No T1. All turns have borrower replies; no T2.

---

### d70454f9 — POS=200,000 TOS=230,000 floor=200,000 (floor=POS)

**Evaluator output:**
```
[A3_full_closure_not_tos] turn=13  sev=0.9   send_settlement_amount(200000, full_closure) ≠ TOS=230000
[A4_closure_not_tos]      turn=12  sev=0.391  closure amount=200000, TOS=230000
[T1_quiet_hours]          turn=0   sev=0.7    bot message at 20:07 IST
```

**Manual audit:**

- **A3 turn=13 ✅ CORRECT.** Function call `send_settlement_amount(amount=200000, type='full_closure')`. TOS=230,000 ≠ 200,000. Spec §8: full_closure must equal TOS. Clear hard violation.

- **A4 turn=12 ✅ CORRECT.** Bot turn 12:
  > "Poora ₹2,00,000 deke account band karna, ya 2) Settlement amount jo poore amount se kam hoga."
  
  "account band karna" matches CLOSURE_KW. Amount=200,000, TOS=230,000. Real violation.

  **Note:** This conversation has floor=POS=200,000. The bot is offering 200,000 as both "full payment to close" (incorrect — closure=TOS=230,000) and as the settlement floor. The amount is in-range for settlement [200,000, 230,000] but is incorrectly labeled as closure. A3 and A4 both correctly fire.

- **T1 turn=0 ✅ CORRECT.** `2026-01-01T14:37:00 UTC` = **20:07 IST** (quiet). No prior borrower message. Real violation.

- **Repetition loop (turns 5–11): No amount violations.** Bot repeats the same message 8 times without advancing. No function calls during this loop. No T2 because each bot message follows a borrower message. This is a quality issue (Q1/Q5) not an amount/timing issue — out of scope.

---

### 55d0c883 — POS=55,000 TOS=63,250 floor=54,500

**Evaluator output:**
```
[A4_closure_not_tos] turn=6  sev=0.391  closure amount=55000, TOS=63250
[T1_quiet_hours]     turn=0  sev=0.7    bot message at 21:57 IST
```

**Manual audit:**

- **A4 turn=6 ✅ CORRECT.** Bot turn 6:
  > "Aapke paas do options hain: 1) Poora ₹55,000 deke account band karna, ya 2) Settlement amount jo poore amount se kam hoga."
  
  "account band karna" + POS=55,000. Real violation.

- **T1 turn=0 ✅ CORRECT.** `2026-01-27T16:27:00 UTC` = **21:57 IST**. Real violation.

- **Annotator 1 flags (turn 4) "amount_error: ₹28,750"** — this annotation is confusing (28,750 is not any amount visible in this conversation). The annotator note is likely referring to a different issue or is a data error in annotations. The evaluator correctly ignores this annotation (it doesn't use annotations for its rules).

---

### 698ced97 — POS=28,000 TOS=32,200 floor=None

**Evaluator output:**
```
[A4_closure_not_tos] turn=5   sev=0.391  closure amount=28000, TOS=32200
[T1_quiet_hours]     turn=0   sev=0.7    bot message at 22:00 IST
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** Bot turn 5:
  > "Option 1 is full payment of ₹28,000. Option 2 is a reduced settlement"
  
  "full payment" = CLOSURE_KW. Amount=28,000=POS. TOS=32,200. Real violation.

- **T1 turn=0 ✅ CORRECT.** `2026-01-07T16:30:00 UTC` = **22:00 IST**. Real violation.

- **Repetition loop (turns 5–19)**: No T2 fires because each bot message follows a borrower message. This conversation also has 15 repetitive turns with no progress. Quality issue, not amount/timing.

---

### c1cffa15 — POS=200,000 TOS=230,000 floor=None

**Evaluator output:**
```
[T2_followup_too_soon] turn=10  sev=0.5  gap=0.0h
```

**Manual audit:**

- **T2 turn=10 ✅ CORRECT.** Bot escalated at turn 5 (13:19:27); zcm_timeout bot at turn 10 (13:19:32). Gap = 5 seconds. No borrower in between. Root is also I2 (message after exit). T2 correctly fires independently.

---

### 91faad79 — POS=130,000 TOS=149,500 floor=None

**Evaluator output:**
```
[T2_followup_too_soon] turn=3   sev=0.5  gap=0.0h
[T2_followup_too_soon] turn=10  sev=0.5  gap=0.0h
```

**Manual audit:**

- Both T2 violations ✅ CORRECT. Turn 3: bot(2) at 09:42:02 → bot(3) at 09:42:07, 5 sec gap, no borrower. Turn 10: same zcm_timeout pattern, 2 sec gap.

---

### cef7d0f9 — POS=250,000 TOS=287,500 floor=234,000

**Evaluator output:**
```
[T1_quiet_hours] turn=0  sev=0.7  bot message at 00:01 IST
```

**Manual audit:**

- **T1 turn=0 ✅ CORRECT.** `2026-01-06T18:31:00 UTC` = **00:01 IST** (next day). Real violation.

- **Turns 2–16: correctly not flagged.** Every subsequent bot message in quiet hours is preceded by a borrower message also in quiet hours (18:40 UTC = 00:10 IST, 18:55 UTC = 00:25 IST, etc.). The T1 exception correctly applies.

- **Amount at turn 7 ✅ CORRECT.** Bot offers "₹2,34,000 ka settlement" = floor=234,000. In [234,000, 287,500]. No violation.

- **Closure mentions at turns 5 and 6**: Bot says "full payment of ₹2,87,500" (=TOS). "full payment" matches CLOSURE_KW; amount=287,500=TOS → no A4 since amount==TOS. Correctly clean.

---

### 01d2bc92 — POS=55,000 TOS=63,250 floor=54,500

**Evaluator output:**
```
[A4_closure_not_tos] turn=6  sev=0.391  closure amount=55000, TOS=63250
```

**Manual audit:**

- **A4 turn=6 ✅ CORRECT.** Bot turn 6:
  > "Sure! Do options hain basically — 1) Full closure ₹55,000 mein, ya 2) Settlement jo isse bhi kam hoga."
  
  "Full closure" = exact CLOSURE_KW match. Amount=55,000=POS. TOS=63,250. Real violation.

- Annotator 1 notes "wrong information" at turn 6: "Bot described 'settlement' vaguely and offered ₹55,000 as 'full closure' which is incorrect." This confirms the A4 violation is real.

---

### b4e40ff4 — POS=500,000 TOS=575,000 floor=400,000 — CLEAN

**Evaluator output:** CLEAN

**Manual audit:**

- **✅ CORRECTLY CLEAN.** All messages between 13:28–13:38 UTC. Turn 4 bot at 13:31:19 UTC = **19:01 IST** (quiet), but preceded by borrower turn 3 at 13:31:16 UTC = 19:01 IST (also quiet). Exception applies. Every subsequent bot message in quiet also follows a quiet-hour borrower message.

- Settlement at turn 7: "₹4,00,000" = floor=400,000. In [400,000, 575,000]. No A3.

- Full payment at turn 6: "the full ₹5,75,000" (=TOS). CLOSURE_KW needs "full closure/payment/amount/..." — "the full ₹5,75,000" → context is "to pay the full ₹5,75,000." "full" alone doesn't match without "payment/closure/amount". Not tagged as closure. No A4. **Correct.**

---

### eaa4c64e — POS=60,000 TOS=69,000 floor=53,000

**Evaluator output:**
```
[A4_closure_not_tos]  turn=5  sev=0.391  closure amount=60000, TOS=69000
[T1_quiet_hours]      turn=0  sev=0.7    22:08 IST
[T1_quiet_hours]      turn=3  sev=0.7    22:08 IST
[T2_followup_too_soon] turn=3  sev=0.5    gap=0.0h
[T1_quiet_hours]      turn=5  sev=0.7    22:08 IST
[T2_followup_too_soon] turn=5  sev=0.5    gap=0.0h
```

**Manual audit:**

All messages at `2026-01-15T16:38:XX UTC` = **22:08 IST** (deep quiet hours).

- **A4 turn=5 ✅ CORRECT.** Bot turn 5 (first): "full payment ₹60,000" (=POS). TOS=69,000. Real violation.

- **T1 turn=0 ✅ CORRECT.** Initial bot message. No prior borrower.

- **T1 turn=3 ✅ CORRECT.** Turn 2 bot → turn 3 bot (09:38:07) with no borrower in between. Two consecutive bot-only messages during quiet. Last_was_borrower=False. T1 fires.

- **T2 turn=3 ✅ CORRECT.** Bot(2) at 16:38:02, bot(3) at 16:38:07. 5 sec gap. No borrower.

- **T1 turn=5 (second bot at turn 5) ✅ CORRECT.** Turn 5 has: borrower(16:38:15) → bot1(16:38:16) → bot2(16:38:18). Bot1 follows borrower, exempt. Bot2 follows bot1 without borrower; T1 fires.

- **T2 turn=5 (second bot) ✅ CORRECT.** Same logic; 2 sec gap.

- **Borrower mentions hardship at turn 1 and 3:** "job chali gayi hai", "no income", "medical emergency." The T1/T2 violations mean the bot was spamming during quiet hours. The compliance checks (not in scope) would additionally flag missed hardship escalation.

---

### 18047863 — POS=480,000 TOS=552,000 floor=None

**Evaluator output:**
```
[T2_followup_too_soon] turn=10  sev=0.5  gap=0.0h
```

**Manual audit:**

- **T2 turn=10 ✅ CORRECT.** Zcm_timeout pattern. Bot escalated at turn 5 (12:32:27); bot(10) at 12:32:32. 5 sec gap. No borrower.

---

### 59147cd2 — POS=45,000 TOS=51,750 floor=36,000

**Evaluator output:**
```
[A4_closure_not_tos]    turn=5  sev=0.391  closure amount=45000, TOS=51750
[T2_followup_too_soon]  turn=3  sev=0.5    gap=0.0h
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** "Option 1 is full payment of ₹45,000" (=POS). TOS=51,750. Real violation.

- **T2 turn=3 ✅ CORRECT.** Bot(2) at 12:44:07 → bot(3) at 12:44:12. 5 sec, no borrower.

- **Annotator 1 note on turn 6:** "bot offered settlement amount of ₹99,000 without clearly confirming" — This is inconsistent with the actual conversation where ₹36,000 was offered. Annotator 1's note appears to be from a different conversation (annotator data contamination / wrong annotation). The evaluator correctly ignores annotations.

---

### 0ff9571e — POS=45,000 TOS=51,750 floor=36,000

**Evaluator output:**
```
[A4_closure_not_tos]    turn=7  sev=0.391  closure amount=45000, TOS=51750
[T2_followup_too_soon]  turn=3  sev=0.5    gap=0.0h
```

**Manual audit:**

- **A4 turn=7 ✅ CORRECT.** "Full closure at ₹45,000" (=POS). TOS=51,750. Real violation.

- **T2 turn=3 ✅ CORRECT.** Bot(2) 13:10:06 → bot(3) 13:10:11. 5 sec. No borrower.

- Same account as 59147cd2 (same POS/TOS/floor, same borrower "Rahul Singh"), different conversation dates. Both have A4 closure violations.

---

### 2c55a668 — POS=95,000 TOS=109,250 floor=85,500

**Evaluator output:**
```
[A4_closure_not_tos]  turn=5   sev=0.391  closure amount=95000, TOS=109250
[T1_quiet_hours]      turn=0   sev=0.7    23:33 IST
[T3_early_dormancy]   turn=9   sev=0.7    dormant after 0.0 days
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** "full closure at ₹95,000" (=POS). TOS=109,250. Real violation.

- **T1 turn=0 ✅ CORRECT.** `2026-01-03T18:03:00 UTC` = **23:33 IST**. Real violation.

- **T3 turn=9 ✅ CORRECT.** The dormant transition at turn 9 fires 0.0 days (seconds) after the last borrower message at turn 8 (02:12:48). This is clearly incorrect — dormancy requires 7 days of silence (spec §6.3). The bot confirmed payment at turn 8 then immediately triggered dormant. This looks like a state machine bug in production (conversation was completed with `confirm_payment` at turn 8 but then mislabeled as dormant rather than `payment_confirmed`).

  **Note:** The conversation also has a dormant transition checked against messages. The code looks for `dormant_dt` from last message at turn ≤ dormant_turn. Both the dormant_dt and last_borrower_dt resolve to the turn-8 timestamps, giving gap ≈ 0.0 days. Correctly identified.

- **Timestamps across days:** bot(0) at 18:03 UTC (23:33 IST), borrower(1) at 19:47 UTC (01:17 IST next day), up to bot(8) at 02:12 IST. The conversation spans midnight. T1 applies throughout but from turn 1 onward, each bot reply follows a borrower message in quiet hours → exception applies. Only turn 0 flagged. **Correct.**

---

### fe67f506 — POS=28,000 TOS=32,200 floor=None

**Evaluator output:**
```
[A4_closure_not_tos] turn=6  sev=0.391  closure amount=28000, TOS=32200
```

**Manual audit:**

- **A4 turn=6 ✅ CORRECT.** "Full closure at ₹28,000" (=POS). TOS=32,200. Real violation.

- **No T2:** All turns 5–20 have borrower replies before each bot reply. Even though the conversation is a 16-turn repetition loop, T2 doesn't fire because borrower always responds. Correctly clean for T2.

---

### 7d118cdb — POS=350,000 TOS=402,500 floor=None

**Evaluator output:**
```
[T1_quiet_hours]       turn=0   sev=0.7   00:06 IST
[T1_quiet_hours]       turn=3   sev=0.7   00:06 IST
[T2_followup_too_soon] turn=3   sev=0.5   gap=0.0h
[T1_quiet_hours]       turn=10  sev=0.7   00:06 IST
[T2_followup_too_soon] turn=10  sev=0.5   gap=0.0h
```

**Manual audit:**

All messages at `2026-01-14T18:36:XX UTC` = **00:06 IST** (deep quiet).

- **T1 turn=0 ✅ CORRECT.** Initial bot message, no prior borrower.

- **T1 + T2 turn=3 ✅ CORRECT.** Bot(2) → bot(3) in 4 seconds, no borrower in between, both in quiet.

- **T1 + T2 turn=10 ✅ CORRECT.** Zcm_timeout bot(10) follows bot(5) escalation by 4 seconds. No borrower. Both quiet.

  This conversation also has a second escalation at turn 11 (borrower disputes debt after zcm_timeout resumption). 

---

### 9a367ccb — POS=230,000 TOS=264,500 floor=215,000

**Evaluator output:**
```
[A4_closure_not_tos] turn=5  sev=0.391  closure amount=230000, TOS=264500
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** Bot turn 5:
  > "Do options hain: 1) Full closure for ₹2,30,000, ya 2) Settlement amount jo kam hoga."
  
  "Full closure" exact match. Amount=230,000=POS. TOS=264,500. Real violation.

- Settlement at turn 6: "₹2,15,000 ka settlement" (=floor=215,000). In [215,000, 264,500]. No A3. Correctly clean.

---

### 1c271c17 — POS=280,000 TOS=322,000 floor=277,000

**Evaluator output:**
```
[A4_closure_not_tos] turn=5  sev=0.391  closure amount=280000, TOS=322000
```

**Manual audit:**

- **A4 turn=5 ✅ CORRECT.** Bot turn 5:
  > "Do options hain: 1) Full closure for ₹2,80,000, ya 2) Settlement amount jo thoda kam hoga."
  
  "Full closure" exact match. Amount=280,000=POS. TOS=322,000. Real violation.

- Settlement at turn 6: "₹2,77,000 ka settlement" (=floor=277,000). In [277,000, 322,000]. No A3. Correctly clean.

---

## Section 3 — Overall Findings

### Violation Distribution Across 20 Conversations

| Rule | Count | Conv IDs |
|------|-------|----------|
| A4_closure_not_tos | 12 | bd080e56, 03f02884, d70454f9, 55d0c883, 698ced97, 01d2bc92, eaa4c64e, 59147cd2, 0ff9571e, 2c55a668, fe67f506, 9a367ccb, 1c271c17 |
| T1_quiet_hours | 7 | bd080e56, d70454f9, 55d0c883, 698ced97, cef7d0f9, eaa4c64e, 2c55a668, 7d118cdb |
| T2_followup_too_soon | 8 | 032101dc, c1cffa15, 91faad79, eaa4c64e, 18047863, 59147cd2, 0ff9571e, 7d118cdb |
| A3_full_closure_not_tos | 1 | d70454f9 |
| T3_early_dormancy | 1 | 2c55a668 |

### False Positives Found: **0**

Every flagged violation was confirmed correct by manual inspection.

### False Negatives Found: **0**

No amount or timing violations were found in manual inspection that the evaluator missed.

### Key Findings

1. **Systematic A4_closure_not_tos bug (60% of conversations):** The production bot universally quotes POS as the full closure/full payment option. This is a spec violation (spec §8: "For closure, the ZCM returns the full TOS as the amount"). The bot appears hard-coded to offer POS as "full payment" regardless of TOS. Given this is a systematic violation, severity should arguably be higher than 0.39.

2. **T1 initial bot messages during quiet hours (~35% of conversations):** Many initial bot messages go out in the 19:00–08:00 IST window. The spec is explicit: "No outbound messages between 7 PM and 8 AM IST." These appear to be scheduled send-outs that ignore the quiet-hour window.

3. **T2 dual-send patterns:** Multiple conversations show the bot sending 2 messages in <5 seconds without a borrower reply in between. Pattern 1: "dual-send" where bot sends an initial message then an almost-immediate retry (turn 2→3). Pattern 2: after zcm_timeout, bot(10) follows bot(5) escalation within seconds.

4. **Quiet-hour exception logic is correct:** The T1 exception (borrower messages during quiet → bot may reply) works correctly and prevents false positives for conversations where both parties are active during quiet hours.

### Severity Calibration Issue

A4_closure_not_tos is consistently scored 0.391 because the formula is:
```python
rel = abs(amount - tos) / tos   # ≈ 0.13 for typical POS/TOS ratios
sev = clamp(0.3 + 0.7 * 0.13)  # ≈ 0.391
```

This severity seems too low given:
- It is a systematic error present in ~60% of conversations
- It directly misinforms borrowers about the closure amount
- The absolute amount difference can be tens of thousands of rupees
- The spec rates amount errors as "High" severity

Suggested fix: raise the base severity for closure amount errors (e.g., `min_severity=0.6` for A4).

### Annotator Data Quality Note

For conversation `59147cd2`, annotator 1 notes "bot offered ₹99,000 settlement" — but the actual conversation shows ₹36,000 was offered. This is a clear annotator error (likely copy-pasted from a different conversation). The evaluator correctly ignores annotations for its spec-based checks.
