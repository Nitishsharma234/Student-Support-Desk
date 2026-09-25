# ML Report

## Status: no metrics to report yet
`data/student_support_tickets_50000.csv` is **not included** in this submission and no model files ship in `ml/models/`. No accuracy, precision/recall, or confusion-matrix numbers are claimed anywhere in this project — that would mean fabricating results. The app is fully functional without the models: `core.classify()` falls back to `category="Other"`, `priority="Medium"`, and flags the ticket `needs_review=True` for manual staff verification (this path is covered by `tests/test_app.py::test_sla_and_low_confidence` and `test_workflow_and_escalation`).

## How to generate a real report
```
cp <your 50k-row CSV> data/student_support_tickets_50000.csv
python -m scripts.train_models
```
This trains two independent pipelines (category, priority), prints per-class precision/recall/F1 and a confusion matrix to stdout, and writes `ML_REPORT_generated.md` with the actual holdout accuracy for whatever data is supplied. That generated file, not this one, is the source of truth for metrics once training has been run.

## Model design
- **Task**: two separate multi-class classifiers — ticket category, ticket priority — not one joint model.
- **Features**: `title + description` text (TF-IDF, uni+bigrams, `min_df=2`, sublinear TF) plus `department`, `channel` (one-hot), and `year`, `semester`, `attachment_present`, `previous_tickets_count` (numeric, passthrough).
- **Model**: `LogisticRegression(class_weight="balanced")` — chosen over heavier models for interpretability and fast inference on a modest tabular+text feature set; class weighting compensates for category/priority imbalance instead of oversampling.
- **Split**: 80/20 stratified holdout, `random_state=42`.
- **Cleaning**: rows missing text/category/priority are dropped; exact `(text, category, priority)` duplicates are dropped before the split so duplicate rows can't inflate the held-out score.

## Leakage prevention
Excluded from every feature set: `assigned_team`, `assigned_staff_id`, `status`, `first_response_at`, `resolved_at`, `sla_hours` (a deterministic function of category — using it would leak the label), `resolution_time_hours`, `sla_breached`, `escalation_count`, `number_of_replies`, `student_response_time_hours`, `satisfaction_score`, `first_response_time_hours`, `reassignment_count`. All of these are only known *after* a ticket is processed, not at creation time, so including any of them would leak the target and produce meaningless inflated accuracy. Only creation-time fields are used as inputs (see list above).

## Inference-time safeguards
- Confidence threshold: predictions below `LOW_CONF = 0.60` are **not applied** — the ticket falls back to the safe default and is flagged for manual review rather than trusting a low-confidence guess.
- Discipline/ragging/harassment keyword rule (`core.DISCIPLINE_RE`) always overrides the model, regardless of what it predicts or how confident it is. Critical safety routing does not depend on ML.
- Models are loaded once at process start and never retrained inside the running app — `train_models.py` is a separate offline step.

## Known dataset caveats (from the columns described in the schema, not from having trained on it)
Priority appears to correlate only loosely with ticket text (e.g. a "double payment" Fee complaint could plausibly be tagged Low), so priority accuracy is expected to be materially lower than category accuracy once real numbers are produced — this should be treated as an expected limitation of the labels, not a bug in the pipeline.
