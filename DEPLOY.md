# Get Cockpit on your iPhone (free, ~20 min)

You'll do three things: (1) get free Plaid keys, (2) put the app online for free,
(3) add it to your iPhone and link your banks. Your bank passwords go ONLY into
Plaid's secure popup — the app never sees them.

------------------------------------------------------------
## STEP 1 — Plaid keys (free, real bank data)
1. Go to dashboard.plaid.com/signup → choose **"Personal use"**.
2. Verify your email. You'll be on the free **Trial plan** (up to 10 linked
   accounts, includes Chase/Robinhood/Fidelity, $0).
3. Open **Team Settings → Keys**. Copy your **client_id** and your
   **Production secret**. Keep this tab open.

## STEP 2 — Put it online (free, on Render)
1. Make a free account at github.com, click **+ → New repository**, name it
   `money-cockpit`, and **upload** the unzipped project files (drag them into
   the upload box). Commit.
2. Make a free account at render.com → **New → Web Service** → connect your
   GitHub → pick `money-cockpit`. Render auto-detects Python and the start
   command. Choose the **Free** plan.
3. In **Environment**, add these variables:
   - `PLAID_CLIENT_ID` = your client_id
   - `PLAID_SECRET` = your Production secret
   - `PLAID_ENV` = production
   - `BILLS_WIRE` = 2650
4. Click **Create Web Service**. After it builds you'll get a URL like
   `https://money-cockpit-xxxx.onrender.com`. Copy it.
5. Add one more env var: `PLAID_REDIRECT_URI` = that URL (with the trailing /).
   In the Plaid Dashboard → **Link → Allowed redirect URIs**, add the same URL.
   Save. Render will redeploy automatically.

## STEP 3 — iPhone + link your banks
1. On your iPhone, open the Render URL in **Safari**.
2. Tap the Share icon → **Add to Home Screen**. Now it's an app icon.
3. Open it, tap **Link Account**, and sign into Chase in the secure popup.
   Repeat for Robinhood and Fidelity.
4. Done. It syncs automatically every time you open it.

------------------------------------------------------------
### Notes
- Free Render sleeps after 15 min idle, so the first open each time takes ~1 min
  to wake. Normal for free hosting.
- Free hosting doesn't keep a permanent disk: if you ever redeploy, you may need
  to tap Link Account again to reconnect. Your data isn't sold or shared — it
  lives only in your own Render service.
- To change your bills amount or budget split later, edit the env vars
  (BILLS_WIRE) or budget.py and redeploy.

### Faster way to just TEST with real data first (optional)
Keep running it on your Mac (`uvicorn app:app --port 8000`) and install
`cloudflared` to get a temporary public https link without GitHub. Good for a
quick test; Render is better for always-on.
