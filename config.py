"""Configuration for your personal finance dashboard.

Everything here is read from a .env file you control. Nothing is hardcoded
and nothing leaves your machine except calls to Plaid's API.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Plaid credentials (get these from dashboard.plaid.com) ---
# .strip() guards against stray spaces/newlines pasted in from the dashboard.
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "").strip()
PLAID_SECRET = os.getenv("PLAID_SECRET", "").strip()
# "sandbox" for testing with fake data, "production" once approved for real banks.
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox").strip().lower()

# Where your data lives. A single file on your machine.
DB_PATH = os.getenv("DB_PATH", "finance.db")

# --- Your wealth rules (tune these to your life) ---
# Pay-yourself-first: fraction of every paycheck that should go to savings/invest
# BEFORE spending envelopes get funded.
SAVINGS_RATE = float(os.getenv("SAVINGS_RATE", "0.20"))

# Emergency buffer to keep in checking, expressed in months of average spending.
EMERGENCY_MONTHS = float(os.getenv("EMERGENCY_MONTHS", "3"))

# You wire a fixed amount to a separate bills account each month. It's handled
# outside this app, so it's excluded from day-to-day spend tracking and only
# used to work out what's left to spend/save.
BILLS_WIRE = float(os.getenv("BILLS_WIRE", "2650"))

PLAID_HOST = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}[PLAID_ENV]

# Required for OAuth banks (Chase). Set to your deployed URL, e.g.
# https://my-cockpit.onrender.com/  — and add the same URL in the Plaid
# Dashboard under "Allowed redirect URIs".
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI", "").strip()
