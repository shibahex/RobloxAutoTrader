"""
Offline tests for the error system. No network: every request goes through
the `router` fixture's fake responses.
"""

import threading
import os
import types

import pytest
import requests

from conftest import FAKE_CATALOG, make_response as resp

from handler import exceptions_types as E
from handler.handle_requests import RequestsHandler

U = "https://api.test/"
SEND = "https://trades.roblox.com/v2/trades/send"
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
        resp(401, {"errors": [{"code": 0, "message": "Authorization has been denied"}]}),
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
        resp(403, {"errors": [{"code": 0, "message": "x"}]}, headers={"rblx-challenge-id": "c"}),
    )
    solved = []
    account.validate_2fa = lambda r: solved.append(1) or {}
    with pytest.raises(E.ChallengeRequired):
        account.send_trade(2, ["a"], ["b"])
    # 3 sends, but no pointless solve after the last one
    assert len([c for c in router.calls if c[1] == SEND]) == roblox_api.SEND_TRADE_ATTEMPTS == 3
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
        resp(429, {"errors": [{"code": 0, "message": "You are sending too many trade requests"}]}),
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
    return acc


def test_send_trade_success(router, account):
    router.set(SEND, resp(200, {"tradeId": 77}))
    assert account.send_trade(2, ["a"], ["b"]) == 77


def test_send_trade_insufficient_robux_refreshes_but_does_not_resend(router, account):
    """Resending with different robux would no longer match the logged trade."""
    router.set(SEND, resp(400, {"errors": [{"code": 17, "message": "robux"}]}), resp(200, {"tradeId": 5}))
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
            headers={"rblx-challenge-id": "c", "rblx-challenge-metadata": "not-base64!!"},
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
    challenge = resp(403, {"errors": [{"code": 0, "message": "x"}]}, headers={"rblx-challenge-id": "c"})
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
    router.set("https://www.rolimons.com/catalog", resp(200, text="<html>changed</html>"))
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
        generate_trade=lambda a, b: {"self_side": ["u1"], "their_side": ["t1"], "self_robux": 0}
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
    doggo.rolimons.return_item_to_scan = lambda: {"original_asset_id": 1}
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


@pytest.mark.parametrize("setting_on", [True, False])
def test_outbound_rolimons_projected_flag_respects_setting(router, outbound, setting_on):
    outbound.config.projected_detection["Detect_Rolimons_Projecteds"] = setting_on
    outbound.rolimon.item_data["1:1"]["projected"] = True
    outbound._check_one_outbound(55)
    assert bool(declined(router)) is setting_on


def test_outbound_rescans_stale_item_before_judging(router, outbound):
    # Algo value is days old; a fresh scan finds the price collapsed
    outbound.rolimon.projected_json.write_data(
        {"1:1": {"is_projected": False, "value": 1000, "timestamp": 0, "collectible_item_id": "abc"}}
    )
    scanned = []

    def fresh_scan(collectibleId, item_id):
        scanned.append((collectibleId, item_id))
        data = outbound.rolimon.projected_json.read_data()
        data[item_id] = {"is_projected": True, "value": 300, "timestamp": 9e18, "collectible_item_id": "abc"}
        outbound.rolimon.projected_json.write_data(data)

    outbound.is_projected_api = fresh_scan
    outbound._check_one_outbound(55)
    assert scanned == [("abc", "1:1")]
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_outbound_does_not_rescan_fresh_items(router, outbound):
    import time as time_module

    outbound.rolimon.projected_json.write_data(
        {"1:1": {"is_projected": False, "value": 1000, "timestamp": time_module.time(), "collectible_item_id": "abc"}}
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
        {"1:1": {"is_projected": False, "value": 1000, "timestamp": 0, "collectible_item_id": "abc"}}
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
    config_changed._evaluate_outbound(55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD)
    assert declined(router) == []


def test_old_trade_that_turns_losing_is_cancelled(router, config_changed):
    config_changed.rolimon.item_data["1:1"]["total_value"] = 100  # receive side crashed
    config_changed._evaluate_outbound(55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_old_trade_losing_because_of_robux_is_cancelled(router, config_changed):
    trade = outbound_trade_json(["1:2"], ["1:1"])
    trade["participantAOffer"]["robux"] = 600  # 1000 - 600 - 600 robux < 0
    config_changed._evaluate_outbound(55, trade, False, created=OLD)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_old_trade_receiving_projected_is_still_cancelled(router, config_changed):
    config_changed.rolimon.projected_json.write_data({"1:1": {"is_projected": True}})
    config_changed._evaluate_outbound(55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_new_trade_uses_full_rules(router, config_changed):
    config_changed._evaluate_outbound(55, outbound_trade_json(["1:2"], ["1:1"]), False, created=NEW)
    assert declined(router) == [DECLINE_URL + "55/decline"]


def test_option_off_uses_full_rules_for_old_trades(router, config_changed):
    config_changed.config.outbound["Only_Cancel_Losing_After_Config_Change"] = False
    config_changed._evaluate_outbound(55, outbound_trade_json(["1:2"], ["1:1"]), False, created=OLD)
    assert declined(router) == [DECLINE_URL + "55/decline"]


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
        resp(200, {"data": [{"id": 55, "user": {"id": 2}, "created": "2026-11-01T12:00:00.123Z"}], "nextPageCursor": None}),
    )
    outbound.outbound_api_checker()
    from datetime import datetime, timezone

    expected = datetime(2026, 11, 1, 12, 0, 0, 123000, tzinfo=timezone.utc).timestamp()
    assert outbound.outbound_cache[55]["created"] == expected


# --- account config editor ------------------------------------------------------

from handler.account_settings import (  # noqa: E402
    HandleConfigs,
    coerce_config_value,
    parse_config_value,
)


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("100", 100),
        (" 100 ", 100),
        ("-5", -5),
        ("0.25", 0.25),
        ("None", None),
        ("none", None),
        ("null", None),
        ("True", True),
        ("false", False),
        ("rap_algo", "rap_algo"),
    ],
)
def test_parse_config_value(typed, expected):
    value = parse_config_value(typed)
    assert value == expected and type(value) is type(expected)


@pytest.mark.parametrize(
    "value, expected_type, result",
    [
        (100, int, 100),
        (100.0, int, 100),
        (None, int, None),
        (0.1, float, 0.1),
        (100, float, 100),
        (None, float, None),
        (True, bool, True),
        ("x", None, "x"),
    ],
)
def test_coerce_accepts(value, expected_type, result):
    assert coerce_config_value(value, expected_type) == result


@pytest.mark.parametrize(
    "value, expected_type",
    [("abc", int), (2.5, int), (True, int), ("yes", bool), (None, bool), (None, str), (1, bool)],
)
def test_coerce_rejects(value, expected_type):
    with pytest.raises(ValueError):
        coerce_config_value(value, expected_type)


@pytest.fixture
def configs(monkeypatch):
    h = HandleConfigs()
    h.default_config = {
        "MaxRobux": 100,
        "Minimum_RAP_Gain": 50.0,
        "Maximum_RAP_Gain": None,
        "TradeForFaces": True,
        "Rap_Algo_For_Valued": "rap_algo",
    }
    return h


def edit(configs, monkeypatch, key, typed, current):
    data = {key: current}
    monkeypatch.setattr("builtins.input", lambda _prompt: typed)
    configs.prompt_and_update(data, key)
    return data[key]


@pytest.mark.parametrize(
    "key, typed, current, result",
    [
        ("MaxRobux", "100", 5, 100),  # the reported bug: stays a number
        ("MaxRobux", "100", None, 100),  # current None no longer means "text"
        ("MaxRobux", "None", 5, None),  # None supported
        ("Maximum_RAP_Gain", "0.5", None, 0.5),
        ("Minimum_RAP_Gain", "none", 50.0, None),
        ("TradeForFaces", "false", True, False),  # was saved as truthy "false"
        ("Rap_Algo_For_Valued", "zero_value", "rap_algo", "zero_value"),
        ("MaxRobux", "abc", 5, 5),  # invalid keeps the old value
        ("MaxRobux", "2.5", 5, 5),
        ("TradeForFaces", "None", True, True),
        ("MaxRobux", "", 5, 5),  # enter keeps the old value
    ],
)
def test_prompt_and_update(configs, monkeypatch, key, typed, current, result):
    value = edit(configs, monkeypatch, key, typed, current)
    assert value == result and type(value) is type(result)


def test_get_config_repairs_values_saved_as_text(configs):
    configs.acc_configs.write_data(
        {"7": {"MaxRobux": "100", "Maximum_RAP_Gain": "None", "TradeForFaces": "False", "Rap_Algo_For_Valued": "rap_algo"}}
    )
    assert configs.get_config("7") == {
        "MaxRobux": 100,
        "Maximum_RAP_Gain": None,
        "TradeForFaces": False,
        "Rap_Algo_For_Valued": "rap_algo",
    }
