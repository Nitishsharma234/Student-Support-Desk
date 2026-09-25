"""Train category + priority models from the historical CSV. Usage: python -m scripts.train_models [csv]"""
import sys, os, joblib, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

CSV = sys.argv[1] if len(sys.argv) > 1 else "data/student_support_tickets_50000.csv"
# Creation-time-only inputs. EXCLUDED (known only after processing => leakage): assigned_team, assigned_staff_id, status,
# first_response_at, resolved_at, sla_hours (derived from category), resolution_time_hours, sla_breached, escalation_count,
# number_of_replies, student_response_time_hours, satisfaction_score, first_response_time_hours, reassignment_count.
CATS, NUMS = ["department", "channel"], ["year", "semester", "attachment_present", "previous_tickets_count"]
NEED = ["ticket_title", "ticket_description", "category", "priority"] + CATS + NUMS
if not os.path.exists(CSV): sys.exit(f"Dataset not found: {CSV}")
df = pd.read_csv(CSV)
miss = [c for c in NEED if c not in df.columns]
if miss: sys.exit(f"Dataset is missing required columns: {miss}")
n0 = len(df)
df = df.dropna(subset=["ticket_title", "ticket_description", "category", "priority"])
df["text"] = df.ticket_title.astype(str) + " " + df.ticket_description.astype(str)
df = df.drop_duplicates(subset=["text", "category", "priority"])   # exact duplicates would inflate test scores
print(f"rows {n0} -> {len(df)} after cleaning")
X = df[["text"] + CATS + NUMS].copy(); X[NUMS] = X[NUMS].apply(pd.to_numeric, errors="coerce").fillna(0)
rep = ["# ML Report (auto-generated)\n", f"Rows used: {len(df)} (dropped {n0-len(df)} incomplete/duplicate)\n"]
for target in ("category", "priority"):
    y = df[target]; print(f"\n== {target} distribution\n{y.value_counts()}")
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    pipe = Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True), "text"),
                                              ("c", OneHotEncoder(handle_unknown="ignore"), CATS), ("n", "passthrough", NUMS)])),
                     ("m", LogisticRegression(max_iter=2000, class_weight="balanced"))])
    pipe.fit(Xtr, ytr); p = pipe.predict(Xte)
    r = classification_report(yte, p, zero_division=0); cm = confusion_matrix(yte, p, labels=pipe.classes_)
    print(r, cm); os.makedirs("ml/models", exist_ok=True); joblib.dump(pipe, f"ml/models/{target}_model.joblib")
    rep += [f"\n## {target}\nDistribution:\n```\n{y.value_counts()}\n```\nAccuracy (20% stratified holdout): {accuracy_score(yte, p):.4f}\n```\n{r}\n```\nLabels: {list(pipe.classes_)}\n```\n{cm}\n```\n"]
open("ML_REPORT_generated.md", "w").write("\n".join(rep))
