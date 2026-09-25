# Student Support & Ticket Management System
FastAPI + MongoDB + vanilla JS + scikit-learn. One landing page (Student / Staff / Manager-Admin); team & permissions come from the account.

## Run
```
pip install -r requirements.txt
cp .env.example .env            # set MONGO_URI (mongodb://localhost:27017) and SECRET_KEY
export $(grep -v '^#' .env | xargs)
python -m scripts.seed_database                       # demo users
cp <your csv> data/student_support_tickets_50000.csv
python -m scripts.train_models                        # trains + saves ml/models/*.joblib, writes ML_REPORT_generated.md
uvicorn app.main:app --reload                         # http://localhost:8000
pytest -q                                             # uses in-memory mongomock (MONGO_URI=mock)
```
Without trained models the app still works: every ticket goes to **General Support / Medium** flagged "manual verification required" (discipline keyword rule still applies).

## Demo accounts (password `Demo@123`)
Student `STU23BCSE0001` (also `STU23BCSE0002`) · Staff `acc_staff1|2`, `acad_staff1|2`, `adm_staff1|2`, `disc_staff1|2`, `gen_staff1|2` · Managers `acc_mgr`, `acad_mgr`, `adm_mgr`, `disc_mgr`, `gen_mgr` · Admin `admin`

## Design decisions
- ML = recommendation only (TF-IDF + metadata → Logistic Regression, class-balanced). Below 60% confidence the app does not apply it and flags the ticket. Discipline/ragging keywords override ML → Discipline team, Urgent, 4h SLA. Staff can Accept/Change; changes are audited and re-route the ticket.
- **Excluded from ML (leakage):** assigned_team, assigned_staff_id, status, first_response_at, resolved_at, sla_hours (a function of category), resolution_time_hours, sla_breached, escalation_count, number_of_replies, student_response_time_hours, satisfaction_score, first_response_time_hours, reassignment_count. Inputs: title+description, department, channel, year, semester, attachment_present, previous_tickets_count.
- **SLA risk is rule-based** (deadline = created + category SLA; At Risk = <25% time left). No ML SLA model: the dataset's only SLA signals are post-hoc outcomes, so a model would leak.
- Teams: Accounts, Academic Office, Administration (ID Card/Documents/Certificate), Discipline, General Support (Other). The CSV's separate "Student Services" team is merged into Administration.
- Tickets embed their timeline/messages (internal notes flagged and stripped for students). Students get 404 for others' tickets.

## Not done / limitations (honest status)
- Model metrics are not reported yet: the full CSV was not available to me; run `train_models` and use its report. No accuracy is claimed.
- Attachments, `import_csv.py`, ARCHITECTURE/ML_REPORT/ASSUMPTIONS/AI_USAGE docs are not written. Frontend is functional but minimal and was not browser-tested. Auto-escalation runs on manager click, not a scheduler.
- Dataset notes from the visible rows: priority looks weakly tied to text (e.g. a double-payment Fee ticket is "Low"), so expect modest priority accuracy; blank satisfaction/response fields are ignored (post-creation anyway); typos in text are common (TF-IDF bigrams help).
