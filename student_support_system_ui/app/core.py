import os, hmac, hashlib, base64, json, secrets, re
from datetime import datetime, timedelta

SECRET = os.getenv("SECRET_KEY", "dev-only-change-me").encode()
_db = None

def get_db():
    global _db
    if _db is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        if uri == "mock":
            import mongomock; c = mongomock.MongoClient()
        else:
            import pymongo; c = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
        _db = c[os.getenv("DB_NAME", "student_support")]
        _db.users.create_index("username", unique=True)
        _db.tickets.create_index("ticket_id", unique=True)
        _db.tickets.create_index([("assigned_team", 1), ("status", 1)])
        _db.tickets.create_index("student_id")
    return _db

def now(): return datetime.utcnow()

# ---- passwords / tokens (PBKDF2, HMAC-signed expiring token) ----
def hash_pw(pw):
    salt = secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()

def verify_pw(pw, stored):
    salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex(), h)

def make_token(username, ttl=8 * 3600):
    p = base64.urlsafe_b64encode(json.dumps({"u": username, "e": int(now().timestamp()) + ttl}).encode()).decode()
    return p + "." + hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()

def read_token(tok):
    try:
        p, sig = tok.split(".")
        if not hmac.compare_digest(sig, hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()): return None
        d = json.loads(base64.urlsafe_b64decode(p))
        return d["u"] if d["e"] > now().timestamp() else None
    except Exception:
        return None

# ---- business rules (authoritative) ----
TEAMS = ["Accounts", "Academic Office", "Administration", "Discipline", "General Support"]
CATEGORY_TEAM = {"Fee": "Accounts", "Attendance": "Academic Office", "ID Card": "Administration",
                 "Documents": "Administration", "Certificate": "Administration",
                 "Discipline": "Discipline", "Other": "General Support"}
SLA_HOURS = {"Fee": 24, "Attendance": 12, "ID Card": 48, "Documents": 48, "Certificate": 72, "Discipline": 4, "Other": 72}
PRIORITIES = ["Low", "Medium", "High", "Urgent"]
TRANSITIONS = {"Open": {"Assigned", "In Progress", "Escalated"},
               "Assigned": {"In Progress", "Escalated"},
               "In Progress": {"Pending Student", "Resolved", "Escalated"},
               "Pending Student": {"In Progress", "Escalated"},
               "Escalated": {"In Progress", "Resolved"},
               "Resolved": {"Closed", "In Progress"},
               "Closed": set()}
FINAL = {"Resolved", "Closed"}
DISCIPLINE_RE = re.compile(r"ragg|harass|bully|threat|assault|molest|eve.?teas|abus", re.I)
LOW_CONF = 0.60

def sla_info(t, at=None):
    at = at or now()
    deadline = t["created_at"] + timedelta(hours=t["sla_hours"])
    done = t["status"] in FINAL
    if done: state = "Breached" if (t.get("resolved_at") or at) > deadline else "Within SLA"
    elif at > deadline: state = "Breached"
    elif (deadline - at).total_seconds() < 0.25 * t["sla_hours"] * 3600: state = "At Risk"
    else: state = "Within SLA"
    end = t["resolved_at"] if done and t.get("resolved_at") else at
    age = (end - t["created_at"]).total_seconds() / 3600
    bucket = "0-24h" if age < 24 else "24-48h" if age < 48 else "48-72h" if age < 72 else "72h+"
    return {"deadline": deadline, "remaining_hours": round((deadline - at).total_seconds() / 3600, 1),
            "age_hours": round(age, 1), "state": state, "ageing": bucket}

# ---- ML (loaded once; never retrained in-app) ----
_models = {}
def _load(name):
    if name not in _models:
        p = os.path.join(os.path.dirname(__file__), "..", "ml", "models", name + ".joblib")
        if os.path.exists(p):
            import joblib; _models[name] = joblib.load(p)
        else: _models[name] = None
    return _models[name]

def _predict(name, row):
    m = _load(name)
    if m is None: return None
    import pandas as pd
    pr = m.predict_proba(pd.DataFrame([row]))[0]
    i = int(pr.argmax())
    return m.classes_[i], float(pr[i])

def classify(title, desc, meta):
    """ML gives a recommendation; discipline keywords override (business rule)."""
    keys = ("department", "year", "semester", "channel", "attachment_present", "previous_tickets_count")
    row = {"text": f"{title} {desc}", **{k: meta.get(k) for k in keys}}
    cat, pri = _predict("category_model", row), _predict("priority_model", row)
    ai = {"category": cat[0] if cat else None, "category_conf": round(cat[1], 3) if cat else None,
          "priority": pri[0] if pri else None, "priority_conf": round(pri[1], 3) if pri else None,
          "needs_review": False, "source": "ml" if cat else "none"}
    category, priority = "Other", "Medium"
    if cat and cat[1] >= LOW_CONF: category = cat[0]
    else: ai["needs_review"] = True
    if pri and pri[1] >= LOW_CONF: priority = pri[0]
    else: ai["needs_review"] = True
    if DISCIPLINE_RE.search(f"{title} {desc}"):
        category, priority, ai["source"] = "Discipline", "Urgent", "rule"
    return category, priority, ai
