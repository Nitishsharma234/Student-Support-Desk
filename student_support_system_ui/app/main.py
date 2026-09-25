import os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import core
from .core import get_db, now, PRIORITIES, TRANSITIONS, FINAL, CATEGORY_TEAM

app = FastAPI(title="Student Support Ticket System")
STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

try:
    from pymongo.errors import PyMongoError
    @app.exception_handler(PyMongoError)
    async def db_err(request, exc):
        return JSONResponse({"detail": "Database unavailable. Check MONGO_URI / that MongoDB is running."}, 503)
except ImportError: pass

@app.get("/")
def index(): return FileResponse(os.path.join(STATIC, "index.html"))

def user_dep(request: Request):
    tok = request.headers.get("authorization", "").removeprefix("Bearer ")
    u = core.read_token(tok)
    user = get_db().users.find_one({"username": u}, {"_id": 0}) if u else None
    if not user: raise HTTPException(401, "Not authenticated")
    return user

def is_mgr(u): return u["role"] in ("manager", "admin")

def get_ticket(tid, u):
    t = get_db().tickets.find_one({"ticket_id": tid})
    ok = t and ((u["role"] == "student" and t["student_id"] == u["username"]) or
                (u["role"] == "staff" and t["assigned_team"] == u["team"]) or is_mgr(u))
    if not ok: raise HTTPException(404, "Ticket not found")   # 404 so ticket existence isn't leaked
    return t

def log(t, actor, action, detail="", **extra):
    t["timeline"].append({"ts": now(), "actor": actor, "action": action, "detail": detail, **extra})

def save(t): get_db().tickets.replace_one({"ticket_id": t["ticket_id"]}, t)

def ser(o):
    if isinstance(o, dict): return {k: ser(v) for k, v in o.items() if k != "_id"}
    if isinstance(o, list): return [ser(v) for v in o]
    return o.isoformat() + "Z" if hasattr(o, "isoformat") else o

def view(t, u):
    t = dict(t); t["sla"] = core.sla_info(t)
    if u["role"] == "student":
        t["timeline"] = [e for e in t["timeline"] if not e.get("internal") and e["action"] != "AI prediction"]
        t.pop("ai", None)
    return ser(t)

# ---------- auth ----------
class LoginIn(BaseModel):
    role: str; username: str; password: str

@app.post("/api/login")
def login(d: LoginIn):
    u = get_db().users.find_one({"username": d.username})
    allowed = {"student": {"student"}, "staff": {"staff"}, "manager": {"manager", "admin"}}.get(d.role, set())
    if not u or u["role"] not in allowed or not core.verify_pw(d.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": core.make_token(u["username"]), "user": {k: u.get(k) for k in ("username", "name", "role", "team")}}

@app.get("/api/me")
def me(u=Depends(user_dep)): return {k: u.get(k) for k in ("username", "name", "role", "team")}

# ---------- tickets ----------
class TicketIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    department: str = Field(min_length=2, max_length=40)
    year: int = Field(ge=1, le=6)
    semester: int = Field(ge=1, le=12)
    course: str = Field(min_length=2, max_length=80)
    channel: str = "Web Portal"

def pick_staff(team):
    db = get_db(); best = None
    for s in db.users.find({"role": "staff", "team": team}):
        n = db.tickets.count_documents({"assigned_staff_id": s["username"], "status": {"$nin": list(FINAL)}})
        if best is None or n < best[0]: best = (n, s["username"])
    return best[1] if best else None

@app.post("/api/tickets", status_code=201)
def create_ticket(d: TicketIn, u=Depends(user_dep)):
    if u["role"] != "student": raise HTTPException(403, "Only students can raise tickets")
    db = get_db()
    if not d.title.strip() or not d.description.strip(): raise HTTPException(422, "Title and description are required")
    if db.tickets.find_one({"student_id": u["username"], "title": d.title.strip(), "status": {"$nin": list(FINAL)}}):
        raise HTTPException(409, "You already have an open ticket with this title")
    prev = db.tickets.count_documents({"student_id": u["username"]})
    cat, pri, ai = core.classify(d.title, d.description, {**d.model_dump(), "attachment_present": 0, "previous_tickets_count": prev})
    team = CATEGORY_TEAM[cat]; staff = pick_staff(team)
    seq = db.counters.find_one_and_update({"_id": "ticket"}, {"$inc": {"n": 1}}, upsert=True, return_document=True)["n"]
    t = {**d.model_dump(), "ticket_id": f"TKT-{now().year}-{seq:05d}", "student_id": u["username"], "title": d.title.strip(),
         "category": cat, "priority": pri, "status": "Assigned" if staff else "Open", "assigned_team": team,
         "assigned_staff_id": staff, "created_at": now(), "sla_hours": core.SLA_HOURS[cat], "escalation_count": 0,
         "ai": ai, "timeline": []}
    log(t, u["username"], "Ticket created")
    log(t, "system", "AI prediction", f"{ai['category']} ({ai['category_conf']}), {ai['priority']} ({ai['priority_conf']}), source={ai['source']}"
        + (" - low confidence / no model: manual verification required" if ai["needs_review"] else ""))
    log(t, "system", "Assignment", f"Routed to {team}" + (f", assigned to {staff}" if staff else ", unassigned"))
    db.tickets.insert_one(t)
    return view(t, u)

@app.get("/api/tickets")
def list_tickets(u=Depends(user_dep), q: Optional[str] = None, category: Optional[str] = None, priority: Optional[str] = None,
                 status: Optional[str] = None, department: Optional[str] = None, staff: Optional[str] = None,
                 team: Optional[str] = None, sla: Optional[str] = None, unassigned: bool = False, ageing: Optional[str] = None):
    f = {}
    if u["role"] == "student": f["student_id"] = u["username"]
    elif u["role"] == "staff": f["assigned_team"] = u["team"]
    for k, v in (("category", category), ("priority", priority), ("status", status), ("department", department),
                 ("assigned_staff_id", staff), ("assigned_team", team)):
        if v: f[k] = v   # query params are always plain strings: no operator injection
    if unassigned: f["assigned_staff_id"] = None
    if q: f["$or"] = [{"ticket_id": q}, {"student_id": q}]
    out = []
    for t in get_db().tickets.find(f).sort("created_at", -1).limit(500):
        s = core.sla_info(t)
        if sla and s["state"] != sla: continue
        if ageing and (s["ageing"] != ageing or t["status"] in FINAL): continue
        t["sla"] = s; t.pop("timeline"); out.append(ser(t))
    return out

@app.get("/api/tickets/{tid}")
def ticket_detail(tid: str, u=Depends(user_dep)): return view(get_ticket(tid, u), u)

class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000); internal: bool = False

@app.post("/api/tickets/{tid}/reply")
def reply(tid: str, d: ReplyIn, u=Depends(user_dep)):
    t = get_ticket(tid, u)
    if u["role"] == "student":
        if d.internal: raise HTTPException(403, "Students cannot add internal notes")
        if t["status"] == "Closed": raise HTTPException(409, "Ticket is closed; please raise a new ticket")
        log(t, u["username"], "Student reply", d.text)
        if t["status"] in ("Resolved", "Pending Student"):
            log(t, "system", "Status changed", f"{t['status']} -> In Progress (student replied)"); t["status"] = "In Progress"; t["resolved_at"] = None
    else:
        log(t, u["username"], "Internal note" if d.internal else "Staff reply", d.text, internal=d.internal)
        if not d.internal and not t.get("first_response_at"): t["first_response_at"] = now()
    save(t); return view(t, u)

class StatusIn(BaseModel): status: str

@app.post("/api/tickets/{tid}/status")
def set_status(tid: str, d: StatusIn, u=Depends(user_dep)):
    if u["role"] == "student": raise HTTPException(403, "Students cannot change status")
    t = get_ticket(tid, u)
    if d.status not in TRANSITIONS: raise HTTPException(422, "Unknown status")
    if d.status not in TRANSITIONS[t["status"]]:
        raise HTTPException(409, f"Invalid transition {t['status']} -> {d.status}")
    if d.status == "Escalated": return do_escalate(t, u["username"], "manual", u)
    log(t, u["username"], "Resolution" if d.status == "Resolved" else "Closure" if d.status == "Closed" else "Status changed", f"{t['status']} -> {d.status}")
    t["status"] = d.status
    if d.status == "Resolved": t["resolved_at"] = now()
    save(t); return view(t, u)

class OverrideIn(BaseModel):
    category: Optional[str] = None; priority: Optional[str] = None

@app.post("/api/tickets/{tid}/override")
def override(tid: str, d: OverrideIn, u=Depends(user_dep)):
    if u["role"] == "student": raise HTTPException(403, "Forbidden")
    t = get_ticket(tid, u)
    if d.category:
        if d.category not in CATEGORY_TEAM: raise HTTPException(422, "Unknown category")
        log(t, u["username"], "Category changed", f"{t['category']} -> {d.category}")
        t["category"] = d.category; t["sla_hours"] = core.SLA_HOURS[d.category]
        t["assigned_team"] = CATEGORY_TEAM[d.category]; t["assigned_staff_id"] = None
        log(t, "system", "Assignment", f"Re-routed to {t['assigned_team']} (unassigned)")
        if t["status"] == "Assigned": t["status"] = "Open"
    if d.priority:
        if d.priority not in PRIORITIES: raise HTTPException(422, "Unknown priority")
        log(t, u["username"], "Priority changed", f"{t['priority']} -> {d.priority}"); t["priority"] = d.priority
    t["ai"]["needs_review"] = False; t["ai"]["reviewed_by"] = u["username"]
    save(t); return view(t, u)

class AssignIn(BaseModel): staff_id: str

@app.post("/api/tickets/{tid}/assign")
def assign(tid: str, d: AssignIn, u=Depends(user_dep)):
    if not is_mgr(u): raise HTTPException(403, "Managers only")
    t = get_ticket(tid, u)
    s = get_db().users.find_one({"username": d.staff_id, "role": "staff"})
    if not s or s["team"] != t["assigned_team"]:
        raise HTTPException(422, "Staff member does not exist or is not in the ticket's team")
    log(t, u["username"], "Reassignment" if t["assigned_staff_id"] else "Assignment", f"{t['assigned_staff_id']} -> {d.staff_id}")
    t["assigned_staff_id"] = d.staff_id
    if t["status"] == "Open": t["status"] = "Assigned"
    t["reassignment_count"] = t.get("reassignment_count", 0) + 1
    save(t); return view(t, u)

def do_escalate(t, actor, kind, u):
    if t["status"] in FINAL or t["status"] == "Escalated": raise HTTPException(409, "Ticket cannot be escalated in its current status")
    t["escalation_count"] += 1
    up = PRIORITIES[min(PRIORITIES.index(t["priority"]) + 1, 3)]
    log(t, actor, "Escalation", f"{kind} escalation #{t['escalation_count']}; {t['status']} -> Escalated; priority {t['priority']} -> {up}")
    t["status"], t["priority"] = "Escalated", up
    save(t); return view(t, u)

@app.post("/api/tickets/{tid}/escalate")
def escalate(tid: str, u=Depends(user_dep)):
    if u["role"] == "student": raise HTTPException(403, "Forbidden")
    return do_escalate(get_ticket(tid, u), u["username"], "manual", u)

@app.post("/api/admin/auto-escalate")
def auto_escalate(u=Depends(user_dep)):
    if not is_mgr(u): raise HTTPException(403, "Managers only")
    n = 0
    for t in list(get_db().tickets.find({"status": {"$nin": list(FINAL | {"Escalated"})}})):
        if core.sla_info(t)["state"] == "Breached": do_escalate(t, "system", "automatic (SLA breach)", u); n += 1
    return {"escalated": n}

class FeedbackIn(BaseModel): score: int = Field(ge=1, le=5)

@app.post("/api/tickets/{tid}/feedback")
def feedback(tid: str, d: FeedbackIn, u=Depends(user_dep)):
    t = get_ticket(tid, u)
    if u["role"] != "student" or t["status"] not in FINAL: raise HTTPException(409, "Feedback only by the student after resolution")
    t["satisfaction_score"] = d.score; log(t, u["username"], "Feedback", str(d.score)); save(t); return view(t, u)

@app.get("/api/staff")
def staff_list(u=Depends(user_dep)):
    if u["role"] == "student": raise HTTPException(403, "Forbidden")
    return list(get_db().users.find({"role": "staff"}, {"_id": 0, "username": 1, "name": 1, "team": 1}))

@app.get("/api/dashboard")
def dashboard(u=Depends(user_dep)):
    ts = list_tickets(u)
    cnt = lambda key: {k: sum(1 for t in ts if t[key] == k) for k in sorted({t[key] for t in ts})}
    act = [t for t in ts if t["status"] not in FINAL]
    sla = {s: sum(1 for t in ts if t["sla"]["state"] == s) for s in ("Within SLA", "At Risk", "Breached")}
    d = {"total": len(ts), "by_status": cnt("status"), "by_priority": cnt("priority"), "by_category": cnt("category"), "sla": sla,
         "ageing": {b: sum(1 for t in act if t["sla"]["ageing"] == b) for b in ("0-24h", "24-48h", "48-72h", "72h+")},
         "attention": {"sla_breached": sla["Breached"], "at_risk": sla["At Risk"],
                       "high_unassigned": sum(1 for t in act if t["priority"] in ("High", "Urgent") and not t["assigned_staff_id"])}}
    if u["role"] != "student":
        d["workload"] = {}
        for t in act:
            k = t["assigned_staff_id"] or "Unassigned"; d["workload"][k] = d["workload"].get(k, 0) + 1
        d["urgent"] = sum(1 for t in act if t["priority"] == "Urgent")
    return d
