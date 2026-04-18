# Handoff: Borrower-Intent Classifier and Evaluator Integration

**Date:** 2026-04-18
**Session focus:** Use Claude Sonnet 4.6 as a ground-truth oracle for borrower-message classification, train a CPU-only classical classifier against those labels, and wire it into `eval_takehome.py` as the first layer of the `AgentEvaluator`.

---

## What Was Accomplished

### Sonnet-based ground-truth annotator (`scripts/annotate_borrower_intents.py`)

Self-paced uv executable script. For each conversation it sends Sonnet 4.6 the raw messages plus metadata, but deliberately withholds the bot's own `bot_classifications` and `state_transitions` so the model is not primed by the production labels. The system prompt attaches the full `spec.tex`, `README.md`, and `docs/domain.md` as context.

Key properties:

1. Prompt caching via `cache_control: ephemeral` on the spec and docs blocks. The ~9.8k-token reference prompt is written once per 5-minute window and read at 0.1x input price thereafter.
2. Parallelism via `ThreadPoolExecutor(max_workers=parallel)`. Caching is unaffected by concurrency; only wall-clock changes. A `--parallel` fire flag exposes this.
3. Full token accounting per request: `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h`. Totals are printed at the end and priced at Sonnet 4.6 rates (`$3 / $15 / $0.30 / $3.75 / $6` per MTok).
4. JSON output per run saved to `scripts/annotations_full.json` containing Sonnet classifications, per-request token counts, and usd cost.

Full run on 700 conversations at `--parallel=20` completed in 6 minutes 19 seconds at a total cost of `$12.09` (about `$0.017` per conversation). Cache writes were zero on the final run because the cache stayed warm across the batch, 6.9M cache-read tokens were billed at `$0.30/MTok`.

### Headline finding from the annotator

Only 53.4 percent agreement between bot's `bot_classifications` and Sonnet labels across 5,542 borrower turns. Dominant failure mode: the bot over-labels messages as `unclear`. Top disagreement is `bot:unclear -> sonnet:asks_time` with 1,380 cases (53 percent of all disagreements). This is strong evidence that the production classifier is under-committing on clear intents.

### CPU-only classical classifier (`scripts/train_classifier.py`)

Self-contained uv script. Treats `annotations_full.json` as ground truth and trains a TF-IDF plus LinearSVC pipeline.

Architecture:

- `FeatureUnion` of TF-IDF word 1-3 grams, TF-IDF char_wb 2-5 grams, and 14 hand-crafted features (length, digit presence, date-regex hit, emoji count, `?` and `!` flags, please/plz/namaste heuristic, and lexicon hit counts for time, refuse, dispute, hardship, settle, closure words in English plus Hindi/Hinglish).
- `CalibratedClassifierCV` wrapping `LinearSVC(class_weight='balanced')` so the evaluator can access `predict_proba` for severity scoring.
- 5-fold stratified `GridSearchCV` over `C` on the training split.

Training data is split at the conversation level, not the message level. Earlier iterations used `train_test_split` on individual messages, which leaked: multiple borrower turns from the same conversation could end up on both sides. The final script groups by `conversation_id`, shuffles with seed 42, and takes the first 70 percent as train. Results: 489 train conversations, 211 held-out conversations, 3,911 train messages, 1,631 held-out messages.

Final metrics on the held-out split:

- macro F1: 0.940
- weighted F1: 0.935
- every class F1 greater than or equal to 0.91
- remaining confusion is almost entirely the `asks_time` vs `unclear` boundary

Artifacts:

- `scripts/classifier_model.pkl`: pickled sklearn Pipeline plus label list
- `scripts/eval_split.json`: `{seed, test_size, train_conversation_ids, eval_conversation_ids}` for downstream no-leak evaluation
- `scripts/classifier_report.txt`: full classification_report plus confusion matrix

### Evaluator integration (`eval_takehome.py`)

Rewritten to be self-contained and network-free. No API calls inside `evaluate()`.

- `HandFeatures` class is redeclared locally with the exact same regexes used at training time. Before unpickling, we do `sys.modules["__main__"].HandFeatures = HandFeatures` so pickle resolves the symbol cleanly despite the class having been defined in `__main__` when the script ran as an entry point.
- `AgentEvaluator.__init__` loads `scripts/classifier_model.pkl` once.
- `evaluate()` runs the classifier on every borrower message and compares against `bot_classifications`. Each disagreement emits a `Q2_accurate_classification` violation. Severity is `min(1.0, 0.3 + 0.7 * classifier_confidence)`, floored at 0.8 when the classifier flips an `unclear` into a high-risk category (`hardship`, `refuses`, `disputes`) because missing those is a compliance concern per spec section 6.
- Scores: `quality_score = 1 - disagreement_rate`, `risk_score = 0.5 * disagreement_rate + 0.5 * mean_severity`.
- `main()` detects `scripts/eval_split.json` and restricts evaluation to the 211 held-out conversation ids so no downstream work can accidentally test on the training set.

Held-out aggregate: average quality 0.556, average risk 0.669, 775 Q2 violations total (about 3.7 per conversation). This matches the 47 percent bot vs Sonnet disagreement rate measured independently.

### Session writeup and plots

- `docs/approach.md`: narrative writeup from problem framing through integration.
- `scripts/make_plots.py`: regenerates six xkcd-styled figures under `docs/plots/`:
  - `class_distribution.png`
  - `bot_vs_sonnet.png`
  - `pipeline.png` (classifier architecture diagram)
  - `confusion_matrix.png`
  - `per_class_f1.png`
  - `eval_scores.png`

---

## Key Decisions

### Why Sonnet 4.6 as the oracle

The 700 conversations have no ground-truth intent labels. Human annotation would be expensive and slow. Sonnet was chosen over Opus because the task is not deeply agentic and Sonnet's pricing is 5x cheaper, while still well above the bot's classifier in spot-checks. Opus would be defensible for a second pass on only the Sonnet-low-confidence subset, but was not needed at this stage.

### Why the bot's output is withheld from Sonnet

Giving Sonnet the bot's `bot_classifications` or `state_transitions` would bias it toward agreeing with the production labels. Since the whole point is to measure where the bot is wrong, the oracle must see only the raw conversation. Metadata is fine, it is an attribute of the account rather than an inference about intent.

### Why a classical classifier, not an LLM, at `evaluate` time

The take-home spec explicitly says `evaluate()` must be self-contained and make no external API calls. A classical TF-IDF + SVM model fits in a pickle under 3 MB, loads in under 100 ms, and predicts a full conversation in under 50 ms on CPU. This fits the run-anywhere constraint.

### Why conversation-level splitting, not message-level

Message-level splitting scored 0.948 macro F1 but leaks: the model sees borrower turns from the same conversation it is later evaluated on, and adjacent turns tend to be semantically similar (same persona, same situation). Conversation-level splitting gives a slightly lower but honest 0.940 macro F1. All downstream evaluator work must use `scripts/eval_split.json` so we do not accidentally report inflated numbers.

### Tried and ruled out

- Balanced-dataset training (downsample every class to the minority class of 271 samples): reduces macro F1 from 0.940 to about 0.931. `class_weight='balanced'` on the full dataset does the same job without throwing away samples. Kept the full-dataset path.
- LogisticRegression with `solver='liblinear'`: errors out because liblinear does not support multiclass. Switched to `lbfgs`. LinearSVC with calibration outperformed LR tuned and untuned.
- Message-level split (rejected): see above, leakage.

---

## Important Context for Future Sessions

### Current branch and repo state

- Branch: `main`, clean aside from this session's additions.
- New files: `scripts/annotate_borrower_intents.py`, `scripts/annotations_full.json` (about 3 MB), `scripts/annotations_sample.json`, `scripts/annotations_sample_p5.json`, `scripts/train_classifier.py`, `scripts/classifier_model.pkl`, `scripts/classifier_report.txt`, `scripts/eval_split.json`, `scripts/make_plots.py`, `docs/approach.md`, `docs/plots/*.png`.
- Modified: `eval_takehome.py`.

### How to re-run the pipeline end to end

```
./scripts/annotate_borrower_intents.py --n=700 --parallel=20 --out=scripts/annotations_full.json
./scripts/train_classifier.py
./scripts/make_plots.py
uv run --with scikit-learn --with numpy --with scipy python eval_takehome.py
```

The API key is read from `.env` at project root (`ANTHROPIC_API_KEY`). The annotate step costs about `$12` per full run. The train step is under 2 minutes on CPU. The evaluator run on 211 held-out conversations is under 5 seconds.

### Data files the evaluator depends on

- `scripts/classifier_model.pkl`: produced by `train_classifier.py`. If the `HandFeatures` class in `eval_takehome.py` drifts from the one in `train_classifier.py` the unpickle will break silently at transform time. Keep them in lockstep.
- `scripts/eval_split.json`: the frozen 211 held-out conversation ids. Do not regenerate unless the Sonnet labels change.
- `scripts/annotations_full.json`: Sonnet labels for all 700 conversations. Safe to check into the repo (about 3 MB).

### Known gaps

- The evaluator currently only emits `Q2_accurate_classification` violations. All the other spec layers (state-transition matrix checks, quiet-hours and spacing timing, amount validation, DNC escalation, compliance keywords) are not yet implemented. The layered rule engine from the previous handoff (`2026-04-18-001`) is still the plan for those.
- No annotator-agreement calibration has been done yet. The three annotator files under `data/annotations/` have not been loaded into any script from this session. They should feed a weighted quality_score once the rule layers exist.
- The classifier's `asks_time` vs `unclear` confusion is the main remaining error mode. Closing it further likely needs a thresholded two-stage detector or a small distilled transformer, which breaks the pure-CPU classical constraint. Left as future work.

### Pricing reference used in cost calculations

Sonnet 4.6 from `https://platform.claude.com/docs/en/about-claude/pricing`:

- input: `$3 / MTok`
- output: `$15 / MTok`
- 5m cache write: `$3.75 / MTok`
- 1h cache write: `$6 / MTok`
- cache read: `$0.30 / MTok`

These constants live in `scripts/annotate_borrower_intents.py` in the `PRICE` dict and should be updated if Anthropic changes rates.
