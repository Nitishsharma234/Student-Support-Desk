# Student Support Desk

A role-based Student Support & Ticket Management System designed for colleges to manage student requests, staff ownership, SLAs, escalations, and ticket resolution.

The system also includes an ML-assisted layer for ticket category and priority prediction, with manual verification for uncertain predictions.

---

## 🚀 Features

### Student
- Create support tickets
- View personal tickets
- Track ticket status
- Reply to tickets
- View ticket history
- Submit feedback after resolution

### Staff
- View assigned tickets
- Process support requests
- Update ticket status
- Reply to students
- Add internal notes
- Resolve or escalate tickets
- Monitor SLA status

### Manager / Admin
- View organization-level ticket information
- Monitor SLA and escalations
- View staff workload
- Track ticket ageing
- Monitor categories and priorities
- Review operational activity

---

## 🤖 ML-Assisted Ticket Classification

The system is designed to predict:

1. **Ticket Category**
   - Fee
   - Attendance
   - ID Card
   - Documents
   - Certificate
   - Other
   - etc.

2. **Ticket Priority**
   - Low
   - Medium
   - High
   - Urgent

### Model

The planned ML pipeline uses:

- TF-IDF text features
- Unigrams + bigrams
- One-hot encoded categorical features
- Logistic Regression
- Class weighting for imbalanced classes
- 80/20 stratified holdout split

The text input consists primarily of the ticket title and description, along with creation-time metadata.

### Important: No Fabricated Metrics

The training dataset is not included in this repository and models are not shipped with the submission.

Therefore, **no accuracy, precision, recall, F1-score, or confusion-matrix values are claimed**.

This is intentional. Reporting metrics without actually training and evaluating the model would be misleading.

When the dataset is available, the training pipeline can generate a real evaluation report.

---

## 🔐 ML Safety & Leakage Prevention

The model only uses information available when a ticket is created.

Post-processing information such as:

- assigned staff
- assigned team
- ticket status
- resolution time
- SLA breach
- escalation count
- number of replies
- satisfaction score
- response times

is excluded from the ML feature set.

This prevents target leakage and avoids artificially inflated evaluation results.

### Low-Confidence Predictions

If model confidence is below `0.60`, the prediction is not blindly applied.

Instead:

```text
Low confidence
      ↓
Safe default
      ↓
needs_review = True
      ↓
Staff manually verifies
