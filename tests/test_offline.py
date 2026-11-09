"""
Offline tests for the error system. No network: every request goes through
the `router` fixture's fake responses.
"""

import random
import threading
import os
import re
import time
import types
import json
import pathlib

import pytest
import requests

from conftest import FAKE_CATALOG, make_response as resp

from handler import exceptions_types as E
from handler.handle_requests import RequestsHandler

U = "https://api.test/"
SEND = "https://trades.roblox.com/v2/trades/send"
REAL_GENERATE_CSRF = RequestsHandler.generate_csrf
INVENTORY = "https://trades.roblox.com/v2/users/"


def handler(router, prefix, *items, cookie=None):
    router.set(prefix, *items)
    return RequestsHandler(cookie=cookie)


# --- request layer ------------------------------------------------------------


def test_ok_returns_response(router):
    h = handler(router, U, resp(200, {"a": 1}))
    assert h.requestAPI(U).json() == {"a": 1}


def test_ok_with_error_body_raises(router):
    h = handler(router, U, resp(200, {"errors": [{"code": 5, "message": "nope"}]}))
    with pytest.raises(E.RobloxAPIError) as info:
        h.requestAPI(U)
    assert info.value.code == 5


def test_bad_request_carries_codes(router):
    h = handler(router, U, resp(400, {"errors": [{"code": 12, "message": "gone"}]}))
    with pytest.raises(E.BadRequest) as info:
        h.requestAPI(U)
    assert info.value.codes == [12] and info.value.status_code == 400


def test_unauthorized_with_cookie_is_cookie_invalid(router):
    h = handler(
        router,
        U,
        resp(
            401, {"errors": [{"code": 0, "message": "Authorization has been denied"}]}
        ),
        cookie={".ROBLOSECURITY": "x"},
    )
    with pytest.raises(E.CookieInvalid):
        h.requestAPI(U)


def test_csrf_refreshed_from_header_then_succeeds(router):
    h = handler(
        router,
        U,
        resp(
            403,
            {"errors": [{"code": 0, "message": "Token Validation Failed"}]},
            headers={"x-csrf-token": "NEW"},
        ),
        resp(200, {"ok": True}),
    )
    assert h.requestAPI(U).json() == {"ok": True}
    assert h.headers["x-csrf-token"] == "NEW"


def _real_csrf(monkeypatch):
    """The router fixture stubs generate_csrf; put the real one back."""
    monkeypatch.setattr(RequestsHandler, "generate_csrf", REAL_GENERATE_CSRF)


def test_csrf_refresh_retries_dropped_connection(router, monkeypatch):
    _real_csrf(monkeypatch)
    dropped = requests.ConnectionError("Remote end closed connection without response")
    router.set(
        "https://auth.roblox.com/", dropped, resp(403, headers={"x-csrf-token": "T"})
    )
    h = RequestsHandler(cookie={".ROBLOSECURITY": "x"})
    assert h.generate_csrf() is True
    assert h.headers["x-csrf-token"] == "T"


def test_csrf_refresh_gives_up_quietly(router, monkeypatch):
    _real_csrf(monkeypatch)
    router.set("https://auth.roblox.com/", requests.ConnectionError("down"))
    h = RequestsHandler()
    h.headers["x-csrf-token"] = "OLD"
    assert h.generate_csrf() is False
    assert h.headers["x-csrf-token"] == "OLD"


def test_csrf_keeps_failing_raises_auth_error(router):
    h = handler(router, U, resp(403, text="XSRF token invalid"))
    with pytest.raises(E.AuthError):
        h.requestAPI(U)


def test_challenge_raises_challenge_required(router):
    h = handler(
        router,
        U,
        resp(
            403,
            {"errors": [{"code": 0, "message": "Challenge is required"}]},
            headers={"rblx-challenge-id": "abc"},
        ),
    )
    with pytest.raises(E.ChallengeRequired) as info:
        h.requestAPI(U)
    assert info.value.response.headers["rblx-challenge-id"] == "abc"


@pytest.mark.parametrize("status", [401, 403])
def test_challenge_detected_by_header_not_message(router, status):
    """Roblox reworded the 2FA message before; only the header should matter."""
    h = handler(
        router,
        U,
        resp(
            status,
            {"errors": [{"code": 0, "message": "Some brand new wording"}]},
            # Also carries a csrf header, must still be treated as 2FA
            headers={"rblx-challenge-id": "abc", "x-csrf-token": "tok"},
        ),
    )
    with pytest.raises(E.ChallengeRequired):
        h.requestAPI(U)


def test_send_trade_solves_2fa_then_sends(router, account):
    challenge = resp(
        403,
        {"errors": [{"code": 0, "message": "anything"}]},
        headers={"rblx-challenge-id": "c"},
    )
    router.set(SEND, challenge, resp(200, {"tradeId": 9}))
    solved = []
    account.validate_2fa = lambda r: solved.append(1) or {"rblx-challenge-id": "c"}
    assert account.send_trade(2, ["a"], ["b"]) == 9
    assert solved == [1]


def test_send_trade_gives_up_after_3_challenges(router, account):
    import roblox_api

    router.set(
        SEND,
        resp(
            403,
            {"errors": [{"code": 0, "message": "x"}]},
            headers={"rblx-challenge-id": "c"},
        ),
    )
    solved = []
    account.validate_2fa = lambda r: solved.append(1) or {}
    with pytest.raises(E.ChallengeRequired):
        account.send_trade(2, ["a"], ["b"])
    # 3 sends, but no pointless solve after the last one
    assert (
        len([c for c in router.calls if c[1] == SEND])
        == roblox_api.SEND_TRADE_ATTEMPTS
        == 3
    )
    assert len(solved) == 2


def test_forbidden_and_not_found(router):
    h = handler(router, U, resp(403, {"errors": [{"code": 1, "message": "private"}]}))
    with pytest.raises(E.Forbidden):
        h.requestAPI(U)
    h = handler(router, U, resp(404, text="nf"))
    with pytest.raises(E.NotFound):
        h.requestAPI(U)


def test_server_error_retries_then_raises(router):
    h = handler(router, U, resp(503, text="down"))
    with pytest.raises(E.ServerError):
        h.requestAPI(U)
    assert len(router.calls) == 4  # first try + 3 retries


def test_server_error_recovers(router):
    h = handler(router, U, resp(500, text="x"), resp(200, {"ok": 1}))
    assert h.requestAPI(U).json() == {"ok": 1}


def test_network_error_retries_then_raises(router):
    h = handler(router, U, requests.ConnectionError("boom"))
    with pytest.raises(E.NetworkError) as info:
        h.requestAPI(U)
    assert isinstance(info.value.cause, requests.ConnectionError)


def test_trade_limit_on_send(router):
    h = handler(
        router,
        SEND,
        resp(
            429,
            {
                "errors": [
                    {"code": 0, "message": "You are sending too many trade requests"}
                ]
            },
        ),
    )
    with pytest.raises(E.TradeLimit) as info:
        h.requestAPI(SEND, "post", payload={})
    assert isinstance(info.value, E.RateLimited)


def test_rate_limit_backs_off_then_raises(router):
    h = handler(router, U, resp(429, text="slow down"))
    with pytest.raises(E.RateLimited):
        h.requestAPI(U)
    assert U not in h.ratelimit_urls


# --- roblox_api ---------------------------------------------------------------


@pytest.fixture
def account(router):
    """A RobloxAPI without the network-heavy __init__."""
    import roblox_api
    from rolimons_api import RolimonAPI

    acc = object.__new__(roblox_api.RobloxAPI)
    acc.request_handler = RequestsHandler(cookie={".ROBLOSECURITY": "x"})
    acc.account_id = 1
    acc.username = "tester"
    acc.account_robux = 100
    acc.rolimon = RolimonAPI()
    acc.config = acc.rolimon.config
    acc.self_duplicates = {}
    acc.all_cached_traders = set()
    acc.cookies = {".ROBLOSECURITY": "x"}
    acc.outbound_cache = {}
    acc.outbound_lock = threading.Lock()
    acc.config_changed_at = None
    acc.posted_accepts = set()
    from handler.counter_history import CounterHistory

    acc.counter_history = CounterHistory(path=None)
    # Never post to the webhooks in the real config.cfg
    acc.config.discord_settings = {
        "Send_Webhook": None,
        "Completed_Webhook": None,
        "Error_Webhook": None,
    }
    acc.discord_webhook = FakeDiscord()
    return acc


class FakeDiscord:
    """Records webhook posts instead of sending them: (url, title, color)."""

    def __init__(self):
        self.posts = []

    def embed_fields_from_trade(self, trade, rolimon_data, projected_data):
        return {}, 5

    def setup_embed(self, title, color, user_id, embed_fields, footer, description=""):
        return (title, color)

    def send_webhook(self, embed, url):
        self.posts.append((url, *embed))
        return True


def test_send_trade_success(router, account):
    router.set(SEND, resp(200, {"tradeId": 77}))
    assert account.send_trade(2, ["a"], ["b"]) == 77


def test_send_trade_insufficient_robux_refreshes_but_does_not_resend(router, account):
    """Resending with different robux would no longer match the logged trade."""
    router.set(
        SEND,
        resp(400, {"errors": [{"code": 17, "message": "robux"}]}),
        resp(200, {"tradeId": 5}),
    )
    refreshed = []
    account.get_robux = lambda: refreshed.append(1)
    with pytest.raises(E.InsufficientRobux):
        account.send_trade(2, ["a"], ["b"], self_robux=50)
    assert refreshed
    assert len([c for c in router.calls if c[1] == SEND]) == 1


def test_send_trade_items_unavailable(router, account):
    router.set(SEND, resp(400, {"errors": [{"code": 12, "message": "gone"}]}))
    checked = []
    account.check_completeds = lambda: checked.append(1)
    with pytest.raises(E.ItemsUnavailable):
        account.send_trade(2, ["a"], ["b"])
    assert checked


def test_send_trade_unknown_rejection(router, account):
    router.set(SEND, resp(400, {"errors": [{"code": 99, "message": "weird"}]}))
    with pytest.raises(E.TradeRejected) as info:
        account.send_trade(2, ["a"], ["b"])
    assert info.value.code == 99


def test_send_trade_bad_2fa_metadata_raises_two_factor_error(router, account):
    router.set(
        SEND,
        resp(
            403,
            {"errors": [{"code": 0, "message": "Challenge"}]},
            headers={
                "rblx-challenge-id": "c",
                "rblx-challenge-metadata": "not-base64!!",
            },
        ),
    )
    with pytest.raises(E.TwoFactorError):
        account.send_trade(2, ["a"], ["b"])


def test_fetch_inventory_private_is_inventory_unavailable(router, account):
    router.set(INVENTORY, resp(403, {"errors": [{"code": 1, "message": "private"}]}))
    with pytest.raises(E.InventoryUnavailable) as info:
        account.fetch_inventory(5)
    assert isinstance(info.value.cause, E.Forbidden)


def test_fetch_inventory_skips_unknown_items(router, account):
    account.rolimon.add_data_to_inventory = lambda inv, is_self=False: inv
    page = {
        "nextPageCursor": None,
        "items": [
            {
                "itemTarget": {"targetId": 999, "itemType": "Asset"},
                "collectibleItemId": "z",
                "instances": [{"collectibleItemInstanceId": "u9"}],
            },
            {
                "itemTarget": {"targetId": 1, "itemType": "Asset"},
                "collectibleItemId": "y",
                "instances": [{"collectibleItemInstanceId": "u1"}],
            },
        ],
    }
    router.set(INVENTORY, resp(200, page))
    assert list(account.fetch_inventory(1)) == ["u1"]


def test_refresh_self_inventory_is_bounded(router, account):
    import roblox_api

    calls = []

    def boom(_):
        calls.append(1)
        raise E.InventoryUnavailable(1, E.ServerError(resp(500)))

    account.fetch_inventory = boom
    with pytest.raises(E.InventoryUnavailable):
        account.refresh_self_inventory()
    assert len(calls) == roblox_api.SELF_INVENTORY_ATTEMPTS


def test_calculate_gains(router, account):
    with pytest.raises(E.UnknownItem):
        account.calculate_gains(["1:404"])
    rap, value, _algo, _overall = account.calculate_gains(["1:1", "1:2"])
    assert rap == 1500 and value == 600


def test_format_trade_bad_json_is_invalid_response(router, account):
    with pytest.raises(E.InvalidResponse):
        account.format_trade_api({"nope": 1})


def test_check_can_trade_logged_out_raises_cookie_invalid(router, account, monkeypatch):
    router.set("https://www.roblox.com/users/", resp(200, text="<html>"))

    def redirected(self, method, URL, *a):
        r = router(self, method, URL, *a)
        r.url = "https://www.roblox.com/NewLogin?ReturnUrl=x"
        return r

    monkeypatch.setattr(RequestsHandler, "_send", redirected)
    with pytest.raises(E.CookieInvalid):
        account.check_can_trade(9)


def test_check_can_trade_uses_solved_2fa(router, account):
    challenge = resp(
        403,
        {"errors": [{"code": 0, "message": "x"}]},
        headers={"rblx-challenge-id": "c"},
    )
    router.set("https://www.roblox.com/users/", challenge, resp(200, text="<html>"))
    account.validate_2fa = lambda r: {"rblx-challenge-id": "c"}
    assert account.check_can_trade(9) is True


def test_fetch_inventory_without_rolimons_data_is_unavailable(router, account):
    """An empty inventory would bench the account for 6 hours; fail instead."""
    account.rolimon.item_data = {}
    router.set("https://www.rolimons.com/catalog", resp(503, text="down"))
    with pytest.raises(E.InventoryUnavailable) as info:
        account.fetch_inventory(1)
    assert isinstance(info.value.cause, E.RolimonsError)


def test_refresh_self_inventory_no_sleep_after_last_try(router, account, monkeypatch):
    import time as time_module

    sleeps = []
    monkeypatch.setattr(time_module, "sleep", lambda s: sleeps.append(s))

    def boom(_):
        raise E.InventoryUnavailable(1, E.ServerError(resp(500)))

    account.fetch_inventory = boom
    with pytest.raises(E.InventoryUnavailable):
        account.refresh_self_inventory()
    assert sleeps == [10, 20]


def test_get_active_traders_returns_none_on_errors(router, account):
    router.set("https://inventory.roblox.com/", resp(503, text="down"))
    assert account.get_active_traders({"original_asset_id": 1}, []) is None


# --- rolimons -----------------------------------------------------------------


def test_rolimons_bad_page_keeps_old_data(router):
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    old = rol.item_data
    router.set(
        "https://www.rolimons.com/catalog", resp(200, text="<html>changed</html>")
    )
    with pytest.raises(E.RolimonsError):
        rol.update_data()
    assert rol.item_data is old and "1:1" in rol.item_data


def test_rolimons_down_raises(router):
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    router.set("https://www.rolimons.com/catalog", resp(503, text="down"))
    with pytest.raises(E.RolimonsError):
        rol.update_data()
    router.set("https://www.rolimons.com/catalog", resp(200, text=FAKE_CATALOG))


def test_no_items_to_scan_is_config_error(router):
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    old = dict(rol.config.scan_items)
    rol.config.scan_items["Minimum_Rap_of_Item"] = 10**12
    rol.config.scan_items["Scan_Type"] = "both"
    try:
        with pytest.raises(E.NoItemsToScan) as info:
            rol.return_item_to_scan()
        assert isinstance(info.value, ValueError)
    finally:
        rol.config.scan_items.clear()
        rol.config.scan_items.update(old)


# --- json files ---------------------------------------------------------------


def test_corrupt_json_backed_up_without_deadlock():
    from handler.handle_json import JsonHandler

    name = "corrupt_test.json"
    with open(name, "w") as f:
        f.write('{"broken": [')
    jh = JsonHandler(name)
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("data", jh.read_data()))
    t.start()
    t.join(5)
    assert not t.is_alive(), "read_data deadlocked"
    assert out["data"] == {}

    backups = [f for f in os.listdir(".") if f.startswith(name + ".corrupt-")]
    assert backups
    with open(backups[0]) as f:
        assert "broken" in f.read()


# --- main.py ------------------------------------------------------------------


@pytest.fixture
def doggo(router):
    import main
    from rolimons_api import RolimonAPI

    d = object.__new__(main.Doggo)
    d.disabled_accounts = set()
    d.rolimons = RolimonAPI()
    d.discord_webhook = main.DiscordHandler()
    d.limited = []
    d.json = types.SimpleNamespace(add_ratelimit_timestamp=d.limited.append)
    d.stop_event = threading.Event()
    d.user_queue = {}
    return d


INV = {"u1": {"item_id": "1:1"}}
THEIR_INV = {"t1": {"item_id": "1:2"}}


def trade_account(account, send_effect):
    account.trade_maker = types.SimpleNamespace(
        generate_trade=lambda a, b, **_k: {
            "self_side": ["u1"],
            "their_side": ["t1"],
            "self_robux": 0,
        }
    )

    def send(*_a, **_k):
        if isinstance(send_effect, BaseException):
            raise send_effect
        return send_effect

    account.send_trade = send
    account.refresh_self_inventory = lambda: None
    account.config.debug["ignore_limit"] = False
    account.config.debug["dont_send_trade"] = False
    account.config.discord_settings["Send_Webhook"] = ""
    return account


@pytest.mark.parametrize(
    "error, outcome",
    [
        (E.TradeLimit(), "stop"),
        (E.UserCannotTrade(resp(400)), "skipped"),
        (E.ItemsUnavailable(resp(400)), "skipped"),
        (E.TwoFactorError("bad"), "next_account"),
        (E.TradeRejected(resp(400)), "skipped"),
    ],
)
def test_trade_with_outcomes(doggo, account, error, outcome):
    acc = trade_account(account, error)
    assert doggo.trade_with(acc, 5, INV, THEIR_INV) == outcome
    if outcome == "stop":
        assert doggo.limited


def test_trade_with_expired_cookie_propagates(doggo, account):
    acc = trade_account(account, E.CookieInvalid(resp(401)))
    with pytest.raises(E.CookieInvalid):
        doggo.trade_with(acc, 5, INV, THEIR_INV)


def test_trade_counts_as_sent_even_if_webhook_breaks(doggo, account):
    acc = trade_account(account, 123)
    # Their item isn't on Rolimons, so building the webhook fails
    assert doggo.trade_with(acc, 5, INV, {"t1": {"item_id": "1:404"}}) == "sent"


def test_run_safely_restarts_after_crash(doggo):
    runs = []

    def flaky():
        runs.append(1)
        if len(runs) < 3:
            raise RuntimeError("bug")

    doggo.run_safely("flaky", flaky)
    assert len(runs) == 3


def test_queue_traders_disables_account_on_expired_cookie(doggo, account):
    def expired(item, owners):
        raise E.CookieInvalid(resp(401))

    account.get_active_traders = expired
    doggo.rolimons.return_item_to_scan = lambda reach=None, skip=():  {"original_asset_id": 1}
    doggo.queue_traders(account, threading.Event())
    assert doggo.is_disabled(account)


# --- outbound checker -----------------------------------------------------------

TRADE_URL = "https://trades.roblox.com/v2/trades/"
DECLINE_URL = "https://trades.roblox.com/v1/trades/"


def outbound_trade_json(self_items, their_items):
    def offer(user_id, items):
        return {
            "user": {"id": user_id},
            "robux": 0,
            "items": [
                {"itemTarget": {"itemType": "Asset", "targetId": i.split(":")[1]}}
                for i in items
            ],
        }

    return {
        "participantAOffer": offer(1, self_items),
        "participantBOffer": offer(2, their_items),
    }


@pytest.fixture
def outbound(router, account):
    """Account set up to check one outbound: we give 1:2 (RAP 500), receive 1:1 (RAP 1000)."""
    from trade_algorithm import TradeMaker

    checker = object.__new__(TradeMaker)
    checker.config = account.config
    # Cancel only if the trade stops being a RAP win; ignore every other rule
    for attr in (
        "min_value_gain max_value_gain min_algo_gain max_algo_gain "
        "min_overall_gain max_overall_gain max_rap_gain "
        "min_rap_score_percentage max_rap_score_percentage "
        "min_overall_score_percentage max_overall_score_percentage "
        "min_value_of_trade min_rap_of_trade"
    ).split():
        setattr(checker, attr, None)
    checker.min_rap_gain = 1
    account.outbound_trader = checker
    account.config.projected_detection["Detect_Rolimons_Projecteds"] = False

    router.set(TRADE_URL, resp(200, outbound_trade_json(["1:2"], ["1:1"])))
    router.set(DECLINE_URL, resp(200, {}))
    account.rolimon.projected_json.write_data({})
    return account


def declined(router):
    return [url for method, url in router.calls if url.endswith("/decline")]


def test_outbound_kept_while_still_a_win(router, outbound):
    outbound._check_one_outbound(55)
    assert declined(router) == []


def test_outbound_cancelled_when_received_item_rap_drops(router, outbound):
    # The item we'd receive crashes from 1000 to 400 RAP: now a loss
    outbound.rolimon.item_data["1:1"]["rap"] = 400
    outbound.rolimon.item_data["1:1"]["total_value"] = 400
    outbound._check_one_outbound(55)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_outbound_cancelled_when_received_item_is_projected(router, outbound):
    outbound.rolimon.projected_json.write_data(
        {"1:1": {"is_projected": True, "value": 1000, "timestamp": 9e18}}
    )
    outbound._check_one_outbound(55)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_outbound_kept_when_receiving_projected_cancel_is_off(router, outbound):
    outbound.config.outbound["Cancel_Receiving_Projected"] = False
    outbound.rolimon.projected_json.write_data(
        {"1:1": {"is_projected": True, "value": 1000, "timestamp": 9e18}}
    )
    outbound._check_one_outbound(55)
    assert declined(router) == []  # still a win on the algorithm value


@pytest.mark.parametrize("setting_on", [True, False])
def test_outbound_sending_projected_respects_setting(router, outbound, setting_on):
    outbound.config.outbound["Cancel_Sending_Projected"] = setting_on
    outbound.config.projected_detection["Check_Valued_Items"] = True  # 1:2 is valued
    outbound.rolimon.projected_json.write_data(
        {"1:2": {"is_projected": True, "value": 500, "timestamp": 9e18}}
    )
    outbound._check_one_outbound(55)
    assert bool(declined(router)) is setting_on


@pytest.mark.parametrize("check_valued", [True, False])
def test_valued_items_only_projected_when_checked(outbound, check_valued):
    outbound.config.projected_detection["Check_Valued_Items"] = check_valued
    outbound.rolimon.item_data["1:2"]["value"] = 500
    outbound.rolimon.item_data["1:1"]["value"] = None  # a RAP item
    outbound.rolimon.projected_json.write_data(
        {
            "1:1": {"is_projected": True, "value": 1000, "timestamp": 9e18},
            "1:2": {"is_projected": True, "value": 500, "timestamp": 9e18},
        }
    )
    expected = ["1:1", "1:2"] if check_valued else ["1:1"]
    assert outbound._projected_items(["1:1", "1:2"]) == expected


def test_check_valued_items_setting_defaults_off(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    for text, expected in (
        ("", False),
        ("[Projected]\nCheck Valued Items = True", True),
        ("[Projected Detection]\nCheck Valued Items = False", False),
    ):
        cfg.write_text(text + "\n")
        assert ConfigHandler(str(cfg)).projected_detection["Check_Valued_Items"] is expected


@pytest.mark.parametrize("setting_on", [True, False])
def test_outbound_rolimons_projected_flag_respects_setting(
    router, outbound, setting_on
):
    outbound.config.projected_detection["Detect_Rolimons_Projecteds"] = setting_on
    outbound.rolimon.item_data["1:1"]["projected"] = True
    outbound._check_one_outbound(55)
    assert bool(declined(router)) is setting_on


def test_outbound_rescans_stale_item_before_judging(router, outbound):
    # Algo value is days old; a fresh scan finds the price collapsed
    outbound.rolimon.projected_json.write_data(
        {
            "1:1": {
                "is_projected": False,
                "value": 1000,
                "timestamp": 0,
                "collectible_item_id": "abc",
            }
        }
    )
    scanned = []

    def fresh_scan(collectibleId, item_id):
        scanned.append((collectibleId, item_id))
        data = outbound.rolimon.projected_json.read_data()
        data[item_id] = {
            "is_projected": True,
            "value": 300,
            "timestamp": 9e18,
            "collectible_item_id": "abc",
        }
        outbound.rolimon.projected_json.write_data(data)

    outbound.is_projected_api = fresh_scan
    outbound._check_one_outbound(55)
    assert scanned == [("abc", "1:1")]
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_outbound_does_not_rescan_fresh_items(router, outbound):
    import time as time_module

    outbound.rolimon.projected_json.write_data(
        {
            "1:1": {
                "is_projected": False,
                "value": 1000,
                "timestamp": time_module.time(),
                "collectible_item_id": "abc",
            }
        }
    )
    outbound.is_projected_api = lambda **_k: pytest.fail("should not rescan")
    outbound._check_one_outbound(55)
    assert declined(router) == []


# --- quick outbound recheck on Rolimons updates -------------------------------


def cached(trade_json, created=None):
    return {"json": trade_json, "created": created}


def outbound_list(*trade_ids):
    return resp(
        200,
        {
            "data": [
                {"id": t, "user": {"id": 2}, "created": "2026-11-01T00:00:00Z"}
                for t in trade_ids
            ],
            "nextPageCursor": None,
        },
    )


def test_full_check_caches_then_recheck_cancels_without_refetching(router, outbound):
    router.set("https://trades.roblox.com/v1/trades/outbound", outbound_list(55))
    outbound.outbound_api_checker()
    assert 55 in outbound.outbound_cache and declined(router) == []

    # Rolimons update: the item we'd receive drops
    router.calls.clear()
    outbound.rolimon.item_data["1:1"]["rap"] = 400
    outbound.rolimon.item_data["1:1"]["total_value"] = 400
    assert outbound.recheck_cached_outbounds() == 1

    # Only the decline went to Roblox: no list or trade-detail requests
    assert [url for _m, url in router.calls] == [DECLINE_URL + "55/decline"]
    assert 55 not in outbound.outbound_cache


def test_recheck_makes_no_requests_when_nothing_changed(router, outbound):
    outbound.outbound_cache[55] = cached(outbound_trade_json(["1:2"], ["1:1"]))
    router.calls.clear()
    assert outbound.recheck_cached_outbounds() == 0
    assert router.calls == []


def test_recheck_never_rescans_price_history(router, outbound):
    outbound.outbound_cache[55] = cached(outbound_trade_json(["1:2"], ["1:1"]))
    outbound.rolimon.projected_json.write_data(
        {
            "1:1": {
                "is_projected": False,
                "value": 1000,
                "timestamp": 0,
                "collectible_item_id": "abc",
            }
        }
    )
    outbound.is_projected_api = lambda **_k: pytest.fail("recheck must not call Roblox")
    outbound.recheck_cached_outbounds()


def test_recheck_skips_while_full_check_runs(router, outbound):
    outbound.outbound_cache[55] = cached(outbound_trade_json(["1:2"], ["1:1"]))
    outbound.rolimon.item_data["1:1"]["rap"] = 400
    with outbound.outbound_lock:
        assert outbound.recheck_cached_outbounds() == 0
    assert declined(router) == []


def test_full_check_forgets_finished_trades(router, outbound):
    outbound.outbound_cache[99] = cached(outbound_trade_json(["1:2"], ["1:1"]))
    router.set("https://trades.roblox.com/v1/trades/outbound", outbound_list(55))
    outbound.outbound_api_checker()
    assert set(outbound.outbound_cache) == {55}


# --- config change: only cancel losing trades -------------------------------------


@pytest.fixture
def config_changed(outbound):
    """The config changed at t=1000 and the new config is much stricter."""
    outbound.config.outbound["Only_Cancel_Losing_After_Config_Change"] = True
    outbound.config_changed_at = 1000
    outbound.outbound_trader.min_rap_gain = 10_000  # nothing passes this
    return outbound


OLD, NEW = 500, 2000  # trade created before / after the change


def test_old_trade_still_winning_is_kept_after_config_change(router, config_changed):
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD
    )
    assert declined(router) == []


def test_old_trade_that_turns_losing_is_cancelled(router, config_changed):
    config_changed.rolimon.item_data["1:1"]["total_value"] = 100  # receive side crashed
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD
    )
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_old_trade_losing_because_of_robux_is_cancelled(router, config_changed):
    trade = outbound_trade_json(["1:2"], ["1:1"])
    trade["participantAOffer"]["robux"] = 600  # 1000 - 600 - 600 robux < 0
    config_changed._evaluate_outbound(55, trade, False, created=OLD)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_old_trade_receiving_projected_is_still_cancelled(router, config_changed):
    config_changed.rolimon.projected_json.write_data({"1:1": {"is_projected": True}})
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD
    )
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_new_trade_uses_full_rules(router, config_changed):
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=NEW
    )
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_option_off_uses_full_rules_for_old_trades(router, config_changed):
    config_changed.config.outbound["Only_Cancel_Losing_After_Config_Change"] = False
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD
    )
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_trade_sent_under_old_config_kept_even_if_newer(router, config_changed, monkeypatch, tmp_path):
    """A bot still on the old config sent it right after the new one started."""
    import roblox_api
    from handler.handle_json import JsonHandler

    monkeypatch.setattr(roblox_api, "SENT_CONFIGS_FILE", str(tmp_path / "sent.json"))
    JsonHandler(roblox_api.SENT_CONFIGS_FILE).write_data(
        {str(config_changed.account_id): {"55": ["old fingerprint", NEW]}}
    )
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=NEW
    )
    assert declined(router) == []


def test_trade_sent_under_current_config_uses_full_rules(router, config_changed, monkeypatch, tmp_path):
    import roblox_api

    monkeypatch.setattr(roblox_api, "SENT_CONFIGS_FILE", str(tmp_path / "sent.json"))
    config_changed._remember_sent_config(55)
    config_changed._evaluate_outbound(
        55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD
    )
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_sent_configs_forget_closed_trades(outbound, monkeypatch, tmp_path):
    import roblox_api
    from handler.handle_json import JsonHandler

    monkeypatch.setattr(roblox_api, "SENT_CONFIGS_FILE", str(tmp_path / "sent.json"))
    key = str(outbound.account_id)
    JsonHandler(roblox_api.SENT_CONFIGS_FILE).write_data(
        {key: {"1": ["f", 100], "2": ["f", 100], "3": ["f", 900]}}
    )
    outbound._forget_sent_configs({1: {}}, checked_at=500)
    # 1 is still open, 3 was sent after the check started
    assert set(JsonHandler(roblox_api.SENT_CONFIGS_FILE).read_data()[key]) == {"1", "3"}


def test_config_change_detected_and_remembered(router, outbound, monkeypatch):
    import time as time_module

    if os.path.exists("outbound_config_state.json"):
        os.remove("outbound_config_state.json")
    monkeypatch.setattr(time_module, "time", lambda: 1000.0)
    first = outbound._config_changed_at()

    monkeypatch.setattr(time_module, "time", lambda: 5000.0)
    assert outbound._config_changed_at() == first == 1000.0  # same config, same time

    outbound.config.trading["Minimum_RAP_Gain"] = 123456  # user edits config
    assert outbound._config_changed_at() == 5000.0


def test_full_check_reads_trade_creation_time(router, outbound):
    router.set(
        "https://trades.roblox.com/v1/trades/outbound",
        resp(
            200,
            {
                "data": [
                    {"id": 55, "user": {"id": 2}, "created": "2026-11-01T12:00:00.123Z"}
                ],
                "nextPageCursor": None,
            },
        ),
    )
    outbound.outbound_api_checker()
    from datetime import datetime, timezone

    expected = datetime(2026, 11, 1, 12, 0, 0, 123000, tzinfo=timezone.utc).timestamp()
    assert outbound.outbound_cache[55]["created"] == expected


# --- account config editor ------------------------------------------------------

from handler.account_settings import HandleConfigs, parse_config_value  # noqa: E402


@pytest.mark.parametrize(
    "typed, expected",
    [
        (" 100 ", 100),
        ("0.25", 0.25),
        ("none", None),
        ("false", False),
        ("rap_algo", "rap_algo"),
    ],
)
def test_parse_config_value(typed, expected):
    value = parse_config_value(typed)
    assert value == expected and type(value) is type(expected)


@pytest.fixture
def configs():
    h = HandleConfigs()
    h.main_values = h.default_config = {
        "MaxRobux": 100,
        "Minimum_RAP_Gain": 50.0,
        "Maximum_RAP_Gain": None,
        "TradeForFaces": True,
        "Rap_Algo_For_Valued": "rap_algo",
        "NFT": [],
        "Select_Trade_Using": "random",
        "Outbound_Variety": 0.5,
    }
    h.acc_configs.write_data({})
    return h


@pytest.mark.parametrize(
    "key, typed, result",
    [
        ("MaxRobux", "100", 100),
        ("MaxRobux", "None", None),
        ("Maximum_RAP_Gain", "0.5", 0.5),
        ("TradeForFaces", "false", False),
        ("Rap_Algo_For_Valued", "Zero_Value", "zero_value"),
        ("Select_Trade_Using", "highest_overall_gain", "highest_overall_gain"),
        ("NFT", "1:5, 2:6, 7", ["5", "6", "7"]),
        ("NFT", "None", []),
    ],
)
def test_account_setting_parse(configs, key, typed, result):
    value = configs.parse(key, typed)
    assert value == result and type(value) is type(result)


@pytest.mark.parametrize(
    "key, typed",
    [("MaxRobux", "abc"), ("MaxRobux", "2.5"), ("TradeForFaces", "None"),
     ("Select_Trade_Using", "best"), ("NFT", "a hat")],
)
def test_account_setting_parse_rejects(configs, key, typed):
    with pytest.raises(ValueError):
        configs.parse(key, typed)


def test_get_config_repairs_values_saved_as_text(configs):
    configs.acc_configs.write_data(
        {"7": {"MaxRobux": "100", "Maximum_RAP_Gain": "None", "TradeForFaces": "False"}}
    )
    assert configs.get_config("7") == {
        "MaxRobux": 100, "Maximum_RAP_Gain": None, "TradeForFaces": False,
    }


def test_account_config_only_overrides_what_it_sets(configs):
    from handler.handle_config import ConfigHandler

    configs.set_value("7", "MaxRobux", 5)
    configs.set_value("7", "Select_Trade_Using", "random")
    configs.set_value("7", "NFT", ["99"])
    config = ConfigHandler("config.default.cfg")
    main_min = config.trading["Minimum_Overall_Gain"]
    assert configs.apply(config, "7")
    assert config.trading["MaxRobux"] == 5
    assert config.trading["Minimum_Overall_Gain"] == main_min  # not set: config.cfg's
    assert config.filter_generated["Select_Trade_Using"] == "random"
    assert config.filter_items["NFT"] == ["99"]
    configs.reset_value("7", "MaxRobux")
    configs.reset_value("7", "Select_Trade_Using")
    configs.reset_value("7", "NFT")
    assert configs.acc_configs.read_data() == {}  # nothing left: entry removed
    assert not configs.apply(ConfigHandler("config.default.cfg"), "7")


def _manager(configs, monkeypatch, answers, **kwargs):
    import config_manager

    configs.cookies.write_data({"roblox_accounts": [{"user_id": "7", "username": "tester"}]})
    answers = iter(answers)
    monkeypatch.setattr(config_manager, "HandleConfigs", lambda: configs)
    kwargs.setdefault("item_names", config_manager.ItemNames(fetch=lambda: {"items": {
        "1029025": ["The Classic ROBLOX Fedora", "Fedora"],
        "1191135761": ["Valkyrie Helm", "VH"],
        "1191125008": ["Valkyrie Helm Replica", ""],
    }}))
    manager = config_manager.AccountSettings(
        ask=lambda _prompt: next(answers), run=False, **kwargs
    )
    manager.cli.clear_console = lambda: None
    manager.cli.print_error = lambda message: None
    return manager


def _index(names, wanted) -> str:
    """The menu number of wanted in names."""
    return str([n.lower() for n in names].index(wanted.lower()) + 1)


def test_config_manager_edits_and_resets_a_setting(configs, monkeypatch):
    import config_manager as cm

    picking = _index(cm.SECTION_ORDER, "Picking Trades")
    labels = [cm.shown_name(k)[1] for k in cm.SECTIONS["Picking Trades"]]
    pick, variety = _index(labels, "Pick Trade By"), _index(labels, "Outbound Variety")
    manager = _manager(configs, monkeypatch, [
        "2", "1", picking,          # Account Configs > tester > Picking Trades
        pick, "2", "1", "4",        # Pick Trade By: replace it with the first option, save
        pick, "5",                  # back to config.cfg's
        variety, "0.25",            # Outbound Variety
        "", "", "", "",             # back out of every menu
    ])
    manager.main()
    assert configs.get_config("7") == {"Outbound_Variety": 0.25}


def test_config_manager_builds_a_blend(configs, monkeypatch):
    import config_manager as cm
    from trade_algorithm import SELECT_TRADE_OPTIONS

    labels = [cm.shown_name(k)[1] for k in cm.SECTIONS["Picking Trades"]]
    ordered = [o for o in cm.PICK_HELP if o in SELECT_TRADE_OPTIONS]
    first = ordered  # "random" was removed, so it's listed again
    second = [o for o in first if o != "highest_demand"]
    manager = _manager(configs, monkeypatch, [
        "2", "1", _index(cm.SECTION_ORDER, "Picking Trades"),
        _index(labels, "Pick Trade By"),
        "1", "3",                                   # Mode: Blend
        "3", "3",                                   # random > Remove
        "2", _index(first, "highest_demand"),       # add highest_demand
        "2", _index(second, "upgrade"),             # add upgrade
        "4", "1",                                   # upgrade > Move up
        "5",                                        # Save
        "", "", "", "",
    ])
    manager.main()
    assert configs.get_config("7") == {"Select_Trade_Using": "blend: upgrade, highest_demand"}


def test_config_manager_adds_items_by_name_or_id(configs, monkeypatch):
    import config_manager as cm

    labels = [cm.shown_name(k)[1] for k in cm.SECTIONS["Items"]]
    manager = _manager(configs, monkeypatch, [
        "2", "1", _index(cm.SECTION_ORDER, "Items"), _index(labels, "Never Give"),
        "fedora, 1191135761",   # by acronym and by ID
        "valkyrie",             # matches 2 names: pick the second
        "2",
        "1",                    # remove the fedora
        "save",
        "", "", "", "",
    ])
    manager.main()
    assert configs.get_config("7") == {"NFT": ["1191135761", "1191125008"]}


def test_config_manager_edits_config_cfg(configs, monkeypatch, tmp_path):
    import shutil
    import config_manager as cm

    path = tmp_path / "config.cfg"
    shutil.copy("config.cfg", path)
    from handler.handle_config import ConfigHandler

    seconds = ConfigHandler(str(path)).filter_generated["Max_Seconds_Spent_on_One_User"]
    sections = cm.read_settings(path.read_text())
    names = [name for name, _ in sections]
    ads = [o for o, _, _ in dict(sections)["Trade Ads"]]
    owners = [o for o, _, _ in dict(sections)["Finding Traders"]]
    picking = [o for o, _, _ in dict(sections)["Picking Trades"]]
    tags = list(cm.TAG_LISTS[("trade ads", "request tags")])
    now = [t.strip() for t in dict((o, v) for o, v, _ in dict(sections)["Trade Ads"])["Request Tags"].split(",")]
    manager = _manager(configs, monkeypatch, [
        "1",
        _index(names, "Finding Traders"), _index(owners, "Scan Type"), "2",  # value
        "",
        _index(names, "Picking Trades"), _index(picking, "Max Seconds Per Trader"),
        "abc",                                                             # won't load: not saved
        "",                                                                # Press enter
        "",
        _index(names, "Trade Ads"), _index(ads, "Request Tags"),
        _index(tags, "rares"), _index(tags, now[0]), str(len(tags) + 1),   # rares on, first off, save
        "", "", "",
    ], config_file=str(path))
    manager.main()
    config = ConfigHandler(str(path))
    assert config.scan_items["Scan_Type"] == "value"
    assert config.filter_generated["Max_Seconds_Spent_on_One_User"] == seconds
    assert "rares" in config.trade_ads["Request_Tags"]
    assert now[0] not in config.trade_ads["Request_Tags"]
    # Comments are kept
    assert "# Time limit for finding a trade with one trader." in path.read_text()


def test_read_settings_keeps_the_notes_above_each_setting():
    import config_manager as cm

    sections = dict(cm.read_settings("[A]\n# what x does\nX = 1\nY = 2\n\n[B]\nZ = True\n"))
    assert sections["A"] == [("X", "1", "what x does"), ("Y", "2", "what x does")]
    assert cm.setting_kind("B", "Z", "True") == ("bool",)
    assert cm.setting_kind("Finding Traders", "Scan Type", "both")[0] == "choice"
    assert cm.pick_parts("blend: a, b") == ("blend", ["a", "b"])
    assert cm.pick_parts("a + b") == ("tiebreak", ["a", "b"])


# --- inbound accept / counter ---------------------------------------------------

INBOUND_LIST = "https://trades.roblox.com/v1/trades/inbound"
ACCEPT_URL = "https://trades.roblox.com/v1/trades/"


def inbound_trade_json(self_items, their_items, self_robux=0, their_robux=0):
    """Inbound as Roblox may send it: the sender (them, id 2) as participant A."""
    trade = outbound_trade_json(self_items, their_items)
    trade["participantAOffer"]["robux"] = self_robux
    trade["participantBOffer"]["robux"] = their_robux
    return {
        "participantAOffer": trade["participantBOffer"],
        "participantBOffer": trade["participantAOffer"],
    }


def inbound_list(*trade_ids):
    return resp(
        200,
        {
            "data": [
                {"id": t, "user": {"id": 2}, "created": "2026-11-01T00:00:00Z"}
                for t in trade_ids
            ],
            "nextPageCursor": None,
        },
    )


@pytest.fixture
def inbound(router, account):
    """
    One inbound: they give 1:1 (1000), we give 1:2 (600 overall) -> a win.
    Config only requires a RAP gain of at least 1.
    """
    from trade_algorithm import TradeMaker

    checker = object.__new__(TradeMaker)
    checker.config = account.config
    for attr in (
        "min_value_gain max_value_gain min_algo_gain max_algo_gain "
        "min_overall_gain max_overall_gain max_rap_gain "
        "min_rap_score_percentage max_rap_score_percentage "
        "min_overall_score_percentage max_overall_score_percentage "
        "min_value_of_trade min_rap_of_trade"
    ).split():
        setattr(checker, attr, None)
    checker.min_rap_gain = 1
    account.inbound_trader = checker
    account.config.projected_detection["Detect_Rolimons_Projecteds"] = False
    account.config.inbounds["Dont_Counter_Wins"] = True
    # 1:1 is a RAP item that sells well (volume and gap pass the filters)
    account.rolimon.projected_json.write_data(
        {
            "1:1": {
                "is_projected": False,
                "volume": 50,
                "average_gap": 0.1,
                "timestamp": 9e18,
            }
        }
    )
    account.config.filter_items.update(
        {
            "NFR": [],
            "MinDemand": None,
            "MinDailySales": 1,
            "MaxSalesGap": 5,
            "Maximum_Amount_of_Trader_Duplicate_Items": 1,
        }
    )
    account.refresh_self_inventory = lambda: None

    router.set(INBOUND_LIST, inbound_list(70))
    router.set(TRADE_URL, resp(200, inbound_trade_json(["1:2"], ["1:1"])))
    router.set(ACCEPT_URL, resp(200, {}))

    account.countered = []
    account._counter_trade = lambda trade_id, trader_id, trade=None: (
        account.countered.append(trade_id) or "countered"
    )
    return account


def accepted(router):
    return [url for method, url in router.calls if url.endswith("/accept")]


def test_format_trade_finds_our_side_when_we_are_participant_b(router, account):
    trade = account.format_trade_api(
        inbound_trade_json(["1:2"], ["1:1"], their_robux=5)
    )
    assert trade["self_id"] == 1 and trade["their_id"] == 2
    assert trade["self_side_item_ids"] == ["1:2"]
    assert trade["their_side_item_ids"] == ["1:1"]
    assert trade["their_robux"] == 5 and trade["self_robux"] == 0


def test_valid_inbound_is_accepted_not_countered(router, inbound):
    results = inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == [ACCEPT_URL + "70/accept"]
    assert inbound.countered == []
    assert results["accepted"] == 1


def test_win_is_kept_when_accepting_is_off(router, inbound):
    results = inbound.handle_inbounds(accept=False, counter=True)
    assert accepted(router) == [] and inbound.countered == []
    assert results["kept"] == 1


def test_win_that_fails_config_is_kept_not_countered(router, inbound):
    inbound.inbound_trader.min_rap_gain = 100000
    inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == [] and inbound.countered == []


def test_losing_inbound_is_countered(router, inbound):
    router.set(TRADE_URL, resp(200, inbound_trade_json(["1:1"], ["1:2"])))
    results = inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == []
    assert inbound.countered == [70] and results["countered"] == 1


def test_win_is_countered_when_dont_counter_wins_is_off(router, inbound):
    inbound.config.inbounds["Dont_Counter_Wins"] = False
    inbound.inbound_trader.min_rap_gain = 100000
    inbound.handle_inbounds(accept=True, counter=True)
    assert inbound.countered == [70]


def test_inbound_giving_projected_is_countered_not_accepted(router, inbound):
    inbound.rolimon.projected_json.write_data(
        {"1:1": {"is_projected": True, "value": 1000, "timestamp": 9e18}}
    )
    inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == [] and inbound.countered == [70]


def test_inbound_asking_for_robux_is_not_accepted(router, inbound):
    router.set(
        TRADE_URL, resp(200, inbound_trade_json(["1:2"], ["1:1"], self_robux=50))
    )
    inbound.handle_inbounds(accept=True, counter=False)
    assert accepted(router) == []


def test_inbound_with_too_many_duplicates_is_not_accepted(router, inbound):
    inbound.config.inbounds["Max_Duplicates"] = 1
    inbound.self_duplicates = {"1:1": 1}
    inbound.handle_inbounds(accept=True, counter=False)
    assert accepted(router) == []


def test_inbound_uses_its_own_duplicate_limit(router, inbound):
    # [Filtering Items] would block it, the inbound limit (2) allows it
    inbound.config.filter_items["Maximum_Amount_of_Duplicate_Items"] = 0
    inbound.config.inbounds["Max_Duplicates"] = 2
    inbound.self_duplicates = {"1:1": 1}
    inbound.handle_inbounds(accept=True, counter=False)
    assert len(accepted(router)) == 1


def with_instances(trade_json, *instance_ids):
    """Tags our side's items (participant B) with instance ids."""
    for item, uaid in zip(trade_json["participantBOffer"]["items"], instance_ids):
        item["collectibleItemInstanceId"] = uaid
    return trade_json


def two_inbounds(router, inbound, small, big):
    inbound.config.inbounds["Max_Duplicates"] = 10
    router.set(INBOUND_LIST, inbound_list(70, 71))
    router.set(TRADE_URL + "70", resp(200, small))
    router.set(TRADE_URL + "71", resp(200, big))


def test_biggest_inbound_win_is_accepted_first(router, inbound):
    two_inbounds(
        router,
        inbound,
        inbound_trade_json(["1:2"], ["1:1"]),
        inbound_trade_json(["1:2"], ["1:1", "1:1"]),
    )
    results = inbound.handle_inbounds(accept=True, counter=False)
    assert accepted(router) == [ACCEPT_URL + "71/accept", ACCEPT_URL + "70/accept"]
    assert results["accepted"] == 2


def test_inbound_needing_an_item_already_traded_is_skipped(router, inbound):
    two_inbounds(
        router,
        inbound,
        with_instances(inbound_trade_json(["1:2"], ["1:1"]), "u1"),
        with_instances(inbound_trade_json(["1:2"], ["1:1", "1:1"]), "u1"),
    )
    results = inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == [ACCEPT_URL + "71/accept"]
    assert inbound.countered == [] and results["accepted"] == 1


def test_duplicates_received_from_an_accept_count_for_the_next(router, inbound):
    two_inbounds(
        router,
        inbound,
        inbound_trade_json(["1:2"], ["1:1"]),
        inbound_trade_json(["1:2"], ["1:1", "1:1"]),
    )
    inbound.config.inbounds["Max_Duplicates"] = 1
    inbound.handle_inbounds(accept=True, counter=False)
    assert accepted(router) == [ACCEPT_URL + "71/accept"]


def test_counter_we_sent_is_judged_by_inbound_settings(account):
    from handler.counter_history import CounterHistory, trade_signature

    account.counter_history = CounterHistory(None)
    trade = {
        "their_id": 2,
        "self_side_item_ids": ["1:1"],
        "their_side_item_ids": ["1:2"],
        "self_robux": 0,
    }
    assert not account._is_our_counter(trade)
    account.counter_history.record_counter(2, trade_signature(["1:1"], ["1:2"]))
    assert account._is_our_counter(trade)


def test_accept_solves_2fa(router, inbound):
    challenge = resp(
        403,
        {"errors": [{"code": 0, "message": "anything"}]},
        headers={"rblx-challenge-id": "c"},
    )
    router.set(ACCEPT_URL, challenge, resp(200, {}))
    inbound.validate_2fa = lambda r: {"rblx-challenge-id": "c"}
    assert inbound.handle_inbounds(accept=True, counter=False)["accepted"] == 1
    assert len(accepted(router)) == 2


def test_accept_refused_by_roblox_is_not_counted(router, inbound):
    router.set(ACCEPT_URL, resp(400, {"errors": [{"code": 2, "message": "gone"}]}))
    assert inbound.handle_inbounds(accept=True, counter=False)["accepted"] == 0


def test_trade_limit_stops_countering_but_keeps_accepting(router, inbound):
    router.set(INBOUND_LIST, inbound_list(70, 71))
    router.set(
        TRADE_URL + "70",
        resp(200, inbound_trade_json(["1:1"], ["1:2"])),  # loss -> counter
    )
    router.set(TRADE_URL + "71", resp(200, inbound_trade_json(["1:2"], ["1:1"])))

    def limited(trade_id, trader_id, trade=None):
        raise E.TradeLimit(resp(429, {}))

    inbound._counter_trade = limited
    with pytest.raises(E.TradeLimit):
        inbound.handle_inbounds(accept=True, counter=True)
    assert accepted(router) == [ACCEPT_URL + "71/accept"]


# --- inbound wiring -------------------------------------------------------------


def inbound_account(account, accept, counter, effect=None):
    calls = []

    def handle_inbounds(accept, counter):
        calls.append((accept, counter))
        if effect:
            raise effect
        return {"accepted": 0, "countered": 0, "kept": 0}

    account.handle_inbounds = handle_inbounds
    account.config.inbounds["Accept_Valid_Trades"] = accept
    account.config.inbounds["CounterTrades"] = counter
    account.config.debug["dont_send_trade"] = False
    account.config.debug["ignore_limit"] = False
    return account, calls


@pytest.mark.parametrize(
    "accept, counter", [(True, True), (True, False), (False, True)]
)
def test_inbound_pass_uses_both_settings(doggo, account, accept, counter):
    acc, calls = inbound_account(account, accept, counter)
    doggo.handle_inbounds_once(acc)
    assert calls == [(accept, counter)]


def test_inbound_pass_does_nothing_when_both_off(doggo, account):
    acc, calls = inbound_account(account, False, False)
    doggo.handle_inbounds_once(acc)
    assert calls == []


def test_inbound_pass_never_runs_in_test_mode(doggo, account):
    acc, calls = inbound_account(account, True, True)
    acc.config.debug["dont_send_trade"] = True
    doggo.handle_inbounds_once(acc)
    assert calls == []


def test_inbound_trade_limit_is_recorded(doggo, account):
    acc, _ = inbound_account(account, True, True, effect=E.TradeLimit())
    doggo.handle_inbounds_once(acc)
    assert doggo.limited == ["x"]


def no_counter_account(router, inbound, decline):
    """A losing inbound where no counter passes the config."""
    del inbound._counter_trade
    inbound.config.inbounds["Decline_If_No_Counter"] = decline
    inbound.check_can_trade = lambda trader_id: True
    inbound.account_inventory = {"x": {}}
    inbound.fetch_inventory = lambda trader_id, **k: {"y": {}}
    inbound.offered_item_counts = lambda: {}
    inbound.counter_maker = types.SimpleNamespace(generate_trade=lambda *a, **k: None)
    router.set(TRADE_URL, resp(200, inbound_trade_json(["1:1"], ["1:2"])))
    router.set(DECLINE_URL, resp(200, {}))
    return inbound


def test_inbound_without_a_counter_is_declined(router, inbound, monkeypatch):
    monkeypatch.setattr("roblox_api.time.sleep", lambda s: None)
    account = no_counter_account(router, inbound, decline=True)
    results = account.handle_inbounds(accept=True, counter=True)
    assert declined(router) == [DECLINE_URL + "70/decline"]
    assert results["declined"] == 1


def test_inbound_without_a_counter_is_left_when_declining_is_off(router, inbound):
    account = no_counter_account(router, inbound, decline=False)
    results = account.handle_inbounds(accept=True, counter=True)
    assert declined(router) == [] and results["declined"] == 0


# --- inbound accepts obey the same item filters as our own trades --------------------


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda acc: acc.config.filter_items.update(NFR=["1:1"]), "Never Receive"),
        (
            lambda acc: acc.rolimon.item_data["1:1"].update(asset_type="asset:18"),
            "face",
        ),
        (
            lambda acc: acc.rolimon.item_data["1:1"].update(asset_type="asset:19"),
            "gear",
        ),
        (lambda acc: acc.config.filter_items.update(MinDemand=4), "demand"),
        (lambda acc: acc.config.filter_items.update(MinDailySales=100), "sells"),
        (lambda acc: acc.config.filter_items.update(MaxSalesGap=0.01), "gap"),
        (lambda acc: acc.rolimon.projected_json.write_data({}), "no sales data"),
    ],
)
def test_inbound_item_filters_block_accepting(router, inbound, change, reason):
    change(inbound)
    trade = inbound.format_trade_api(inbound_trade_json(["1:2"], ["1:1"]))
    assert reason in (inbound._inbound_reject_reason(trade) or "")


def test_inbound_item_filters_pass_a_good_item(router, inbound):
    trade = inbound.format_trade_api(inbound_trade_json(["1:2"], ["1:1"]))
    assert inbound._inbound_item_filter_reason(trade["their_side_item_ids"]) is None


def test_inbound_too_many_copies_from_one_trader(router, inbound):
    assert "copies" in inbound._inbound_item_filter_reason(["1:1", "1:1", "1:1"])
    assert inbound._inbound_item_filter_reason(["1:1", "1:1"]) is None


def test_valued_items_skip_sales_volume_checks(router, inbound):
    inbound.rolimon.item_data["1:2"]["value"] = 600
    inbound.rolimon.projected_json.write_data({})
    assert inbound._inbound_item_filter_reason(["1:2"]) is None


# --- config + speed fixes -------------------------------------------------------------


@pytest.mark.parametrize("typed", ["0", "-5"])
def test_bad_inbound_interval_falls_back_to_30(tmp_path, typed):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(f"[Inbound Settings]\nCheck Inbounds Every Minutes = {typed}\n")
    assert ConfigHandler(str(cfg)).inbounds["Check_Every_Minutes"] == 30


@pytest.mark.parametrize("typed", ["10m", ""])
def test_typo_in_inbound_interval_stops_startup(tmp_path, typed):
    from handler.exceptions_types import ConfigError
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(f"[Inbound Settings]\nCheck Inbounds Every Minutes = {typed}\n")
    with pytest.raises(ConfigError, match="Check Inbounds Every Minutes"):
        ConfigHandler(str(cfg))


def test_unknown_select_option_falls_back(router):
    from trade_algorithm import SELECT_TRADE_OPTIONS, TradeMaker

    assert "closest_score" not in SELECT_TRADE_OPTIONS
    maker = object.__new__(TradeMaker)
    trades = [
        {"self_rap": 1, "their_rap": 5, "demand": 1},
        {"self_rap": 1, "their_rap": 3, "demand": 1},
    ]
    maker.select_by = "closest_score"
    # generate_trade's picker falls back to the default instead of crashing
    picked = maker.select_trade(trades, select_by="lowest_rap_gain")
    assert picked in trades


def test_read_cached_reuses_until_the_file_changes(tmp_path, monkeypatch):
    from handler.handle_json import JsonHandler

    monkeypatch.chdir(tmp_path)
    jh = JsonHandler("p.json")
    jh.write_data({"a": 1})
    first = jh.read_cached()
    assert jh.read_cached() is first  # no re-read
    jh.write_data({"a": 2})
    assert jh.read_cached() == {"a": 2}  # a write is seen immediately
    other = JsonHandler("p.json")  # another handler for the same file
    other.write_data({"a": 3})
    assert jh.read_cached() == {"a": 3}


def test_valued_item_algo_setting_survives_scan_data(router):
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    rol.item_data["1:2"].update(value=600, total_value=600)
    rol.projected_json.write_data(
        {
            "1:2": {
                "is_projected": False,
                "value": 999,
                "volume": 50,
                "average_gap": 0.1,
                "timestamp": __import__("time").time(),
                "last_price": rol.item_data["1:2"]["best_price"],
            }
        }
    )
    for mode, expected in [
        ("rolimon_value", 600),
        ("zero_value", 0),
        ("rap_algo", 999),
    ]:
        rol.config.trading["Rap_Algo_For_Valued"] = mode
        out = rol.add_data_to_inventory(
            {"u": {"item_id": "1:2", "collectibleItemId": "c"}}, is_self=True
        )
        assert out["u"]["rap_algorithm"] == expected, mode


# --- no accounts -> account manager ---------------------------------------------------


@pytest.mark.parametrize(
    "saved, expected",
    [
        ([], "option 1 (Firefox) or 2 (Manual)"),
        ([{"use_account": False}], "option 4"),
        ([{"use_account": True}], "add the account again"),
    ],
)
def test_no_accounts_opens_account_manager(doggo, monkeypatch, saved, expected):
    import main

    shown, opened = [], []
    doggo.json = types.SimpleNamespace(read_data=lambda: {"roblox_accounts": saved})
    doggo.cli = types.SimpleNamespace(print_error=shown.append)
    doggo.load_roblox_accounts = lambda: []
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(
        main,
        "AccountManager",
        lambda: types.SimpleNamespace(main=lambda: opened.append(1)),
    )
    doggo.start_trader()
    assert opened == [1]
    assert expected in shown[0]


# --- preset configs ------------------------------------------------------------------

PRESETS = sorted(
    p
    for p in os.listdir(os.path.join(os.path.dirname(__file__), "..", "configs"))
    if p.endswith(".cfg")
)


def preset_path(name):
    return os.path.join(os.path.dirname(__file__), "..", "configs", name)


@pytest.mark.parametrize("name", PRESETS)
def test_preset_loads_without_unreadable_values(name):
    from handler.handle_config import ConfigHandler

    config = ConfigHandler(preset_path(name))  # validate_config runs here
    for section in [
        "scan_items",
        "filter_users",
        "filter_items",
        "filter_generated",
        "trading",
        "debug",
        "inbounds",
        "outbound",
        "projected_detection",
    ]:
        for key, value in getattr(config, section).items():
            assert value != "Not Set", f"{name}: {section}.{key} can't be read"


@pytest.mark.parametrize("name", PRESETS)
def test_every_preset_setting_is_read_by_the_bot(name):
    """A setting in the wrong section (or one the code never reads) does nothing."""
    import configparser
    import inspect

    from handler import handle_config

    # Everything but the old -> new name map (it would match itself)
    source = inspect.getsource(handle_config).replace(
        inspect.getsource(handle_config._layout), ""
    )
    used = {(s.lower(), o.lower()) for s, o in re.findall(r'"([^"]+)",\s*"([^"]+)"', source)}
    raw = configparser.ConfigParser(interpolation=None)
    raw.optionxform = str
    raw.read(preset_path(name))
    for section in raw.sections():
        if section == "Info":
            continue
        for key in raw[section]:
            # New names ([Profit] Min Overall Profit) are read through the old ones
            old = handle_config.OLD_NAMES.get((section.lower(), key.lower()))
            read_as = (old[0].lower(), old[1].lower()) if old else (section.lower(), key.lower())
            assert read_as in used, f"{name}: [{section}] {key} isn't read by the bot"


def test_nft_and_nfr_accept_plain_item_ids(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text("[Filtering Items]\nNFT = 1029025, 2:939596\nNFR = None\n")
    config = ConfigHandler(str(cfg))
    assert config.filter_items["NFT"] == ["1029025", "939596"]
    assert config.filter_items["NFR"] == []


@pytest.mark.parametrize(
    "sales, gap, kept", [(None, None, True), (100, None, False), (None, 0.01, False)]
)
def test_sales_limits_none_means_no_limit(router, sales, gap, kept):
    from rolimons_api import RolimonAPI

    rol = RolimonAPI()
    rol.config.filter_items.update(MinDailySales=sales, MaxSalesGap=gap)
    rol.projected_json.write_data(
        {
            "1:1": {
                "is_projected": False,
                "value": 1000,
                "volume": 2,
                "average_gap": 1,
                "timestamp": __import__("time").time(),
                "last_price": rol.item_data["1:1"]["best_price"],
            }
        }
    )
    out = rol.add_data_to_inventory({"u": {"item_id": "1:1", "collectibleItemId": "c"}})
    assert bool(out) is kept


@pytest.mark.parametrize(
    "line, expected",
    [
        (
            "[Filtering Items]\nMaximum Amount of Duplicate Items = None\n",
            "[Filtering Items] Maximum Amount of Duplicate Items (must be a whole number)",
        ),
        (
            "[Trading Settings]\nMinimum RAP Gain = 3oo\n",
            "[Trading Settings] Minimum RAP Gain (must be a number or None)",
        ),
        (
            "[debug]\nDont Send Trades = yes please\n",
            "[debug] Dont Send Trades (must be True or False)",
        ),
    ],
)
def test_invalid_settings_stop_startup_with_their_real_name(tmp_path, line, expected):
    from handler.exceptions_types import ConfigError
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(line)
    with pytest.raises(ConfigError) as info:
        ConfigHandler(str(cfg))
    assert expected in str(info.value)


# --- projected detection: Max Price Rise / Drop settings --------------------------------


@pytest.mark.parametrize(
    "past, max_rise, max_drop, projected",
    [
        (5_999, 0.4, -0.4, True),  # typical price more than 40% below today
        (6_001, 0.4, -0.4, False),
        (14_001, 0.4, -0.4, True),  # price crashed since
        (14_001, 0.4, None, False),  # crash check off
        (5_999, None, -0.4, False),  # spike check off
        (8_999, 1000, -1000, True),  # Robux: more than 1,000 below today
        (9_001, 1000, -1000, False),
        (11_001, 1000, -1000, True),  # Robux: more than 1,000 above today
    ],
)
def test_graph_difference_settings(past, max_rise, max_drop, projected):
    from roblox_api import price_swing_is_projected

    assert price_swing_is_projected(10_000, past, max_rise, max_drop) is projected


@pytest.mark.parametrize(
    "lines, expected",
    [
        ("", (0.35, -0.35)),  # missing -> today's default
        (
            "Maximum Graph Difference = 0.25\nMinimum Graph Difference = None\n",
            (0.25, None),
        ),
        (
            "Maximum Graph Difference = 1000\nMinimum Graph Difference = -1000\n",
            (1000, -1000),
        ),
    ],
)
def test_graph_difference_config(tmp_path, lines, expected):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text("[Projected Detection]\n" + lines)
    p = ConfigHandler(str(cfg)).projected_detection
    assert (p["MaximumGraphDifference"], p["MinimumGraphDifference"]) == expected


# --- Outbound Variety -------------------------------------------------------------


def variety_maker(variety):
    from trade_algorithm import TradeMaker

    maker = object.__new__(TradeMaker)
    maker.outbound_variety = variety
    return maker


VARIETY_TRADES = [
    {"self_side": ("a", "b")},  # offered 3 + 2 = 5
    {"self_side": ("a",)},  # 3
    {"self_side": ("c",)},  # 0
    {"self_side": ("b", "d")},  # 2
]
OFFERED = {"a": 3, "b": 2}


@pytest.mark.parametrize(
    "variety, kept",
    [
        (0, [0, 1, 2, 3]),
        (None, [0, 1, 2, 3]),
        (0.5, [2, 3]),  # counts run 0..5, keep 2.5 or less
        (0.4, [1, 2, 3]),  # keep 3 or less
        (1, [2]),
    ],
)
def test_outbound_variety_drops_the_most_offered_trades(variety, kept):
    result = variety_maker(variety).prefer_unoffered(VARIETY_TRADES, OFFERED)
    assert result == [VARIETY_TRADES[i] for i in kept]


def test_outbound_variety_with_nothing_offered_keeps_everything():
    maker = variety_maker(1)
    assert maker.prefer_unoffered(VARIETY_TRADES, {}) == VARIETY_TRADES
    assert maker.prefer_unoffered(VARIETY_TRADES, None) == VARIETY_TRADES


def test_generate_trade_avoids_items_already_in_outbounds():
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    maker = TradeMaker(ConfigHandler("configs/small_value.cfg"))
    for name in (
        "min_rap_gain max_rap_gain min_overall_gain max_overall_gain min_algo_gain "
        "max_algo_gain min_value_gain max_value_gain min_rap_score_percentage "
        "max_rap_score_percentage min_overall_score_percentage "
        "max_overall_score_percentage max_valid_trades"
    ).split():
        setattr(maker, name, None)
    maker.min_value_of_trade = maker.min_rap_of_trade = 0
    maker.min_items_self = maker.min_items_their = 1
    maker.max_items_self = 1
    maker.max_items_their = 2
    maker.trade_robux = False
    maker.trade_timeout = 10
    maker.select_by = "highest_overall_gain"

    def item(item_id, value):
        return {
            "item_id": item_id,
            "value": value,
            "rap": value,
            "demand": 2,
            "rap_algorithm": value,
            "total_value": value,
            "item_volume": 5,
        }

    mine = {"uaid-big": item("10", 1000), "uaid-small": item("11", 900)}
    theirs = {"x": item("20", 1500), "y": item("21", 100)}

    maker.outbound_variety = 0
    best = maker.generate_trade(mine, theirs, offered={"uaid-big": 4})
    assert best["self_side"] == ("uaid-small",)  # 900 for 1600 is the biggest gain

    maker.outbound_variety = 1
    spread = maker.generate_trade(mine, theirs, offered={"uaid-small": 4})
    assert spread["self_side"] == ("uaid-big",)


def outbound_json(trade_id, mine, theirs, my_id=1):
    def offer(user, uaids):
        return {
            "user": {"id": user},
            "items": [{"collectibleItemInstanceId": u} for u in uaids],
        }

    # Roblox doesn't promise which side is ours
    return {
        "id": trade_id,
        "participantAOffer": offer(2, theirs),
        "participantBOffer": offer(my_id, mine),
    }


def test_offered_item_counts_uses_cached_outbounds_and_new_sends(account):
    account.outbound_cache = {
        1: cached(outbound_json(1, ["u1", "u2"], ["t1"])),
        2: cached(outbound_json(2, ["u1"], ["u2"])),  # their u2 isn't ours
    }
    account.note_sent_trade(["u1", "u3"])
    assert account.offered_item_counts() == {"u1": 3, "u2": 1, "u3": 1}


def test_offered_item_counts_forgets_sends_older_than_a_day(account):
    import time as _time

    account.sent_since_check = [(_time.time() - 2 * 86400, ["old"])]
    account.note_sent_trade(["new"])
    assert account.offered_item_counts() == {"new": 1}


def test_send_trade_counts_the_items_it_sent(router, account):
    router.set(SEND, resp(200, {"tradeId": 77}))
    account.send_trade(2, ["a", "b"], ["c"])
    assert account.offered_item_counts() == {"a": 1, "b": 1}


def test_outbound_check_drops_sends_it_now_has_cached(router, outbound):
    import time as _time

    outbound.sent_since_check = [(_time.time() - 60, ["seen"])]
    router.set("https://trades.roblox.com/v1/trades/outbound", outbound_list())
    outbound.outbound_api_checker()
    assert outbound.sent_since_check == []


@pytest.mark.parametrize(
    "line, expected",
    [("", 0.0), ("Outbound Variety = None", 0.0), ("Outbound Variety = 0.7", 0.7)],
)
def test_outbound_variety_config(tmp_path, line, expected):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(f"[Filtering Generated Trades]\n{line}\n")
    assert ConfigHandler(str(cfg)).filter_generated["Outbound_Variety"] == expected


@pytest.mark.parametrize("typed", ["2", "-0.1", "lots"])
def test_bad_outbound_variety_stops_startup(tmp_path, typed):
    from handler.exceptions_types import ConfigError
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(f"[Filtering Generated Trades]\nOutbound Variety = {typed}\n")
    with pytest.raises(ConfigError, match="Outbound Variety"):
        ConfigHandler(str(cfg))


# --- notes/TODO cleanup fixes ------------------------------------------------------


def test_outbound_algo_gain_follows_valued_item_setting(router, account):
    # Outbound checks must work out RAP Algorithm the same way trades are made
    account.rolimon.projected_json.write_data({"1:2": {"value": 999}})
    for mode, expected in [
        ("rolimon_value", 600),
        ("zero_value", 0),
        ("rap_algo", 999),
    ]:
        account.config.trading["Rap_Algo_For_Valued"] = mode
        _rap, _value, algo, _overall = account.calculate_gains(["1:2"])
        assert algo == expected, mode


def test_webhook_lists_duplicate_items_twice(router):
    from handler.handle_discord import DiscordHandler
    from rolimons_api import RolimonAPI

    trade = {
        "self_side_item_ids": ["1:1", "1:1"],
        "their_side_item_ids": ["1:2"],
        "self_robux": 0,
        "their_rap": 500,
        "their_value": 600,
        "their_rap_algo": 500,
        "their_overall_value": 600,
        "self_rap": 2000,
        "self_value": 0,
        "self_rap_algo": 2000,
        "self_overall_value": 2000,
    }
    fields, _profit = DiscordHandler().embed_fields_from_trade(
        trade, RolimonAPI().item_data, {}
    )
    assert str(fields["Send"]).count("Hat") == 2


def resale_points(prices, start=None):
    import datetime as dt

    start = start or dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0)
    return [
        {
            "value": p,
            "date": (start - dt.timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for i, p in enumerate(prices)
    ]


def test_no_sale_days_dont_make_an_item_projected(router, account):
    # A day with no sales comes back as price 0; it isn't a 100% price swing
    prices = [1000, 1010, 0, 990, 1005, 0, 1000, 995, 1008, 1000]
    router.set(
        "https://apis.roblox.com/marketplace-sales",
        resp(
            200,
            {
                "priceDataPoints": resale_points(prices),
                "volumeDataPoints": resale_points([3] * len(prices)),
            },
        ),
    )
    account.parse_handler = account.request_handler
    account.config.projected_detection["Detect_Rolimons_Projecteds"] = False
    account.is_projected_api(collectibleId="c", item_id="1:1")
    saved = account.rolimon.projected_json.read_data()["1:1"]
    assert saved["is_projected"] is False
    assert saved["value"] > 900  # the 0 days aren't counted as price dips


@pytest.mark.parametrize(
    "prices, projected",
    [
        # newest first: a one-day spike weeks ago that went back to normal
        ([181, 185, 178, 190, 700, 182, 180, 184, 179, 183], False),
        # today's price is way above what it usually sells for
        ([700, 185, 178, 190, 182, 180, 184, 179, 183, 181], True),
        # crashed: today is far below what it usually sells for, RAP still high
        ([90, 185, 178, 190, 182, 180, 184, 179, 183, 181], True),
    ],
)
def test_projected_compares_today_with_typical_price(router, account, prices, projected):
    account.rolimon.item_data["1:1"]["rap"] = 180
    router.set(
        "https://apis.roblox.com/marketplace-sales",
        resp(
            200,
            {
                "priceDataPoints": resale_points(prices),
                "volumeDataPoints": resale_points([3] * len(prices)),
            },
        ),
    )
    account.parse_handler = account.request_handler
    account.config.projected_detection.update(
        Detect_Rolimons_Projecteds=False, MaximumGraphDifference=0.4, MinimumGraphDifference=-0.4
    )
    account.is_projected_api(collectibleId="c", item_id="1:1")
    assert account.rolimon.projected_json.read_data()["1:1"]["is_projected"] is projected


def test_price_drop_settled_when_rap_followed_it(router, account):
    # Sold ~270 for months, now 186 and RAP came down to 181: not projected
    prices = [186, 190, 185] + [270] * 10
    router.set(
        "https://apis.roblox.com/marketplace-sales",
        resp(200, {"priceDataPoints": resale_points(prices),
                   "volumeDataPoints": resale_points([3] * len(prices))}),
    )
    account.parse_handler = account.request_handler
    account.config.projected_detection.update(
        Detect_Rolimons_Projecteds=False, MaximumGraphDifference=0.4, MinimumGraphDifference=-0.4
    )
    account.rolimon.item_data["1:1"]["rap"] = 181
    account.is_projected_api(collectibleId="c", item_id="1:1")
    assert account.rolimon.projected_json.read_data()["1:1"]["is_projected"] is False
    account.rolimon.item_data["1:1"]["rap"] = 270  # RAP still up there
    account.is_projected_api(collectibleId="c", item_id="1:1")
    assert account.rolimon.projected_json.read_data()["1:1"]["is_projected"] is True


def test_typical_price_is_the_median():
    from roblox_api import typical_price

    assert typical_price([100, 900, 110]) == 110
    assert typical_price([100, 120]) == 110
    assert typical_price([]) is None


def test_items_are_rescanned_after_2_days(router, monkeypatch):
    import time as _time

    import roblox_api
    from rolimons_api import RolimonAPI

    scans = []

    class FakeRoblox:
        def is_projected_api(self, item_id, collectibleId):
            scans.append(item_id)

    monkeypatch.setattr(roblox_api, "RobloxAPI", FakeRoblox)
    rol = RolimonAPI()
    for days_old, rescanned in [(1.5, False), (2.5, True)]:
        scans.clear()
        rol.projected_json.write_data(
            {
                "1:1": {
                    "is_projected": False,
                    "value": 900,
                    "volume": 5,
                    "average_gap": 1,
                    "timestamp": _time.time() - days_old * 86400,
                    "last_price": rol.item_data["1:1"]["best_price"],
                }
            }
        )
        rol.add_data_to_inventory(
            {"u": {"item_id": "1:1", "collectibleItemId": "c"}}, is_self=True
        )
        assert bool(scans) is rescanned, days_old


# --- RAP Algorithm split + Robux in gains --------------------------------------------


def test_rap_algorithm_is_the_same_whichever_order_the_data_comes_in():
    from handler.price_algorithm import SalesVolumeAnalyzer

    day = 86400
    # Price rises over time, with a dip every other day
    sales = [{"value": 100 + i + (i % 2) * 20, "date": i * day} for i in range(90)]
    volume = [{"value": 3 + (i % 2) * 4, "date": i * day} for i in range(90)]
    newest_first = SalesVolumeAnalyzer(sales[::-1], volume[::-1], "x").process()
    oldest_first = SalesVolumeAnalyzer(sales, volume, "x").process()
    assert newest_first["value"] == oldest_first["value"]
    assert newest_first["volume"] == oldest_first["volume"]


def test_rap_algorithm_splits_history_into_even_thirds():
    from handler.price_algorithm import SalesVolumeAnalyzer

    day = 86400
    points = [{"value": 100 + (i % 2) * 10, "date": i * day} for i in range(90)]
    analyzer = SalesVolumeAnalyzer(points[::-1], [], "x")
    lows, _ = analyzer.find_extrema(analyzer.sales_data)
    assert [len(s) for s in analyzer.segment_data(lows)] == [15, 14, 15]


def loose_maker(**settings):
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    maker = TradeMaker(ConfigHandler("configs/small_value.cfg"))
    for name in (
        "min_rap_gain max_rap_gain min_overall_gain max_overall_gain min_algo_gain "
        "max_algo_gain min_value_gain max_value_gain min_rap_score_percentage "
        "max_rap_score_percentage min_overall_score_percentage "
        "max_overall_score_percentage"
    ).split():
        setattr(maker, name, None)
    maker.min_value_of_trade = maker.min_rap_of_trade = 0
    for name, value in settings.items():
        setattr(maker, name, value)
    return maker


def rap_trade(maker, robux=None, their_robux=None):
    return maker.validate_trade(
        self_rap=1000,
        self_rap_algo=1000,
        self_value=0,
        self_overall_value=1000,
        their_rap=1700,
        their_rap_algo=1700,
        their_value=0,
        their_overall_value=1700,
        robux=robux,
        their_robux=their_robux,
    )


@pytest.mark.parametrize(
    "setting", ["min_rap_gain", "min_overall_gain", "min_algo_gain"]
)
def test_robux_you_add_counts_against_your_gains(setting):
    maker = loose_maker(**{setting: 600})
    assert rap_trade(maker)[0]  # +700
    assert rap_trade(maker, robux=50)[0]  # +650
    assert not rap_trade(maker, robux=200)[0]  # +500


def test_robux_they_add_counts_for_you():
    maker = loose_maker(min_rap_gain=800)
    assert not rap_trade(maker)[0]
    assert rap_trade(maker, their_robux=150)[0]


def test_robux_doesnt_count_toward_value_gain():
    maker = loose_maker(min_value_gain=1)
    assert not rap_trade(maker, their_robux=5000)[0]


def test_webhook_profit_includes_robux():
    from handler.handle_discord import DiscordHandler

    trade = {
        "their_rap": 1700,
        "their_value": 0,
        "their_rap_algo": 1700,
        "their_overall_value": 1700,
        "self_rap": 1000,
        "self_value": 0,
        "self_rap_algo": 1000,
        "self_overall_value": 1000,
        "self_robux": 200,
    }
    total, algo, rap, value = DiscordHandler().trade_profit(trade)
    assert (total, algo, rap, value) == (500, 500, 500, 0)


# --- Rolimons trade ads ----------------------------------------------------------------


class FakeAdSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []

    def post(self, url, json=None, cookies=None, timeout=None):
        self.sent.append({"url": url, "json": json, "cookies": cookies})
        answer = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def ad_response(body, status=200):
    if isinstance(body, str):
        return resp(status, text=body)
    return resp(status, body)


AD_INVENTORY = {
    "u1": {"item_id": "1:10", "total_value": 500},
    "u2": {"item_id": "1:11", "total_value": 9000},
    "u3": {"item_id": "1:11", "total_value": 9000},  # a second copy
    "u4": {"item_id": "2:12", "total_value": 99999},  # bundle, can't be listed
    "u5": {"item_id": "1:13", "total_value": 3000},
}


@pytest.mark.parametrize(
    "pick, count, expected",
    [
        ("highest_value", 2, [11, 13]),
        ("lowest_value", 2, [10, 13]),
        ("highest_value", 4, [11, 13, 10]),
    ],
)
def test_pick_offer_items(pick, count, expected):
    from handler.handle_trade_ads import pick_offer_items

    assert pick_offer_items(AD_INVENTORY, count, pick) == expected


def test_pick_offer_items_random_lists_each_item_once():
    from handler.handle_trade_ads import pick_offer_items

    picked = pick_offer_items(AD_INVENTORY, 4, "random")
    assert sorted(picked) == [10, 11, 13]


def test_post_trade_ad_sends_the_cookie_and_ad():
    from handler.handle_trade_ads import build_ad, post_trade_ad

    session = FakeAdSession(ad_response({"success": True}))
    ad = build_ad("55", [11, 13], [], ["any", "upgrade"])
    post_trade_ad("roli-cookie", ad, session)
    sent = session.sent[0]
    assert sent["url"] == "https://api.rolimons.com/tradeads/v1/createad"
    assert sent["cookies"] == {"_RoliVerification": "roli-cookie"}
    assert sent["json"] == {
        "player_id": 55,
        "offer_item_ids": [11, 13],
        "request_item_ids": [],
        "request_tags": ["any", "upgrade"],
    }


@pytest.mark.parametrize(
    "answer, error",
    [
        (
            ad_response(
                {"success": False, "code": 5, "message": "Invalid verification data"},
                401,
            ),
            "RolimonsCookieInvalid",
        ),
        (
            ad_response(
                {"success": False, "code": 4, "message": "Missing verification cookie"},
                401,
            ),
            "RolimonsCookieInvalid",
        ),
        (
            ad_response({"success": False, "code": 7, "message": "Too soon"}, 429),
            "TradeAdRejected",
        ),
        (ad_response("<html>down</html>", 502), "RolimonsError"),
        (requests.ConnectionError("no route"), "NetworkError"),
    ],
)
def test_post_trade_ad_errors(answer, error):
    from handler.handle_trade_ads import build_ad, post_trade_ad

    with pytest.raises(getattr(E, error)):
        post_trade_ad("c", build_ad(1, [10], [], ["any"]), FakeAdSession(answer))


AD_SETTINGS = {
    "Enabled": True,
    "Post_Every_Minutes": 20,
    "Offer_Items": 2,
    "Offer_Items_Using": "highest_value",
    "Request_Items": [],
    "Request_Tags": ["any"],
}


def ad_account(account_id, cookie, inventory=AD_INVENTORY):
    return types.SimpleNamespace(
        account_id=account_id,
        username=f"acc{account_id}",
        rolimons_cookie=cookie,
        account_inventory=inventory,
    )


def test_trade_ad_poster_posts_on_schedule():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(ad_response({"success": True}))
    poster = TradeAdPoster(AD_SETTINGS, session)
    accounts = [
        ad_account(1, "c1"),
        ad_account(2, None),  # no cookie: skipped
        ad_account(3, "c3", inventory=None),  # inventory not loaded yet
    ]
    assert poster.run_once(accounts, now=0) == 1
    assert poster.run_once(accounts, now=19 * 60) == 0  # not due yet
    assert poster.run_once(accounts, now=20 * 60) == 1
    assert [s["cookies"]["_RoliVerification"] for s in session.sent] == ["c1", "c1"]


def test_trade_ad_poster_stops_on_a_refused_cookie():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(
        ad_response(
            {"success": False, "code": 5, "message": "Invalid verification data"}, 401
        )
    )
    poster = TradeAdPoster(AD_SETTINGS, session)
    accounts = [ad_account(1, "bad")]
    assert poster.run_once(accounts, now=0) == 0
    assert poster.run_once(accounts, now=10_000) == 0
    assert len(session.sent) == 1


def test_trade_ad_poster_retries_after_other_errors():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(
        ad_response({"success": False, "code": 7, "message": "Too soon"}, 429),
        ad_response({"success": True}),
    )
    poster = TradeAdPoster(AD_SETTINGS, session)
    accounts = [ad_account(1, "c1")]
    assert poster.run_once(accounts, now=0) == 0
    assert poster.run_once(accounts, now=20 * 60) == 1


def test_trade_ads_config_defaults(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text("[Trade Ads]\n")
    assert ConfigHandler(str(cfg)).trade_ads == {
        "Enabled": False,
        "Auto_Rolimons_Login": True,
        "Post_Every_Minutes": 20,
        "Offer_Items": 4,
        "Offer_Items_Using": "highest_value",
        "Offer_Item_IDs": [],
        "Request_Items": [],
        "Request_Tags": ["any"],
    }


def test_trade_ads_config_reads_items_and_tags(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(
        "[Trade Ads]\nEnabled = True\nOffer Items Using = Random\n"
        "Request Item IDs = 1:1029025, 1191135761\nRequest Tags = Upgrade, adds\n"
    )
    ads = ConfigHandler(str(cfg)).trade_ads
    assert ads["Enabled"] is True
    assert ads["Offer_Items_Using"] == "random"
    assert ads["Request_Items"] == [1029025, 1191135761]
    assert ads["Request_Tags"] == ["upgrade", "adds"]


@pytest.mark.parametrize(
    "lines, named",
    [
        ("Post Every Minutes = 5", "Post Every Minutes"),
        ("Offer Items = 5", "Offer Items"),
        ("Offer Items Using = best", "Offer Items Using"),
        ("Request Tags = any, cheap", "Request Tags"),
        ("Request Item IDs = hat", "Request Item IDs"),
        ("Request Item IDs = 1, 2, 3\nRequest Tags = any, adds", "Request Item IDs"),
        ("Offer Item IDs = 1, 2, 3, 4, 5", "Offer Item IDs"),
        ("Enabled = True\nOffer Items Using = manual", "Offer Item IDs"),
        ("Enabled = True\nRequest Tags = None", "Request Tags"),
    ],
)
def test_bad_trade_ads_settings_stop_startup(tmp_path, lines, named):
    from handler.exceptions_types import ConfigError
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(f"[Trade Ads]\n{lines}\n")
    with pytest.raises(ConfigError, match=named):
        ConfigHandler(str(cfg))


def test_rolimons_cookie_is_saved_by_user_id(tmp_path, monkeypatch):
    from handler.handle_json import JsonHandler

    monkeypatch.chdir(tmp_path)
    store = JsonHandler("cookies.json")
    store.write_data({"roblox_accounts": [{"user_id": 7, "cookie": "x"}]})
    assert store.save_rolimons_cookie_for("7", "roli")
    assert store.read_data()["roblox_accounts"][0]["rolimons_cookie"] == "roli"
    assert not store.save_rolimons_cookie_for(8, "roli")


def test_trade_ad_poster_logs_in_again_on_a_refused_cookie():
    from handler.handle_trade_ads import TradeAdPoster

    refused = ad_response(
        {"success": False, "code": 5, "message": "Invalid verification data"}, 401
    )
    session = FakeAdSession(refused, ad_response({"success": True}))
    logins = []

    def login(account):
        logins.append(account.account_id)
        account.rolimons_cookie = "new"
        return True

    poster = TradeAdPoster(AD_SETTINGS, session, login=login)
    accounts = [ad_account(1, "old")]
    assert poster.run_once(accounts, now=0) == 0
    assert poster.run_once(accounts, now=60) == 1
    assert logins == [1]
    assert [s["cookies"]["_RoliVerification"] for s in session.sent] == ["old", "new"]


def test_trade_ad_poster_logs_in_at_most_once_an_hour():
    from handler.handle_trade_ads import TradeAdPoster

    refused = ad_response(
        {"success": False, "code": 5, "message": "Invalid verification data"}, 401
    )
    session = FakeAdSession(refused)
    logins = []
    poster = TradeAdPoster(
        AD_SETTINGS, session, login=lambda a: logins.append(1) or True
    )
    accounts = [ad_account(1, "bad")]
    for minute in range(5):
        poster.run_once(accounts, now=minute * 60)
    assert logins == [1]
    assert poster.run_once(accounts, now=10_000) == 0  # given up on


class FakeOAuthHandler:
    def __init__(self, location):
        self.location = location
        self.sent = []

    def requestAPI(self, url, method="get", payload=None, additional_headers=None):
        self.sent.append((url, method, payload))
        return types.SimpleNamespace(json=lambda: {"location": self.location})


class FakeRolimonsSession:
    def __init__(self, cookies):
        self.cookies = cookies
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return types.SimpleNamespace(status_code=302, cookies=self.cookies)


def test_rolimons_login_gets_the_cookie_through_roblox_oauth():
    from handler.rolimons_login import AUTHORIZE_URL, CLIENT_ID, rolimons_login

    link = "https://api.rolimons.com/auth/v1/robloxoauth?code=abc"
    roblox = FakeOAuthHandler(link)
    rolimons = FakeRolimonsSession({"_RoliVerification": "roli"})
    assert rolimons_login(roblox, 7, rolimons) == "roli"
    url, method, body = roblox.sent[0]
    assert (url, method) == (AUTHORIZE_URL, "post")
    assert body["clientId"] == CLIENT_ID
    assert body["resourceInfos"][0]["owner"] == {"id": "7", "type": "User"}
    assert rolimons.urls == [link]


@pytest.mark.parametrize(
    "location, cookies",
    [
        ("https://evil.example/?code=abc", {"_RoliVerification": "roli"}),
        ("https://api.rolimons.com/auth/v1/robloxoauth?code=abc", {}),
    ],
)
def test_rolimons_login_errors(location, cookies):
    from handler.rolimons_login import rolimons_login

    with pytest.raises(E.RolimonsError):
        rolimons_login(FakeOAuthHandler(location), 7, FakeRolimonsSession(cookies))


def ad_outbound(trade_id, mine, theirs, my_id=1):
    def offer(user, ids):
        return {
            "user": {"id": user},
            "items": [
                {"itemTarget": {"itemType": t, "targetId": str(i)}} for t, i in ids
            ],
        }

    return {
        "json": {
            "participantAOffer": offer(2, theirs),
            "participantBOffer": offer(my_id, mine),
        }
    }


def outbound_ad_account(cache, inventory=AD_INVENTORY):
    account = ad_account(1, "c1", inventory)
    account.outbound_cache = cache
    return account


def posted(session):
    return [
        (
            s["json"]["offer_item_ids"],
            s["json"]["request_item_ids"],
            s["json"]["request_tags"],
        )
        for s in session.sent
    ]


def test_outbound_ads_take_turns_through_open_outbounds():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(ad_response({"success": True}))
    settings = dict(
        AD_SETTINGS,
        Offer_Items_Using="outbound",
        Request_Items=[999],  # ignored: outbound asks for their items
        Request_Tags=["any", "upgrade", "adds"],
    )
    poster = TradeAdPoster(settings, session)
    account = outbound_ad_account(
        {
            101: ad_outbound(101, [("Asset", 10)], [("Asset", 20), ("Asset", 21)]),
            # bundles can't be listed, and their side has nothing else: skipped
            102: ad_outbound(102, [("Asset", 11)], [("Bundle", 30)]),
            103: ad_outbound(103, [("Asset", 13), ("Asset", 13)], [("Asset", 22)]),
        }
    )
    for minute in (0, 20, 40):
        poster.run_once([account], now=minute * 60)
    assert posted(session) == [
        ([10], [20, 21], ["any", "upgrade"]),  # tags fill the 2 slots left
        ([13], [22], ["any", "upgrade", "adds"]),
        ([10], [20, 21], ["any", "upgrade"]),  # every outbound had a turn
    ]


def test_outbound_ads_fall_back_to_highest_value_without_outbounds():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(ad_response({"success": True}))
    poster = TradeAdPoster(dict(AD_SETTINGS, Offer_Items_Using="outbound"), session)
    poster.run_once([outbound_ad_account({})], now=0)
    assert posted(session) == [([11, 13], [], ["any"])]


def test_manual_ads_list_only_items_you_own():
    from handler.handle_trade_ads import TradeAdPoster

    session = FakeAdSession(ad_response({"success": True}))
    settings = dict(
        AD_SETTINGS,
        Offer_Items_Using="manual",
        Offer_Item_IDs=[13, 777, 10],  # 777 isn't owned
        Request_Items=[555],
        Request_Tags=["any"],
    )
    TradeAdPoster(settings, session).run_once([ad_account(1, "c1")], now=0)
    assert posted(session) == [([13, 10], [555], ["any"])]


def test_trade_ads_config_reads_manual_offer_ids(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(
        "[Trade Ads]\nEnabled = True\nOffer Items Using = manual\n"
        "Offer Item IDs = 1:10, 13\n"
    )
    ads = ConfigHandler(str(cfg)).trade_ads
    assert ads["Offer_Items_Using"] == "manual"
    assert ads["Offer_Item_IDs"] == [10, 13]


def test_outbound_ads_need_no_request_settings(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(
        "[Trade Ads]\nEnabled = True\nOffer Items Using = outbound\nRequest Tags = None\n"
    )
    assert ConfigHandler(str(cfg)).trade_ads["Request_Tags"] == []


# --- version ---------------------------------------------------------------------------


def test_version_strings(monkeypatch):
    import version

    monkeypatch.setattr(version, "VERSION", "2.0")
    monkeypatch.setattr(version, "edition", lambda: "")
    monkeypatch.setattr(version, "STAGE", "BETA")
    assert version.full_version() == "2.0 (BETA)"
    assert version.release_tag() == "v2.0-beta"
    monkeypatch.setattr(version, "STAGE", "")
    assert version.full_version() == "2.0"
    assert version.release_tag() == "v2.0"
    monkeypatch.setattr(version, "edition", lambda: "-community")
    assert version.release_tag() == "v2.0-community"


# --- packaged build -------------------------------------------------------------------


@pytest.mark.parametrize(
    "env, expected",
    [
        # User had their own LD_LIBRARY_PATH: put it back
        ({"LD_LIBRARY_PATH": "/bundle", "LD_LIBRARY_PATH_ORIG": "/mine"}, "/mine"),
        # User had none: remove the bundle's
        ({"LD_LIBRARY_PATH": "/bundle"}, None),
    ],
)
def test_packaged_build_gives_child_programs_the_users_library_path(env, expected):
    from handler.startup import restore_child_library_path

    restore_child_library_path(env, frozen=True)
    assert env.get("LD_LIBRARY_PATH") == expected


def test_library_path_is_left_alone_when_running_from_source():
    from handler.startup import restore_child_library_path

    env = {"LD_LIBRARY_PATH": "/mine"}
    restore_child_library_path(env, frozen=False)
    assert env == {"LD_LIBRARY_PATH": "/mine"}


# --- adding an account by cookie --------------------------------------------------------

TOKEN = "ABC123TOKEN"


@pytest.mark.parametrize(
    "pasted, expected",
    [
        # With Roblox's warning text: used as-is
        (
            "_|WARNING:-DO-NOT-SHARE-THIS.--x.|_" + TOKEN,
            ["_|WARNING:-DO-NOT-SHARE-THIS.--x.|_" + TOKEN],
        ),
        # Without it: the standard warning is added first, then the raw cookie
        (TOKEN, ["STD" + TOKEN, TOKEN]),
        # Pasted with the name, quotes, spaces or a trailing ;
        (f'  .ROBLOSECURITY="{TOKEN}";  ', ["STD" + TOKEN, TOKEN]),
        ("   ", []),
    ],
)
def test_cookie_candidates(pasted, expected):
    import account_manager

    std = account_manager.COOKIE_WARNING + "_"
    expected = [
        e.replace("STD", std, 1) if e.startswith("STD") else e for e in expected
    ]
    assert account_manager.cookie_candidates(pasted) == expected


def manual_add(monkeypatch, pasted, accepted):
    """Runs manually_add_account; RobloxAPI only accepts cookies in `accepted`."""
    import account_manager

    tried, saved = [], []

    class FakeRoblox:
        def __init__(self, cookie, auth_secret):
            tried.append(cookie[".ROBLOSECURITY"])
            if cookie[".ROBLOSECURITY"] not in accepted:
                raise E.CookieInvalid(message="bad cookie")
            self.username, self.account_id = "tester", 1

    answers = iter(["2fa-secret", pasted])
    manager = object.__new__(account_manager.AccountManager)
    manager.cli = types.SimpleNamespace(
        input_prompt=lambda _p: next(answers), print_error=lambda _m: None
    )
    manager.json_handler = types.SimpleNamespace(add_cookie=lambda *a: saved.append(a))
    monkeypatch.setattr(account_manager, "RobloxAPI", FakeRoblox)
    monkeypatch.setattr(
        account_manager,
        "AuthHandler",
        lambda: types.SimpleNamespace(verify_auth_secret=lambda _s: True),
    )
    manager.manually_add_account()
    return tried, saved


def test_cookie_without_warning_gets_it_added(monkeypatch):
    import account_manager

    full = account_manager.COOKIE_WARNING + "_" + TOKEN
    tried, saved = manual_add(monkeypatch, TOKEN, accepted={full})
    assert tried == [full]
    assert saved[0][0] == full


def test_cookie_falls_back_to_exactly_what_was_pasted(monkeypatch):
    tried, saved = manual_add(monkeypatch, TOKEN, accepted={TOKEN})
    assert len(tried) == 2 and saved[0][0] == TOKEN


def test_invalid_cookie_is_not_saved(monkeypatch):
    tried, saved = manual_add(monkeypatch, TOKEN, accepted=set())
    assert len(tried) == 2 and saved == []


# --- inbound gains and close counters -------------------------------------------


def test_inbound_gains_replace_trading_gains_only_when_set(tmp_path):
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    cfg = tmp_path / "c.cfg"
    preset = pathlib.Path(__file__).parent.parent / "configs" / "small_value.cfg"
    trading, inbound = preset.read_text().split("[Inbounds]\n")
    inbound = re.sub(
        r"^(Min|Max) [A-Za-z ]+ Profit = .*\n",
        "", inbound, flags=re.M,
    )
    cfg.write_text(
        trading
        + "[Inbounds]\nMin Overall Profit = 7\n"
        + "Max Value Profit = None\n"
        + inbound
    )
    config = ConfigHandler(str(cfg))
    assert config.inbounds["Gains"] == {
        "Minimum_Overall_Gain": 7,
        "Maximum_Value_Gain": None,
    }
    normal = TradeMaker(config)
    counter = TradeMaker(config, gains=config.inbounds["Gains"])
    assert counter.min_overall_gain == 7
    assert counter.max_value_gain is None
    assert counter.min_rap_gain == normal.min_rap_gain  # not set: trading's


def test_counter_keeps_their_trade_items():
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    maker = TradeMaker(ConfigHandler("configs/small_value.cfg"))
    for name in (
        "min_rap_gain max_rap_gain min_overall_gain max_overall_gain min_algo_gain "
        "max_algo_gain min_value_gain max_value_gain min_rap_score_percentage "
        "max_rap_score_percentage min_overall_score_percentage "
        "max_overall_score_percentage max_valid_trades"
    ).split():
        setattr(maker, name, None)
    maker.min_overall_gain = 1
    maker.min_value_of_trade = maker.min_rap_of_trade = 0
    maker.min_items_self = maker.min_items_their = 1
    maker.max_items_self = maker.max_items_their = 2
    maker.trade_robux = False
    maker.trade_timeout = 10

    def item(item_id, value):
        return {
            "item_id": item_id,
            "value": value,
            "rap": value,
            "demand": 2,
            "rap_algorithm": value,
            "total_value": value,
            "item_volume": 5,
        }

    mine = {f"m{i}": item(f"1:{i}", 100 * i) for i in range(1, 6)}
    theirs = {f"t{i}": item(f"1:{20 + i}", 110 * i) for i in range(1, 6)}
    # They asked for our 1:3 and offered 1:22 (220 for 300: a loss for us)
    original = {"self": ["1:3"], "their": ["1:22"]}
    for _ in range(20):
        trade = maker.generate_trade(
            mine, theirs, counter_trade=True, original=original
        )
        # One item changed: they add one, or we swap ours for a smaller one
        assert trade["changes"] == 1


# --- inbound webhooks ----------------------------------------------------------


def webhooks_on(account):
    account.config.discord_settings.update(
        Send_Webhook="send-url", Completed_Webhook="completed-url"
    )
    return account.discord_webhook.posts


def test_accepted_inbound_is_posted_to_completed_once(router, inbound):
    posts = webhooks_on(inbound)
    inbound.handle_inbounds(accept=True, counter=True)
    assert posts == [("completed-url", "Accepted an inbound trade (5 profit)", 2)]
    assert inbound.posted_accepts == {"70"}

    # The completed-trades check skips it instead of posting it again
    inbound._post_completed_trade = lambda trade_id: posts.append(trade_id)
    inbound.get_trades = lambda *a, **k: {"70": {}, "60": {}}
    inbound.last_completed_scanned = "60"
    inbound.json = types.SimpleNamespace(update_last_completed=lambda *a: None)
    inbound.check_completeds()
    assert len(posts) == 1 and inbound.posted_accepts == set()


def test_declined_inbound_is_posted_red_to_send(router, inbound, monkeypatch):
    monkeypatch.setattr("roblox_api.time.sleep", lambda s: None)
    account = no_counter_account(router, inbound, decline=True)
    posts = webhooks_on(account)
    account.handle_inbounds(accept=True, counter=True)
    assert posts == [
        (
            "send-url",
            "Declined a trade: no counter passed your gains (5 profit)",
            0,
        )
    ]


def test_counter_is_posted_yellow_to_send(router, inbound):
    del inbound._counter_trade
    posts = webhooks_on(inbound)
    inbound.check_can_trade = lambda trader_id: True
    inbound.account_inventory = {"m": {"item_id": "1:1"}}
    inbound.fetch_inventory = lambda trader_id, **k: {"t": {"item_id": "1:2"}}
    inbound.offered_item_counts = lambda: {}
    inbound.counter_maker = types.SimpleNamespace(
        generate_trade=lambda *a, **k: {
            "self_side": ("m",),
            "their_side": ("t",),
            "self_robux": 0,
        }
    )
    inbound.send_trade = lambda *a, **k: 99
    router.set(TRADE_URL, resp(200, inbound_trade_json(["1:1"], ["1:2"])))
    results = inbound.handle_inbounds(accept=True, counter=True)
    assert results["countered"] == 1
    assert posts == [("send-url", "Countered a trade (5 profit)", 3)]


# --- console output ------------------------------------------------------------


def test_log_lines_read_without_color():
    from handler.handle_logs import format_line

    assert format_line("[INBOUND] Countered", clock="1:02:11 PM") == (
        "1:02:11 PM Inbound   Countered"
    )
    warning = format_line("[REQUESTS] slow", 2, clock="1:02:11 PM")
    assert warning.endswith("WARNING: slow") and "\033" not in warning
    # Later lines start under the tag, indented a little
    first, second = format_line("[BOT] a\nb", clock="1:02:11 PM").split("\n")
    assert second == " " * 11 + "  b"
    # A tag with a name: the name moves into the message
    assert format_line("[WAYDROID two] Joining", clock="1").endswith(
        "Waydroid  two: Joining"
    )


def test_log_lines_wrap_to_the_terminal():
    from handler.handle_logs import format_line

    text = "[TRADING] " + " ".join(["word"] * 40)
    lines = format_line(text, clock="1:02:11 PM", width=60).split("\n")
    assert len(lines) > 1 and all(len(line) <= 60 for line in lines)
    assert format_line(text, clock="1:02:11 PM").count("\n") == 0  # log file


def test_gains_table_shows_every_gain_and_the_failed_one():
    from trade_algorithm import gains_table

    maker = types.SimpleNamespace(
        min_overall_gain=450, max_overall_gain=1200, min_value_gain=None,
        max_value_gain=None, min_rap_gain=None, max_rap_gain=None,
        min_algo_gain=0.05, max_algo_gain=None,
    )
    trade = dict(
        their_overall_value=7000, self_overall_value=6900, their_value=3500,
        self_value=4000, their_rap=4000, self_rap=3000, their_rap_algo=3900,
        self_rap_algo=2800, self_robux=50,
    )
    table = gains_table(trade, maker, "overall_gain").split("\n")
    overall = next(line for line in table if "Overall Value" in line)
    assert "+50" in overall and "450" in overall and "1,200" in overall
    assert overall.endswith("<- failed")
    assert any("RAP Algorithm" in line and "5%" in line for line in table)
    assert table[-1] == "(Robux in the trade: -50)"


def test_failed_field_lists_what_stopped_the_trades():
    from trade_algorithm import failed_field

    stats = {
        "tried": 1442,
        "passed": 0,
        "failed": {"value_gain": 43, "overall_gain": 1399, "rap_gain": 900},
        "only": {"value_gain": 0, "overall_gain": 0, "rap_gain": 545},
    }
    text = failed_field(stats)
    assert text.startswith(
        "Tried 1,442 trades, none passed.\n"
        "Loosening only RAP gain (below min) would let 545 pass."
    )
    body = text.split("```")[1].strip().split("\n")
    width = len("Overall Value gain (below min)")
    assert body == [
        f"{'Setting':<{width}}  Failed  Sole Failure",
        f"{'RAP gain (below min)':<{width}}     900           545",
        f"{'Overall Value gain (below min)':<{width}}   1,399             0",
        f"{'Value gain (below min)':<{width}}      43             0",
    ]
    assert "Sole Failure = " in text.split("```")[2]
    # Old style counts still work
    assert failed_field({"rap_gain": 3}).startswith("Tried 3 trades, none passed.")
    assert "No trades to try" in failed_field({})


def test_keep_trades_setting_reads_new_and_old_name(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    key = "Only_Cancel_Losing_After_Config_Change"
    for text, expected in (
        ("Keep Trades Sent Before Config Change = True", True),
        ("Keep Trades Sent Before Config Change = False", False),
        ("Only Cancel Losing Trades After Config Change = True", True),
        ("", False),
    ):
        cfg.write_text(f"[Outbound Settings]\n{text}\n")
        assert ConfigHandler(str(cfg)).outbound[key] is expected, text


# --- counter loops ---------------------------------------------------------------


def test_counter_history_remembers_counters_and_replies(tmp_path):
    from handler.counter_history import CounterHistory, trade_signature

    now = [1000.0]
    path = str(tmp_path / "h.json")
    history = CounterHistory(path, "1", memory_hours=1, clock=lambda: now[0])
    sig = trade_signature(["1:2", "1:1"], ["1:3"])
    assert sig == trade_signature(["1:1", "1:2"], ["1:3"], 0)  # order doesn't matter

    history.record_counter(5, sig)
    assert history.sent(5) == {sig} and history.counters(5) == 1
    assert history.note_inbound(5, 70, 1010) == 10
    assert history.note_inbound(5, 70, 1010) == 10  # counted once
    assert history.note_inbound(5, 71, 500) is None  # sent before our counter
    assert history.instant_replies(5, 60) == 1

    # Saved per account, and forgotten after the memory runs out
    again = CounterHistory(path, "1", memory_hours=1, clock=lambda: now[0])
    assert again.counters(5) == 1
    assert CounterHistory(path, "2", clock=lambda: now[0]).counters(5) == 0
    now[0] += 3601
    assert again.counters(5) == 0 and again.instant_replies(5, 60) == 0


def test_instant_streak_breaks_on_a_slow_reply():
    from handler.counter_history import CounterHistory

    now = [0.0]
    history = CounterHistory(None, clock=lambda: now[0])
    for n, delay in enumerate((5, 500, 5, 5)):
        now[0] += 1000
        history.record_counter(9, f"sig{n}")
        history.note_inbound(9, n, now[0] + delay)
    assert history.instant_replies(9, 60) == 2


def counter_maker():
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    maker = TradeMaker(ConfigHandler("configs/small_value.cfg"))
    for name in (
        "min_rap_gain max_rap_gain min_overall_gain max_overall_gain min_algo_gain "
        "max_algo_gain min_value_gain max_value_gain min_rap_score_percentage "
        "max_rap_score_percentage min_overall_score_percentage "
        "max_overall_score_percentage max_valid_trades"
    ).split():
        setattr(maker, name, None)
    maker.min_overall_gain = 1
    maker.min_value_of_trade = maker.min_rap_of_trade = 0
    maker.min_items_self = maker.min_items_their = 1
    maker.max_items_self = maker.max_items_their = 2
    maker.trade_robux = False
    maker.trade_timeout = 10

    def item(item_id, value):
        return {
            "item_id": item_id, "value": value, "rap": value, "demand": 2,
            "rap_algorithm": value, "total_value": value, "item_volume": 5,
        }

    mine = {f"m{i}": item(f"1:{i}", 100 * i) for i in range(1, 4)}
    theirs = {f"t{i}": item(f"1:{20 + i}", 110 * i) for i in range(1, 4)}
    return maker, mine, theirs


def test_counter_is_never_sent_twice():
    from handler.counter_history import trade_signature

    maker, mine, theirs = counter_maker()

    def signature(trade):
        return trade_signature(
            [mine[k]["item_id"] for k in trade["self_side"]],
            [theirs[k]["item_id"] for k in trade["their_side"]],
            trade["self_robux"],
        )

    sent = set()
    while True:
        trade = maker.generate_trade(mine, theirs, counter_trade=True, avoid=sent)
        if trade is None:
            break
        assert signature(trade) not in sent
        sent.add(signature(trade))
    assert sent and maker.last_failed["already_sent"] == len(sent)


def loop_account(router, inbound, monkeypatch):
    monkeypatch.setattr("roblox_api.time.sleep", lambda s: None)
    inbound.config.inbounds.update(
        Max_Counters_Per_Trader=3,
        Instant_Reply_Seconds=60,
        Instant_Replies_For_Bot=2,
        Counter_Memory_Hours=24,
    )
    router.set(TRADE_URL, resp(200, inbound_trade_json(["1:1"], ["1:2"])))
    router.set(DECLINE_URL, resp(200, {}))
    return inbound


def test_trader_countered_too_often_is_declined(router, inbound, monkeypatch):
    account = loop_account(router, inbound, monkeypatch)
    for n in range(3):
        account.counter_history.record_counter(2, f"sig{n}")
    results = account.handle_inbounds(accept=True, counter=True)
    assert account.countered == [] and results["declined"] == 1
    assert declined(router) == [DECLINE_URL + "70/decline"]


def test_instant_counter_backs_are_declined_as_a_bot(router, inbound, monkeypatch):
    account = loop_account(router, inbound, monkeypatch)
    sent_at = parse_created_ts("2026-11-01T00:00:00Z") - 5  # inbound 70: 5s later
    now = [sent_at - 1000]
    history = account.counter_history
    history.clock = lambda: now[0]
    history.record_counter(2, "sig0")
    history.note_inbound(2, 1, now[0] + 3)  # an earlier instant reply
    now[0] = sent_at
    history.record_counter(2, "sig1")
    results = account.handle_inbounds(accept=True, counter=True)
    assert account.countered == [] and results["declined"] == 1


def test_slow_trader_under_the_limit_is_still_countered(router, inbound, monkeypatch):
    account = loop_account(router, inbound, monkeypatch)
    account.counter_history.record_counter(2, "sig0")
    account.handle_inbounds(accept=True, counter=True)
    assert account.countered == [70]


def parse_created_ts(text):
    from roblox_api import parse_created

    return parse_created(text)


def test_failed_table_is_one_column():
    from trade_algorithm import failed_text

    stats = {
        "tried": 2541,
        "failed": {"overall_gain_max": 2355, "value_gain": 186, "rap_gain": 0},
        "only": {"overall_gain_max": 2000, "value_gain": 0, "rap_gain": 0},
    }
    lines = failed_text(stats, width=200).split("\n")
    assert lines[0] == "Tried 2,541 trades, none passed."
    assert lines[1] == "Loosening only Overall Value gain (above max) would let 2,000 pass."
    assert lines[2].startswith("Setting") and " | " not in lines[2]
    assert lines[3].startswith("Overall Value gain (above max)")
    assert len(lines) == 7 and lines[-1].startswith("Sole Failure =")


def test_failures_say_if_it_was_the_min_or_the_max():
    maker, mine, theirs = _small_maker(min_overall=-10_000)
    maker.max_overall_gain = 100  # a+b is +500
    maker.min_items_their = 2
    assert maker.generate_trade(mine, theirs) is None
    assert maker.last_failed["not_made"] == 1  # over the max: never even built
    assert maker.validate_trade(
        self_rap=1000, self_rap_algo=1000, self_value=0, their_rap=1500,
        their_rap_algo=1500, their_value=0, self_overall_value=1000,
        their_overall_value=1500,
    ) == (False, "overall_gain_max")


def test_what_stopped_them_finds_the_setting_that_blocks_alone():
    """Overall is checked first, but only RAP sum of trade blocks these trades."""
    maker, mine, theirs = _small_maker(min_overall=350)
    maker.min_rap_of_trade = 3000  # a+b is 2,500
    assert maker.generate_trade(mine, theirs) is None
    stats = maker.last_failed
    assert stats["only"]["min_rap_of_trade"] > 0
    assert stats["only"]["overall_gain"] == 0
    assert "Loosening only RAP sum of trade (below min)" in failed_text_of(stats)


def failed_text_of(stats):
    from trade_algorithm import failed_text

    return failed_text(stats, width=80)


def _small_maker(min_overall=None):
    """Our 1000 item for their 1500 in items: +500 overall."""
    from trade_algorithm import TradeMaker
    from handler.handle_config import ConfigHandler

    config = ConfigHandler("config.cfg")
    for key in list(config.trading):
        if key.startswith(("Minimum_", "Maximum_")) and key.endswith("_Gain"):
            config.trading[key] = None
    config.trading.update(
        Minimum_Overall_Gain=min_overall,
        MinimumItemsYourSide=1, MaximumItemsYourSide=1,
        MinimumItemsTheirSide=1, MaximumItemsTheirSide=2,
        MinimumValueOfTrade=None, MinimumRapOfTrade=None,
        MinRapScorePercentage=None, MaxRapScorePercentage=None,
        MinOverallValueScorePercentage=None, MaxOverallValueScorePercentage=None,
        TradeRobux=False,
    )
    maker = TradeMaker(config=config)

    def item(item_id, total):
        return {"item_id": item_id, "value": total, "rap": total, "rap_algorithm": total,
                "demand": 1, "total_value": total, "item_volume": 1}

    mine = {"m": item("1:1", 1000)}
    theirs = {"a": item("1:2", 800), "b": item("1:3", 700)}
    return maker, mine, theirs


def test_no_trades_reason_names_the_gain_range_that_left_nothing():
    maker, mine, theirs = _small_maker(min_overall=1000)
    maker.max_overall_gain = 3000  # their best side is only +500
    assert maker.generate_trade(mine, theirs) is None
    why = maker.last_failed["why_none"]
    assert "Overall Value gain range (min 1,000, max 3,000)" in why


def test_endpoint_hides_ids_and_query():
    from handler.handle_requests import endpoint

    assert endpoint("https://trades.roblox.com/v2/trades/1998757328879237/counter") == (
        "trades.roblox.com/v2/trades/{id}/counter"
    )
    assert endpoint(
        "https://inventory.roblox.com/v2/assets/37819953/owners?cursor=abc&limit=100"
    ) == "inventory.roblox.com/v2/assets/{id}/owners"
    assert endpoint(
        "https://trades.roblox.com/v2/users/3249113585/tradableItems"
    ) == "trades.roblox.com/v2/users/{id}/tradableItems"
    assert endpoint(
        "https://x.com/a/7792dea7-78d8-4f85-b608-8e5ad0d55541"
    ) == "x.com/a/{id}"


# --- paused accounts ----------------------------------------------------------


def _accounts_file(tmp_path, monkeypatch, *accounts):
    import json
    from handler.handle_json import JsonHandler

    monkeypatch.chdir(tmp_path)
    (tmp_path / "cookies.json").write_text(json.dumps({"roblox_accounts": list(accounts)}))
    return JsonHandler("cookies.json")


def test_only_paused_when_every_on_account_is(tmp_path, monkeypatch):
    j = _accounts_file(
        tmp_path,
        monkeypatch,
        {"cookie": "a", "username": "A", "use_account": True},
        {"cookie": "b", "username": "B", "use_account": True},
        {"cookie": "c", "username": "C", "use_account": False},
    )
    assert not j.is_all_ratelimited()
    j.add_ratelimit_timestamp("a")
    assert not j.is_all_ratelimited()
    j.add_ratelimit_timestamp("b", "doesn't have Premium", hours=1)
    assert j.is_all_ratelimited()
    text = j.paused_text()
    assert "A: hit the trade limit, until" in text
    assert "B: doesn't have Premium, until" in text and "C" not in text


def test_pause_ends_after_its_hours(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    old = (datetime.now() - timedelta(hours=2)).isoformat()
    j = _accounts_file(
        tmp_path,
        monkeypatch,
        {"cookie": "a", "username": "A", "use_account": True,
         "ratelimit_timestamp": old, "ratelimit_hours": 1},
        {"cookie": "b", "username": "B", "use_account": True,
         "ratelimit_timestamp": old},
    )
    assert not j.check_ratelimit_cookie("a")
    assert j.check_ratelimit_cookie("b")  # old stamps default to 6 hours


def test_no_accounts_on_is_not_all_paused(tmp_path, monkeypatch):
    j = _accounts_file(tmp_path, monkeypatch)
    assert not j.is_all_ratelimited()


def test_webhook_footer_hides_the_username_by_default(account):
    footers = []
    account.discord_webhook.setup_embed = (
        lambda title, color, user_id, embed_fields, footer, description="":
        footers.append(footer) or (title, color)
    )
    account.config.discord_settings["Send_Webhook"] = "send-url"
    trade = {"their_id": 9}
    assert account.post_trade_webhook("Send_Webhook", trade, "t", 1)
    account.config.discord_settings["Hide_Username"] = False
    assert account.post_trade_webhook("Send_Webhook", trade, "t", 1)
    assert footers == ["", "tester"]


def test_embed_footer_without_a_name_is_just_the_id():
    from handler.handle_discord import DiscordHandler

    d = DiscordHandler.__new__(DiscordHandler)
    import requests as rq

    real = rq.get
    rq.get = lambda *a, **k: (_ for _ in ()).throw(rq.RequestException())
    try:
        assert d.setup_embed("t", 1, 42, {}, "").footer["text"] == "42"
        assert d.setup_embed("t", 1, 42, {}, "bob").footer["text"] == "bob • 42"
    finally:
        rq.get = real


def test_error_alerts_hide_usernames(doggo):
    doggo.json = types.SimpleNamespace(read_data=lambda: {"roblox_accounts": [
        {"username": "tisiallyyy"}, {"username": "DesiredDesigner"}]})
    assert doggo.hide_usernames("DesiredDesigner disabled; tisiallyyy too") == (
        "account 2 disabled; account 1 too"
    )


# --- update check ---------------------------------------------------------------


def test_version_compare():
    from handler.update_check import is_newer

    assert is_newer("v2.0", "2.0", "BETA")  # stable after its beta
    assert is_newer("v2.0.1", "2.0", "")
    assert not is_newer("v2.0", "2.0", "")
    assert not is_newer("v2.0-beta", "2.0", "")
    assert not is_newer("v1.9", "2.0", "BETA")
    assert not is_newer("nightly", "2.0", "")


def test_update_message_for_each_install(monkeypatch):
    from handler import update_check as u

    release = {"tag": "v2.1", "url": "https://github.com/x/releases/tag/v2.1"}
    exe = u.update_message(release, True, False, False, True)
    assert "2.1 is out" in exe and release["url"] in exe and "git pull" not in exe
    clone = u.update_message(release, False, True, False, False)
    assert "  git pull" in clone and "config.cfg" in clone and "checkout" not in clone
    old_clone = u.update_message(release, False, True, True, True)
    steps = [line.strip() for line in old_clone.splitlines() if line.startswith("  ")]
    assert steps[:4] == [
        "copy config.cfg config.backup.cfg",
        "git checkout -- config.cfg",
        "git pull",
        "copy /Y config.backup.cfg config.cfg",
    ]
    no_git = u.update_message(release, False, False, False, False)
    assert u.SOURCE_ZIP in no_git


def test_update_check_only_speaks_when_newer(monkeypatch):
    from handler import update_check as u

    def fake_get(tag, status=200):
        return lambda *a, **k: types.SimpleNamespace(
            status_code=status, json=lambda: {"tag_name": tag, "html_url": "u"}
        )

    monkeypatch.setattr(u.version, "VERSION", "2.0")
    monkeypatch.setattr(u.version, "STAGE", "")
    monkeypatch.setattr(u, "message", None)
    assert u.check(get=fake_get("v2.0")) is None
    assert u.check(get=fake_get("v9.0", status=403)) is None
    assert "9.0 is out" in u.check(get=fake_get("v9.0"))
    assert u.message and "9.0 is out" in u.message
    assert u.check(get=lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError())) is None


def test_config_cfg_is_made_from_the_default(tmp_path):
    from handler.handle_config import ConfigHandler, DEFAULT_CONFIG

    (tmp_path / DEFAULT_CONFIG).write_text("[Discord]\nHide Username = False\n")
    config = ConfigHandler(str(tmp_path / "config.cfg"))
    assert (tmp_path / "config.cfg").exists()
    assert config.discord_settings["Hide_Username"] is False
    # An existing config.cfg is never replaced
    (tmp_path / "config.cfg").write_text("[Discord]\nHide Username = True\n")
    assert ConfigHandler(str(tmp_path / "config.cfg")).discord_settings["Hide_Username"]


def test_rate_limit_waits_as_long_as_roblox_says(router, monkeypatch):
    from handler import handle_requests

    waits = []
    monkeypatch.setattr(handle_requests.time, "sleep", waits.append)
    h = handler(router, U, resp(429, headers={"Retry-After": "7"}), resp(200, {"ok": 1}))
    assert h.requestAPI(U).json() == {"ok": 1}
    assert waits == [7.0]
    h = handler(router, U, resp(429), resp(200, {"ok": 1}))
    waits.clear()
    h.requestAPI(U)
    assert waits == [20]  # nothing said: our own backoff


def test_retry_after_forms():
    from handler.handle_requests import retry_after, rate_limit_headers

    def r(headers):
        return types.SimpleNamespace(headers=headers)

    assert retry_after(r({})) is None
    assert retry_after(r({"x-ratelimit-reset": "12"})) == 12
    assert retry_after(r({"Retry-After": "9999"})) == 300  # capped
    assert retry_after(r({"Retry-After": "0"})) == 1
    assert 55 <= retry_after(r({"x-ratelimit-reset": str(time.time() + 60)})) <= 60
    assert retry_after(r({"Retry-After": "soon"})) is None
    # Roblox sends Retry-After 5 even when the limit resets later: wait for the reset
    assert retry_after(r({"retry-after": "5", "x-ratelimit-reset": "13"})) == 13
    assert retry_after(r({"retry-after": "5", "x-ratelimit-reset": "1"})) == 5
    assert rate_limit_headers(r({"Retry-After": "1", "set-cookie": "x"})) == {"Retry-After": "1"}


# --- making an account config the main config ---------------------------------


def test_trading_options_cover_every_trading_setting():
    from handler.handle_config import ConfigHandler

    assert set(ConfigHandler.TRADING_OPTIONS) == set(ConfigHandler("config.default.cfg").trading)


def test_account_config_round_trips_into_config_cfg(tmp_path, monkeypatch):
    import shutil

    from handler.account_settings import HandleConfigs
    from handler.handle_config import ConfigHandler

    root = pathlib.Path(__file__).parent.parent
    monkeypatch.chdir(tmp_path)
    shutil.copy(root / "config.default.cfg", "config.cfg")
    shutil.copy(root / "config.default.cfg", "config.default.cfg")
    before = (tmp_path / "config.cfg").read_text()

    account = dict(ConfigHandler("config.cfg").trading)
    account.update(
        Minimum_Overall_Gain=300.0, Maximum_Overall_Gain=None, MaxRobux=750,
        TradeRobux=False, Outbound_Cancel_Offset=123,
        MinimumItemsTheirSide=2, Rap_Algo_For_Valued="rap_algorithm",
    )
    (tmp_path / "account_configs.jsonc").write_text(json.dumps({"42": account}))
    (tmp_path / "cookies.json").write_text(json.dumps({"roblox_accounts": [
        {"cookie": "c", "username": "DesiredDesigner", "user_id": "42"}]}))

    answers = iter(["", "y", "y"])  # skip none, write, remove
    handler = HandleConfigs()
    assert handler.apply_to_main("42", ask=lambda _: next(answers))

    loaded = ConfigHandler("config.cfg").trading
    for key, value in account.items():
        assert loaded[key] == value, key
    after = (tmp_path / "config.cfg").read_text()
    assert after.count("\n#") == before.count("\n#")  # comments kept
    assert (tmp_path / "config.backup.cfg").read_text() == before
    assert "42" not in json.loads((tmp_path / "account_configs.jsonc").read_text())


def test_account_config_not_written_when_you_say_no(tmp_path, monkeypatch):
    import shutil

    from handler.account_settings import HandleConfigs

    root = pathlib.Path(__file__).parent.parent
    monkeypatch.chdir(tmp_path)
    shutil.copy(root / "config.default.cfg", "config.cfg")
    shutil.copy(root / "config.default.cfg", "config.default.cfg")
    before = (tmp_path / "config.cfg").read_text()
    (tmp_path / "account_configs.jsonc").write_text(json.dumps({"42": {"MaxRobux": 5}}))
    (tmp_path / "cookies.json").write_text(json.dumps({"roblox_accounts": []}))
    answers = iter(["", "n"])
    assert not HandleConfigs().apply_to_main("42", ask=lambda _: next(answers))
    assert (tmp_path / "config.cfg").read_text() == before
    assert "42" in json.loads((tmp_path / "account_configs.jsonc").read_text())


def test_account_config_can_skip_settings(tmp_path, monkeypatch):
    import shutil

    from handler.account_settings import HandleConfigs
    from handler.handle_config import ConfigHandler

    root = pathlib.Path(__file__).parent.parent
    monkeypatch.chdir(tmp_path)
    shutil.copy(root / "config.default.cfg", "config.cfg")
    shutil.copy(root / "config.default.cfg", "config.default.cfg")
    before = ConfigHandler("config.cfg").trading
    account = dict(before, Minimum_Overall_Gain=300.0, MaxRobux=750, MinimumItemsTheirSide=2)
    (tmp_path / "account_configs.jsonc").write_text(json.dumps({"42": account}))
    (tmp_path / "cookies.json").write_text(json.dumps({"roblox_accounts": []}))

    # Changes are listed in config.cfg order: Overall Gain (1), Max Robux (2), Their Side (3)
    answers = iter(["x", "9", "2", "y", "n"])  # bad input, out of range, skip 2, write, keep
    assert HandleConfigs().apply_to_main("42", ask=lambda _: next(answers))
    loaded = ConfigHandler("config.cfg").trading
    assert loaded["Minimum_Overall_Gain"] == 300
    assert loaded["MaxRobux"] == before["MaxRobux"]  # skipped
    assert loaded["MinimumItemsTheirSide"] == 2
    assert "42" in json.loads((tmp_path / "account_configs.jsonc").read_text())


def test_config_fingerprint_changes_with_inbound_gains(account):
    before = account._config_fingerprint()
    account.config.inbounds = {**account.config.inbounds, "Gains": {"Minimum_Overall_Gain": 1}}
    assert account._config_fingerprint() != before


def test_no_trades_to_try_says_why():
    from trade_algorithm import failed_field, failed_text

    maker, mine, theirs = _small_maker()
    maker.min_items_their = 2
    assert maker.generate_trade(mine, {"a": theirs["a"]}) is None
    text = failed_text(maker.last_failed)
    assert "They have 1 usable item" in text and "Min Items Theirs is 2" in text
    assert "Min Items Theirs is 2" in failed_field(maker.last_failed)
    assert maker.generate_trade(mine, {}) is None
    assert "They have no usable items" in failed_text(maker.last_failed)


def test_value_gain_can_skip_trades_without_valued_items():
    maker, mine, theirs = _small_maker()
    for item in [*mine.values(), *theirs.values()]:
        item["value"] = 0  # RAP items only
    maker.min_value_gain = 1
    assert maker.generate_trade(mine, theirs) is None
    assert maker.last_failed["only"]["value_gain"] == 1
    maker.skip_value_without_valued = True
    assert maker.generate_trade(mine, theirs)
    mine["m"]["value"] = 1000  # a valued item in the trade: checked again
    assert maker.generate_trade(mine, theirs) is None


def test_added_setting_goes_in_its_own_section_not_under_the_next_banner():
    from handler.account_settings import set_options

    text = "[A]\nX = 1\n\n\n# =====\n[B]\n# =====\nY = 2\n"
    new, changes = set_options(text, {("A", "Z"): "3"})
    assert new == "[A]\nX = 1\nZ = 3\n\n\n# =====\n[B]\n# =====\nY = 2\n"
    assert changes == [("A", "Z", None, "3")]


def test_nft_and_nfr_match_items_and_bundles_by_plain_id():
    from handler.handle_config import on_item_list

    assert on_item_list("1:1029025", ["1029025"])
    assert on_item_list("2:939596", ["939596"])  # bundle, no prefix needed
    assert on_item_list("2:939596", ["2:939596"])  # old style still works
    assert not on_item_list("1:5", ["55"])
    assert not on_item_list("1:5", [])


def _owners_page(owner_ids, cursor, days_ago=1):
    from datetime import datetime, timedelta

    when = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"nextPageCursor": cursor,
            "data": [{"owner": {"id": i}, "updated": when} for i in owner_ids]}


def test_owner_scan_carries_on_where_it_stopped(account, tmp_path, monkeypatch):
    import roblox_api

    monkeypatch.chdir(tmp_path)
    pages = {"": _owners_page([1, 2], "p2"), "p2": _owners_page([3], "p3"),
             "p3": _owners_page([4], None)}
    asked = []

    def request(url, **kwargs):
        cursor = url.split("cursor=")[1].split("&")[0]
        asked.append(cursor)
        return types.SimpleNamespace(status_code=200, json=lambda: pages[cursor])

    monkeypatch.setattr(account.request_handler, "requestAPI", request)
    monkeypatch.setattr(roblox_api, "read_json", lambda r: r.json())
    account.all_cached_traders = set()
    account.config.scan_items.update(
        Owner_Pages_Per_Scan=1, Recent_Owner_Days=7, Remember_Scanned_Owners_Days=3)
    item = {"original_asset_id": 77}
    assert account.get_active_traders(item, []) == [1, 2]
    assert account.get_active_traders(item, []) == [3]  # next page, not page 1 again
    assert account.get_active_traders(item, []) == [4]
    assert account.get_active_traders(item, []) == []  # every owner read: skipped
    assert asked == ["", "p2", "p3"]


def test_owner_scan_memory_is_forgotten_after_its_days(tmp_path):
    from handler.owner_pages import OwnerPages

    now = [1000.0]
    pages = OwnerPages(3, clock=lambda: now[0], file=str(tmp_path / "o.json"))
    pages.save(77, None)
    assert pages.start(77) is None
    now[0] += 3 * 86400 + 1
    assert pages.start(77) == ""  # forgotten: from the first page again
    assert OwnerPages(0, file=str(tmp_path / "o.json")).start(77) == ""  # memory off


def test_owner_scan_uses_every_recent_owner_on_a_page(account, tmp_path, monkeypatch):
    import roblox_api

    monkeypatch.chdir(tmp_path)
    page = _owners_page([1, 2, 3, 4], "next")
    page["data"][1]["updated"] = "2020-01-01T00:00:00Z"  # got it long ago
    monkeypatch.setattr(account.request_handler, "requestAPI",
                        lambda url, **kw: types.SimpleNamespace(json=lambda: page))
    monkeypatch.setattr(roblox_api, "read_json", lambda r: r.json())
    account.all_cached_traders = {3}  # already traded with
    account.config.scan_items.update(Owner_Pages_Per_Scan=1, Recent_Owner_Days=7,
                                     Remember_Scanned_Owners_Days=0)
    assert account.get_active_traders({"original_asset_id": 5}, []) == [1, 4]


def test_old_and_new_setting_names_load_the_same(tmp_path):
    from handler.handle_config import ConfigHandler

    old = tmp_path / "old.cfg"
    old.write_text(
        "[Trading Settings]\nMinimum Overall Value Gain = 321\nTrade For Faces = True\n"
        "[Filtering Items]\nNFT = 5, 6\n[Filtering Users]\nMinimum Total Items = 9\n"
        "[Inbound Settings]\nMinimum Overall Value Gain = 12\nCounter Trades = False\n"
        "[debug]\nDont Send Trades = True\n"
    )
    new = tmp_path / "new.cfg"
    new.write_text(
        "[Profit]\nMin Overall Profit = 321\n"
        "[Trade Rules]\nReceive Faces = True\n[Items]\nNever Give = 5, 6\n"
        "[Finding Traders]\nMin Trader Items = 9\n"
        "[Inbounds]\nMin Overall Profit = 12\nCounter = False\n"
        "[Debug]\nDont Send Trades = True\n"
    )
    a, b = ConfigHandler(str(old)), ConfigHandler(str(new))
    for name in ("trading", "filter_items", "filter_users", "inbounds", "debug"):
        assert getattr(a, name) == getattr(b, name), name
    assert b.trading["Minimum_Overall_Gain"] == 321
    assert b.inbounds["Gains"]["Minimum_Overall_Gain"] == 12


def test_new_names_show_in_config_errors(tmp_path):
    from handler.exceptions_types import ConfigError
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text("[Trade Rules]\nMax Items Yours = lots\n")
    with pytest.raises(ConfigError, match=r"\[Trade Rules\] Max Items Yours"):
        ConfigHandler(str(cfg))


def test_owner_scan_with_fewer_owners_than_the_pages_allow(account, tmp_path, monkeypatch):
    """2 pages per scan, but the item only has 10 owners (one short page)."""
    import roblox_api

    monkeypatch.chdir(tmp_path)
    asked = []

    def request(url, **kwargs):
        asked.append(url.split("cursor=")[1].split("&")[0])
        return types.SimpleNamespace(json=lambda: _owners_page(range(1, 11), None))

    monkeypatch.setattr(account.request_handler, "requestAPI", request)
    monkeypatch.setattr(roblox_api, "read_json", lambda r: r.json())
    account.all_cached_traders = set()
    account.config.scan_items.update(Owner_Pages_Per_Scan=2, Recent_Owner_Days=7,
                                     Remember_Scanned_Owners_Days=3)
    item = {"original_asset_id": 3}
    assert account.get_active_traders(item, []) == list(range(1, 11))
    assert asked == [""]  # one request: no second page to ask for
    assert account.get_active_traders(item, []) == []  # all read: skipped
    assert asked == [""]


@pytest.mark.parametrize(
    "text, part, key, expected",
    [
        ("[Inbounds]\n", "inbounds", "Accept_Valid_Trades", False),
        ("[Inbounds]\nAccept Good Trades = True\n", "inbounds", "Accept_Valid_Trades", True),
        ("[Inbounds]\n", "inbounds", "Decline_If_No_Counter", True),
        ("[Inbounds]\nDecline If No Counter = False\n", "inbounds", "Decline_If_No_Counter", False),
        ("[Inbounds]\n", "inbounds", "Max_Duplicates", 2),
        ("[Inbounds]\n", "inbounds", "Max_Trader_Duplicates", 2),
        ("[Inbounds]\n", "inbounds", "Check_Every_Minutes", 30),
        ("[Inbounds]\nCheck Every Minutes = 10\n", "inbounds", "Check_Every_Minutes", 10),
        ("[Inbounds]\n", "inbounds", "Max_Counters_Per_Trader", 3),
        ("[Inbounds]\n", "inbounds", "Instant_Replies_For_Bot", 3),
        ("[Inbounds]\n", "inbounds", "Instant_Reply_Seconds", 20 * 60),
        ("[Inbounds]\n", "inbounds", "Counter_Memory_Hours", 24),
        ("[Inbounds]\nMax Counters Per Trader = 0\n", "inbounds", "Max_Counters_Per_Trader", 0),
        ("[Inbounds]\nBot Replies = None\n", "inbounds", "Instant_Replies_For_Bot", 0),
        ("[Discord]\n", "discord_settings", "Hide_Username", True),
        ("[Discord]\nHide Username = False\n", "discord_settings", "Hide_Username", False),
    ],
)
def test_setting_defaults_and_values(tmp_path, text, part, key, expected):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text(text)
    assert getattr(ConfigHandler(str(cfg)), part)[key] == expected


def test_owner_scan_waits_for_room_in_the_queue(doggo, account):
    """A full queue pauses loading inventories; stopping ends the wait."""
    import main

    doggo.user_queue = {}
    doggo.rolimons.return_item_to_scan = lambda reach=None, skip=():  {"original_asset_id": 1}

    def found_owners(item, owners):
        # The queue fills up (other accounts' scans) right after this page
        doggo.user_queue.update({n: {} for n in range(main.MAX_QUEUED_TRADERS + 1)})
        owners.extend([5, 6])
        return owners

    account.get_active_traders = found_owners
    account.fetch_inventory = lambda *a, **k: pytest.fail("loaded an inventory with no room")
    stop = threading.Event()
    stop.wait = lambda seconds: stop.set() or True
    doggo.queue_traders(account, stop)
    assert 5 not in account.all_cached_traders


def test_ruling_out_by_gain_range_never_loses_a_passing_trade(monkeypatch):
    """The early range check finds exactly the trades the full check finds."""
    from trade_algorithm import TradePicker

    rng = random.Random(3)
    runs_with_trades = 0
    for _ in range(60):
        maker, _, _ = _small_maker()
        maker.min_items_self = rng.randint(1, 2)
        maker.max_items_self = rng.randint(maker.min_items_self, 4)
        maker.min_items_their = rng.randint(1, 2)
        maker.max_items_their = rng.randint(maker.min_items_their, 4)
        maker.trade_robux, maker.max_robux = rng.random() < 0.7, rng.choice([0, 50, 400])
        for name in ("overall", "rap", "algo", "value"):
            low = rng.choice([None, -300, 0, 120, 0.05, -0.1])
            high = rng.choice([None, 900, 2500, 0.4])
            setattr(maker, f"min_{name}_gain", low)
            setattr(maker, f"max_{name}_gain", high)

        def items(tag, n):
            out = {}
            for i in range(n):
                total = rng.randint(50, 3000)
                valued = rng.random() < 0.5
                out[f"{tag}{i}"] = {
                    "item_id": f"1:{tag}{i}", "value": total if valued else 0,
                    "rap": rng.randint(50, 3000), "rap_algorithm": rng.randint(50, 3000),
                    "demand": 1, "total_value": total, "item_volume": 1,
                }
            return out

        mine, theirs = items("m", rng.randint(2, 6)), items("t", rng.randint(2, 12))
        found = []
        monkeypatch.setattr(TradePicker, "add", lambda picker, trade: found.append(trade))
        maker.generate_trade(mine, theirs)
        fast = {(t["self_side"], t["their_side"]) for t in found}

        found.clear()
        # No ranges: every combination gets the full check
        maker.gain_windows = lambda *a, **k: []
        maker.generate_trade(mine, theirs)
        full = {(t["self_side"], t["their_side"]) for t in found}
        assert fast == full
        runs_with_trades += bool(full)
    assert runs_with_trades > 10


def test_trade_picker_picks_what_the_full_list_would():
    """The picker keeps one trade per Outbound Variety count, not every passing
    trade; it must still pick the same trade as sorting through all of them."""
    from trade_algorithm import SELECT_TRADE_OPTIONS, TradePicker, TradeMaker

    rng = random.Random(7)
    maker = TradeMaker.__new__(TradeMaker)
    fields = ("value", "rap", "rap_algo", "volume", "overall_value")
    for run in range(500):
        trades = [
            {
                "id": i,
                "self_side": rng.sample("abcd", rng.randint(1, 3)),
                **{f"{s}_{f}": rng.choice([0, 50, 100]) for s in ("self", "their") for f in fields},
                **{k: rng.choice([0, 50, 100]) for k in ("total_value", "total_rap", "total_overall_value", "total_volume")},
                "rap_close_score": rng.choice([-5, 0, 5]), "overall_close_score": rng.choice([-5, 0, 5]),
                "demand": rng.randint(0, 3), "num_items_self": rng.randint(1, 4), "num_items_their": rng.randint(1, 4),
                "changes": 0,
            }
            for i in range(rng.randint(1, 30))
        ]
        select_by = rng.choice([o for o in SELECT_TRADE_OPTIONS if o != "random"])
        maker.outbound_variety = rng.choice([None, 0.5, 1])
        offered = {"a": 3, "b": 1}
        avoid = set(rng.sample(range(30), 10))
        picker = TradePicker(select_by, maker.outbound_variety, offered, avoid, lambda t: t["id"])
        for trade in trades:
            picker.add(trade)
        fresh = [t for t in maker.prefer_unoffered(trades, offered) if t["id"] not in avoid]
        expected = maker.select_trade(fresh, select_by) if fresh else None
        assert picker.pick() is expected, (run, select_by)


def test_bundle_owner_scan_uses_its_resellers(account, tmp_path, monkeypatch):
    """Roblox doesn't list bundle owners, so bundles find traders through the
    people reselling them (looked up by the bundle's collectible id)."""
    import roblox_api

    monkeypatch.chdir(tmp_path)
    asked = []

    def listing(seller_id, seller_type="User"):
        return {"seller": {"sellerId": seller_id, "sellerType": seller_type}}

    def request(url, **kwargs):
        asked.append(url)
        if "/bundles/" in url:
            body = {"collectibleItemDetail": {"collectibleItemId": "abc-123"}}
        else:
            body = {"nextPageCursor": None,
                    "data": [listing(5), listing(6), listing(5), listing(9, "Group"), listing(7)]}
        return types.SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(account.request_handler, "requestAPI", request)
    monkeypatch.setattr(roblox_api, "read_json", lambda r: r.json())
    monkeypatch.setattr(type(account), "_bundle_collectible_ids", {})
    account.all_cached_traders = {7}
    account.config.scan_items.update(
        Owner_Pages_Per_Scan=2, Recent_Owner_Days=7, Remember_Scanned_Owners_Days=3)
    bundle = {"item_id": "2:31281416357406", "original_asset_id": 31281416357406}
    assert account.get_active_traders(bundle, []) == [5, 6]
    assert "catalog.roblox.com/v1/bundles/31281416357406/details" in asked[0]
    assert "marketplace-sales/v1/item/abc-123/resellers" in asked[1]
    assert len(asked) == 2  # one page, then every reseller was read


def test_sales_history_days_defaults_to_90_and_rejects_zero():
    from handler.handle_config import ConfigHandler

    handler = ConfigHandler.__new__(ConfigHandler)
    import configparser

    handler.config = configparser.ConfigParser()
    handler.config.optionxform = str
    handler.config.read_string("[Filtering Items]\n")
    handler.invalid_settings = []
    handler.shown = lambda section, option: f"[{section}] {option}"
    assert handler.load_sales_history_days() == 90
    handler.config.set("Filtering Items", "Sales History Days", "30")
    assert handler.load_sales_history_days() == 30
    handler.config.set("Filtering Items", "Sales History Days", "0")
    assert handler.load_sales_history_days() == 90
    assert handler.invalid_settings


def test_pick_trade_by_combos_break_ties_in_order():
    from trade_algorithm import parse_pick, TradeMaker

    assert parse_pick("lowest_overall_gain + upgrade + highest_demand") == (
        ["lowest_overall_gain", "upgrade", "highest_demand"], False
    )
    assert parse_pick("lowest_rap_gain+random") == (["lowest_rap_gain"], True)
    with pytest.raises(ValueError, match="best"):
        parse_pick("lowest_rap_gain + best")

    def trade(rap_gain, demand):
        return {"self_rap": 0, "their_rap": rap_gain, "demand": demand}

    trades = [trade(100, 1), trade(100, 5), trade(300, 9)]
    maker = TradeMaker.__new__(TradeMaker)
    assert maker.select_trade(trades, "lowest_rap_gain + highest_demand") is trades[1]
    assert maker.select_trade(trades, "highest_demand") is trades[2]


@pytest.mark.parametrize(
    "minimum, offset, expected",
    [
        (600, 200, 400),  # Robux
        (600, 0.02, 588),  # 2% under the minimum
        (600, 800, 0),  # never below 0
        (-500, 0.1, -550),  # a negative minimum can go lower
        (0.05, 0.2, 0.04),  # a % minimum: 20% under 5% = 4%
        (600, None, 600),
        (None, 0.02, None),
    ],
)
def test_cancel_offset_in_robux_or_share_of_the_minimum(minimum, offset, expected):
    from trade_algorithm import cancel_minimum

    if expected is None:
        assert cancel_minimum(minimum, offset) is None
    else:
        assert cancel_minimum(minimum, offset) == pytest.approx(expected)


def test_blend_ranks_every_option_with_the_first_counting_most():
    from trade_algorithm import blend_pick, parse_pick, is_blend, TradeMaker

    def trade(rap_gain, demand):
        return {"self_rap": 0, "their_rap": rap_gain, "demand": demand}

    # a: best RAP gain, worst demand. b: second on both. c: worst RAP, best demand
    a, b, c = trade(100, 1), trade(200, 5), trade(300, 9)
    names, _ = parse_pick("blend: lowest_rap_gain, highest_demand")
    assert is_blend("Blend: lowest_rap_gain, highest_demand")
    # RAP weighs 2, demand 1: a = 0 + 1, b = 1 + 0.5, c = 2 + 0
    assert blend_pick([a, b, c], names) is a
    # Flipped order: demand counts most
    names, _ = parse_pick("blend: highest_demand + lowest_rap_gain")
    assert blend_pick([a, b, c], names) is c
    maker = TradeMaker.__new__(TradeMaker)
    assert maker.select_trade([a, b, c], "blend: highest_demand, lowest_rap_gain") is c
    with pytest.raises(ValueError):
        parse_pick("blend: highest_demand, best")


def test_trade_picker_blend_matches_blend_pick():
    from trade_algorithm import TradePicker

    picker = TradePicker("blend: lowest_rap_gain, highest_demand")
    trades = [
        {"self_rap": 0, "their_rap": g, "demand": d, "changes": 0,
         "self_side": [], "their_side": []}
        for g, d in ((300, 9), (100, 1), (200, 5))
    ]
    for t in trades:
        picker.add(t)
    assert picker.pick() is trades[1]


def test_upgrade_means_giving_more_items_than_you_get():
    from trade_algorithm import PICK_KEYS

    one_for_four = {"num_items_self": 1, "num_items_their": 4}  # a downgrade
    four_for_one = {"num_items_self": 4, "num_items_their": 1}  # an upgrade
    assert min([one_for_four, four_for_one], key=PICK_KEYS["upgrade"]) is four_for_one
    assert min([one_for_four, four_for_one], key=PICK_KEYS["downgrade"]) is one_for_four


def test_picker_prefers_giving_away_projecteds():
    from trade_algorithm import TradePicker

    picker = TradePicker("lowest_rap_gain")
    plain = {"self_rap": 0, "their_rap": 100, "wanted_items": 0, "changes": 0,
             "projected_given": 0, "self_side": [], "their_side": []}
    dumps = dict(plain, their_rap=300, projected_given=1)
    for t in (plain, dumps):
        picker.add(t)
    # Bigger RAP gain loses on Pick Trade By, but gives away a projected item
    assert picker.pick() is dumps


def test_prioritize_sending_projecteds_config(tmp_path):
    from handler.handle_config import ConfigHandler

    cfg = tmp_path / "c.cfg"
    cfg.write_text("[Projected]\n")
    assert ConfigHandler(str(cfg)).projected_detection["Prioritize_Sending_Projecteds"] is True
    cfg.write_text("[Projected]\nPrioritize Sending Projecteds = False\n")
    assert ConfigHandler(str(cfg)).projected_detection["Prioritize_Sending_Projecteds"] is False


def test_generated_trade_gives_away_projected_item():
    from handler.handle_config import ConfigHandler
    from trade_algorithm import TradeMaker

    maker = TradeMaker(ConfigHandler("configs/small_value.cfg"))
    for name in (
        "min_rap_gain max_rap_gain min_overall_gain max_overall_gain min_algo_gain "
        "max_algo_gain min_value_gain max_value_gain min_rap_score_percentage "
        "max_rap_score_percentage min_overall_score_percentage "
        "max_overall_score_percentage max_valid_trades"
    ).split():
        setattr(maker, name, None)
    maker.min_value_of_trade = maker.min_rap_of_trade = 0
    maker.min_items_self = maker.min_items_their = 1
    maker.max_items_self = 1
    maker.max_items_their = 2
    maker.trade_robux = False
    maker.trade_timeout = 10
    maker.outbound_variety = 0
    maker.select_by = "highest_overall_gain"

    def item(item_id, value, projected=False):
        return {"item_id": item_id, "value": value, "rap": value, "demand": 2,
                "rap_algorithm": value, "total_value": value, "item_volume": 5,
                "projected": projected}

    # Giving the 900 is the bigger gain, but the 1000 is projected
    mine = {"proj": item("10", 1000, projected=True), "plain": item("11", 900)}
    theirs = {"x": item("20", 1500), "y": item("21", 100)}

    maker.prioritize_projected = True
    trade = maker.generate_trade(mine, theirs)
    assert trade, maker.last_failed
    assert trade["self_side"] == ("proj",)
    maker.prioritize_projected = False
    assert maker.generate_trade(mine, theirs)["self_side"] == ("plain",)
