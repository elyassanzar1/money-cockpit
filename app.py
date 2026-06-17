"""FastAPI server. Serves the installable dashboard and a small JSON API.

Run locally:   uvicorn app:app --reload --port 8000
Then open:     http://localhost:8000  (and "Add to Home Screen" on your phone)
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

import config
import db
import budget
import plaid_client

app = FastAPI(title="My Money Cockpit")
STATIC = os.path.join(os.path.dirname(__file__), "static")

db.init_db()
# Seed default envelopes on first run so the dashboard isn't empty.
if not db.get_envelopes():
    for name, alloc in budget.DEFAULT_ENVELOPES.items():
        db.set_envelope(name, alloc)
if not db.get_goals():
    db.set_goal("Emergency Fund", 12450, "emergency", "#34E3FF")
    db.set_goal("Roth IRA 2026", 7500, "roth", "#3DF5A0", saved=0)
    db.set_goal("Investments", 100000, "investments", "#A98BFF")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


# --- dashboard data ---
@app.get("/api/dashboard")
def dashboard():
    return {
        "envelopes": budget.envelope_state(),
        "wealth": budget.safe_to_invest(),
        "net_worth": budget.net_worth(),
        "accounts": db.get_accounts(),
        "goals": budget.goals_state(),
        "plan": budget.wealth_plan(),
        "allocation": budget.income_allocation(),
        "road": budget.road_to_goal(100000),
        "recurring": budget.recurring(),
        "last_sync": db.get_meta("last_sync"),
        "plaid_env": config.PLAID_ENV,
        "configured": bool(config.PLAID_CLIENT_ID and config.PLAID_SECRET),
    }


class GoalSavedIn(BaseModel):
    name: str
    saved: float


@app.post("/api/goal-progress")
def goal_progress(g: GoalSavedIn):
    db.update_goal_saved(g.name, g.saved)
    return {"ok": True, "goals": budget.goals_state()}


@app.get("/api/transactions")
def transactions(limit: int = 100):
    return db.get_transactions(limit=limit)


@app.get("/api/history")
def history():
    return db.get_snapshots()


# --- envelopes ---
class EnvelopeIn(BaseModel):
    name: str
    allocation: float


@app.post("/api/envelopes")
def set_envelope(e: EnvelopeIn):
    db.set_envelope(e.name, e.allocation)
    return {"ok": True, "envelopes": budget.envelope_state()}


class RecategorizeIn(BaseModel):
    txn_id: str
    envelope: str


@app.post("/api/recategorize")
def recategorize(r: RecategorizeIn):
    db.set_envelope_category(r.txn_id, r.envelope)
    return {"ok": True}


# --- plaid link + sync ---
@app.get("/api/link-token")
def link_token():
    _require_plaid()
    try:
        return {"link_token": plaid_client.create_link_token()}
    except Exception as e:
        raise HTTPException(500, f"Plaid link error: {e}")


class ExchangeIn(BaseModel):
    public_token: str


@app.post("/api/exchange")
def exchange(x: ExchangeIn):
    _require_plaid()
    try:
        item_id = plaid_client.exchange_public_token(x.public_token)
        plaid_client.sync_all()
        return {"ok": True, "item_id": item_id}
    except Exception as e:
        raise HTTPException(500, f"Exchange error: {e}")


@app.post("/api/sync")
def sync():
    _require_plaid()
    try:
        plaid_client.sync_all()
        return {"ok": True, "last_sync": db.get_meta("last_sync")}
    except Exception as e:
        raise HTTPException(500, f"Sync error: {e}")


def _require_plaid():
    if not (config.PLAID_CLIENT_ID and config.PLAID_SECRET):
        raise HTTPException(400, "Add PLAID_CLIENT_ID and PLAID_SECRET to your .env file.")


# static assets (manifest, service worker, js, css)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/manifest.json")
def manifest():
    return FileResponse(os.path.join(STATIC, "manifest.json"))


@app.get("/sw.js")
def service_worker():
    return FileResponse(os.path.join(STATIC, "sw.js"), media_type="application/javascript")
