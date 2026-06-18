"""Load realistic data modeled on Elyas's real numbers so the dashboard is
populated before linking Plaid.  $2,300 bi-weekly income, ~$2,650 fixed.

    python seed_demo.py        # populate
    python seed_demo.py clear  # wipe and start fresh
"""
import sys
from datetime import date, timedelta
import db, budget

def clear():
    with db.get_db() as c:
        for t in ("transactions", "accounts", "items", "meta", "snapshots", "goals"):
            c.execute(f"DELETE FROM {t}")
    print("cleared.")

def seed():
    db.init_db()
    for n, a in budget.DEFAULT_ENVELOPES.items():
        db.set_envelope(n, a)

    # Goals (gamified)
    db.set_goal("Emergency Fund", 12450, "emergency", "#34E3FF")
    db.set_goal("Roth IRA 2026", 7500, "roth", "#3DF5A0", saved=1250)
    db.set_goal("Invested by 2030", 100000, "investments", "#A98BFF")

    # Accounts: main checking, cash emergency reserve (no interest), brokerages
    db.upsert_account(dict(account_id="chk", item_id="demo", name="Chase Total Checking",
        official_name="", type="depository", subtype="checking", current=2480.0, available=2380.0))
    db.upsert_account(dict(account_id="resv", item_id="demo", name="Chase Savings — Emergency",
        official_name="", type="depository", subtype="savings", current=5400.0, available=5400.0))
    db.upsert_account(dict(account_id="rh", item_id="demo", name="Robinhood",
        official_name="", type="investment", subtype="brokerage", current=6820.0, available=None))
    db.upsert_account(dict(account_id="fid", item_id="demo", name="Fidelity 401(k)",
        official_name="", type="investment", subtype="401k", current=24300.0, available=None))

    today = date.today()
    ms = today.replace(day=1)
    def d(off): return (ms + timedelta(days=off)).isoformat()
    # Plaid sign: negative = money IN, positive = money OUT
    rows = [
        ("pay1", -2300, "INCOME", 1, "Direct Deposit - Thermo Fisher", "chk"),
        ("pay2", -2300, "INCOME", 15, "Direct Deposit - Thermo Fisher", "chk"),
        # the bills wire (excluded from spend tracking, handled in separate account)
        ("billwire", 2650, "TRANSFER_OUT", 2, "Wire to Bills Account", "chk"),
        ("loan", 284, "LOAN_PAYMENTS", 5, "Dept of Education Student Ln", "chk"),
        # discretionary spending — what you actually manage
        ("g1", 118.4, "FOOD_AND_DRINK", 2, "ShopRite", "chk"),
        ("g2", 86.2, "FOOD_AND_DRINK", 9, "Costco", "chk"),
        ("e1", 32.4, "FOOD_AND_DRINK", 3, "Halal Guys", "chk"),
        ("e2", 18.6, "FOOD_AND_DRINK", 5, "Chipotle", "chk"),
        ("e3", 41.0, "FOOD_AND_DRINK", 7, "Wingstop", "chk"),
        ("e4", 26.75, "FOOD_AND_DRINK", 10, "DoorDash", "chk"),
        ("e5", 14.2, "FOOD_AND_DRINK", 12, "Dunkin", "chk"),
        ("e6", 58.9, "FOOD_AND_DRINK", 13, "Texas Roadhouse", "chk"),
        ("gas1", 62.0, "TRANSPORTATION", 4, "Wawa Fuel", "chk"),
        ("gas2", 58.5, "TRANSPORTATION", 11, "Shell", "chk"),
        ("amzn", 74.99, "GENERAL_MERCHANDISE", 6, "Amazon", "chk"),
        ("shoes", 89.0, "GENERAL_MERCHANDISE", 9, "Nike", "chk"),
        ("fun1", 32.0, "ENTERTAINMENT", 10, "AMC Theatres", "chk"),
        ("per1", 45.0, "PERSONAL_CARE", 9, "Barber", "chk"),
        # pay-yourself-first wealth moves
        ("toRoth", 300, "TRANSFER_OUT", 2, "Transfer to Roth IRA", "chk"),
        ("toRH", 250, "TRANSFER_OUT", 15, "Transfer to Robinhood", "chk"),
        ("zakat", 115, "GOVERNMENT_AND_NON_PROFIT", 3, "Zakat Donation", "chk"),
    ]
    for tid, amt, pfc, off, name, acct in rows:
        env = "Zakat" if "zakat" in name.lower() else budget.map_envelope(pfc)
        db.upsert_transaction(dict(txn_id=tid, account_id=acct, date=d(off), name=name,
            merchant=name, amount=float(amt), pfc_primary=pfc,
            envelope=env, pending=0))

    # 45 days of net worth history
    import math, random
    random.seed(11)
    target = budget.net_worth()["net_worth"]
    days = 45
    base = target * 0.88
    for i in range(days + 1):
        frac = i / days
        trend = base + (target - base) * frac
        noise = math.sin(i / 3.5) * (target * 0.01) + random.uniform(-target * 0.005, target * 0.005)
        val = round(trend + noise, 2) if i < days else target
        dt = (date.today() - timedelta(days=days - i)).isoformat()
        inv = round(val * 0.66, 2)
        db.record_snapshot(dt, val, round(val - inv, 2), inv, 0.0)

    db.set_meta("last_sync", "demo data")
    print("seeded demo data. run: uvicorn app:app --port 8000")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear()
    else:
        seed()
