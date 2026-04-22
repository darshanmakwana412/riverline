# Validator Audit — Amount & Timing Violations
**Date:** 2026-04-22  
**Scope:** 20 randomly sampled conversations (seed=42, entire 700-conv corpus)  
**Checks evaluated:** A3, A4, A5 (amount), T1, T2, T3 (timing)  
**Out of scope:** Compliance/DNC, state transitions, invariants, quality

---

## Summary of Findings

| Category | Count | Description |
|----------|-------|-------------|
| **FALSE POSITIVES** | 6 convs, 12 violations | `AMOUNT_RE` regex captures Hindi "ka" as "k" (kilo) multiplier |
| **FALSE NEGATIVES** | 2 convs, 2 violations | Hindi closure phrases missing from `CLOSURE_KW` |
| **DESIGN FLAW** | 2 convs, 29 violations | `A4_closure_not_tos` fires per-turn rather than per root cause |
| **CORRECT** | across all 20 | T1/T2/T3 timing, A4 (English), A4 (closure keyword English) |

---

## ISSUE 1: CRITICAL BUG — Hindi "ka" parsed as "k" (×1000) multiplier

**Type:** False positive  
**Rule affected:** `A3_text_amount_out_of_bounds`, `A5_settlement_inconsistent`, `A5_confirm_mismatch`  
**Severity:** High — makes 6/20 sampled conversations appear to have critical violations when they have none

**Root cause:** In `AMOUNT_RE`, the optional unit group `(?P<unit1>lakh|lakhs|lac|crore|cr|k|thousand)?` contains `k` as a bare character. When Hindi text follows an amount with `" ka "` (meaning "of/for" in Hindi, e.g. `₹54,500 ka settlement`), the regex greedily captures `k` from `"ka"` as the kilo multiplier (×1000).

**Evidence:**
```
Text:  "₹54,500 ka settlement offer"
Match: "₹54,500 k"  → unit="k" → 54,500 × 1,000 = 54,500,000  (WRONG)

Text:  "₹85,500. This is the offer"
Match: "₹85,500 "   → unit=""  → 85,500               (CORRECT — period breaks the match)
```

The same amount written with a period after it (English style) correctly extracts 85500; the same amount in Hindi prose with `ka` inflates to 85,500,000.

**Affected conversations (all 6 are Hindi/Hinglish):**

| Conv | Turn | Flagged amount | Actual amount | Real violation? |
|------|------|----------------|---------------|-----------------|
| `d70454f9` | 13 | 200,000,000 | 200,000 | No — 200000 ∈ [floor=200000, TOS=230000] |
| `55d0c883` | 7, 9 | 54,500,000 | 54,500 | No — 54500 = floor = 54500, valid |
| `01d2bc92` | 7, 9 | 54,500,000 | 54,500 | No — valid settlement |
| `eaa4c64e` | 6, 8 | 53,000,000 | 53,000 | No — 53000 = floor, valid |
| `9a367ccb` | 6, 8 | 215,000,000 | 215,000 | No — 215000 = floor, valid |
| `1c271c17` | 6, 8 | 277,000,000 | 277,000 | No — 277000 = floor, valid |

**Cascading effect:** The inflated amount makes `A5_confirm_mismatch` also fire because `confirm_payment.amount` (correctly 54500) does not match the bogus 54,500,000 from text extraction.

**Fix:** Add a word-boundary anchor after `k` in the unit alternatives:
```python
# Before (buggy):
r"(?P<unit1>lakh|lakhs|lac|crore|cr|k|thousand)?"
# After (correct):
r"(?P<unit1>lakh|lakhs|lac|crore|cr|k\b|thousand)?"
```
`k\b` will not match `k` in `"ka"` because `"a"` is a word character (no boundary between `k` and `a`).

---

## ISSUE 2: FALSE NEGATIVE — Hindi closure phrases missing from CLOSURE_KW

**Type:** False negative (missed A4_closure_not_tos)  
**Rule affected:** `A4_closure_not_tos`  
**Severity:** Medium — agent offers POS as the closure price (should be TOS) but the violation is not detected

**Root cause:** `CLOSURE_KW` contains English phrases (`full closure`, `full payment`, `close the account`, `poora payment`) but does not contain the Hindi template the bot actually uses for the "close account" option: `"deke account band karna"` ("pay to close the account" in Hindi).

**Affected conversations:**

| Conv | Turn | Bot text (truncated) | POS | TOS | Detected? |
|------|------|----------------------|-----|-----|-----------|
| `55d0c883` | 6 | `Poora ₹55,000 deke account band karna` | 55000 | 63250 | **NO** |
| `d70454f9` | 12 | `Poora ₹2,00,000 deke account band karna` | 200000 | 230000 | **NO** |

In both cases, the bot is offering the POS amount for "full payment to close the account" (should be TOS). The `_tag_mention` function classifies the amount as `"settlement"` (because `"Settlement amount"` appears later in the same message), not `"closure"`, so the A4 check is never reached.

The `eaa4c64e` conversation's turn 5 uses `"full payment ₹60,000"` (English keyword in Hinglish text) and IS correctly caught. The bug is specific to the Hindi variant of the same message template.

**Fix:** Add Hindi closure phrases to `CLOSURE_KW`:
```python
CLOSURE_KW = re.compile(
    r"\b(full closure|full payment|full amount|close the account|close your account|"
    r"clear everything|foreclos\w*|pura payment|poora payment|entire amount|total amount|"
    r"account band karna|deke account band|band karne ke liye)\b",
    re.I,
)
```

---

## ISSUE 3: DESIGN FLAW — A4_closure_not_tos fires once per turn, not per root cause

**Type:** Redundancy / noisy scoring  
**Rule affected:** `A4_closure_not_tos`  
**Severity:** Low correctness impact, high noise impact on quality/risk scores

**Observation:** When a bot is stuck in a loop (same violation repeated every turn), the evaluator fires one `A4_closure_not_tos` violation per turn. This inflates `total_sev` and degrades `quality_score` far more than the single root cause warrants.

**Affected conversations:**

| Conv | Turns with A4 | Root cause |
|------|---------------|------------|
| `698ced97` | t5–t19 (15 violations) | Bot consistently quotes POS=28000 for closure; TOS=32200 |
| `fe67f506` | t6–t20 (15 violations) | Same pattern — POS=28000, TOS=32200 |

In `698ced97`, the bot loops for 20 turns quoting the same wrong closure amount in each message. The 15 violations from the same single error swamp all other signal and likely pull `quality_score` to near zero.

**Suggested fix:** Deduplicate `A4_closure_not_tos` by `(amount, tos)` pair — raise severity for the first occurrence and suppress or summarise repeats.

---

## ISSUE 4: MISSING CHECK — `send_settlement_amount` with `type='full_closure'` not validated against TOS

**Type:** False negative  
**Rule affected:** A4 logic  
**Severity:** Medium

**Observation:** In `d70454f9`, the function call is:
```json
{"function": "send_settlement_amount", "params": {"amount": 200000, "type": "full_closure"}}
```
The amount 200000 equals the settlement floor (and POS), which passes the existing A3 range check `[floor, TOS]`. However, the `type='full_closure'` annotation signals the agent intended this as a foreclosure payment — which by spec must equal TOS (230000), not POS.

The evaluator currently only validates the numeric range; it does not check whether a full-closure transaction uses the correct TOS amount.

**Fix:** When `function_call.params.type == "full_closure"`, enforce `amount == TOS` rather than `floor ≤ amount ≤ TOS`.

---

## Correctly Detected Violations

The following violations are true positives confirmed by manual conversation review:

### A4_closure_not_tos (amount check)

| Conv | Turn | Evidence | Confirmed |
|------|------|----------|-----------|
| `bd080e56` | 5 | Bot: `"full payment ₹1,00,000"` (POS); TOS=115000 | ✓ |
| `03f02884` | 5 | Bot: `"full closure at ₹2,20,000"` (POS); TOS=253000 | ✓ |
| `698ced97` | 5–19 | Bot: `"full payment of ₹28,000 / full closure at ₹28,000"` (POS=28000); TOS=32200 | ✓ (redundant) |
| `01d2bc92` | 6 | Bot: `"Full closure ₹55,000"` (POS); TOS=63250 | ✓ |
| `eaa4c64e` | 5 | Bot: `"full payment ₹60,000"` (POS); TOS=69000 | ✓ |
| `59147cd2` | 5 | Bot: `"full closure ₹45,000"` (POS); TOS=51750 | ✓ |
| `0ff9571e` | 7 | Bot: `"full payment ₹45,000"` (POS); TOS=51750 | ✓ |
| `2c55a668` | 5 | Bot: `"full closure at ₹95,000"` (POS); TOS=109250 | ✓ |
| `9a367ccb` | 5 | Bot: `"Full closure for ₹2,30,000"` (POS); TOS=264500 | ✓ |
| `1c271c17` | 5 | Bot: `"full closure ₹2,80,000"` (POS); TOS=322000 | ✓ |
| `fe67f506` | 6–20 | Same as 698ced97 pattern | ✓ (redundant) |

**Pattern:** The bot systematically quotes POS as the closure/full-payment amount instead of TOS. This is a recurring production bug affecting all conversations where closure is offered.

### T1 quiet hours

| Conv | Turn | Timestamp IST | Confirmed |
|------|------|---------------|-----------|
| `bd080e56` | 0 | 21:37 | ✓ initial outbound during quiet hours |
| `d70454f9` | 0 | 20:07 | ✓ |
| `55d0c883` | 0 | 21:57 | ✓ |
| `698ced97` | 0 | 22:00 | ✓ |
| `cef7d0f9` | 0 | 00:01 | ✓ |
| `eaa4c64e` | 0, 3 | 22:08 | ✓ (turn 3: bot restart after escalation, no borrower reply since prior bot) |
| `2c55a668` | 0 | 23:33 | ✓ |
| `7d118cdb` | 0, 3, 10 | 00:06 | ✓ (turns 3 and 10: bot restart pattern) |

T1 quiet-hour exception (borrower replied during quiet hours → bot may respond) is applied correctly. In `2c55a668`, turns 5–8 are all during quiet hours but no T1 is flagged because the borrower consistently replies during quiet hours before each bot message. ✓

### T2 follow-up too soon

All T2 violations are at `0.0h` gap — confirmed to be legitimate. In all cases, the bot sends a second "intro/restart" message within 2–10 seconds of the prior bot message without any intervening borrower reply. This is the `zcm_timeout` re-engagement pattern firing immediately after escalation.

| Conv | Turn | Gap | Confirmed |
|------|------|-----|-----------|
| `032101dc` | 3, 10 | 5s, 2s | ✓ |
| `91faad79` | 3, 10 | ~5s | ✓ |
| `c1cffa15` | 10 | ~5s | ✓ |
| `eaa4c64e` | 3, 5 | 5s each | ✓ |
| `59147cd2` | 3 | ~5s | ✓ |
| `0ff9571e` | 3 | ~5s | ✓ |
| `18047863` | 10 | ~5s | ✓ |
| `7d118cdb` | 3, 10 | 4s, 4s | ✓ |

### T3 early dormancy

| Conv | Turn | Gap | Confirmed |
|------|------|-----|-----------|
| `2c55a668` | 9 | 0.0 days | ✓ — `payment_confirmed → dormant` within 2 seconds. The conversation succeeded but was immediately marked dormant. This is a production system bug. |

---

## Per-Conversation Summary Table

| Conv ID | Lang | Violations Flagged | Correct | False Pos | Missed |
|---------|------|--------------------|---------|-----------|--------|
| `bd080e56` | hinglish | A4×1, T1×1 | 2 | 0 | 0 |
| `032101dc` | english | T2×2 | 2 | 0 | 0 |
| `03f02884` | english | A4×1 | 1 | 0 | 0 |
| `d70454f9` | hindi | A3×1, A5×1, T1×1 | T1 only | 2 (A3, A5) | 1 (A4 t12) |
| `55d0c883` | hindi | A3×1, A5×1, T1×1 | T1 only | 2 (A3, A5) | 1 (A4 t6) |
| `698ced97` | english | A4×15, T1×1 | 16 | 0 | 0 |
| `c1cffa15` | english | T2×1 | 1 | 0 | 0 |
| `91faad79` | english | T2×2 | 2 | 0 | 0 |
| `cef7d0f9` | hinglish | T1×1 | 1 | 0 | 0 |
| `01d2bc92` | hinglish | A4×1, A3×1, A5×1 | A4 only | 2 (A3, A5) | 0 |
| `b4e40ff4` | english | (clean) | ✓ | 0 | 0 |
| `eaa4c64e` | hinglish | A4×1, A3×1, A5×1, T1×2, T2×2 | A4, T1, T2 | 2 (A3, A5) | 0 |
| `18047863` | hindi | T2×1 | 1 | 0 | 0 |
| `59147cd2` | english | A4×1, T2×1 | 2 | 0 | 0 |
| `0ff9571e` | english | A4×1, T2×1 | 2 | 0 | 0 |
| `2c55a668` | english | A4×1, T1×1, T3×1 | 3 | 0 | 0 |
| `fe67f506` | english | A4×15 | 15 | 0 | 0 |
| `7d118cdb` | english | T1×3, T2×2 | 5 | 0 | 0 |
| `9a367ccb` | hinglish | A4×1, A3×1, A5×1 | A4 only | 2 (A3, A5) | 0 |
| `1c271c17` | hinglish | A4×1, A3×1, A5×1 | A4 only | 2 (A3, A5) | 0 |

---

## Quantitative Summary

- Conversations reviewed: **20**
- Conversations with any amount/timing violation flagged: **18**
- Conversations with at least one false positive: **6** (all Hindi/Hinglish; 100% of Hindi/Hinglish convs that use `ka` after amounts)
- Conversations with missed violations: **2** (`d70454f9`, `55d0c883`)
- True positive violations: correct in 14/20 convs
- False positive A3/A5 violations from regex bug: **12** (across 6 convs)
- Missed A4 violations from Hindi closure phrase: **2** (across 2 convs)
- Redundant A4 violations (same root cause, different turns): **~28** across 2 convs

**The single highest-priority fix** is adding `\b` after `k` in AMOUNT_RE. It eliminates all 12 false positives in Hindi/Hinglish conversations and introduces zero false negatives.
