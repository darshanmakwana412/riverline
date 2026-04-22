# Handoff: Amount Violation Checks via Text Extraction

**Date:** 2026-04-22
**Session focus:** Extend `eval_takehome.py` with amount validation rules that work on message text rather than only on function calls. Data quality audit of amount fields in the production logs, regex extractor for rupee amounts, semantic tagging per mention, and five new checks under A3/A4/A5 driven by `spec.tex` section 7.

---

## What Was Accomplished

All changes are in `/home/darshan/Projects/riverline/eval_takehome.py`. No other files touched.

### Data quality audit (before coding)

Ran a scan across `data/production_logs.jsonl` (700 conversations) to ground the approach:

| Field / signal | Count |
| --- | --- |
| `pos`, `tos` present | 700 / 700 |
| `settlement_offered` (floor) present | 501 / 700 (199 missing) |
| `pos > tos` in metadata | 0 |
| `settlement_offered > pos` in metadata | 0 |
| `send_settlement_amount` function calls | 41 |
| `request_settlement_amount` function calls | 460 |
| `confirm_payment` function calls | 384 |
| Bot messages quoting "full closure at POS" where TOS > POS | ~749 |

Key insight: the existing `_check_amounts` A3 implementation only inspects `send_settlement_amount.params.amount`, which fires in only 41 of 700 conversations. The bot overwhelmingly communicates the amount in message prose, so almost all amount-correctness failures were invisible to the evaluator.

### New regex extractor

`AMOUNT_RE` at module level handles:

- Currency tokens: `₹`, `Rs`, `Rs.`, `INR`, `rupees`, `rupee`
- Indian comma grouping (`1,65,000`) and western grouping (`165,000`), plus plain digits and optional decimals
- Suffix units: `lakh`, `lakhs`, `lac`, `crore`, `cr`, `k`, `thousand`
- Also matches unitted numbers without a currency token (e.g. `1.5 lakh`)

Normalises to integer rupees via `UNIT_MULT`. `_extract_amounts(text)` returns a list of `(amount, start, end)` tuples. Amounts below 100 are dropped as noise.

### Context tagger

`_tag_mention(text, start, end, role)` reads a 50-char window on each side of the match and assigns one of:

- `counter_offer` -- only when role is `borrower` and COUNTER_KW matches (I can pay, will pay, manage, max, de sakta, kar sakti, etc.)
- `closure` -- CLOSURE_KW matches (full closure, full payment, close the account, foreclose, pura payment, entire amount)
- `settlement` -- SETTLEMENT_KW matches (settle, settlement, reduced, approved, offer, discount, waiver, kam amount)
- `outstanding` -- OUTSTANDING_KW matches (outstanding, pending, balance, overdue, you owe, dues, bakaya)
- `generic` -- fallback

Precedence is deliberate: borrower counter-offer first, then closure (most specific), then settlement, then outstanding.

### New checks in `_check_amount_text(conversation)`

1. **A4_closure_not_tos** -- bot message with a `closure`-tagged amount not equal to TOS. Spec section 3 says closure returns the full TOS. Severity scales with `abs(amount - TOS) / TOS`.
2. **A3_text_amount_out_of_bounds** -- bot `settlement`-tagged amount outside `[floor, TOS]`. Skipped when `settlement_offered` is missing. Severity scales with the out-of-range magnitude.
3. **A4_accepts_below_floor** -- borrower `counter_offer` < floor followed by a bot message containing agreement keywords (okay, sure, works, deal, confirmed, etc.) with no `escalate` function call. Severity scales with `(floor - amount) / floor`.
4. **A5_settlement_inconsistent** -- bot settlement-tagged amount changes across messages without an intervening `request_settlement_amount` call to reset the baseline. Severity scales with relative spread.
5. **A5_confirm_mismatch** -- `confirm_payment.params.settlement_amount` differs from the last bot-quoted `settlement` amount.

All severities go through `_clamp_sev(0.3 + 0.7 * relative_error, 0.3, 1.0)`.

### Wired into the evaluator

`_check_amount_text(conversation)` is appended to the violation list in `AgentEvaluator.evaluate` directly after the existing `_check_amounts(conversation)`. The existing A1, A2, and function-call-based A3 are preserved unchanged.

---

## Key Decisions

- **Closure quoted at POS flagged with a dedicated rule, not folded into A5.** Spec section 3 ("For closure, the ZCM returns the full TOS as the amount") makes this a distinct correctness violation, not a consistency one. Fired 212 times on the eval split.
- **Missing floor silently skips A3.** 199 of 700 conversations lack `settlement_offered`. A proxy like 0.7 x POS was rejected to avoid false positives on the hidden test set. A data-quality rule for missing floor was considered but skipped to keep the violation stream focused on spec violations.
- **Borrower amounts are extracted, not only bot amounts.** Enables A4_accepts_below_floor. Currently fires zero times on the eval split (floor is often equal to POS and counter offers rarely go below it), but the check is present for the hidden test set.
- **Severity scales with magnitude, clamped to [0.3, 1.0].** Applies across all five new rules, more informative than the static 0.6 / 0.9 levels used by A1 / A2 / existing A3.
- **Baseline reset uses `request_settlement_amount`, not `send_settlement_amount`.** The latter is too rare in the data (41 calls) to be useful as a reset signal. A new ZCM quote cycle in practice begins when the bot re-requests.
- **No changes to scoring formulas.** `quality_score` and `risk_score` still use the same `total_sev / total_turns` and `max_sev * 0.5 + avg_sev * 0.5` combination.

---

## Important Context for Future Sessions

### Results on the eval split (211 conversations, using `scripts/eval_split.json`)

```
avg quality_score: 0.401
avg risk_score:    0.911
total violations:  1818
per-rule counts:
  A3_text_amount_out_of_bounds: 75
  A4_closure_not_tos:           212
  A5_confirm_mismatch:          50
  (A4_accepts_below_floor and A5_settlement_inconsistent both fire 0 on this split)
```

Spot check on conversation `192f029c-2626-7e25-7fee-3fff275530b7`: one `A4_closure_not_tos` at turn 6 for amount 150000 against TOS 165000, no `A5_*`, matches the planned expectation.

### Files and data

- Production logs: `data/production_logs.jsonl`
- Eval split: `scripts/eval_split.json` (211 IDs)
- Classifier bundle: `scripts/classifier_model.pkl`
- Spec: `spec.tex`, section 7 is the amount rules
- Plan file for this session: `~/.claude/plans/hey-we-are-working-synthetic-mountain.md`

### Running the evaluator

The script is a uv executable; `./eval_takehome.py` picks up dependencies inline. Direct `python3 eval_takehome.py` will fail because sklearn is not in the global interpreter.

### Known caveats for the hidden test set

- The context tagger uses English plus some Hindi keywords. Telugu and heavier Hinglish variants may slip through as `generic` and therefore be ignored.
- The closure/settlement keyword sets are heuristic; edge cases where the bot uses synonyms not in the keyword list will silently skip those checks.
- `A5_settlement_inconsistent` treats same-amount re-quotes as identical. If the bot re-quotes after a legitimate ZCM cycle but the `request_settlement_amount` call is missing, the check will false-positive. This trade-off is intentional since missing function calls are already flagged by I4.
- Agreement detection in `A4_accepts_below_floor` is simple keyword match on the first 200 characters. A bot that says "I understand but we cannot accept that" may tokenise partly as "works"-like phrasing and false-positive, though no such cases fired on the eval split.

### Branch status

Working on `main`. No commits made this session. Change is confined to `eval_takehome.py` plus this handoff document.
