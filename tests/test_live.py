"""
Live tests against real Roblox and Rolimons. READ-ONLY: nothing here sends,
counters, accepts or declines a trade, or changes the account.

Needs a cookie in tests/.roblox_cookie (git-ignored) or the ROBLOX_COOKIE env
var, except the tests marked "no cookie needed". Run with:
    pytest tests/test_live.py -v
"""

import pytest

from handler import exceptions_types as E
from handler.handle_requests import RequestsHandler

pytestmark = pytest.mark.live

ROBLOX_USER_ID = 1  # the official "Roblox" account, always exists


@pytest.fixture(autouse=True)
def rate_limits_skip_not_fail(monkeypatch):
    """
    The bot may be running on the same account, so a 429 here is expected and
    not a bug: back off once (20s), then the test is skipped (see conftest.py).
    """
    from handler import handle_requests

    monkeypatch.setattr(handle_requests, "MAX_RATE_LIMIT_RETRIES", 1)


@pytest.fixture(scope="module")
def live_account(roblox_cookie):
    """A RobloxAPI logged in with the cookie, without the heavy __init__."""
    import roblox_api
    from rolimons_api import RolimonAPI

    acc = object.__new__(roblox_api.RobloxAPI)
    acc.cookies = {".ROBLOSECURITY": roblox_cookie}
    acc.request_handler = RequestsHandler(cookie=acc.cookies)
    acc.request_handler.generate_csrf()
    acc.rolimon = RolimonAPI()
    acc.config = acc.rolimon.config
    acc.self_duplicates = {}
    acc.all_cached_traders = set()
    acc.account_robux = 0
    acc.account_id, acc.username = acc.fetch_userid_and_name()
    return acc


# --- no cookie needed ---------------------------------------------------------


def test_rolimons_catalog_format_still_matches():
    """Fails if Rolimons changed the catalog page or the item field layout."""
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    rol.update_data()
    assert len(rol.item_data) > 1000
    item = next(iter(rol.item_data.values()))
    for key in ("item_name", "rap", "value", "total_value", "original_asset_id"):
        assert key in item


def test_garbage_cookie_raises_cookie_invalid():
    h = RequestsHandler(cookie={".ROBLOSECURITY": "not-a-real-cookie"})
    with pytest.raises(E.CookieInvalid):
        h.requestAPI("https://users.roblox.com/v1/users/authenticated")


def test_missing_page_raises_not_found_or_bad_request():
    h = RequestsHandler()
    with pytest.raises((E.NotFound, E.BadRequest)):
        h.requestAPI("https://users.roblox.com/v1/users/0")


# --- with your cookie ---------------------------------------------------------


def test_cookie_logs_in(live_account):
    assert isinstance(live_account.account_id, int)
    assert live_account.username


def test_csrf_token(live_account):
    assert live_account.request_handler.generate_csrf() is True
    assert live_account.request_handler.headers["x-csrf-token"]


def test_robux(live_account):
    live_account.get_robux()
    assert isinstance(live_account.account_robux, int)
    assert live_account.account_robux >= 0


def test_premium_check(live_account):
    assert live_account.check_premium(live_account.account_id) in (True, False)


@pytest.mark.parametrize("kind", ["inbound", "outbound", "inactive", "completed"])
def test_trade_lists(live_account, kind):
    trades = live_account.get_trades(
        f"https://trades.roblox.com/v1/trades/{kind}?limit=10&sortOrder=Desc",
        limit_pages=1,
    )
    assert isinstance(trades, dict)
    for info in trades.values():
        assert {"trade_id", "user_id", "created"} <= info.keys()


def test_first_completed_trade_formats(live_account):
    """Checks the v2 trade detail format still matches format_trade_api."""
    trades = live_account.get_trades(
        "https://trades.roblox.com/v1/trades/completed?limit=10&sortOrder=Desc",
        limit_pages=1,
    )
    if not trades:
        pytest.skip("Account has no completed trades")
    trade_id = next(iter(trades))
    response = live_account.request_handler.requestAPI(
        f"https://trades.roblox.com/v2/trades/{trade_id}"
    )
    try:
        trade = live_account.format_trade_api(response.json())
    except E.UnknownItem as e:
        pytest.skip(f"Trade has an item not on Rolimons: {e}")
    assert trade["self_id"] and trade["their_id"]


def test_own_tradable_inventory_page(live_account):
    """One page of the tradable items API, parsed the way fetch_inventory does."""
    response = live_account.request_handler.requestAPI(
        f"https://trades.roblox.com/v2/users/{live_account.account_id}/tradableItems"
        "?sortBy=CreationTime&sortOrder=2&limit=10&cursor="
    )
    page = response.json()
    assert "items" in page
    for item in page["items"]:
        assert "targetId" in item["itemTarget"]
        assert "itemType" in item["itemTarget"]
        assert "collectibleItemId" in item


def test_check_can_trade_returns_bool(live_account):
    assert live_account.check_can_trade(ROBLOX_USER_ID) in (True, False)


def test_owner_scan_does_not_crash(live_account):
    item = next(
        i for i in live_account.rolimon.item_data.values() if i.get("original_asset_id")
    )
    owners = []
    result = live_account.get_active_traders(item, owners)
    assert result is None or isinstance(result, list)
