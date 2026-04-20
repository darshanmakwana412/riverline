# Evaluator Audit — Bugs, Gaps, and Missing Checks

Manual verification of 5 randomly sampled held-out conversations (seed=7) plus a full-dataset scan of `bot_classifications.input_text` vs actual borrower message text.
Each item is a distinct problem found either in the evaluator logic or in spec coverage.

---

## Bugs (evaluator produces wrong output)

- [ ] **T2 sort bug — same-turn bot follow-ups silently skip T2 check**
  
  `_check_timing` sorts messages by `(turn, 0 if borrower else 1)`, placing borrower messages before bot messages whenever they share the same turn number. In practice, the data records a bot follow-up and a borrower reply under the same turn when the borrower responds after the second bot message. The sort places the borrower message first, so `last_borrower_ts` is updated before the bot message is evaluated, making the condition `last_borrower_ts <= last_bot_ts` false — the T2 check is then skipped entirely even though no borrower reply had arrived at the time the bot sent its follow-up.

  **CONV 4 (`04e42d86`):** bot t02 at 15:51:08 → bot t03 at 15:51:12, 4-second gap, no borrower reply in between. T2 (min 240 min) violation not flagged.

  **CONV 5 (`4ed96e1c`):** bot t02 at 10:29:04 → bot t03 at 10:29:05, 1-second gap, no borrower reply in between. T2 violation not flagged.

  In both cases the borrower reply at the same turn number (t03) had a timestamp *after* the second bot message, confirming the sort puts them in the wrong order relative to wall-clock time.

---

- [ ] **Q2 false positive — classifier mislabels payment commitment as `asks_time`**

  `_check_q2` trusts the classifier's prediction without any sanity check on plausibility. The classifier predicts `asks_time` with confidence 0.95 for "I'll take care of it within 3 days, don't worry." — a clear payment commitment, not a request for more time. The bot's label of `unclear` is also imprecise, but the classifier is categorically wrong here. The resulting Q2 violation at t10 of CONV 5 (`4ed96e1c`) is a false positive: the bot did not misclassify; the classifier did.

  This turns up as `Q2_accurate_classification sev=0.967` for a turn where the borrower is committing to pay. Any downstream analysis treating all Q2 flags as bot errors will over-count compliance risk on this conversation.

---

## Gaps in existing checks (check exists but covers only half the rule)

- [ ] **I4 only checks function→transition direction, not transition→function direction**

  `_check_actions` iterates over `function_calls` and verifies that each call fired during the correct transition. It never checks the reverse: whether a transition that requires a specific function call actually had that call. Spec §4 states `send_settlement_amount` must happen during every `amount_pending → amount_sent` transition. In three conversations this transition fires without any `send_settlement_amount` in `function_calls`, and none are flagged.

  **CONV 2 (`a243eecc`):** transitions `amount_pending → amount_sent` at t06; no `send_settlement_amount` in function_calls. Bot message says "After discussing with my team, we can offer you a settlement of ₹85,500" — the amount was sent to the borrower without the action being recorded. Not flagged.

  **CONV 3 (`a66d82a7`):** transitions `amount_pending → amount_sent` at t07; no `send_settlement_amount` in function_calls. Bot message says "maine aapke liye ₹39,500 ka settlement approve karwa liya hai." Not flagged.

  **CONV 5 (`4ed96e1c`):** transitions `amount_pending → amount_sent` at t08; no `send_settlement_amount` in function_calls. Not flagged.

  The same gap applies to `confirm_payment` (required on `date_amount_asked → payment_confirmed`) and `request_settlement_amount` (required on `settlement_explained → amount_pending`), though those were not observed to be missing in this sample.

---

## Missing checks (spec rules with no evaluator coverage)

- [ ] **Q5 repetition not implemented — bot loops with identical/near-identical messages**

  Spec §Q5 ("No Repetition"): the agent must not send identical or near-identical messages; repeated messages indicate the agent is stuck in a loop, with severity increasing with repetition count. No check for this exists in the evaluator.

  **CONV 1 (`4f46015f`):** the bot sends the message "Aapka ₹63,250 ka amount 35 din se pending hai. Hum aapki madad karna chahte hain. Aap kya sochte hain?" verbatim at t05, t06, t07, and t08 — four consecutive identical bot messages — while the borrower is repeatedly saying "Main pay karna chahta hun. Options batayein?" The bot is stuck in a loop at `intent_asked` for 4 turns with no state change and no new information to the borrower. Not flagged.

  **CONV 5 (`4ed96e1c`):** the bot sends the same introductory message ("Hi Rahul! This is Priya from Riverline Financial Services...") at t00 and again at t03, the second time without any borrower reply in between (the t03 follow-up that also violated T2 above). Not flagged.

---

- [ ] **DNC / compliance keyword check not implemented**

  Spec §6.3 (Do Not Contact): if the borrower explicitly asks to stop communication the agent must immediately escalate and never send another message. Spec §6.1 lists "explicit requests to stop communication" as a mandatory escalation trigger. No compliance keyword check exists in the evaluator.

  **CONV 4 (`04e42d86`):** at t01 (15:51:03) the borrower writes "Who tf are you? Stop harassing me." — "stop" and "harassing" are clear DNC/communication-refusal signals. Per spec the bot was required to immediately escalate at this point. Instead the bot sent four more messages (t02, t03, t04, t05) before eventually escalating at t05 after "Talk to my lawyer." The 4-turn delay is a compliance failure. The evaluator only flags Q2 (misclassification of `unclear` vs `refuses`) at t01; the DNC compliance break is not flagged at all.

---

- [ ] **Amount validation (spec §7) not implemented — no A1–A5 checks**

  Spec §7 defines three invariants on loan amounts: POS ≤ TOS (A1), settlement floor ≤ POS (A2), and settlement floor ≤ offered amount ≤ TOS (A3). A4 covers the floor counter-offer requirement and A5 covers intra-conversation amount consistency. None of these are checked.

  **CONV 2 (`a243eecc`):** metadata has pos=95000, tos=109250, settlement_offered=85500. The offered amount (85500) is below POS (95000). Without knowing the floor (metadata shows `None`) we cannot determine if A3 is violated, but the check infrastructure does not exist to catch this even when floor is present.

  **CONV 3 (`a66d82a7`):** metadata has pos=40000, tos=46000, settlement_offered=39500. Offered is below POS; floor is `None`. Same gap.

  **CONV 5 (`4ed96e1c`):** metadata has pos=45000, tos=51750, settlement_offered=36000. Offered (36000) is below POS (45000) by a wide margin. Bot message at t07 quotes "Option 1 is a full payment of ₹45,000" (correctly POS) but the settlement was approved at ₹36,000. Without floor data from metadata the A3 constraint cannot be verified, but the evaluator makes no attempt even when the data is present.

---

## Data integrity — bot classified on a different text than the actual borrower message

- [ ] **`bot_classifications.input_text` does not match the actual borrower message in 39.7% of all turns**

  Every `bot_classifications` entry carries an `input_text` field — the text the bot actually passed to its classifier. A full scan of all 700 conversations (5,542 classification entries) shows that `input_text` differs from the corresponding borrower message in `messages[]` at the same turn in **2,199 cases (39.7%)**.

  The pattern is not random noise. Only **165 unique mismatched input_texts** exist across those 2,199 cases, meaning the bot is collapsing thousands of distinct real borrower messages into a small vocabulary of canonical paraphrase templates before classification. The top reused templates and how often they appear as the classified text instead of the actual message:

  | Times reused | Canonical input_text used for classification |
  |---|---|
  | 58 | `'Main kuch nahi dunga. Main apne vakil se baat karunga.'` |
  | 50 | `'Maine already pay kar diya hai. Apne records check karo.'` |
  | 49 | `"Yes, I'd like to settle this. What are my options?"` |
  | 46 | `"Hi, I'm doing fine. Yes, I know about the pending amount."` |
  | 35 | `'Yes, my number ends with 4523.'` |
  | 34 | `'Stop calling me. I don\'t owe you anything.'` |
  | 30 | `"I'm not paying anything. I'll talk to my lawyer."` |

  The actual messages behind these classifications are all semantically similar but carry different phrasing, tone, emotional intensity, and — critically — different nuance that affects the correct label. For example, one of the 5 actual messages behind the 58x Hindi refuses template is `"Please anything lower Priya ji... I'm telling you honestly I barely have enough to feed my family right now."` — a `hardship` signal, not `refuses` — yet it received the same classification as messages that were genuine refusals, because the classifier never saw the real text.

  **Consequence for the evaluator:** Every Q2 check in `_check_q2` compares the classifier's prediction (run on the actual text) against the bot's stored label (produced from the paraphrase template). The two models are not evaluating the same input. This means some Q2 violations are not bot misclassifications — they are the legitimate consequence of the bot classifying a lossy paraphrase while the evaluator's classifier sees the richer original. The Q2 severity scores are systematically misleading for all 2,199 affected turns.

- [ ] **14 cases where `input_text` exactly matches a borrower message from a different turn in the same conversation**

  In 14 classification entries across the dataset the `input_text` is not the paraphrase of the current turn — it is the verbatim text of a different borrower turn in the same conversation. The bot classified an older message and attached the result to the wrong turn. Example from conv `894d88d8`:

  - bc at turn 7, `input_text = "I'll think about it and get back to you."` — this is the exact text of turn 5. The actual message at turn 7 is `"I'll get back to you, I said."` The classification `unclear` was assigned to turn 7 but was derived from turn 5's text.
  - bc at turn 8 in the same conversation has the same `input_text` as turn 5, while the actual turn 8 message differs again.

  Any state-transition check that uses `preds_by_turn` (which the evaluator's backward-exception logic does) will look up the wrong classification for these turns.

- [ ] **33 cases where `input_text` matches no borrower message anywhere in the entire dataset**

  In 33 entries the `input_text` is neither the actual message at that turn nor any other borrower message in the full 700-conversation corpus. These are fully fabricated strings — the bot classified phantom text that no borrower ever sent. Similarity to the actual message ranges from 0.59 to 0.78, so they are paraphrases that were further distorted to the point of being unique. Example from conv `0b632db3` turn 6:

  - `input_text`: `'Please, anything lower. I barely have enough to feed my family.'`
  - `actual`: `"Please, man, *anything* lower. I'm literally struggling to feed my family here."`
  - `classification`: `wants_settlement` — but the actual message contains strong `hardship` language (`struggling to feed my family`) that was stripped out of the paraphrase, potentially causing a missed escalation trigger.
