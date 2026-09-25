import os
os.environ["MONGO_URI"] = "mock"
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import core
from scripts.seed_database import seed, PW

@pytest.fixture(scope="module")
def c():
    seed(); return TestClient(app)

def login(c, role, user):
    r = c.post("/api/login", json={"role": role, "username": user, "password": PW}); assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

T = dict(title="Fee receipt problem", description="My fee payment is not shown on the portal.", department="CSE", year=2, semester=3, course="B.Tech CSE")

def test_auth(c):
    assert c.post("/api/login", json={"role": "student", "username": "STU23BCSE0001", "password": "x"}).status_code == 401
    assert c.post("/api/login", json={"role": "staff", "username": "STU23BCSE0001", "password": PW}).status_code == 401
    assert c.get("/api/tickets").status_code == 401

def test_create_access_and_internal_notes(c):
    s, o, st = login(c, "student", "STU23BCSE0001"), login(c, "student", "STU23BCSE0002"), login(c, "staff", "gen_staff1")
    r = c.post("/api/tickets", json=T, headers=s); assert r.status_code == 201
    t = r.json(); assert t["ticket_id"].startswith("TKT-") and t["assigned_staff_id"]
    assert c.post("/api/tickets", json=T, headers=s).status_code == 409           # duplicate
    assert c.get(f"/api/tickets/{t['ticket_id']}", headers=o).status_code == 404   # other student
    assert c.post("/api/tickets", json={**T, "title": ""}, headers=s).status_code == 422
    c.post(f"/api/tickets/{t['ticket_id']}/reply", json={"text": "secret", "internal": True}, headers=st)
    assert "secret" not in c.get(f"/api/tickets/{t['ticket_id']}", headers=s).text

def test_discipline_rule_routing(c):
    s = login(c, "student", "STU23BCSE0002")
    t = c.post("/api/tickets", json={**T, "title": "Ragging by seniors", "description": "Seniors are harassing and threatening me in hostel."}, headers=s).json()
    assert (t["category"], t["priority"], t["assigned_team"]) == ("Discipline", "Urgent", "Discipline")
    assert c.get(f"/api/tickets/{t['ticket_id']}", headers=login(c, "staff", "acc_staff1")).status_code == 404

def test_workflow_and_escalation(c):
    s, st, m = login(c, "student", "STU23BCSE0001"), login(c, "staff", "gen_staff1"), login(c, "manager", "gen_mgr")
    t = c.post("/api/tickets", json={**T, "title": "Refund pending"}, headers=s).json(); u = f"/api/tickets/{t['ticket_id']}"
    assert t["assigned_team"] == "General Support"   # no ML model in test env -> safe default route
    stf = t["assigned_staff_id"]; other = "gen_staff2" if stf == "gen_staff1" else "gen_staff1"
    hs = login(c, "staff", stf)
    assert c.post(u + "/status", json={"status": "Closed"}, headers=hs).status_code == 409
    assert c.post(u + "/status", json={"status": "In Progress"}, headers=hs).status_code == 200
    assert c.post(u + "/status", json={"status": "Escalated"}, headers=hs).json()["escalation_count"] == 1
    assert c.post(u + "/assign", json={"staff_id": "disc_staff1"}, headers=m).status_code == 422   # wrong team
    assert c.post(u + "/assign", json={"staff_id": other}, headers=m).status_code == 200
    assert c.post(u + "/assign", json={"staff_id": other}, headers=hs).status_code == 403
    assert c.post(u + "/status", json={"status": "Resolved"}, headers=hs).status_code == 200

def test_sla_and_low_confidence():
    t = {"created_at": core.now() - timedelta(hours=30), "sla_hours": 24, "status": "Open"}
    assert core.sla_info(t)["state"] == "Breached" and core.sla_info(t)["ageing"] == "24-48h"
    t = {"created_at": core.now() - timedelta(hours=20), "sla_hours": 24, "status": "Open"}
    assert core.sla_info(t)["state"] == "At Risk"
    cat, pri, ai = core.classify("hello", "some vague text here please", {})
    assert ai["needs_review"] and cat == "Other"
