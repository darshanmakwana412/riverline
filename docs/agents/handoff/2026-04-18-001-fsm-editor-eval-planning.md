# Handoff: FSM Editor Build and Eval Planning

**Date:** 2026-04-18  
**Session focus:** Initial project exploration, visual FSM editor implementation, data analysis, evaluation strategy design

---

## What Was Accomplished

### Visual FSM Editor (`editor.py`)

Built a self-contained Flask web app that serves a single-page conversation inspector at `http://127.0.0.1:5000`. Run with `./editor.py` (uv executable, no venv needed).

**Layout:**
- Left sidebar: searchable list of all 700 conversations by index (#1-#700) or UUID fragment
- Center panel: conversation messages, metadata, outcome card, full annotator annotations
- Right panel: SVG FSM graph with visited states highlighted purple, state transition log

**Key features implemented:**
- FSM rendered as SVG with 11 states in a 3-column grid layout. States visited in the conversation are filled light purple; the final state is filled solid purple with a darker border. Arrows drawn between visited state pairs.
- Each borrower message has a circular annotation button (top-right of bubble) showing a count badge if that turn has failure points. Clicking opens a popover listing all annotators' failure points for that turn (annotator name, category, severity, note). Clicking elsewhere closes it.
- Function calls rendered inline below the bot message at the turn they were called, styled as blue monospace blocks with a left border. Only appears under bot messages (a bug was fixed mid-session where they also appeared under borrower messages at shared turn numbers).
- Outcome card includes all fields: payment received, days to payment, payment amount, expected amount, channel attribution, concurrent channels (tag pills), borrower life event, borrower complained, regulatory flag, human intervention required.
- State transition log in right panel shows turn number, from state, to state, and reason for each transition.

### Data Analysis and Observations

Several findings confirmed by querying the data directly:

1. **Synthetic personas:** The dataset uses approximately 90 recurring borrower personas (e.g. Deepak: 8 conversations, Gaurav Pandey: 6) across 700 conversations. Each persona appears with different loan amounts, DPDs, and outcomes across multiple conversations.

2. **Redacted credentials:** Only 78 unique verification responses exist across all 700 conversations. Credentials like "rajesh@email.com" and "my number ends with 4523" are synthetic placeholders, not real personal data. This is a data generation artifact, not PII scrubbing of real transcripts.

3. **expected_amount is always 10000:** The `expected_amount` field in `data/outcomes.jsonl` is 10000 for every record. The `payment_amount` field uses the same normalized 0-10000 scale. The POS and TOS values in conversation metadata are in real rupees. Do not compare outcome amounts directly to metadata amounts.

4. **Intentionally seeded failures:** Conversation #11 (ID `373469b5-c72f-0ac9-77a3-6f03ccf19a9e`) shows the bot asked for last 4 digits of phone at turn 2, the borrower gave an email address at turn 3 (classified `unclear (low)`), and the bot still transitioned `verification -> intent_asked` with reason `"verification_accepted"` at turn 4. This pattern repeats across adjacent conversations with the same persona, suggesting it is a deliberately planted spec violation rather than a generation artifact.

5. **Striking annotator disagreement:** Conversation #660 (ID `9fa3d4a0-dc9f-d736-9fcb-d65caa87a05b`) has all three annotators: annotator_1 scored 0.38 with 6 failure points including `ignored_hardship` at turn 2; annotator_2 scored 0.70 with 2 failure points; annotator_3 scored 0.75 with zero failure points. This is the sharpest disagreement observed and a good anchor example for the writeup's annotator disagreement section.

---

## Key Decisions and Architecture

### Evaluator approach settled on

The `AgentEvaluator` in `eval_takehome.py` must not make external API calls inside `evaluate()`, and must generalize to unseen conversations. This rules out pre-caching LLM analysis of the 700 training conversations. The agreed approach is a **layered rule engine**:

| Layer | Detection method | Coverage |
|---|---|---|
| FSM transitions | Deterministic matrix check against spec Table 3 | Near-perfect |
| Timing (quiet hours, follow-up spacing, dormancy) | Timestamp arithmetic in IST (UTC+5:30) | Perfect |
| Amount validation | Arithmetic against POS/TOS from metadata | Perfect |
| Compliance (DNC, hardship, threats) | Keyword regex on message text | ~80% recall |
| Quality (repetition, context loss, efficiency) | String similarity + structural heuristics | Partial |

**Specific checks to implement:**

FSM layer:
- Validate every (from_state, to_state) pair against the allowed transition matrix
- Detect verification bypass: `verification -> intent_asked` when the last borrower classification was `unclear`
- Detect post-exit messages: any bot message after entering `escalated` or `dormant`
- Detect action-state mismatch: e.g. `confirm_payment` function called outside the `date_amount_asked -> payment_confirmed` transition

Timing layer:
- Quiet hours: bot-initiated messages (no preceding borrower message) with IST timestamp between 19:00 and 08:00
- Follow-up spacing: consecutive bot messages with no borrower message in between and gap less than 4 hours
- Dormancy: conversation ending without exit state where last borrower message is more than 7 days before last bot message

Compliance layer:
- DNC: borrower message contains stop/block/leave-me-alone signals; check that next transition is `escalated`
- Hardship: borrower message contains job-loss/medical/crisis signals; check next bot message for empathy keywords and absence of payment-push keywords
- Threats: bot message contains legal-action/court/property-seizure keywords

Quality layer:
- Repetition: `difflib.SequenceMatcher` between consecutive bot messages, flag ratio above 0.85
- Misclassification proxy: count of `unclear (low)` classifications where the bot still advanced state
- Turn excess: `total_turns` significantly above minimum expected for the final state reached

### Risk and quality score design

- `risk_score`: weighted sum of compliance and invariant violations, clamped to 0-1. Critical violations (DNC ignored, post-exit message) add 0.4 each; high severity (quiet hours, threat language) add 0.2; medium add 0.1.
- `quality_score`: 1.0 minus penalties for soft violations (repetition, misclassification rate, turn excess), clamped to 0.

### Outcome correlation strategy

The `channel_attribution` field is "uncertain" for most records, making payment outcome a poor direct signal for conversation quality. Focus correlation analysis on `borrower_complained` and `regulatory_flag` as the dependent variables -- these are causally attributable to the WhatsApp conversation itself. Use payment outcomes only for records where attribution is deterministic and no concurrent channels are present.

---

## Important Context for Future Sessions

### File locations

```
data/production_logs.jsonl      700 conversations (3.5 MB)
data/outcomes.jsonl             700 outcome records
data/annotations/annotator_1.jsonl  200 annotations
data/annotations/annotator_2.jsonl  200 annotations
data/annotations/annotator_3.jsonl  200 annotations (100 overlap all three)
spec.tex                        Full FSM specification source
docs/domain.md                  Glossary and compliance rules
eval_takehome.py                AgentEvaluator stub (not yet implemented)
editor.py                       Visual FSM editor (implemented, working)
```

### Annotation coverage

Each annotator labeled 200 conversations. 100 conversations were labeled by all three annotators. The other 400 conversations have no annotations at all. The 100 triple-annotated conversations are the primary dataset for inter-annotator agreement analysis.

### Known spec facts to encode

- Valid progression states in order: `new`, `message_received`, `verification`, `intent_asked`, `settlement_explained`, `amount_pending`, `amount_sent`, `date_amount_asked`, `payment_confirmed`
- Exit states: `escalated`, `dormant` (no transitions out)
- Only allowed backward transition: from `settlement_explained` or `amount_pending` back to `intent_asked`, only when borrower intent is `unclear` with low confidence
- Any progression state can transition to `payment_confirmed` on a `payment_received` system event
- Dormancy after 7 days (10,080 minutes) of no borrower response
- `zcm_timeout` from `amount_pending` must escalate

### Outstanding deliverables

Nothing has been written to `eval_takehome.py` yet. The `AgentEvaluator.evaluate()` method returns the stub `{"quality_score": 0.5, "risk_score": 0.5, "violations": []}`. The next session should implement the full rule engine described above.

After the evaluator is built, run it on all 700 conversations and produce:
- `violations.md`: violation type frequencies, outcome correlations, segment breakdowns (by DPD, language, zone), specific conversation examples with turn references
- `writeup.md`: 4-page max covering methodology, annotator disagreement analysis (Krippendorff's alpha on the 100 triple-labeled), findings, limitations, and the 3-month production eval system design

### Running the editor

```bash
./editor.py           # starts at http://127.0.0.1:5000
./editor.py --port 8080  # alternate port
```

The editor loads all data at startup and serves it in memory. No rebuild needed for data changes.
