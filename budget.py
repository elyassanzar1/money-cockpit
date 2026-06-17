"""The brain. Turns raw transactions into 'what's left to spend' and
'what's safe to invest'.

Sign convention follows Plaid: a positive amount means money LEFT your
account (a purchase); a negative amount means money came IN (a deposit).
"""
from datetime import date
from collections import defaultdict

import db
from config import SAVINGS_RATE, EMERGENCY_MONTHS, BILLS_WIRE

# Map Plaid's personal_finance_category.primary -> your envelope.
PFC_TO_ENVELOPE = {
    "FOOD_AND_DRINK": "Food & Groceries",
    "GENERAL_MERCHANDISE": "Shopping",
    "TRANSPORTATION": "Transport",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Bills (handled)",
    "LOAN_PAYMENTS": "Bills (handled)",
    "ENTERTAINMENT": "Fun",
    "PERSONAL_CARE": "Personal",
    "GENERAL_SERVICES": "Services",
    "MEDICAL": "Medical",
    "HOME_IMPROVEMENT": "Home",
    "GOVERNMENT_AND_NON_PROFIT": "Other",
}

# Categories that represent money coming in, not spending.
INFLOW_PFCS = {"INCOME", "TRANSFER_IN"}
# Movements never counted as discretionary spending (incl. the bills wire).
IGNORE_PFCS = {"TRANSFER_OUT", "BANK_FEES"}
# Bills are wired to a separate account and handled there, not tracked daily.
HANDLED_ENVELOPES = {"Bills (handled)", "Zakat"}

# Only what you actually manage day-to-day. Bills live in the wired account.
DEFAULT_ENVELOPES = {
    "Food & Groceries": 700, "Transport": 200, "Shopping": 200,
    "Fun": 120, "Personal": 80,
}


def map_envelope(pfc_primary: str) -> str:
    if pfc_primary in INFLOW_PFCS:
        return "Income"
    if pfc_primary in IGNORE_PFCS:
        return "Transfer"
    return PFC_TO_ENVELOPE.get(pfc_primary, "Other")


def _month_start(d: date = None) -> str:
    d = d or date.today()
    return d.replace(day=1).isoformat()


def envelope_state(today: date = None):
    """Return per-envelope spent / allocated / remaining for the current month."""
    today = today or date.today()
    month_start = _month_start(today)
    allocations = db.get_envelopes() or DEFAULT_ENVELOPES
    txns = db.get_transactions(since=month_start, limit=5000)

    spent = defaultdict(float)
    for t in txns:
        env = t["envelope"]
        if env in ("Income", "Transfer"):
            continue
        if t["amount"] > 0:  # money out = spending
            spent[env] += t["amount"]

    rows = []
    for name, alloc in sorted(allocations.items()):
        s = round(spent.get(name, 0.0), 2)
        rows.append({
            "name": name,
            "allocated": alloc,
            "spent": s,
            "remaining": round(alloc - s, 2),
            "pct_used": round(100 * s / alloc, 1) if alloc else 0,
        })
    # Surface any spending in categories with no envelope yet.
    for name, s in spent.items():
        if name not in allocations and name not in ("Income", "Transfer") and name not in HANDLED_ENVELOPES:
            rows.append({"name": name, "allocated": 0, "spent": round(s, 2),
                         "remaining": round(-s, 2), "pct_used": 100})
    return rows


def income_this_month(today: date = None) -> float:
    today = today or date.today()
    txns = db.get_transactions(since=_month_start(today), limit=5000)
    total = 0.0
    for t in txns:
        if t["envelope"] == "Income" or t["amount"] < 0:
            total += abs(min(t["amount"], 0)) if t["amount"] < 0 else 0
    # Income is recorded as negative amounts (money in); sum their magnitude.
    inflow = sum(-t["amount"] for t in txns if t["amount"] < 0 and t["envelope"] != "Transfer")
    return round(inflow, 2)


def checking_balance() -> float:
    """Spendable cash: depository accounts that are NOT savings."""
    total = 0.0
    for a in db.get_accounts():
        if a["type"] == "depository" and (a["subtype"] or "") != "savings":
            total += a["current"] or 0
    return round(total, 2)


def savings_balance() -> float:
    """Cash held in savings / high-yield savings (your emergency fund)."""
    total = 0.0
    for a in db.get_accounts():
        if a["type"] == "depository" and (a["subtype"] or "") == "savings":
            total += a["current"] or 0
    return round(total, 2)


def investment_balance() -> float:
    total = 0.0
    for a in db.get_accounts():
        if a["type"] == "investment":
            total += a["current"] or 0
    return round(total, 2)


def avg_monthly_spend(months_back: int = 3) -> float:
    """Rough average monthly outflow, for sizing the emergency buffer."""
    txns = db.get_transactions(limit=10000)
    if not txns:
        return sum(DEFAULT_ENVELOPES.values())
    monthly = defaultdict(float)
    for t in txns:
        if t["amount"] > 0 and t["envelope"] not in ("Transfer",):
            monthly[t["date"][:7]] += t["amount"]
    if not monthly:
        return sum(DEFAULT_ENVELOPES.values())
    recent = sorted(monthly.values(), reverse=True)[:months_back]
    return round(sum(recent) / len(recent), 2)


def safe_to_invest(today: date = None):
    """How much surplus cash you can move to investments right now without
    touching your emergency buffer or this month's remaining budget.

        buffer        = EMERGENCY_MONTHS x average monthly spend
        committed     = sum of remaining (unspent) envelope money this month
        safe          = checking - buffer - committed
    """
    cash = checking_balance()
    buffer_target = round(EMERGENCY_MONTHS * avg_monthly_spend(), 2)
    committed = round(sum(max(0, e["remaining"]) for e in envelope_state(today)), 2)
    safe = round(cash - buffer_target - committed, 2)

    income = income_this_month(today)
    pay_yourself = round(income * SAVINGS_RATE, 2)

    return {
        "checking": cash,
        "buffer_target": buffer_target,
        "committed_to_budget": committed,
        "safe_to_invest": max(0.0, safe),
        "raw_surplus": safe,
        "income_this_month": income,
        "pay_yourself_first": pay_yourself,
        "savings_rate_pct": round(SAVINGS_RATE * 100),
        "investment_balance": investment_balance(),
    }


def net_worth():
    cash = checking_balance() + savings_balance()
    invest = investment_balance()
    debt = 0.0
    for a in db.get_accounts():
        if a["type"] == "credit":
            debt += a["current"] or 0
    return {
        "cash": cash,
        "investments": invest,
        "debt": round(debt, 2),
        "net_worth": round(cash + invest - debt, 2),
    }


def goals_state():
    """Live progress on savings goals. Emergency-fund and investment goals
    auto-track their linked balances; manual goals track logged contributions."""
    goals = db.get_goals()
    sav, inv = savings_balance(), investment_balance()
    out = []
    for g in goals:
        saved = g["saved"]
        if g["kind"] == "emergency":
            saved = sav
        elif g["kind"] == "investments":
            saved = inv
        pct = round(100 * saved / g["target"], 1) if g["target"] else 0
        out.append({"name": g["name"], "target": g["target"], "saved": round(saved, 2),
                    "pct": min(100, pct), "kind": g["kind"], "accent": g["accent"]})
    return out


def wealth_plan():
    """The money order-of-operations, personalized to your numbers. Each stage
    unlocks the next. Targets use your ~$4,150/mo expense base."""
    monthly_exp = round(total_monthly_expenses(), -1) or (BILLS_WIRE + sum(DEFAULT_ENVELOPES.values()))
    emfund_3mo = round(monthly_exp * 3, -2)
    sav = savings_balance()
    chk = checking_balance()
    # detectable signals
    has_401k = any(a["type"] == "investment" and (a["subtype"] or "") in ("401k", "401a")
                   for a in db.get_accounts())
    roth = next((g for g in db.get_goals() if g["kind"] == "roth"), None)
    roth_done = bool(roth) and roth["saved"] >= roth["target"]
    stages = [
        {"n": 1, "title": "Starter buffer", "target": f"${int(monthly_exp):,} cash in checking",
         "why": "One month of expenses set aside so a surprise bill never derails you. Plain cash, no interest.",
         "done": (chk + sav) >= monthly_exp},
        {"n": 2, "title": "Capture 401(k) match", "target": "Full Fidelity match",
         "why": "Free money from your employer. Inside it, pick the most Sharia-compliant fund your plan offers.",
         "done": has_401k},
        {"n": 3, "title": "Cash emergency fund", "target": f"${int(emfund_3mo):,} held as cash",
         "why": "3 months of expenses, liquid and riba-free. Safety is the return here, not interest.",
         "done": sav >= emfund_3mo},
        {"n": 4, "title": "Max Roth IRA — halal funds", "target": "$7,500 for 2026",
         "why": "Open at Fidelity/Robinhood, hold halal ETFs like SPUS or HLAL. Tax-free growth, fully Sharia-screened.",
         "done": roth_done},
        {"n": 5, "title": "Invest the surplus", "target": "Halal ETFs + gold in Robinhood",
         "why": "Everything extra into SPUS/HLAL, sukuk (SPSK) instead of bonds, and gold (physically-backed).",
         "done": False},
    ]
    active = next((s["n"] for s in stages if not s["done"]), 5)
    return {"stages": stages, "active": active, "monthly_surplus": invest_target()}


def detected_monthly_income() -> float:
    """Average monthly income detected from your actual deposits (Plaid INCOME
    inflows). Returns 0 until accounts are linked, so nothing is invented."""
    txns = db.get_transactions(limit=10000)
    by_month = defaultdict(float)
    for t in txns:
        is_income = t["envelope"] == "Income" or (t["amount"] < 0 and t["envelope"] != "Transfer")
        if is_income and t["amount"] < 0:
            by_month[t["date"][:7]] += -t["amount"]
    months = [v for v in by_month.values() if v > 0]
    return round(sum(months) / len(months), 2) if months else 0.0


def monthly_avg_income() -> float:
    """Income used across the app. Detected from accounts; no fake fallback."""
    return detected_monthly_income()


def monthly_surplus() -> float:
    """Real free cash: detected income minus actual average monthly spending."""
    return round(max(0.0, monthly_avg_income() - avg_monthly_spend()), 2)


# --- the budget, baked in: pay-yourself-first on what's left after bills ---
# Of your spendable money (income minus the bills wire), this is the plan.
PAYF_SPLIT = {"Invest": 40, "Zakat": 5, "Living": 55}  # sums to 100
BUCKET_ACCENTS = {"Living": "#34E3FF", "Invest": "#3DF5A0", "Zakat": "#A98BFF", "Bills": "#6F88A0"}
LIVING_ENVELOPES = ["Food & Groceries", "Transport", "Shopping", "Fun", "Personal", "Home"]


def income_allocation(today=None):
    today = today or date.today()
    income = monthly_avg_income()
    bills = BILLS_WIRE
    spendable = max(0.0, round(income - bills, 2))
    spent = {e["name"]: e["spent"] for e in envelope_state(today)}
    txns = db.get_transactions(since=_month_start(today), limit=5000)

    living_actual = round(sum(spent.get(n, 0) for n in LIVING_ENVELOPES), 2)
    invest_actual = round(sum(
        t["amount"] for t in txns if t["envelope"] == "Transfer"
        and any(k in (t["name"] or "") for k in ("Roth", "Robinhood", "Invest", "Savings", "401"))
        and "Bill" not in (t["name"] or "")), 2)
    zakat_actual = round(sum(
        abs(t["amount"]) for t in txns
        if any(k in (t["name"] or "").lower() for k in ("zakat", "charity", "sadaqah", "donation"))), 2)
    actuals = {"Living": living_actual, "Invest": invest_actual, "Zakat": zakat_actual}

    buckets = []
    for name, pct in PAYF_SPLIT.items():
        target = round(spendable * pct / 100, 2)
        a = actuals[name]
        buckets.append({
            "name": name, "pct": pct, "target": target, "actual": a,
            "accent": BUCKET_ACCENTS[name],
            "status": "over" if a > target * 1.05 else "under" if a < target * 0.6 else "ok",
        })
    return {"income": income, "bills": bills, "spendable": spendable, "buckets": buckets}


def invest_target() -> float:
    """The pay-yourself-first amount the plan says to invest each month."""
    spendable = max(0.0, monthly_avg_income() - BILLS_WIRE)
    return round(spendable * PAYF_SPLIT["Invest"] / 100, 2)


def total_monthly_expenses() -> float:
    """Bills wire + your actual discretionary (living) spending."""
    living = sum(e["spent"] for e in envelope_state())
    return round(BILLS_WIRE + living, 2)


def road_to_goal(target=100000, annual_return=0.08):
    """Project net worth to a target. Investments compound; your free monthly
    surplus is added each month. Returns an ETA and a projection series.

    annual_return is a conservative estimate for broad Sharia-compliant equity;
    real returns vary and are never guaranteed."""
    nw = net_worth()["net_worth"]
    invest = investment_balance()
    cash_const = nw - invest
    monthly = invest_target()
    r = annual_return / 12

    bal, inv, months = nw, invest, 0
    series = [round(bal)]
    while bal < target and months < 600:
        inv = inv * (1 + r) + monthly
        bal = cash_const + inv
        months += 1
        if months % 3 == 0:
            series.append(round(bal))
    yrs = months / 12
    eta = date.today()
    em = eta.month - 1 + months
    eta = eta.replace(year=eta.year + em // 12, month=em % 12 + 1)
    return {
        "current": nw, "target": target, "pct": min(100, round(100 * nw / target, 1)),
        "monthly_contribution": monthly, "annual_return_pct": round(annual_return * 100),
        "months": months, "years": round(yrs, 1),
        "eta": eta.strftime("%b %Y"), "series": series,
    }


def recurring():
    """Detect fixed monthly commitments: any merchant seen more than once, plus
    anything in a bill/mortgage/loan category. This is what's locked in each
    month before discretionary spending."""
    txns = db.get_transactions(limit=10000)
    groups = defaultdict(list)
    for t in txns:
        if t["amount"] > 0 and t["envelope"] != "Transfer":
            key = (t["merchant"] or t["name"] or "").strip().lower()
            if key:
                groups[key].append(t)
    fixed_envelopes = {"Mortgage", "Bills"}
    out = []
    for key, ts in groups.items():
        recurs = len(ts) >= 2 or any(t["envelope"] in fixed_envelopes for t in ts)
        if not recurs:
            continue
        amts = [t["amount"] for t in ts]
        out.append({
            "name": ts[0]["merchant"] or ts[0]["name"],
            "amount": round(sum(amts) / len(amts), 2),
            "envelope": ts[0]["envelope"],
            "count": len(ts),
        })
    out.sort(key=lambda x: x["amount"], reverse=True)
    return {"items": out, "total": round(sum(o["amount"] for o in out), 2)}
