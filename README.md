# Money Cockpit

A personal, single-user finance dashboard. It links your Chase debit account,
Robinhood, and Fidelity through Plaid, auto-categorizes spending into monthly
envelopes ("you have $370 left for Food"), and tells you how much surplus is
**safe to invest** after keeping an emergency buffer.

Your data lives in one local SQLite file (`finance.db`). Nothing is sold,
shared, or sent anywhere except your own calls to Plaid to pull your data in.

---

## 1. See it immediately (fake data, no setup)

```bash
pip install -r requirements.txt
python seed_demo.py
uvicorn app:app --port 8000
```

Open http://localhost:8000. You'll see demo accounts and transactions.
Wipe them anytime with `python seed_demo.py clear`.

---

## 2. Connect your real accounts

1. Make a free account at https://dashboard.plaid.com and grab your
   **client_id** and **secret**.
2. Copy `.env.example` to `.env` and paste them in:
   ```
   PLAID_CLIENT_ID=...
   PLAID_SECRET=...
   PLAID_ENV=sandbox        # keep this while testing
   ```
3. **Sandbox test first.** With `PLAID_ENV=sandbox`, run the app, tap
   *Connect*, pick any bank, and use Plaid's test login `user_good` /
   `pass_good`. Confirm transactions and balances flow in.
4. **Go live.** In the Plaid dashboard request **Production** access (free tier
   covers a personal app — up to 200 calls per product). Set `PLAID_ENV=production`
   and use your real Chase / Robinhood / Fidelity logins. Chase connects through
   its OAuth screen automatically inside Plaid Link.

```bash
python seed_demo.py clear     # remove demo rows before going live
uvicorn app:app --port 8000
```

---

## 3. Put it on your phone

The app is an installable PWA.

- Same Wi-Fi: run `uvicorn app:app --host 0.0.0.0 --port 8000`, then open
  `http://<your-computer-ip>:8000` on your phone.
- For always-on access, deploy to a small box (Railway, Fly.io, a $5 VPS) and
  open that URL.
- In Safari/Chrome on the phone: **Share → Add to Home Screen**. It launches
  full-screen like a native app.

---

## 4. Make it hands-off (daily auto-sync)

The dashboard refreshes when you tap *Sync*, but for true "set and forget" run
the sync on a schedule. Add a cron job:

```bash
# every day at 6am – pulls new transactions + balances
0 6 * * * cd /path/to/finance-dashboard && /usr/bin/python3 -c "import plaid_client; plaid_client.sync_all()"
```

Now you just open the app and today's numbers are already there.

---

## 5. Tune it to your life

- **Budgets:** tap *Adjust budgets* in the app, or edit `DEFAULT_ENVELOPES` in
  `budget.py`.
- **Wealth rules:** in `.env`, `SAVINGS_RATE` is your pay-yourself-first %, and
  `EMERGENCY_MONTHS` is how many months of spending to protect before any cash
  counts as investable.
- **Categories:** `PFC_TO_ENVELOPE` in `budget.py` maps Plaid's categories to
  your envelopes. Re-tag any single transaction from the app if Plaid guesses
  wrong.

---

## How "safe to invest" is calculated

```
buffer     = EMERGENCY_MONTHS x average monthly spend
committed  = unspent budget remaining this month
safe       = checking balance - buffer - committed   (never below 0)
```

It's intentionally conservative: it won't tell you to invest money you still
need for this month's bills or your safety net.

## Files

| file | role |
|------|------|
| `app.py` | web server + JSON API |
| `plaid_client.py` | the only file that talks to Plaid |
| `db.py` | SQLite storage |
| `budget.py` | envelopes + safe-to-invest math |
| `config.py` | reads your `.env` |
| `static/` | the installable dashboard |
| `seed_demo.py` | fake data for trying it out |
