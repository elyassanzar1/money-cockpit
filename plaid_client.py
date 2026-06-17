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
    return _client.link_token_create(req).link_token


def exchange_public_token(public_token: str):
    """Turn the one-time public token from Plaid Link into a permanent
    access token, and store the item."""
    res = _client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token, item_id = res.access_token, res.item_id
    db.save_item(item_id, access_token, institution="")
    sync_balances(access_token)
    return item_id


def sync_balances(access_token: str):
    res = _client.accounts_balance_get(
        AccountsBalanceGetRequest(access_token=access_token)
    )
    item_id = res.item.item_id
    for a in res.accounts:
        db.upsert_account({
            "account_id": a.account_id,
            "item_id": item_id,
            "name": a.name,
            "official_name": a.official_name,
            "type": str(a.type),
            "subtype": str(a.subtype) if a.subtype else "",
            "current": a.balances.current,
            "available": a.balances.available,
        })


def sync_investments(access_token: str):
    """Refresh brokerage / 401k balances (Robinhood, Fidelity)."""
    try:
        res = _client.investments_holdings_get(
            InvestmentsHoldingsGetRequest(access_token=access_token)
        )
    except plaid.ApiException:
        return  # institution may not support investments product
    item_id = res.item.item_id
    for a in res.accounts:
        db.upsert_account({
            "account_id": a.account_id,
            "item_id": item_id,
            "name": a.name,
            "official_name": a.official_name,
            "type": str(a.type),
            "subtype": str(a.subtype) if a.subtype else "",
            "current": a.balances.current,
            "available": a.balances.available,
        })


def sync_transactions(access_token: str, cursor: str | None):
    """Pull new/modified/removed transactions since last cursor.
    Returns the new cursor to persist."""
    added = modified = removed = []
    has_more = True
    cur = cursor
    while has_more:
        kwargs = {"access_token": access_token}
        if cur:
            kwargs["cursor"] = cur
        res = _client.transactions_sync(TransactionsSyncRequest(**kwargs))
        for t in list(res.added) + list(res.modified):
            pfc = ""
            if t.personal_finance_category:
                pfc = str(t.personal_finance_category.primary)
            db.upsert_transaction({
                "txn_id": t.transaction_id,
                "account_id": t.account_id,
                "date": t.date.isoformat() if hasattr(t.date, "isoformat") else str(t.date),
                "name": t.name,
                "merchant": t.merchant_name or "",
                "amount": t.amount,
                "pfc_primary": pfc,
                "envelope": map_envelope(pfc),
                "pending": 1 if t.pending else 0,
            })
        for t in res.removed:
            db.delete_transaction(t.transaction_id)
        cur = res.next_cursor
        has_more = res.has_more
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
