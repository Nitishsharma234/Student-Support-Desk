"""Seed demo users (fake data). Usage: python -m scripts.seed_database"""
from app.core import get_db, hash_pw, TEAMS
PW = "Demo@123"
def seed(db=None):
    db = db or get_db(); db.users.delete_many({})
    short = {"Accounts": "acc", "Academic Office": "acad", "Administration": "adm", "Discipline": "disc", "General Support": "gen"}
    users = [dict(username="STU23BCSE0001", name="Demo Student", role="student"),
             dict(username="STU23BCSE0002", name="Other Student", role="student"),
             dict(username="admin", name="System Admin", role="admin")]
    for t in TEAMS:
        users += [dict(username=f"{short[t]}_staff1", name=f"{t} Staff 1", role="staff", team=t),
                  dict(username=f"{short[t]}_staff2", name=f"{t} Staff 2", role="staff", team=t),
                  dict(username=f"{short[t]}_mgr", name=f"{t} Manager", role="manager", team=t)]
    for u in users: u["password_hash"] = hash_pw(PW); u.setdefault("team", None)
    db.users.insert_many(users); return len(users)
if __name__ == "__main__": print("seeded", seed(), "users; password:", PW)
