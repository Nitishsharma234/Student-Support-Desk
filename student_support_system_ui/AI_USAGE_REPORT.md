# AI Usage Report

## What AI was used for
- Scaffolding and writing the initial implementation of the FastAPI backend (`app/core.py`, `app/main.py`), the vanilla-JS frontend (`app/static/index.html`), the seed/train scripts, and the pytest suite.
- A subsequent QA/review pass (this pass): the codebase was inspected end-to-end, all tests were run, and the previously-missing documentation files (this file, `ARCHITECTURE.md`, `ML_REPORT.md`, `ASSUMPTIONS.md`) were written to close out the submission checklist. No application logic needed to change — startup, auth, RBAC, routing, SLA/escalation, and the full test suite (5/5) were already working, so this pass was documentation-only plus verification.

## What AI was explicitly not used for
- No ML metrics, accuracy numbers, or confusion matrices were invented. `ml/models/` contains no trained model files because the real 50k-row training CSV was never supplied; the app's documented fallback behavior (safe defaults + manual-review flag) is what's actually running, not a fabricated model.
- No architecture, features, or dependencies (chatbot, WhatsApp integration, Kafka, Kubernetes, microservices, etc.) were added beyond what the brief specifies.

## Human review
All AI-generated code and docs in this submission should be read and understood before presenting it as your own work in an interview — in particular, be ready to explain: the PBKDF2/HMAC auth design in `core.py`, why the ML feature list excludes the columns it excludes (leakage), the status-transition graph, and the SLA "At Risk" threshold, since these are the most likely areas to be questioned on.

## Verification performed this pass
- `pytest -q` → 5/5 tests passing (auth, cross-student access denial, internal-note visibility, discipline-keyword routing override, full status/assignment/escalation workflow, SLA state/ageing calculation, low-confidence fallback).
- App boots and serves `/` and `/api/*` correctly under `MONGO_URI=mock` (no live MongoDB required for tests) and against a real MongoDB URI in normal operation.
- Manually traced the ticket lifecycle (create → ML/rule classification → routing → assignment → SLA calc → reply/status → escalation → resolution → closure) against the code to confirm it matches the required workflow.
