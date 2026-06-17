"""SQLite storage. One local file, owned by you.

Tables:
  items         - one row per linked institution (Chase, Robinhood, Fidelity)
  accounts      - each account inside an item, with latest balance
  transactions  - every transaction Plaid has sent us
  envelopes     - your monthly budget per category
  meta          - key/value store (sync cursors, settings)
"""
import sqlite3
from contextlib import contextmanager
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id       TEXT PRIMARY KEY,
    access_token  TEXT NOT NULL,
    institution   TEXT,
    cursor        TEXT,                 -- transactions_sync pagination cursor
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id    TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL,
    name          TEXT,
    official_name TEXT,
    type          TEXT,                 -- depository / investment / credit
    subtype       TEXT,                 -- checking / savings / brokerage / 401k
    current       REAL,                 -- latest balance
    available     REAL,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id        TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL,
    date          TEXT NOT NULL,        -- YYYY-MM-DD
    name          TEXT,
    merchant      TEXT,
    amount        REAL NOT NULL,        -- Plaid sign: positive = money out
    pfc_primary   TEXT,                 -- Plaid personal_finance_category
    envelope      TEXT,                 -- our mapped category
    pending       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS envelopes (
    name          TEXT PRIMARY KEY,
    allocation    REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key           TEXT PRIMARY KEY,
    value         TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    date          TEXT PRIMARY KEY,   -- one row per day (YYYY-MM-DD)
    net_worth     REAL,
    cash          REAL,
    investments   REAL,
    debt          REAL
);

CREATE TABLE IF NOT EXISTS goals (
    name          TEXT PRIMARY KEY,
    target        REAL NOT NULL,
    saved         REAL DEFAULT 0,     -- used for manual goals
    kind          TEXT,               -- emergency / roth / investments / manual
    accent        TEXT
);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)


# --- items ---
def save_item(item_id, access_token, institution):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO items (item_id, access_token, institution, cursor) "
            "VALUES (?, ?, ?, COALESCE((SELECT cursor FROM items WHERE item_id=?), NULL))",
            (item_id, access_token, institution, item_id),
        )


def get_items():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM items")]


def update_cursor(item_id, cursor):
    with get_db() as conn:
        conn.execute("UPDATE items SET cursor=? WHERE item_id=?", (cursor, item_id))


# --- accounts ---
def upsert_account(acc):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO accounts
               (account_id, item_id, name, official_name, type, subtype,
                current, available, updated_at)
               VALUES (:account_id,:item_id,:name,:official_name,:type,:subtype,
                       :current,:available, datetime('now'))""",
            acc,
        )


def get_accounts():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM accounts")]


# --- transactions ---
def upsert_transaction(txn):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO transactions
               (txn_id, account_id, date, name, merchant, amount,
                pfc_primary, envelope, pending)
               VALUES (:txn_id,:account_id,:date,:name,:merchant,:amount,
                       :pfc_primary,:envelope,:pending)""",
            txn,
        )


def delete_transaction(txn_id):
    with get_db() as conn:
        conn.execute("DELETE FROM transactions WHERE txn_id=?", (txn_id,))


def get_transactions(since=None, limit=500):
    q = "SELECT * FROM transactions"
    args = []
    if since:
        q += " WHERE date >= ?"
        args.append(since)
    q += " ORDER BY date DESC LIMIT ?"
    args.append(limit)
    with get_db() as conn:
        return [dict(r) for r in conn.execute(q, args)]


def set_envelope_category(txn_id, envelope):
    with get_db() as conn:
        conn.execute("UPDATE transactions SET envelope=? WHERE txn_id=?", (envelope, txn_id))


# --- envelopes ---
def set_envelope(name, allocation):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO envelopes (name, allocation) VALUES (?, ?)",
            (name, allocation),
        )


def get_envelopes():
    with get_db() as conn:
        return {r["name"]: r["allocation"] for r in conn.execute("SELECT * FROM envelopes")}


# --- meta ---
def set_meta(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


def get_meta(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


# --- snapshots (net worth history) ---
def record_snapshot(date_str, net_worth, cash, investments, debt):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots (date, net_worth, cash, investments, debt) "
            "VALUES (?, ?, ?, ?, ?)",
            (date_str, net_worth, cash, investments, debt),
        )


def get_snapshots(limit=180):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]  # oldest -> newest


# --- goals ---
def set_goal(name, target, kind, accent, saved=0):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO goals (name, target, saved, kind, accent) VALUES (?, ?, ?, ?, ?)",
            (name, target, saved, kind, accent),
        )


def update_goal_saved(name, saved):
    with get_db() as conn:
        conn.execute("UPDATE goals SET saved=? WHERE name=?", (saved, name))


def get_goals():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM goals")]
