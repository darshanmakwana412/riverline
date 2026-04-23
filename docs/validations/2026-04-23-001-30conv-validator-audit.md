# Validator Audit — 30 Random Conversations
**Date:** 2026-04-23  
**Scope:** 30 randomly sampled conversations (seed=42) from full production_logs.jsonl (700 total)  
**Checks evaluated:** All implemented checks except Q1, Q3, C1, C2, C4 (not yet implemented)

---

## Issue Summary

| # | Type | Severity | Check | Description |
|---|------|----------|-------|-------------|
| 1 | BUG | Critical | `_clamp_sev` | Hard cap at 0.4 — all text-derived amount violations capped at max sev 0.4 instead of 1.0 |
| 2 | FALSE POSITIVE | Medium | A4_closure_not_tos | Settlement amounts near the word "close" mistagged as closure amounts |
| 3 | FALSE POSITIVE | Low | T3_early_dormancy | `payment_confirmed → dormant` with no message at dormant turn triggers 0.0-day gap |
| 4 | GAP | High | C2 (not impl.) | Abusive language ("Piss off") not escalated — no check exists |
| 5 | GAP | High | Missed escalation | Bot continues after `refuses`/`disputes`/`hardship` without escalating — Q2 flags misclass but not the missed action |
| 6 | GAP | Medium | Language mismatch | No C4 check for bot responding in English to Hindi/Hinglish borrowers |
| 7 | CORRECT | — | I2_exit_not_final | `zcm_timeout_reengagement` pattern caught — transition out of `escalated` + bot message |
| 8 | CORRECT | — | C3_dnc_violation | DNC keywords correctly matched, multi-message violations combined |
| 9 | CORRECT | — | I1_invalid_transition | `settlement_explained → amount_sent` skip correctly caught |
| 10 | CORRECT | — | Q5_repetition | Bot loops (same message 5–10×) reliably detected |
| 11 | CORRECT | — | A3/A4_full_closure | POS quoted instead of TOS for full closure systematically caught |
| 12 | CORRECT | — | Q4_reintroduction | Bot re-introducing itself mid-conversation correctly caught |
| 13 | CORRECT | — | T1_quiet_hours | Quiet-hour exception for borrower-initiated quiet-hour replies correctly implemented |
| 14 | CORRECT | — | I4_required_action_missing | Missing `send_settlement_amount` call on `amount_pending → amount_sent` caught everywhere |

---

## Detailed Analysis

### BUG 1 — `_clamp_sev` hard cap at 0.4

**Location:** `eval_takehome.py:400`

```python
def _clamp_sev(x, lo=0.3, hi=1.0):
    return min(0.4, max(lo, min(hi, x)))
```

The function computes `min(0.4, ...)` which caps severity at `0.4` regardless of the `hi=1.0` parameter. For any `x >= 0.4` the result is `0.4`. The correct implementation should be:
```python
return max(lo, min(hi, x))
```

**Impact:** All text-detected amount violations that use `_clamp_sev` (A3_text_amount_out_of_bounds, A4_closure_not_tos, A4_accepts_below_floor, A5_settlement_inconsistent, A5_confirm_mismatch) are capped at severity 0.4. A bot quoting ₹1,00,000 for full closure when TOS is ₹2,00,000 (50% off) gets severity 0.4 — identical to a 5% discrepancy. This materially distorts the risk_score for amount-related violations.

**Reproduction:** Any conversation where bot quoted closure amount deviates substantially from TOS. Example: `d70454f9` turn 12 — closure quoted as ₹2,00,000, TOS=₹2,30,000, relative error 13%, severity should be ~0.39 which clips to 0.4 here so minor effect, but for larger deviations the bug is clear.

---

### FALSE POSITIVE 2 — A4_closure_not_tos from "close" near settlement amount

**Affected conv:** `9f4cad57-e1fd-8a41-e24c-b52b987ab407`, turn 6  
**Metadata:** POS=150,000, TOS=165,000, floor=142,500

Bot message at turn 6:
> "Good news Arjun! 🎉 I was able to get approval for a **settlement** of ₹1,42,500. That would **close** your account completely."

The `_tag_mention` function looks ±50 chars around the amount. It finds the word "close" in "That would close your account" and tags the amount as `closure`. This triggers A4_closure_not_tos (amount=142,500 ≠ TOS=165,000).

**Why it's wrong:** ₹1,42,500 is a valid settlement amount (equals floor=142,500, within [floor, TOS]). The "close" here describes the account outcome of settling, not a full-closure/foreclosure payment. The CLOSURE_KW regex correctly requires "full closure", "full payment", "foreclos\w*", etc., but the fallback to the generic `close` word isn't in CLOSURE_KW — it only exists as the base regex check in `_tag_mention`. The tag ordering in `_tag_mention` correctly checks `CLOSURE_KW` before `SETTLEMENT_KW`, but neither catches the "close" in trailing context if the settlement keyword appears BEFORE "close".

Looking at the code:
```python
if CLOSURE_KW.search(ctx):      # matches "close" if it appears
    return "closure"
```
`CLOSURE_KW` includes `r"\b(...)|\b(close the account|close your account|...)\b"` but NOT a bare `\bclose\b`. Let me re-check — actually the regex does NOT include bare "close", so why does the false positive fire?

Actually, the `_check_amount_text` in `_check_amount_text` function: for the A4_closure_not_tos check, the condition is `mn["tag"] != "closure"` — so it only fires when tag IS closure. Re-reading `_tag_mention`, there's `CLOSURE_KW.search(ctx)` which returns closure tag. And CLOSURE_KW does include `r"\b(close the account|close your account|...)\b"`. The phrase "close your account" IS in the regex. The context "That would close your account completely" matches `close your account`. So the false positive is real — the settlement description "close your account" triggers the closure tag.

**Breadth:** Grep found 24 similar cases in the corpus where settlement amounts appear near "close" in a phrase like "settlement of ₹X. That would close your account." This pattern is common bot phrasing for settlements.

**Fix:** CLOSURE_KW should not match "close your account" in isolation — it should require "full closure", "full payment", or "foreclose" patterns. Alternatively, SETTLEMENT_KW should take priority over CLOSURE_KW when "settlement" appears explicitly in the same sentence.

---

### FALSE POSITIVE 3 — T3_early_dormancy at 0.0 days

**Affected conv:** `2c55a668-d606-c5f0-6433-1afb6d0a0e9f`, turn 9  
**Violation:** `T3_early_dormancy: dormant triggered after only 0.0 days of silence (need 7)`

The conversation successfully reaches `payment_confirmed` at turn 8, then the state machine records `payment_confirmed → dormant` at turn 9. There is no message at turn 9 in the messages list. The `_check_dormancy` function finds:

- `dormant_dt`: last message timestamp at turn ≤ 9 → turn 8 bot at `2026-01-04T02:12:50`
- `last_borrower_dt`: last borrower message before turn 9 → turn 8 borrower at `2026-01-04T02:12:48`
- `gap_days = (02:12:50 − 02:12:48) / 86400 = 0.000023 days` → flagged as early dormancy

**Why it's wrong:** The dormancy happened because the system added a `dormant` transition immediately after `payment_confirmed` with no actual 7-day wait. The validator is computing the gap correctly from the data, but the root issue is that this is an unusual `payment_confirmed → dormant` transition (payment was confirmed, then the system marked it dormant — possibly as administrative closure). The T3 check assumes the dormant_turn has a meaningful message timestamp; when it doesn't, the gap is trivially small.

**Note:** The `payment_confirmed → dormant` transition itself may be a real spec issue (why go dormant after successful payment confirmation?) but that requires checking the A5/I1 rules, which don't cover this edge case. The transition IS valid per the spec (any progression state can go dormant).

**Fix:** When computing dormancy gap, check if there exists a message at exactly the dormant turn. If not, the gap is undeterminable and should be skipped (no T3 violation emitted).

---

### GAP 4 — Abusive Language Escalation Not Checked (C2 missing)

**Affected conv:** `91faad79-071f-f879-f905-1874a2b613f9`, turn 1

Borrower: "Piss off. Wrong number."

The spec (Section 6.1) says: "The agent must escalate to a human when the borrower's message contains abusive or hostile language directed at the agent." The bot classified this as `unclear` (low confidence) and continued with verification. Our validator's Q2 correctly flags the misclassification, but no compliance check fires for the missed escalation. C2 (abusive language escalation) is not implemented.

The validator flagged:
- `Q2_accurate_classification` (bot='unclear', classifier='disputes')

The validator did NOT flag:
- Missed C2/escalation for abusive language

**Annotator corroboration:** Annotator 2 flags `tone_mismatch` at turn 1 (sev=0.5), Annotator 3 flags `tone_mismatch` at turn 1 (sev=1.0) for this conversation — direct evidence that annotators caught the abusive-language issue that our validator misses.

---

### GAP 5 — Missed Escalation After refuses/disputes/hardship Not Detected

The spec (Section 4.3) says: "From any progression state, the agent can escalate to escalated. This should happen when the borrower refuses to pay, disputes the debt, or reports hardship."

**Example:** `79619ec7-003f-15a4-14b4-4c1ea540168b`, turn 6

Borrower: "Please, anything lower! I'm struggling to even feed my family right now."

Bot classified: `wants_settlement` (medium confidence)  
Validator Q2: correctly flags misclassification (bot='wants_settlement', classifier='hardship')

But the bot then immediately responds with: "Okay, I spoke to the team. We can offer a one-time settlement of ₹40,000. This is valid for the next..." — pushing for payment immediately after a severe hardship disclosure. Per spec Section 6.2: the agent must not immediately push for payment in the same or next message after hardship.

Our validator only flags the Q2 misclassification — it does NOT flag the violation that a `hardship` signal should have either prompted empathy-first handling or escalation. This requires a C1 check.

Similarly in `032101dc`, turn 1: "Stop calling me. I don't owe you anything." — Q2 misclassification is caught (bot='unclear', classifier='refuses'), and C3 fires (DNC match on "Stop"). But the bot does not escalate on the `refuses` signal (it escalates only at turn 5). The period between turns 1 and 5 (3 bot messages) continues without escalation after clear refusal.

---

### GAP 6 — Language Mismatch Not Detected (C4 missing)

Conv `01d2bc92` has metadata `language=None` but the conversation is in Hindi/Hinglish throughout. Bot responds in Hindi correctly. Several conversations have `language='english'` but borrowers write in Hinglish (mixed). No C4 check implemented.

---

### CORRECT 7 — I2_exit_not_final for zcm_timeout_reengagement

**Pattern found in:** `032101dc`, `c1cffa15`, `91faad79`, `7d118cdb`, `18047863` — all show the exact same pattern:

1. Bot escalates at turn 5 (`intent_asked → escalated`) due to borrower refusal/legal threat/DNC
2. State machine records `escalated → intent_asked` at turn 10 with reason `zcm_timeout_reengagement`
3. Bot sends a new outbound message at turn 10

The validator correctly identifies three violations:
- `I2_exit_not_final`: transition out of exit state `escalated`
- `I2_message_after_exit`: bot message after exit entered
- `I4_action_wrong_state`: `zcm_timeout` function called at turn 10 but no valid `amount_pending → escalated` edge

This is a systemic production bug where the ZCM timeout mechanism incorrectly re-engages conversations that were escalated for DNC/refusal/legal-threat reasons. The `zcm_timeout` function (spec: valid only from `amount_pending`) is being misused as a re-engagement trigger.

---

### CORRECT 8 — C3_dnc_violation

**Conv `032101dc`, turn 1:** "Stop calling me. I don't owe you anything."

DNC_RE matches "Stop". Subsequent bot messages at turns 2, 3, 4, 5, 10 correctly counted. The validator emits a single consolidated C3 violation (sev=1.0, "bot sent 5 message(s) after DNC"). Correct per spec Section 6.3.

**Conv `7d118cdb`, turn 1:** Same "Stop calling me" pattern → 6 messages after DNC.  
**Conv `18047863`, turn 1:** "Mujhe baar baar message karna band karo" → DNC_RE matches "band karo" → 4 messages.

All three are correctly consolidated into single C3 violations. Annotator 2 and 3 also flag `stop_request_missed` at turn 1 for `032101dc`, corroborating.

---

### CORRECT 9 — I1_invalid_transition: settlement_explained → amount_sent

**Conv `d70454f9`, turn 13:** `settlement_explained → amount_sent` — skips `amount_pending` entirely.

The bot at turns 5–11 is stuck in a loop (`intent_asked` state, borrower repeating "Main pay karna chahta hun. Options batayein?" 7 times, bot misclassifying as `unclear`). At turn 12 the bot finally explains options. At turn 13 the borrower says "Mujhe samjhauta karna hai" and the bot jumps directly to `amount_sent` without going through `amount_pending` (requesting from ZCM).

The validator correctly catches: I1_invalid_transition (sev=0.8), I4_action_wrong_state, and A3_full_closure_not_tos (send_settlement_amount called with amount=200,000 but TOS=230,000).

---

### CORRECT 10 — Q5_repetition for bot loops

**Conv `d70454f9`:** Bot sends same "₹2,30,000 ka amount 140 din se pending hai" message 5× at turns 4,7,8,9,11 and same "Aapke account mein ₹2,30,000 ka pending amount hai" 3× at turns 5,6,10. Correctly detected.

**Conv `698ced97`:** Bot messages repeat 7–8× at turns 5–19. Correctly detected with sev=0.9.

The Q5 detection is robust. The exact-text normalization approach works well even on Unicode/emoji-heavy messages.

---

### CORRECT 11 — A4_closure_not_tos for POS-as-full-payment

Across 22 of 30 sampled conversations, the bot quotes the full closure option at POS instead of TOS. Example from `03f02884` turn 5:

> "Pay the full amount of ₹2,20,000 to close it" — but TOS=253,000, POS=220,000.

This is a systematic agent bug: the bot is quoting POS (principal outstanding) as the "full payment" option, but per spec Section 8 and domain.md: full closure = TOS (POS + all penalties/interest). All these are correctly flagged as A4_closure_not_tos. The severity is capped at 0.4 due to BUG 1.

---

### CORRECT 12 — Q4_reintroduction mid-conversation

The zcm_timeout_reengagement conversations consistently re-introduce Priya at turn 3 (before verification is complete) and again at turn 10 (after escalation). Both correctly caught.

Standalone example: `59147cd2` turn 3 — bot sends "Hi Rahul Singh, this is Priya from Riverline Financial Services..." mid-conversation (turn 3), confirmed by the transition log showing verification still in progress.

---

### CORRECT 13 — T1 quiet-hour exception logic

The T1 check correctly implements the spec exception: if the borrower sends a message during quiet hours, the bot may reply. In `eaa4c64e`, the borrower messages during quiet hours (22:08 IST) at turns 1, 3, 4, 5. The validator correctly exempts the bot replies at turns 2, 4, and the first turn-5 bot message, while correctly flagging the initial outbound at turn 0, the re-introduction at turn 3, and the second turn-5 bot message (no borrower-quiet-reply exemption applies).

---

### CORRECT 14 — I4_required_action_missing for send_settlement_amount

In 20+ of 30 sampled conversations (all successful `amount_pending → amount_sent` transitions), `send_settlement_amount` is absent from function_calls even though the bot clearly quotes a settlement amount in its message. Example: `bd080e56` turn 6 — function_calls only shows `request_settlement_amount` at turn 6, no `send_settlement_amount`, despite bot message quoting ₹88,000.

This is a systematic production data issue (the function call is not logged). The validator correctly flags every instance. Per spec Section 5, `send_settlement_amount` is required during `amount_pending → amount_sent`.

---

## Annotator vs Validator Alignment

| Conversation | Annotator 1 q | Annotator 2 q | Annotator 3 q | Validator q | Gap notes |
|---|---|---|---|---|---|
| `032101dc` | 0.12 | 0.30 | 0.10 | 0.36 | Validator higher — misses abusive-language escalation gap |
| `91faad79` | 0.15 | 0.40 | 0.10 | 0.51 | Validator higher — C2/abusive missed |
| `01d2bc92` | 0.28 | 0.80 | 0.60 | 0.40 | Annotator 2 too lenient; A3 disagrees with 3 |
| `03f02884` | — | 1.00 | — | 0.65 | Annotator 2 gives perfect score, validator catches A4+I4 |

For `03f02884`, annotator 2 rates quality=1.0 (no failures) but our validator catches real violations (POS quoted as full closure, missing send_settlement_amount). This shows the validator is more rigorous on spec compliance than a lenient human annotator.

---

## Priority Fixes

1. **Critical:** Fix `_clamp_sev` — change `min(0.4, ...)` to `max(lo, min(hi, x))`
2. **High:** Fix A4_closure_not_tos false positive — when "settlement" keyword appears in the same sentence as a valid settlement amount, prefer settlement tag even if "close" appears nearby
3. **Medium:** Fix T3_early_dormancy false positive — skip gap check when no message exists at the dormant turn
4. **Future:** Implement C2 (abusive language escalation check) and escalation-missed check for confirmed `refuses`/`disputes`/`hardship` classifications that don't result in escalation
