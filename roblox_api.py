import requests
from datetime import datetime, timedelta
import time
import threading
import pyotp
import json
import base64
import hashlib
import rolimons_api
from handler.handle_requests import RequestsHandler
from handler.counter_history import CounterHistory, trade_signature
from handler.handle_discord import DiscordHandler
from handler.handle_config import ConfigHandler, on_item_list
from handler.owner_pages import OwnerPages
from handler.handle_json import JsonHandler
from handler.handle_2fa import AuthHandler
from trade_algorithm import (
    TradeMaker,
    failed_field,
    failed_text,
    gains_table,
    reason_text,
    trade_lines,
)
from handler.account_settings import HandleConfigs
from handler.handle_logs import log
from handler import exceptions_types
from handler.exceptions_types import (
    short_error,
    TradebotError,
    RobloxAPIError,
    BadRequest,
    ChallengeRequired,
    CookieInvalid,
    Forbidden,
    NotFound,
    InvalidResponse,
    InventoryUnavailable,
    InsufficientRobux,
    ItemsUnavailable,
    RateLimited,
    TradeRejected,
    TwoFactorError,
    UnknownItem,
    UserCannotTrade,
)
from handler.price_algorithm import SalesVolumeAnalyzer

SECONDS_IN_DAY = 86400
SELF_INVENTORY_ATTEMPTS = 3
SEND_TRADE_ATTEMPTS = 3
# Outbound checker re-scans an item's price history if it's older than this
OUTBOUND_RESCAN_AGE_SECONDS = 6 * 60 * 60
SECONDS_PER_DAY = 86400
# account id -> {trade id: [config fingerprint, sent at]} for trades the bot sent
SENT_CONFIGS_FILE = "outbound_sent_configs.json"
_sent_configs_lock = threading.Lock()

# Roblox trade error codes
TRADE_CODE_ITEMS_UNAVAILABLE = 12
TRADE_CODE_INSUFFICIENT_ROBUX = 17


def read_json(response):
    """response.json() that raises InvalidResponse instead of a bare ValueError."""
    try:
        return response.json()
    except ValueError as e:
        raise InvalidResponse(f"Response wasn't JSON: {e}", response.url) from e


def parse_created(created) -> float | None:
    """Roblox ISO time ("2026-11-01T12:00:00.123Z") to a unix timestamp, or None."""
    if not created:
        return None
    try:
        return datetime.fromisoformat(str(created).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def price_swing_is_projected(current, past, max_rise, max_drop) -> bool:
    """
    [Projected] Max Price Rise / Max Price Drop. Compares the typical price
    (see typical_price) with today's:
      max_rise  how far BELOW today it can be (price went up since)
      max_drop  how far ABOVE today it can be, as a negative number
    Between -1 and 1 = a share of today's price (0.4 = 40%); otherwise Robux.
    None skips that direction. Defaults 0.4 / -0.4.
    """

    def change(limit):
        return (current - past) / current if abs(limit) < 1 else current - past

    if max_rise is not None and change(max_rise) > max_rise:
        return True
    return max_drop is not None and change(max_drop) < max_drop


def typical_price(prices) -> float | None:
    """
    The median of the daily prices: what the item usually sells for. One-day
    spikes or dips (a single big sale) don't move it, so an item whose price
    went back to normal isn't projected.
    """
    prices = sorted(prices)
    if not prices:
        return None
    middle = len(prices) // 2
    return prices[middle] if len(prices) % 2 else (prices[middle - 1] + prices[middle]) / 2


class RobloxAPI:
    """
    Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie: dict = None, auth_secret=None, Proxies=False):
        self.all_cached_traders = set()
        # trade_id -> trade JSON of our open outbounds, so they can be re-priced
        # on every Rolimons update without calling Roblox again
        self.outbound_cache = {}
        self.outbound_lock = threading.Lock()
        # (sent at, our instance ids) for trades sent since the last outbound
        # check; they aren't in outbound_cache yet (see offered_item_counts)
        self.sent_since_check = []
        # When this account's trading config last changed (see _config_changed_at)
        self.config_changed_at = None
        self.auth_secret = auth_secret
        # Rolimons verification cookie for [Trade Ads], set from cookies.json
        self.rolimons_cookie = None
        # 0 = check inbounds as soon as the bot starts
        self.counter_timer = 0
        # Accepted inbounds already posted to the Completed webhook
        self.posted_accepts = set()

        self.account_configs = HandleConfigs()

        self.json = JsonHandler("cookies.json")
        # TODO: USE PROXIES
        self.parse_handler = RequestsHandler(
            Session=requests.Session(), use_proxies=False
        )
        self.config = ConfigHandler("config.cfg")
        self.rolimon = rolimons_api.RolimonAPI()
        self.discord_webhook = DiscordHandler()
        self.last_sent_trade = time.time()
        self.last_generated_csrf_timer = time.time()
        self.cookies = None
        if cookie is not None:
            self.cookies = cookie
            self.last_completed_scanned = self.json.get_last_completed(
                cookie[".ROBLOSECURITY"]
            )

            self.authenticator = pyotp.TOTP(self.auth_secret)
            self.request_handler = RequestsHandler(
                cookie=self.cookies, use_proxies=False, Session=requests.Session()
            )
            self.auth_handler = AuthHandler()
            self.account_id, self.username = self.fetch_userid_and_name()

            # This account's own settings over config.cfg's
            self.account_configs.apply(self.config, self.account_id)
            self.trade_maker = TradeMaker(config=self.config)
            self.outbound_trader = TradeMaker(
                config=self.config, is_outbound_checker=True
            )
            # Inbound trades use the [Inbound Settings] gains, when set
            inbound_gains = self.config.inbounds.get("Gains")
            self.inbound_trader = TradeMaker(
                config=self.config, is_inbound_checker=True, gains=inbound_gains
            )
            self.counter_maker = TradeMaker(config=self.config, gains=inbound_gains)
            # Counters we sent are judged by the inbound gains, not the trading ones
            self.counter_checker = TradeMaker(
                config=self.config, is_outbound_checker=True, gains=inbound_gains
            )
            self.counter_history = CounterHistory(
                account_id=self.account_id,
                memory_hours=self.config.inbounds["Counter_Memory_Hours"],
            )

            # log("getting self")
            self.self_duplicates = {}
            self.account_inventory = None
            try:
                self.refresh_self_inventory()
            except InventoryUnavailable as e:
                # Not fatal: the trading loop refreshes it again every round
                log(
                    f"[ACCOUNT] Couldn't load {self.username}'s inventory yet, will retry: {e.cause}",
                    severityNum=2,
                )

            self.account_robux = 0
            self.get_robux()

            try:
                self.check_completeds()
            except TradebotError as e:
                log(
                    f"[ACCOUNT] Couldn't check completed trades for {self.username}: {e}",
                    severityNum=2,
                )

            self.request_handler.generate_csrf()
            self.last_generated_csrf_timer = time.time()

    def check_premium(self, userid):
        """
        checks if the account is premium
        Raises RobloxAPIError/NetworkError if Roblox can't be asked.
        """
        premium_api = (
            f"https://premiumfeatures.roblox.com/v1/users/{userid}/validate-membership"
        )
        response = self.request_handler.requestAPI(premium_api)
        return response.text.strip().lower() == "true"

    # refresh current inventory
    def refresh_self_inventory(self):
        """
        Gets inventory of current .ROBLOSECURITY used on class.
        Returns False if the account has no tradeable items.
        Raises InventoryUnavailable if it can't be loaded after a few tries.
        """
        last_error = None
        for attempt in range(1, SELF_INVENTORY_ATTEMPTS + 1):
            self.self_duplicates = {}
            try:
                self.account_inventory = self.fetch_inventory(self.account_id)
            except InventoryUnavailable as e:
                last_error = e
                log(
                    f"[ACCOUNT] Couldn't get {self.username}'s inventory (try {attempt}/{SELF_INVENTORY_ATTEMPTS}): {e.cause}",
                    severityNum=2,
                )
                if attempt < SELF_INVENTORY_ATTEMPTS:
                    time.sleep(10 * attempt)
                continue

            # NOTE: False = no tradeable inventory
            if self.account_inventory is False:
                log(f"[TRADING] {self.username} has no items it can trade")
                return False
            return self.account_inventory

        self.account_inventory = None
        raise InventoryUnavailable(
            self.account_id, last_error.cause if last_error else None
        )

    def fetch_userid_and_name(self):
        """
        Gets info on the current account to self class.
        Raises CookieInvalid if the cookie doesn't log in.
        """
        url = "https://users.roblox.com/v1/users/authenticated"
        try:
            auth_response = self.request_handler.requestAPI(url)
        except (Forbidden, exceptions_types.AuthError) as e:
            raise CookieInvalid(e.response, f"Couldn't log in with cookie: {e}") from e

        data = read_json(auth_response)
        try:
            return data["id"], data["name"]
        except (KeyError, TypeError) as e:
            raise InvalidResponse(
                f"No id/name in authenticated user response: {e}", url
            ) from e

    def fetch_inventory(self, userid, max_owned=None, max_from_trader=None):
        """
        Returns a dict of items from the user, will return False if there no scrapable items.
        Raises InventoryUnavailable if the inventory is private or the API keeps failing.
        max_owned / max_from_trader: duplicate limits to use instead of
        [Filtering Items] (counters use the [Inbound Settings] ones).
        """
        filters = self.config.filter_items
        if max_owned is None:
            max_owned = filters["Maximum_Amount_of_Duplicate_Items"]
        if max_from_trader is None:
            max_from_trader = filters["Maximum_Amount_of_Trader_Duplicate_Items"]

        def add_to_duplicates(duplicates: dict, itemId: str):
            if itemId not in duplicates:
                duplicates[itemId] = 0
            else:
                duplicates[itemId] += 1
            return duplicates

        cursor = ""
        inventory = {}

        trader_duplicates = {}

        is_self = False

        # Without Rolimons data every item would be skipped and the inventory
        # would look empty, which benches the account. Fail loudly instead.
        if not self.rolimon.item_data:
            try:
                self.rolimon.update_data()
            except exceptions_types.RolimonsError as e:
                raise InventoryUnavailable(userid, e) from e

        while cursor is not None:
            # NOTE: 100 sometimes has internal server error.
            inventory_API = f"https://trades.roblox.com/v2/users/{userid}/tradableItems?sortBy=CreationTime&sortOrder=2&limit=50&cursor={cursor}"

            try:
                page = read_json(self.request_handler.requestAPI(inventory_API))
                cursor = page.get("nextPageCursor")
                items = page["items"]
            except (
                RobloxAPIError,
                exceptions_types.NetworkError,
                InvalidResponse,
            ) as e:
                raise InventoryUnavailable(userid, e) from e
            except (KeyError, AttributeError) as e:
                raise InventoryUnavailable(
                    userid, InvalidResponse(f"Bad inventory page: {e}", inventory_API)
                ) from e

            for item in items:
                try:
                    itemId = str(item["itemTarget"]["targetId"])
                    collectibleItemId = item["collectibleItemId"]
                    item_type = item["itemTarget"]["itemType"]
                except (KeyError, TypeError) as e:
                    log(
                        f"Skipping malformed inventory item {item}: {e}", dontPrint=True
                    )
                    continue

                # Check if item is bundle or not for the new rolimons format
                if item_type == "Bundle":
                    itemId = "2:" + itemId
                else:
                    itemId = "1:" + itemId

                item_data = self.rolimon.item_data.get(itemId)
                if item_data is None:
                    if self.config.debug["show_scanning_inventory"]:
                        log(f"[INVENTORY] {itemId} isn't on Rolimons yet, skipping it", dontPrint=True)
                    continue
                current_demand = item_data["demand"]

                # Resolve instance ID
                instances = item.get("instances")
                if isinstance(instances, list):
                    instance = instances[0] if instances else None
                else:
                    instance = instances

                if not instance:
                    continue

                if instance.get("isOnHold"):
                    continue

                uaid = str(instance.get("collectibleItemInstanceId"))

                # Check for duplicates
                if str(userid) == str(self.account_id):
                    self.self_duplicates = add_to_duplicates(
                        self.self_duplicates, itemId
                    )
                else:
                    trader_duplicates = add_to_duplicates(trader_duplicates, itemId)

                if str(userid) == str(self.account_id):
                    is_self = True
                    nft_list = self.config.filter_items["NFT"]

                    if on_item_list(itemId, nft_list):
                        if self.config.debug["show_scanning_inventory"]:
                            log(f"[INVENTORY] {itemId} is in your Never Give list, skipping it")
                        continue

                    inventory[uaid] = {
                        "item_id": itemId,
                        "collectibleItemId": collectibleItemId,
                    }
                else:
                    # Dont trade for faces or gears depending on the config
                    asset_type = item_data.get("asset_type")
                    if (
                        asset_type == "asset:18"
                        and not self.config.trading["TradeForFaces"]
                    ):
                        continue
                    if (
                        asset_type == "asset:19"
                        and not self.config.trading["TradeForGears"]
                    ):
                        continue

                    if (
                        current_demand is not None
                        and int(current_demand) < self.config.filter_items["MinDemand"]
                    ):
                        continue

                    if (
                        str(itemId) in self.self_duplicates
                        and self.self_duplicates[str(itemId)] >= max_owned
                    ):
                        if self.config.debug["show_scanning_inventory"]:
                            log(
                                f"[INVENTORY] {userid}: not trading for {itemId} (duplicates setting)"
                            )
                        continue

                    if (
                        str(itemId) in trader_duplicates
                        and trader_duplicates[str(itemId)] > max_from_trader
                    ):
                        if self.config.debug["show_scanning_inventory"]:
                            log(
                                f"[INVENTORY] {userid}: not trading for another {itemId}"
                            )
                        continue

                    nfr_list = self.config.filter_items["NFR"]
                    if not on_item_list(itemId, nfr_list):
                        inventory[uaid] = {
                            "item_id": itemId,
                            "collectibleItemId": collectibleItemId,
                        }
                    else:
                        if self.config.debug["show_scanning_inventory"]:
                            log(f"[INVENTORY] {itemId} is in your Never Receive list, skipping it")

        minimum_items = self.config.filter_users["Minimum_Total_Items"]
        if not is_self:
            if len(inventory.keys()) < minimum_items:
                if self.config.debug["show_scanning_inventory"]:
                    log(f"[INVENTORY] {userid} doesn't have enough tradeable items", dontPrint=True)

                return False

        if inventory == {}:
            return False

        return self.rolimon.add_data_to_inventory(inventory, is_self=is_self)

    def validate_2fa(self, response):
        """
        Takes a response that has a 2FA challenge and solves it.
        Returns the headers to resend the request with.
        Raises TwoFactorError if it can't be solved.
        """
        try:
            challengeid = response.headers["rblx-challenge-id"]
            metadata = json.loads(
                base64.b64decode(response.headers["rblx-challenge-metadata"])
            )
            metadata_challengeid = metadata["challengeId"]
            senderid = metadata["userId"]
        except (KeyError, TypeError, ValueError) as e:
            # ValueError covers bad base64 and bad JSON
            raise TwoFactorError(
                f"Couldn't read 2FA challenge from {response.url}: {e}; headers {response.headers}"
            ) from e

        # send the totp verify request to roblox
        verification_token = self.auth_handler.verify_request(
            self.request_handler, senderid, metadata_challengeid, self.authenticator
        )

        # send the continue request, its really important
        self.auth_handler.continue_request(
            self.request_handler, challengeid, verification_token, metadata_challengeid
        )

        return {
            "rblx-challenge-id": challengeid,
            "rblx-challenge-metadata": base64.b64encode(
                json.dumps(
                    {
                        "rememberdevice": True,
                        "actiontype": "generic",
                        "verificationtoken": verification_token,
                        "challengeid": metadata_challengeid,
                    }
                ).encode()
            ).decode(),
            "rblx-challenge-type": "twostepverification",
        }

    def return_trade_details(self, data):
        """
        For APIs like inbounds, outbounds and inactive, scrapes the data and returns it formatted
        """
        trades = {}
        for trade in data:
            trade_id = trade.get("id", None)
            created = trade.get("created", None)
            user = trade.get("user", None)
            if user is None:
                continue
            user_id = user.get("id", None)

            if trade_id is None or user_id is None or created is None:
                continue

            trades[trade["id"]] = {
                "trade_id": trade["id"],
                "user_id": trade["user"]["id"],
                "created": trade["created"],
            }
        return trades

    def get_trades(self, page_url, limit_pages=None) -> dict:
        """
        Get every trade_id from trade pages from APIs: inbounds, outbounds and inactive
        Make sure cursor isn't in the URL arg as the func adds it for you
        Raises RobloxAPIError/NetworkError/InvalidResponse if a page can't be loaded.
        """
        if self.cookies is None:
            return {}

        cursor = ""
        page_count = 0
        trades = {}
        while cursor is not None:
            if limit_pages and page_count >= limit_pages:
                break

            # Assuming the URL already has page limit = 100
            url = f"{page_url}&cursor={cursor}"
            page = read_json(self.request_handler.requestAPI(url))
            try:
                data = page.get("data") or []
                cursor = page.get("nextPageCursor")
            except AttributeError as e:
                raise InvalidResponse(f"Bad trades page: {e}", url) from e

            trades.update(self.return_trade_details(data))
            page_count += 1

        return trades

    def handle_inbounds(self, accept=True, counter=True) -> dict:
        """
        Goes through every inbound trade in three steps:
          1. scan: load every inbound and check which ones pass the config
          2. accept: accept the passing ones biggest overall win first, since
             accepting one usually moves items the other inbounds asked for
          3. counter: keep, counter or decline the ones that weren't accepted
        Returns how many were accepted/countered/declined/kept.
        A TradeLimit stops countering but accepting carries on; it's re-raised
        at the end so the caller can record the limit. CookieInvalid is raised
        right away; other errors only skip the trade they happened on.
        """
        results = {"accepted": 0, "countered": 0, "declined": 0, "kept": 0}
        if not accept and not counter:
            return results
        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/inbound?limit=100&sortOrder=Desc"
        )

        scanned = []
        for trade_info in trades.values():
            trade_id = trade_info["trade_id"]
            try:
                scanned.append(
                    self._scan_inbound(
                        trade_id,
                        trade_info["user_id"],
                        accept,
                        created=parse_created(trade_info.get("created")),
                    )
                )
            except CookieInvalid:
                raise
            except TradebotError as e:
                log(
                    f"[INBOUND] Skipping trade {trade_id}: {short_error(e)}",
                    severityNum=2,
                )

        leftover = self._accept_best_inbounds(scanned, results) if accept else scanned

        if results["accepted"]:
            try:
                self.refresh_self_inventory()
            except InventoryUnavailable as e:
                log(
                    f"[INBOUND] Couldn't reload inventory after accepting: {e}",
                    severityNum=2,
                )

        trade_limit = None
        for inbound in leftover:
            try:
                outcome = self._counter_inbound(inbound, counter)
            except exceptions_types.TradeLimit as e:
                log(f"[INBOUND] Trade limit hit, not countering anymore: {e}")
                trade_limit = e
                counter = False
                continue
            except CookieInvalid:
                raise
            except TradebotError as e:
                log(
                    f"[INBOUND] Skipping trade {inbound['trade_id']}: {short_error(e)}",
                    severityNum=2,
                )
                continue
            if outcome in results:
                results[outcome] += 1

        if trade_limit is not None:
            raise trade_limit
        return results

    def _scan_inbound(self, trade_id, trader_id, accept, created=None) -> dict:
        """
        Loads one inbound and works out whether it can be accepted.
        created: when they sent it (a timestamp), to spot instant counter-backs.
        """
        trade_json = read_json(
            self.request_handler.requestAPI(
                f"https://trades.roblox.com/v2/trades/{trade_id}"
            )
        )
        trade = self.format_trade_api(trade_json)
        reply = self.counter_history.note_inbound(trader_id, trade_id, created)
        if reply is not None:
            log(
                f"[INBOUND] {trader_id} countered back {reply:.0f}s after our counter",
                dontPrint=True,
            )

        reason = "Accept Good Trades is off"
        if accept:
            reason = self._inbound_reject_reason(trade)
            # Accepting can't be undone: make sure prices are fresh, then re-check
            if reason is None and self._rescan_stale_items(
                trade["their_side_item_ids"]
            ):
                trade = self.format_trade_api(trade_json)
                reason = self._inbound_reject_reason(trade)
            if reason is not None:
                log(
                    f"[INBOUND] Not accepting {trade_id}: {reason_text(reason)}",
                    dontPrint=True,
                )
        return {
            "trade_id": trade_id,
            "trader_id": trader_id,
            "trade": trade,
            "instance_ids": self._our_instance_ids(trade_json),
            "reason": reason,
        }

    def _our_instance_ids(self, trade_json) -> set:
        """Instance ids of the items we'd give in this trade (empty if Roblox left them out)."""
        account_id = str(getattr(self, "account_id", None))
        for key in ("participantAOffer", "participantBOffer"):
            offer = trade_json.get(key) or {}
            if str((offer.get("user") or {}).get("id")) == account_id:
                return {
                    str(item["collectibleItemInstanceId"])
                    for item in offer.get("items") or []
                    if item.get("collectibleItemInstanceId")
                }
        return set()

    def _accept_best_inbounds(self, scanned, results) -> list:
        """
        Accepts the inbounds that passed the config, biggest overall win first.
        Skips ones that need an item a better trade already took, and re-checks
        duplicate limits as items come in. Returns the inbounds left to counter.
        """
        passing = [i for i in scanned if i["reason"] is None]
        passing.sort(key=lambda i: self._overall_profit(i["trade"]), reverse=True)
        leftover = [i for i in scanned if i["reason"] is not None]
        given_away = set()

        for inbound in passing:
            trade_id, trade = inbound["trade_id"], inbound["trade"]
            if inbound["instance_ids"] & given_away:
                log(
                    f"[INBOUND] Skipping {trade_id}: a bigger win already took "
                    "items it asks for",
                    dontPrint=True,
                )
                continue
            if results["accepted"]:  # items we just received can hit duplicate limits
                reason = self._inbound_reject_reason(trade)
                if reason is not None:
                    inbound["reason"] = reason
                    leftover.append(inbound)
                    continue
            try:
                if not self._accept_trade(trade_id):
                    continue
            except CookieInvalid:
                raise
            except TradebotError as e:
                log(
                    f"[INBOUND] Skipping trade {trade_id}: {short_error(e)}",
                    severityNum=2,
                )
                continue

            results["accepted"] += 1
            given_away |= inbound["instance_ids"]
            # same counting as fetch_inventory: first copy is 0, each extra +1
            for item_id in map(str, trade["their_side_item_ids"]):
                owned = self.self_duplicates.get(item_id)
                self.self_duplicates[item_id] = 0 if owned is None else owned + 1
            log(
                f"[INBOUND] Accepted trade {trade_id} from {inbound['trader_id']} "
                f"(overall {self._overall_profit(trade):+})"
            )
            if self.post_trade_webhook(
                "Completed_Webhook",
                trade,
                "Accepted an inbound trade ({profit} profit)",
                color=2,
            ):
                self.posted_accepts.add(str(trade_id))
        return leftover

    def _counter_inbound(self, inbound, counter) -> str:
        """
        Keeps, counters or declines an inbound that wasn't accepted.
        Returns "countered", "declined", "kept" or "failed".
        """
        trade_id, trader_id = inbound["trade_id"], inbound["trader_id"]
        trade, reason = inbound["trade"], inbound["reason"]

        profit = self._overall_profit(trade)
        receiving_projected = self._projected_items(trade["their_side_item_ids"])
        if profit > 0 and not receiving_projected:
            if self.config.inbounds["Dont_Counter_Wins"] or not counter:
                log(
                    f"[INBOUND] Keeping {trade_id}, it's an overall win (+{profit})",
                    dontPrint=True,
                )
                return "kept"

        if not counter:
            return "kept"

        loop = self._counter_loop_reason(trader_id)
        if loop:
            if not self._decline_trade(trade_id):
                return "failed"
            log(
                f"[INBOUND] Declined {trade_id} from {trader_id}: {loop}\n"
                f"Not accepted: {reason_text(reason)}"
            )
            self.post_trade_webhook(
                "Send_Webhook",
                trade,
                "Declined a trade: counter loop ({profit} profit)",
                color=0,
                extra_fields={
                    "Not accepted": (reason_text(reason), False),
                    "Why no counter": (loop[0].upper() + loop[1:], False),
                },
            )
            return "declined"

        outcome = self._counter_trade(trade_id, trader_id, trade)
        if outcome == "declined":
            failed = getattr(self.counter_maker, "last_failed", None) or {}
            log(
                f"[INBOUND] Declined {trade_id} from {trader_id}: no counter passed "
                f"your config\nNot accepted: {reason_text(reason)}\n"
                + failed_text(failed)
            )
            self.post_trade_webhook(
                "Send_Webhook",
                trade,
                "Declined a trade: no counter passed your gains ({profit} profit)",
                color=0,
                extra_fields={
                    "Not accepted": (reason_text(reason), False),
                    "Why no counter": (failed_field(failed), False),
                },
            )
        return outcome

    @staticmethod
    def _overall_profit(trade) -> int:
        """Overall value we gain, counting robux on both sides."""
        return (
            trade["their_overall_value"]
            + (trade.get("their_robux") or 0)
            - trade["self_overall_value"]
            - (trade.get("self_robux") or 0)
        )

    def _too_many_duplicates(self, item_ids, limit=None):
        """
        First item we'd receive that we already own too many of, or None.
        limit: extra copies allowed (default [Filtering Items]).
        """
        if limit is None:
            limit = self.config.filter_items["Maximum_Amount_of_Duplicate_Items"]
        for item_id in item_ids:
            owned = self.self_duplicates.get(str(item_id))
            if owned is not None and limit is not None and owned >= limit:
                return item_id
        return None

    def _inbound_item_filter_reason(self, item_ids, max_copies=None):
        """
        The same item filters our own trades use (fetch_inventory and
        add_data_to_inventory), applied to what we'd receive: NFR list, faces and
        gears, minimum demand, sales volume and gaps for RAP items, and how many
        copies of one item we'd take from them.
        """
        filters = self.config.filter_items
        trading = self.config.trading
        nfr = filters.get("NFR") or []
        min_demand = filters.get("MinDemand")
        min_sales = filters.get("MinDailySales")
        max_gap = filters.get("MaxSalesGap")
        if max_copies is None:
            max_copies = filters.get("Maximum_Amount_of_Trader_Duplicate_Items")
        projected_data = self.rolimon.projected_json.read_cached()

        for item_id in set(map(str, item_ids)):
            item = self.rolimon.item_data.get(item_id) or {}
            if on_item_list(item_id, nfr):
                return f"{item_id} is on the Never Receive list"
            if item.get("asset_type") == "asset:18" and not trading.get(
                "TradeForFaces"
            ):
                return f"{item_id} is a face (Receive Faces is off)"
            if item.get("asset_type") == "asset:19" and not trading.get(
                "TradeForGears"
            ):
                return f"{item_id} is a gear (Receive Gears is off)"
            demand = item.get("demand")
            if (
                isinstance(min_demand, int)
                and demand is not None
                and int(demand) < min_demand
            ):
                return f"{item_id} demand {demand} is below {min_demand}"

            if not item.get("value"):  # RAP items need proof they actually sell
                scan = projected_data.get(item_id) or {}
                volume, gap = scan.get("volume"), scan.get("average_gap")
                if volume is None:
                    return f"{item_id} has no sales data yet"
                if isinstance(min_sales, (int, float)) and float(volume) < min_sales:
                    return f"{item_id} sells {volume}/day, below {min_sales}"
                if (
                    isinstance(max_gap, (int, float))
                    and gap is not None
                    and float(gap) > max_gap
                ):
                    return f"{item_id} sales gap {gap} is above {max_gap}"

        if isinstance(max_copies, int):
            ids = [str(i) for i in item_ids]
            for item_id in set(ids):
                # same rule as fetch_inventory: the first copy plus max_copies more
                if ids.count(item_id) > max_copies + 1:
                    return f"too many copies of {item_id} from one trader"
        return None

    def _inbound_reject_reason(self, trade):
        """Why an inbound shouldn't be accepted, or None if it passes the config."""
        if trade.get("self_robux"):
            return f"asks for {trade['self_robux']} robux"

        projected = self._projected_items(trade["their_side_item_ids"])
        if projected:
            return f"receiving projected {projected}"

        inbounds = self.config.inbounds
        duplicate = self._too_many_duplicates(
            trade["their_side_item_ids"], inbounds["Max_Duplicates"]
        )
        if duplicate is not None:
            return f"too many duplicates of {duplicate}"

        filtered = self._inbound_item_filter_reason(
            trade["their_side_item_ids"], inbounds["Max_Trader_Duplicates"]
        )
        if filtered:
            return filtered

        valid, reason = self.inbound_trader.validate_trade(
            self_rap=trade["self_rap"],
            self_rap_algo=trade["self_rap_algo"],
            self_value=trade["self_value"],
            self_overall_value=trade["self_overall_value"],
            their_rap=trade["their_rap"],
            their_rap_algo=trade["their_rap_algo"],
            their_value=trade["their_value"],
            their_overall_value=trade["their_overall_value"],
            their_robux=trade.get("their_robux"),
        )
        return None if valid else reason

    def _accept_trade(self, trade_id) -> bool:
        """
        Accepts an inbound, solving 2FA if Roblox asks.
        Returns False if Roblox refused (trade gone, items moved).
        """
        url = f"https://trades.roblox.com/v1/trades/{trade_id}/accept"
        validation_headers = None
        for attempt in range(1, SEND_TRADE_ATTEMPTS + 1):
            try:
                self.request_handler.requestAPI(
                    url, "post", additional_headers=validation_headers
                )
                return True
            except ChallengeRequired as e:
                if attempt == SEND_TRADE_ATTEMPTS:
                    raise
                log(f"Accept needs 2FA, solving (attempt {attempt})", dontPrint=True)
                validation_headers = self.validate_2fa(e.response)
                time.sleep(10)
            except BadRequest as e:
                log(
                    f"[INBOUND] Roblox refused to accept {trade_id}: {e}", severityNum=2
                )
                return False
            finally:
                time.sleep(1)
        return False

    def _is_our_counter(self, trade) -> bool:
        """True if this outbound is a counter the bot sent (Counter Memory Hours)."""
        history = getattr(self, "counter_history", None)
        if history is None:
            return False
        signature = trade_signature(
            trade["self_side_item_ids"],
            trade["their_side_item_ids"],
            trade.get("self_robux") or 0,
        )
        return signature in history.sent(trade["their_id"])

    def _counter_loop_reason(self, trader_id) -> str | None:
        """
        Why this trader shouldn't be countered again, or None:
        Max Counters Per Trader reached, or they counter back instantly every
        time (Instant Replies To Call It A Bot).
        """
        settings = self.config.inbounds
        hours = settings["Counter_Memory_Hours"]
        limit = settings["Max_Counters_Per_Trader"]
        sent = self.counter_history.counters(trader_id)
        if limit and sent >= limit:
            return (
                f"already countered them {sent} times in {hours:g} hours "
                "(Max Counters Per Trader)"
            )
        bot = settings["Instant_Replies_For_Bot"]
        seconds = settings["Instant_Reply_Seconds"]
        streak = self.counter_history.instant_replies(trader_id, seconds)
        if bot and streak >= bot:
            return (
                f"they countered back within {seconds / 60:g} minutes {streak} times "
                "in a row, "
                "likely a bot (Bot Replies)"
            )
        return None

    def _counter_trade(self, trade_id, trader_id, trade=None) -> str:
        """
        Generates a trade from our config and sends it as a counter.
        When no trade passes the config, declines it (Decline If No Counter).
        Returns "countered", "declined" or "failed".
        """
        if not self.check_can_trade(trader_id):
            return "failed"

        if not self.account_inventory:
            log(
                f"[INBOUND] {self.username} has no tradeable items, reloading inventory to counter", dontPrint=True)
            self.refresh_self_inventory()
            if not self.account_inventory:
                return "failed"

        trader_inventory = self.fetch_inventory(
            trader_id,
            max_owned=self.config.inbounds["Max_Duplicates"],
            max_from_trader=self.config.inbounds["Max_Trader_Duplicates"],
        )
        if not trader_inventory:
            return "failed"

        generated_trade = self.counter_maker.generate_trade(
            self.account_inventory,
            trader_inventory,
            counter_trade=True,
            offered=self.offered_item_counts(),
            original=(
                {
                    "self": trade["self_side_item_ids"],
                    "their": trade["their_side_item_ids"],
                }
                if trade
                else None
            ),
            # Never the same counter twice
            avoid=self.counter_history.sent(trader_id),
        )
        if not generated_trade:
            if not self.config.inbounds["Decline_If_No_Counter"]:
                log(
                    f"[INBOUND] No counter for {trade_id} passed your config, "
                    "leaving it\n" + failed_text(getattr(self.counter_maker, "last_failed", {}))
                )
                return "failed"
            if self._decline_trade(trade_id):
                return "declined"
            return "failed"

        self.send_trade(
            trader_id,
            generated_trade["self_side"],
            generated_trade["their_side"],
            counter_trade=True,
            counter_id=trade_id,
            self_robux=generated_trade["self_robux"],
        )
        self.counter_history.record_counter(
            trader_id,
            trade_signature(
                [self.account_inventory[k]["item_id"] for k in generated_trade["self_side"]],
                [trader_inventory[k]["item_id"] for k in generated_trade["their_side"]],
                generated_trade["self_robux"],
            ),
        )
        counter = dict(
            generated_trade,
            their_id=trader_id,
            self_side_item_ids=[
                self.account_inventory[key]["item_id"]
                for key in generated_trade["self_side"]
            ],
            their_side_item_ids=[
                trader_inventory[key]["item_id"]
                for key in generated_trade["their_side"]
            ],
        )
        header = f"[INBOUND] {self.username} countered trade {trade_id} from {trader_id}"
        try:
            log(trade_lines(header, *self.trade_fields(counter)))
        except (TradebotError, KeyError, TypeError, ValueError):
            log(header)
        self.post_trade_webhook(
            "Send_Webhook", counter, "Countered a trade ({profit} profit)", color=3
        )
        return "countered"

    def trade_fields(self, trade) -> tuple[dict, int]:
        """(webhook fields, overall profit) for an inbound or counter trade."""
        return self.discord_webhook.embed_fields_from_trade(
            trade,
            self.rolimon.item_data,
            self.rolimon.projected_json.read_cached(),
        )

    def post_trade_webhook(
        self, webhook, trade, title, color, extra_fields=None
    ) -> bool:
        """
        Posts a trade to a [Discord] webhook ("Send_Webhook" or
        "Completed_Webhook"). {profit} in the title becomes the overall profit.
        extra_fields: more {name: (text, inline)} fields under the trade.
        Never raises: the trade already happened. Returns True if posted.
        """
        url = self.config.discord_settings.get(webhook)
        if not url:
            return False
        try:
            fields, profit = self.trade_fields(trade)
            fields.update(extra_fields or {})
            embed = self.discord_webhook.setup_embed(
                title=title.format(profit=profit),
                color=color,
                user_id=trade["their_id"],
                embed_fields=fields,
                footer=(
                    ""
                    if self.config.discord_settings.get("Hide_Username", True)
                    else self.username
                ),
            )
            return self.discord_webhook.send_webhook(embed, url)
        except (TradebotError, KeyError, TypeError) as e:
            log(f"[WEBHOOK] Couldn't post to the {webhook.replace('_', ' ')}: {e}", severityNum=2)
            return False

    def send_trade(
        self,
        trader_id,
        trade_send,
        trade_recieve,
        self_robux=None,
        counter_trade=False,
        counter_id=None,
    ):
        """
        Send Trader ID Then the list of items (list of collectibleItemInstanceIds)
        Returns the trade id.

        Raises:
            TradeLimit: account hit its trade limit
            RateLimited: send endpoint still rate limited after backing off
            ItemsUnavailable / InsufficientRobux / UserCannotTrade / TradeRejected
            TwoFactorError: couldn't solve the 2FA challenge
            RobloxAPIError / NetworkError for anything else
        """
        trade_api = "https://trades.roblox.com/v2/trades/send"
        if counter_trade and counter_id is not None:
            trade_api = f"https://trades.roblox.com/v2/trades/{counter_id}/counter"

        validation_headers = None
        last_error = None
        for attempt in range(1, SEND_TRADE_ATTEMPTS + 1):
            robux = self._capped_robux(self_robux)
            trade_payload = {
                "senderOffer": {
                    "userId": self.account_id,
                    "collectibleItemInstanceIds": trade_send,
                    "robux": robux,
                },
                "recipientOffer": {
                    "userId": trader_id,
                    "collectibleItemInstanceIds": trade_recieve,
                    "robux": 0,
                },
            }

            try:
                trade_response = self.request_handler.requestAPI(
                    trade_api,
                    "post",
                    payload=trade_payload,
                    additional_headers=validation_headers,
                )
            except ChallengeRequired as e:
                last_error = e
                if attempt == SEND_TRADE_ATTEMPTS:
                    raise
                log(f"Trade needs 2FA, solving (attempt {attempt})", dontPrint=True)
                validation_headers = self.validate_2fa(e.response)
                time.sleep(10)
                continue
            except BadRequest as e:
                rejection = self._classify_trade_rejection(e)
                if isinstance(rejection, InsufficientRobux):
                    # Refresh so the next generated trade uses the real balance.
                    # Don't resend this one with less robux: it would no longer
                    # match the trade that was generated and logged.
                    self.get_robux()
                if isinstance(rejection, ItemsUnavailable):
                    try:
                        self.check_completeds()
                    except TradebotError as check_error:
                        log(f"[COMPLETED] Couldn't check completed trades: {check_error}", severityNum=2)
                raise rejection from e
            finally:
                # this is a very ratelimited API so dont spam
                time.sleep(1)

            try:
                trade_id = read_json(trade_response)["tradeId"]
            except (KeyError, TypeError) as e:
                raise InvalidResponse(
                    f"Trade sent but no tradeId: {e}", trade_api
                ) from e
            log("[TRADING] Trade sent", dontPrint=True)
            self.note_sent_trade(trade_send)
            self._remember_sent_config(trade_id)
            return trade_id

        raise last_error or TradeRejected(message=f"Couldn't send trade to {trader_id}")

    def _capped_robux(self, self_robux) -> int:
        """Never offer more robux than the account has."""
        if not self_robux:
            return 0
        if self_robux >= self.account_robux:
            self_robux = self.account_robux
            if self_robux > 1:
                self_robux -= 1
        return max(self_robux, 0)

    @staticmethod
    def _classify_trade_rejection(error: BadRequest) -> TradeRejected:
        """Turns a 400 from the trade API into the matching TradeRejected subtype."""
        if TRADE_CODE_ITEMS_UNAVAILABLE in error.codes:
            cls = ItemsUnavailable
        elif TRADE_CODE_INSUFFICIENT_ROBUX in error.codes:
            cls = InsufficientRobux
        elif error.has_message("trade") and (
            error.has_message("privacy") or error.has_message("cannot trade")
        ):
            cls = UserCannotTrade
        else:
            cls = TradeRejected
        return cls(error.response)

    def get_robux(self):
        """Updates self.account_robux; keeps 0 if Roblox can't be reached."""
        robux_api = f"https://economy.roblox.com/v1/users/{self.account_id}/currency"
        try:
            response = self.request_handler.requestAPI(robux_api)
            self.account_robux = int(response.json()["robux"])
        except (TradebotError, ValueError, KeyError, TypeError) as e:
            log(
                f"[ACCOUNT] Couldn't get Robux for {getattr(self, 'username', self.account_id)}: {e}",
                severityNum=2,
            )
            self.account_robux = 0

    def get_recent_traders(self, max_days_since=5):
        """
        Remembers everyone you traded with (inbound, outbound or finished) in
        the last max_days_since days, so the bot doesn't send them another trade.
        """

        check_urls = [
            "https://trades.roblox.com/v1/trades/inactive?limit=100&sortOrder=Desc",
            "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Desc",
            "https://trades.roblox.com/v1/trades/inbound?cursor=&limit=100&sortOrder=Desc",
        ]

        self.all_cached_traders = set()
        for url in check_urls:
            try:
                trades = self.get_trades(url, limit_pages=6)
            except CookieInvalid:
                raise
            except TradebotError as e:
                log(
                    f"[TRADING] Couldn't load recent traders, may trade some players again: {e}",
                    severityNum=2,
                )
                continue

            for trade_id, trade_info in trades.items():
                trader_id = trade_info["user_id"]
                created = trade_info["created"]

                timestamp_format = datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                )
                timestamp_format = timestamp_format.replace(tzinfo=None)
                current_time = datetime.utcnow()

                time_difference = current_time - timestamp_format

                if (
                    time_difference < timedelta(days=max_days_since)
                    and trader_id not in self.all_cached_traders
                ):
                    self.all_cached_traders.add(trader_id)

    def format_trade_api(self, trade_json):
        """
        Turns a /v2/trades/{id} response into the trade dict used by webhooks and validation.
        Raises InvalidResponse if the trade JSON is malformed, UnknownItem if an item
        isn't on Rolimons yet.
        """

        def asset_ids(offer):
            return [
                ("1:" if asset["itemTarget"]["itemType"] == "Asset" else "2:")
                + str(asset["itemTarget"]["targetId"])
                for asset in offer["items"]
            ]

        try:
            self_offer = trade_json["participantAOffer"]
            trader_offer = trade_json["participantBOffer"]
            # Don't trust the order: work out which side is ours by user id
            if str(trader_offer["user"]["id"]) == str(
                getattr(self, "account_id", None)
            ):
                self_offer, trader_offer = trader_offer, self_offer
            self_user = self_offer["user"]["id"]
            trader_user = trader_offer["user"]["id"]
            self_robux = self_offer.get("robux") or 0
            their_robux = trader_offer.get("robux") or 0
            self_assets = asset_ids(self_offer)
            trader_assets = asset_ids(trader_offer)
        except (KeyError, TypeError) as e:
            raise InvalidResponse(f"Trade JSON missing field: {e}") from e

        self_rap, self_value, self_algorithm_value, self_overall = self.calculate_gains(
            self_assets
        )
        trader_rap, trader_value, trader_algorithm_value, trader_overall = (
            self.calculate_gains(trader_assets)
        )

        trade = {
            "their_id": trader_user,
            "their_side_item_ids": trader_assets,
            "their_value": trader_value,
            "their_rap": trader_rap,
            "their_rap_algo": trader_algorithm_value,
            "their_overall_value": trader_overall,
            "their_robux": their_robux,
            "self_robux": self_robux,
            "self_rap": self_rap,
            "self_id": self_user,
            "self_value": self_value,
            "self_rap_algo": self_algorithm_value,
            "self_side_item_ids": self_assets,
            "self_overall_value": self_overall,
        }

        return trade

    def check_completeds(self):
        """
        Posts newly completed trades to the Completed webhook.
        Raises if the completed list can't be loaded; a single bad trade is skipped.
        """
        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/completed?limit=100&sortOrder=Desc",
            limit_pages=1,
        )

        if not trades:
            return None

        # get new trades not logged
        trades_items = list(reversed(trades.items()))
        unlogged_trades = []
        found_start = False

        for trade_id, trade_data in trades_items:
            if found_start:
                unlogged_trades.append(trade_id)
            elif trade_id == self.last_completed_scanned:
                found_start = True

        first_trade = next(iter(trades))
        self.last_completed_scanned = first_trade
        self.json.update_last_completed(
            self.cookies[".ROBLOSECURITY"], self.last_completed_scanned
        )

        if unlogged_trades:
            # Items changed hands, so refresh what we own
            try:
                self.refresh_self_inventory()
            except InventoryUnavailable as e:
                log(
                    f"[COMPLETED] Couldn't reload inventory after completed trades: {e}",
                    severityNum=2,
                )

            for trade_id in unlogged_trades:
                if str(trade_id) in self.posted_accepts:
                    self.posted_accepts.discard(str(trade_id))
                    continue  # already posted when it was accepted
                try:
                    self._post_completed_trade(trade_id)
                except CookieInvalid:
                    raise
                except TradebotError as e:
                    log(
                        f"[COMPLETED] Couldn't post completed trade {trade_id}, skipping: {e}",
                        severityNum=2,
                    )

        return unlogged_trades

    def _post_completed_trade(self, trade_id):
        trade_info = self.request_handler.requestAPI(
            f"https://trades.roblox.com/v2/trades/{trade_id}"
        )
        formatted_trade = self.format_trade_api(read_json(trade_info))
        embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(
            formatted_trade,
            self.rolimon.item_data,
            self.rolimon.projected_json.read_cached(),
        )
        embed = self.discord_webhook.setup_embed(
            title=f"Trade Completed ({total_profit} profit)",
            color=2,
            user_id=formatted_trade["their_id"],
            embed_fields=embed_fields,
            footer="Frick shedletsk",
        )
        self.discord_webhook.send_webhook(
            embed, self.config.discord_settings["Completed_Webhook"]
        )

    def calculate_gains(self, item_ids):
        """
        Returns (rap, value, algorithm value, overall value), worked out the same
        way the trade generator does: RAP items have 0 value, and valued items'
        algorithm value follows "RAP Algorithm for Valued Items". Raises UnknownItem.
        """
        valued_mode = (
            self.config.trading.get("Rap_Algo_For_Valued") or "rap_algo"
        ).lower()

        account_rap = 0
        account_value = 0
        account_algorithm_value = 0
        account_overall_value = 0
        projected_data = self.rolimon.projected_json.read_cached()

        for item in item_ids:
            item_data = self.rolimon.item_data.get(str(item))
            if item_data is None:
                raise UnknownItem(item)

            rap = item_data["rap"] or 0
            value = item_data["value"] or 0
            overall_value = item_data["total_value"] or 0

            projected = projected_data.get(str(item))
            if value and valued_mode == "rolimon_value":
                account_algorithm_value += value
            elif value and valued_mode == "zero_value":
                pass
            elif projected and projected.get("value") is not None:
                account_algorithm_value += projected["value"]
            else:
                account_algorithm_value += rap

            account_rap += rap
            account_value += value
            account_overall_value += overall_value

        return (
            account_rap,
            account_value,
            account_algorithm_value,
            account_overall_value,
        )

    def note_sent_trade(self, instance_ids):
        sent = getattr(self, "sent_since_check", None)
        if sent is None:
            sent = self.sent_since_check = []
        sent.append((time.time(), list(instance_ids)))

    def offered_item_counts(self) -> dict:
        """
        How many open outbounds each of our items (by instance id) is in: the
        trades from the last outbound check plus the ones sent since. Trades
        sent over a day ago that were never seen by a check are forgotten.
        """
        counts = {}
        account_id = str(getattr(self, "account_id", None))
        for cached in list(getattr(self, "outbound_cache", {}).values()):
            trade_json = cached.get("json") or {}
            for key in ("participantAOffer", "participantBOffer"):
                offer = trade_json.get(key) or {}
                if str((offer.get("user") or {}).get("id")) != account_id:
                    continue
                for item in offer.get("items") or []:
                    uaid = item.get("collectibleItemInstanceId")
                    if uaid:
                        counts[uaid] = counts.get(uaid, 0) + 1
        cutoff = time.time() - SECONDS_PER_DAY
        sent = getattr(self, "sent_since_check", [])
        sent[:] = [entry for entry in sent if entry[0] >= cutoff]
        for _, instance_ids in sent:
            for uaid in instance_ids:
                counts[uaid] = counts.get(uaid, 0) + 1
        return counts

    def outbound_api_checker(self):
        """
        Scans the outbound API for bad trades then cancels them.
        Json way is more messy and not needed for this bot
        """

        log("in outbound checker", dontPrint=True)
        check_started = time.time()
        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Asc"
        )

        self.config_changed_at = self._config_changed_at()
        self._forget_sent_configs(trades, check_started)

        with self.outbound_lock:
            # Forget trades that were accepted, declined or expired
            for gone in set(self.outbound_cache) - set(trades):
                self.outbound_cache.pop(gone, None)

            for trade_id, trade_info in trades.items():
                trader_id = trade_info["user_id"]
                if trader_id not in self.all_cached_traders:
                    self.all_cached_traders.add(trader_id)

                try:
                    self._check_one_outbound(
                        trade_info["trade_id"], parse_created(trade_info.get("created"))
                    )
                except CookieInvalid:
                    raise
                except TradebotError as e:
                    log(f"[OUTBOUND] Skipping {trade_id}: {short_error(e)}", severityNum=2)
                    time.sleep(2)

            # Trades sent before this check are in outbound_cache now
            self.sent_since_check = [
                entry
                for entry in getattr(self, "sent_since_check", [])
                if entry[0] >= check_started
            ]

    def recheck_cached_outbounds(self) -> int:
        """
        Re-prices the outbounds saved by the last full check using the current
        Rolimons data. Makes no Roblox calls except to decline a losing trade,
        so it's safe to run on every Rolimons update. Returns how many were declined.
        Skips if a full check is running right now.
        """
        if not self.outbound_lock.acquire(blocking=False):
            return 0
        try:
            declined = 0
            for trade_id, cached in list(self.outbound_cache.items()):
                try:
                    if self._evaluate_outbound(
                        trade_id,
                        cached["json"],
                        allow_rescan=False,
                        created=cached["created"],
                    ):
                        declined += 1
                except CookieInvalid:
                    raise
                except TradebotError as e:
                    log(f"Couldn't re-price outbound {trade_id}: {e}", dontPrint=True)
            return declined
        finally:
            self.outbound_lock.release()

    def _decline_trade(self, trade_id) -> bool:
        """Declines a trade. A 400 means it's already gone, which counts as done."""
        url = f"https://trades.roblox.com/v1/trades/{trade_id}/decline"
        try:
            self.request_handler.requestAPI(url, method="post")
            return True
        except BadRequest:
            return True
        except TradebotError as e:
            log(f"Failed to decline {trade_id}: {e}", dontPrint=True)
            return False
        finally:
            time.sleep(1.5)

    def _rescan_stale_items(self, item_ids) -> bool:
        """
        Re-scans price history for items whose projected/algorithm data is
        older than OUTBOUND_RESCAN_AGE_SECONDS. Returns True if any were rescanned.
        """
        projected_data = self.rolimon.projected_json.read_cached()
        rescanned = False
        for item_id in set(map(str, item_ids)):
            entry = projected_data.get(item_id) or {}
            collectible_id = entry.get("collectible_item_id")
            scanned_at = entry.get("timestamp") or 0
            if not collectible_id:
                continue  # scanned before IDs were saved; next inventory scan adds it
            if time.time() - scanned_at < OUTBOUND_RESCAN_AGE_SECONDS:
                continue
            log(f"[OUTBOUND] Re-scanning {item_id}, data is stale", dontPrint=True)
            self.is_projected_api(collectibleId=collectible_id, item_id=item_id)
            rescanned = True
        return rescanned

    def _projected_items(self, item_ids) -> list:
        """Items that are projected now, by Rolimons' flag (if enabled) or our own scan."""
        use_rolimons_flag = self.config.projected_detection[
            "Detect_Rolimons_Projecteds"
        ]
        check_valued = self.config.projected_detection.get("Check_Valued_Items", False)
        projected_data = self.rolimon.projected_json.read_cached()
        projected = []
        for item_id in map(str, item_ids):
            item = self.rolimon.item_data.get(item_id) or {}
            if not check_valued and item.get("rolimons_value", item.get("value")):
                continue  # valued: priced by Rolimons ([Projected] Check Valued Items)
            rolimons_flag = item.get("projected")
            scanned_flag = (projected_data.get(item_id) or {}).get("is_projected")
            if scanned_flag or (use_rolimons_flag and rolimons_flag):
                projected.append(item_id)
        return projected

    def _config_fingerprint(self) -> str:
        """Hash of every setting the outbound checker or trade generator uses."""
        settings = {
            "trading": self.config.trading,
            "inbound_gains": (getattr(self.config, "inbounds", None) or {}).get("Gains"),
            "filter_items": self.config.filter_items,
            "projected_detection": self.config.projected_detection,
        }
        raw = json.dumps(settings, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _config_changed_at(self) -> float:
        """
        Returns when this account's config last changed, as a unix timestamp.
        Saved in outbound_config_state.json so it survives restarts.
        The first time an account is seen counts as a change, so outbounds that
        already exist are treated as sent under an older config.
        """
        state_file = JsonHandler("outbound_config_state.json")
        state = state_file.read_data()
        key = str(self.account_id)
        fingerprint = self._config_fingerprint()
        entry = state.get(key) or {}
        if entry.get("fingerprint") != fingerprint:
            entry = {"fingerprint": fingerprint, "changed_at": time.time()}
            state[key] = entry
            state_file.write_data(state)
            log(f"[OUTBOUND] Config changed for {self.username}", dontPrint=True)
        return entry["changed_at"]

    def _remember_sent_config(self, trade_id):
        """Saves which config a trade was sent under (see _sent_before_config_change)."""
        try:
            with _sent_configs_lock:
                state_file = JsonHandler(SENT_CONFIGS_FILE)
                state = state_file.read_data()
                state.setdefault(str(self.account_id), {})[str(trade_id)] = [
                    self._config_fingerprint(),
                    time.time(),
                ]
                state_file.write_data(state)
        except (OSError, TradebotError) as e:
            log(f"[OUTBOUND] Couldn't save the config of trade {trade_id}: {e}", dontPrint=True)

    def _forget_sent_configs(self, open_trades, checked_at):
        """Drops saved trades that were sent before checked_at and aren't open anymore."""
        open_ids = {str(trade_id) for trade_id in open_trades}
        try:
            with _sent_configs_lock:
                state_file = JsonHandler(SENT_CONFIGS_FILE)
                state = state_file.read_data()
                sent = state.get(str(self.account_id)) or {}
                kept = {
                    trade_id: entry
                    for trade_id, entry in sent.items()
                    if trade_id in open_ids or entry[1] >= checked_at
                }
                if len(kept) != len(sent):
                    state[str(self.account_id)] = kept
                    state_file.write_data(state)
        except (OSError, TradebotError, TypeError, IndexError) as e:
            log(f"[OUTBOUND] Couldn't clean up {SENT_CONFIGS_FILE}: {e}", dontPrint=True)

    def _sent_before_config_change(self, created, trade_id=None) -> bool:
        """
        True if the option is on and this trade was sent under an older config.
        Trades the bot sent are matched by the config they were sent with, so a
        trade sent by a bot still running the old config right after a restart
        counts as old. Other trades (sent by hand) go by when they were sent.
        """
        if not self.config.outbound["Only_Cancel_Losing_After_Config_Change"]:
            return False
        if trade_id is not None:
            sent = JsonHandler(SENT_CONFIGS_FILE).read_cached().get(str(self.account_id)) or {}
            entry = sent.get(str(trade_id))
            if entry:
                return entry[0] != self._config_fingerprint()
        if created is None or self.config_changed_at is None:
            return False
        return created < self.config_changed_at

    def _check_one_outbound(self, trade_id, created=None):
        trade_info_req = self.request_handler.requestAPI(
            f"https://trades.roblox.com/v2/trades/{trade_id}"
        )
        trade_json = read_json(trade_info_req)
        self.outbound_cache[trade_id] = {"json": trade_json, "created": created}
        self._evaluate_outbound(
            trade_id, trade_json, allow_rescan=True, created=created
        )

    def _cancel_outbound(self, trade_id) -> bool:
        """Declines and forgets the trade. Returns True if it's gone."""
        if self._decline_trade(trade_id):
            self.outbound_cache.pop(trade_id, None)
            return True
        return False

    def _evaluate_outbound(
        self, trade_id, trade_json, allow_rescan, created=None
    ) -> bool:
        """
        Decides if an outbound should be cancelled and cancels it.
        allow_rescan: re-scan stale price history first (costs Roblox API calls).
        Returns True if the trade was cancelled.
        """
        formatted_trade = self.format_trade_api(trade_json)

        # Make sure what we'd receive is valued on fresh data before judging
        if allow_rescan and self._rescan_stale_items(
            formatted_trade["their_side_item_ids"]
        ):
            formatted_trade = self.format_trade_api(trade_json)

        # Projected = price is being pushed up and likely to drop. Off, the
        # trade is judged on the RAP algorithm value like any other.
        settings = self.config.outbound
        for side, key, default, word in (
            ("their_side_item_ids", "Cancel_Receiving_Projected", True, "receiving"),
            ("self_side_item_ids", "Cancel_Sending_Projected", False, "sending"),
        ):
            if not settings.get(key, default):
                continue
            projected = self._projected_items(formatted_trade[side])
            if projected:
                if self._cancel_outbound(trade_id):
                    log(f"[OUTBOUND] Cancelled a trade: {word} projected {projected}")
                    return True
                return False

        # Sent under an older config: only a real loss is a reason to cancel
        if self._sent_before_config_change(created, trade_id):
            profit = (
                formatted_trade["their_overall_value"]
                - formatted_trade["self_overall_value"]
                - (formatted_trade["self_robux"] or 0)
            )
            if profit < 0:
                log(
                    f"[OUTBOUND] Cancelled a trade sent before your config changed (losing {profit:,} overall)"
                )
                return self._cancel_outbound(trade_id)
            return False

        # NOTE: Check for duplicates
        # A counter we sent follows the [Inbound Settings] it was made with
        is_counter = self._is_our_counter(formatted_trade)
        duplicate = self._too_many_duplicates(
            formatted_trade["their_side_item_ids"],
            self.config.inbounds["Max_Duplicates"] if is_counter else None,
        )
        if duplicate is not None:
            if self._cancel_outbound(trade_id):
                log(f"[OUTBOUND] Cancelled a trade: too many of {duplicate} (duplicates setting)")
                return True
            return False

        checker = self.counter_checker if is_counter else self.outbound_trader
        valid_trade, reason = checker.validate_trade(
            self_rap=formatted_trade["self_rap"],
            self_rap_algo=formatted_trade["self_rap_algo"],
            self_value=formatted_trade["self_value"],
            self_overall_value=formatted_trade["self_overall_value"],
            their_rap=formatted_trade["their_rap"],
            their_rap_algo=formatted_trade["their_rap_algo"],
            their_value=formatted_trade["their_value"],
            their_overall_value=formatted_trade["their_overall_value"],
            robux=formatted_trade["self_robux"],
            their_robux=formatted_trade.get("their_robux"),
        )

        if not valid_trade:
            if self._cancel_outbound(trade_id):
                log(
                    f"[OUTBOUND] Cancelled trade {trade_id}: {reason_text(reason)} "
                    "doesn't pass your config anymore\n"
                    + gains_table(formatted_trade, checker, reason)
                )
                return True
        return False

    def check_can_trade(self, userid):
        """
        Checks if /trade endpoint is valid for userid.
        Raises CookieInvalid if Roblox sends us to the login page.
        """
        if int(userid) not in self.all_cached_traders:
            self.all_cached_traders.add(int(userid))

        url = f"https://www.roblox.com/users/{userid}/trade"
        try:
            try:
                can_trade = self.request_handler.requestAPI(url)
            except ChallengeRequired as e:
                log(
                    f"Can-trade check wants 2FA for {userid}",
                    severityNum=5,
                    dontPrint=True,
                )
                # Solve once and resend with the verification headers
                validation_headers = self.validate_2fa(e.response)
                can_trade = self.request_handler.requestAPI(
                    url, additional_headers=validation_headers
                )
        except (ChallengeRequired, TwoFactorError) as e:
            log(f"[TRADING] Couldn't pass 2FA on the can-trade check: {e}", severityNum=2)
            return False
        except (Forbidden, NotFound, BadRequest):
            return False
        except (exceptions_types.ServerError, exceptions_types.NetworkError) as e:
            log(f"[TRADING] Can-trade check failed for {userid}: {e}", severityNum=2)
            time.sleep(10)
            return False

        if "NewLogin" in can_trade.url:
            raise CookieInvalid(
                can_trade, f"{self.username} was logged out (cookie expired)"
            )

        return True

    def parse_date(self, date_str):
        # Define the possible time formats
        time_formats = [
            "%Y-%m-%dT%H:%M:%SZ",  # Format with 'Z' (UTC indicator)
            "%Y-%m-%dT%H:%M:%S.%fZ",  # Format with fractional seconds and 'Z'
            "%Y-%m-%dT%H:%M:%S.%f",  # Format with fractional seconds, no 'Z'
        ]

        # Check if there is a '.' to handle microsecond truncation
        if "." in date_str:
            # Ensure only 6 digits for microseconds
            date_str = date_str.split(".")[0] + "." + date_str.split(".")[1][:6]

        # Try each format in sequence
        for time_format in time_formats:
            try:
                return datetime.strptime(date_str, time_format)
            except ValueError:
                continue  # Try the next format if the current one fails

        # Return None if all formats fail
        return None

    def is_projected_api(self, collectibleId, item_id):
        """
        Check rolimons projected API, scan the price chart and determine the value of an item and if its projected
        then update all the data to the projected_checker.json
        """
        config_projected = self.config.projected_detection
        use_rolimons_projected = config_projected["Detect_Rolimons_Projecteds"]

        # is_projected starts False; may be set True by rolimons flag or price chart analysis
        is_projected = False
        if self.rolimon.item_data[item_id]["projected"] and use_rolimons_projected:
            is_projected = True

        url = f"https://apis.roblox.com/marketplace-sales/v1/item/{collectibleId}/resale-data"
        resale_json = None
        for attempt in range(1, 4):
            try:
                resale_json = read_json(self.parse_handler.requestAPI(url))
                break
            except RateLimited:
                log(f"[ITEMS] Sales data rate limited (try {attempt}/3)", dontPrint=True)
                time.sleep(30)
            except TradebotError as e:
                log(f"[ITEMS] Couldn't get sales data for {item_id}: {e}", severityNum=2)
                return
        if resale_json is None:
            log(
                f"[ITEMS] Gave up on sales data for {item_id} after rate limits", severityNum=2
            )
            return

        def parse_api_data(data_points, is_price=False):
            parsed = []
            for point in data_points or []:
                date = self.parse_date(point.get("date", ""))
                if date is None or point.get("value") is None:
                    continue
                # Days with no sales come back as price 0; they aren't a price
                if is_price and point["value"] <= 1:
                    continue
                parsed.append(
                    {
                        "value": point["value"],
                        "date": date.timestamp(),
                        "date_string": point["date"],
                    }
                )
            return sorted(parsed, key=lambda x: x["date"], reverse=True)

        sales_data = parse_api_data(resale_json.get("priceDataPoints"), is_price=True)
        volume_data = parse_api_data(resale_json.get("volumeDataPoints"))
        if not sales_data:
            log(
                f"No sales data for {item_id}, skipping projected check", dontPrint=True
            )
            return

        # RAP Algorithm, daily sales and sales gaps only use recent sales
        # ([Items] Sales History Days), so old prices don't skew them
        history_days = self.config.filter_items.get("Sales_History_Days") or 90
        cutoff = time.time() - history_days * SECONDS_IN_DAY
        recent_sales = [p for p in sales_data if p["date"] >= cutoff]
        recent_volume = [p for p in volume_data if p["date"] >= cutoff]

        result = SalesVolumeAnalyzer(recent_sales, recent_volume, item_id).process()
        if not result["value"]:
            # Too few recent sales to find any dips: use the whole history
            # rather than calling the item worth 0
            recent_volume = volume_data
            result = SalesVolumeAnalyzer(sales_data, volume_data, item_id).process()

        result_value = result["value"]
        result_volume = result["volume"]
        result_timestamp = result["timestamp"]

        if len(recent_volume) > 1:
            timestamp_gaps = [
                recent_volume[i]["date"] - recent_volume[i + 1]["date"]
                for i in range(len(recent_volume) - 1)
            ]
            average_gap = (sum(timestamp_gaps) / len(timestamp_gaps)) / SECONDS_IN_DAY
        else:
            average_gap = 0

        today = datetime.utcnow()
        three_months_ago = today - timedelta(days=90)
        current_price = int(sales_data[0]["value"])

        recent_data_points = [
            point
            for point in sales_data
            if self.parse_date(point["date_string"]) > three_months_ago
        ]

        typical = typical_price([int(point["value"]) for point in recent_data_points])
        if current_price > 0 and typical:
            max_rise = config_projected.get("MaximumGraphDifference")
            max_drop = config_projected.get("MinimumGraphDifference")
            rap = self.rolimon.item_data[item_id].get("rap")
            # Selling far above its usual price: being pushed up right now
            pushed_up = price_swing_is_projected(current_price, typical, max_rise, None)
            # Selling far below its usual price only matters while RAP is still
            # up there too; once RAP has come down with the price, it's settled
            crashed = price_swing_is_projected(current_price, typical, None, max_drop) and (
                not rap or price_swing_is_projected(current_price, rap, None, max_drop)
            )
            if pushed_up or crashed:
                is_projected = True

        data = self.rolimon.projected_json.read_data()
        data.update(
            {
                f"{item_id}": {
                    "is_projected": is_projected,
                    "value": result_value,
                    "volume": result_volume,
                    "timestamp": result_timestamp,
                    "last_price": self.rolimon.item_data[item_id]["best_price"],
                    "average_gap": average_gap,
                    # Trade responses don't include it; the outbound checker
                    # needs it to re-scan items it's about to receive
                    "collectible_item_id": collectibleId,
                }
            }
        )
        self.rolimon.projected_json.write_data(data)

    def owner_pages(self) -> OwnerPages:
        """Where the owner scan of each item got to ([Getting Owners of Items])."""
        return OwnerPages(self.config.scan_items.get("Remember_Scanned_Owners_Days", 3))

    # bundle id -> its collectible item id (they don't change)
    _bundle_collectible_ids: dict = {}

    def bundle_collectible_id(self, bundle_id) -> str | None:
        """The bundle's collectibleItemId (for its resellers), or None."""
        cached = self._bundle_collectible_ids.get(bundle_id)
        if cached:
            return cached
        try:
            details = read_json(
                self.request_handler.requestAPI(
                    f"https://catalog.roblox.com/v1/bundles/{bundle_id}/details"
                )
            )
        except CookieInvalid:
            raise
        except TradebotError as e:
            log(f"[OWNERS] Couldn't look up bundle {bundle_id}: {e}", severityNum=2)
            return None
        collectible_id = (details.get("collectibleItemDetail") or {}).get("collectibleItemId")
        if not collectible_id:
            log(f"[OWNERS] Bundle {bundle_id} isn't a limited, skipping it", dontPrint=True)
            return None
        self._bundle_collectible_ids[bundle_id] = collectible_id
        return collectible_id

    def get_active_traders(self, item, owners):
        """
        Reads the item's next owner pages ([Getting Owners of Items] Owner
        Pages Per Scan) and adds every owner on them who got it recently.
        Bundles: their resellers instead (Roblox doesn't list bundle owners).
        Carries on from the page the last scan of this item stopped at
        (owner_pages.OwnerPages), so the same owners aren't read twice.
        Returns owners, or None if Roblox wouldn't list them.
        """
        settings = self.config.scan_items
        pages_per_scan = max(1, settings.get("Owner_Pages_Per_Scan") or 2)
        recent = timedelta(days=settings.get("Recent_Owner_Days") or 7)
        memory = self.owner_pages()

        item_id = item["original_asset_id"]
        page_cursor = memory.start(item_id)
        if page_cursor is None:
            log(f"[OWNERS] Already read every owner of {item_id}, skipping it", dontPrint=True)
            return owners

        bundle = str(item.get("item_id", "")).startswith("2:")
        if bundle:
            # Roblox can't list a bundle's owners: use the people reselling it
            # (like OTB does), found through its collectible id
            collectible_id = self.bundle_collectible_id(item_id)
            if not collectible_id:
                return None

        for _ in range(pages_per_scan):
            inventory_api = (
                f"https://apis.roblox.com/marketplace-sales/v1/item/{collectible_id}"
                f"/resellers?cursor={page_cursor}&limit=100"
                if bundle
                else f"https://inventory.roblox.com/v2/assets/{item_id}/owners"
                f"?sortOrder=Asc&cursor={page_cursor}&limit=100"
            )
            try:
                page = read_json(self.request_handler.requestAPI(inventory_api))
            except CookieInvalid:
                raise
            except (Forbidden, NotFound):
                return None
            # TODO: maybe resolve faces because thier ItemID makes this response fail
            except TradebotError as e:
                if page_cursor:
                    memory.forget(item_id)  # maybe a stale cursor: start over next time
                log(f"[OWNERS] Couldn't get owners of {item_id}: {e}", severityNum=2)
                return None

            now = datetime.now()
            if bundle:
                # Listing it for sale = active right now
                for listing in page.get("data") or []:
                    seller = listing.get("seller") or {}
                    owner_id = seller.get("sellerId")
                    if (
                        not owner_id
                        or seller.get("sellerType", "User") != "User"
                        or int(owner_id) in self.all_cached_traders
                        or owner_id in owners
                    ):
                        continue
                    owners.append(owner_id)
            for asset in [] if bundle else page.get("data") or []:
                if not asset.get("owner") or not asset.get("updated"):
                    continue
                owner_id = asset["owner"]["id"]
                if int(owner_id) in self.all_cached_traders or owner_id in owners:
                    continue
                # Got the item recently = likely still trading
                got_it = datetime.fromisoformat(asset["updated"].replace("Z", "+00:00"))
                if now - got_it.replace(tzinfo=None) < recent:
                    owners.append(owner_id)

            # Next time starts on the next page (None = every owner was read)
            page_cursor = page.get("nextPageCursor")
            memory.save(item_id, page_cursor)
            if page_cursor is None:
                break

        if self.config.debug["show_scanning_users"]:
            log(f"[OWNERS] Owners: {owners}")
        return owners
# while True:
#    hat = input("enter id > ")
#    if RobloxAPI().is_projected(hat) == True:
#        log("Is projected")
#    else:
#        log("Not projected")
