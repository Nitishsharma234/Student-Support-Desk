# Architecture

## Stack
FastAPI (API + static file serving) · MongoDB via PyMongo (mongomock for tests) · scikit-learn (offline-trained classifiers, loaded read-only at runtime) · single-file vanilla JS/HTML frontend (no build step, no framework).

## Layout
```
app/
  core.py     business rules: auth (PBKDF2 password hashing, HMAC-signed expiring tokens),
              SLA table, status-transition graph, ML loading/inference, discipline keyword rule
  main.py     FastAPI routes: auth, ticket CRUD/workflow, dashboard, staff list
  static/     single-page vanilla-JS frontend (role landing -> dashboard/queue/detail views)
scripts/
  seed_database.py   creates demo student/staff/manager accounts
  train_models.py    trains category/priority classifiers from the historical CSV (not run automatically)
ml/models/    trained .joblib pipelines (absent until train_models.py is run against real data)
tests/        pytest suite against mongomock (no live DB needed)
```

## Request flow (ticket lifecycle)
1. Student submits a ticket (`POST /api/tickets`).
2. `core.classify()` runs the saved TF-IDF + Logistic Regression pipelines (if present) to suggest category/priority. A regex rule for discipline/ragging/harassment keywords **overrides** the ML suggestion unconditionally — critical routing never depends solely on the model.
3. Category maps to a fixed team (`CATEGORY_TEAM`); the least-loaded staff member on that team is auto-assigned (`pick_staff`).
4. SLA deadline = `created_at + SLA_HOURS[category]` (a fixed table, not learned).
5. Staff reply/add internal notes/change status through a validated transition graph (`TRANSITIONS`); students can only reply and cannot see internal notes or set status.
6. Escalation (manual or via `/api/admin/auto-escalate` for SLA-breached tickets) bumps priority one level and logs to the ticket timeline; a ticket already `Escalated` or in a final state can't be re-escalated (guards against duplicate escalation).
7. Every action is appended to an in-ticket `timeline` array (audit trail), with internal entries filtered out of the student's view.

## Authn/authz
- Passwords: PBKDF2-HMAC-SHA256, per-user salt, 200k iterations.
- Tokens: base64 JSON payload `{username, expiry}` + HMAC-SHA256 signature, verified with constant-time compare; 8-hour TTL.
- Role scoping is enforced server-side on every route (not just hidden in the UI): students are filtered to their own tickets, staff to their team, managers/admins see everything. Cross-tenant ticket access returns `404` (not `403`) so ticket existence isn't leaked to unauthorized users.

## Data model (MongoDB collections)
- `users`: username, name, role (student/staff/manager/admin), team (staff/manager only), password_hash.
- `tickets`: full ticket document including `timeline` (embedded array of {ts, actor, action, detail, internal}), `ai` (model output + review flag), SLA fields computed on read (not stored, so they're always current).
- `counters`: atomic sequence for human-readable ticket IDs (`TKT-<year>-<seq>`).

## Config
`MONGO_URI`, `DB_NAME`, `SECRET_KEY` via environment (`.env`, see `.env.example`). No secrets are hardcoded; `SECRET_KEY` has a dev-only fallback that must be overridden in any real deployment.
