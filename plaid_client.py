"""Thin wrapper around the Plaid SDK. This is the only file that talks to
the outside world. It pulls your data in; nothing pushes data out.
"""
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

import config
import db
from budget import map_envelope

_cfg = plaid.Configuration(
    host=config.PLAID_HOST,
    api_key={"clientId": config.PLAID_CLIENT_ID, "secret": config.PLAID_SECRET},
)
_client = plaid_api.PlaidApi(plaid.ApiClient(_cfg))


def create_link_token() -> str:
    """Token the browser uses to open Plaid Link and connect an institution.
    Requests both transactions and investments so one link covers Chase,
    Robinhood and Fidelity."""
    req = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id="me"),
        client_name="My Money Cockpit",
        products=[Products("transactions"), Products("investments")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    if config.PLAID_REDIRECT_URI:
        req.redirect_uri = config.PLAID_REDIRECT_URI
    return _client.link_token_create(req).link_token


def _as_dict(obj):
    """Normalize a Plaid response (model or dict) into a plain dict so we can
    read it consistently regardless of how the SDK deserializes it."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def exchange_public_token(public_token: str):
    """Turn the one-time public token from Plaid Link into a permanent
    access token, and store the item."""
    res = _as_dict(_client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    ))
    access_token, item_id = res.get("access_token"), res.get("item_id")
    db.save_item(item_id, access_token, institution="")
    try:
        sync_balances(access_token)
        sync_investments(access_token)
    except Exception:
        pass  # link is saved; the next auto-sync will pull the data
    return item_id


def _store_accounts(data):
    item_id = (data.get("item") or {}).get("item_id")
    for a in data.get("accounts", []):
        bal = a.get("balances") or {}
        sub = a.get("subtype")
        db.upsert_account({
            "account_id": a.get("account_id"),
            "item_id": item_id,
            "name": a.get("name"),
            "official_name": a.get("official_name") or "",
            "type": str(a.get("type")),
            "subtype": str(sub) if sub else "",
            "current": bal.get("current"),
            "available": bal.get("available"),
        })


def sync_balances(access_token: str):
    res = _as_dict(_client.accounts_balance_get(
        AccountsBalanceGetRequest(access_token=access_token),
        _check_return_type=False,
    ))
    _store_accounts(res)


def sync_investments(access_token: str):
    """Refresh brokerage / 401k balances (Robinhood, Fidelity)."""
    try:
        res = _as_dict(_client.investments_holdings_get(
            InvestmentsHoldingsGetRequest(access_token=access_token),
            _check_return_type=False,
        ))
    except Exception:
        return  # institution may not support investments, or returned odd data
    _store_accounts(res)


def sync_transactions(access_token: str, cursor: str | None):
    """Pull new/modified/removed transactions since last cursor.
    Returns the new cursor to persist."""
    has_more = True
    cur = cursor
    while has_more:
        kwargs = {"access_token": access_token}
        if cur:
            kwargs["cursor"] = cur
        res = _as_dict(_client.transactions_sync(
            TransactionsSyncRequest(**kwargs), _check_return_type=False))
        for t in res.get("added", []) + res.get("modified", []):
            cat = t.get("personal_finance_category") or {}
            pfc = str(cat.get("primary", "")) if cat else ""
            d = t.get("date")
            date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
            db.upsert_transaction({
                "txn_id": t.get("transaction_id"),
                "account_id": t.get("account_id"),
                "date": date_str,
                "name": t.get("name"),
                "merchant": t.get("merchant_name") or "",
                "amount": t.get("amount"),
                "pfc_primary": pfc,
                "envelope": map_envelope(pfc),
                "pending": 1 if t.get("pending") else 0,
            })
        for t in res.get("removed", []):
            db.delete_transaction(t.get("transaction_id"))
        cur = res.get("next_cursor")
        has_more = res.get("has_more", False)
    return cur


def sync_all():
    """Refresh everything. Call this on a daily schedule (cron) and on demand."""
    for item in db.get_items():
        tok = item["access_token"]
        sync_balances(tok)
        sync_investments(tok)
        new_cursor = sync_transactions(tok, item["cursor"])
        db.update_cursor(item["item_id"], new_cursor)
    # Record today's net worth so the portfolio chart builds real history.
    import budget
    from datetime import date
    nw = budget.net_worth()
    db.record_snapshot(date.today().isoformat(), nw["net_worth"],
                       nw["cash"], nw["investments"], nw["debt"])
    db.set_meta("last_sync", _now())


def _now():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
