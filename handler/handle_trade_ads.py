"""
Posts Rolimons trade ads for accounts that have a Rolimons cookie.

Rolimons doesn't publish docs for this API; it's the one rolimons.com uses
when you post an ad. Errors are logged with Rolimons' own message, so a format
change shows up clearly.
"""

import random
import time

import requests

from handler.exceptions_types import (
    NetworkError,
    RolimonsCookieInvalid,
    RolimonsError,
    TradeAdRejected,
)
from handler.handle_logs import log

CREATE_AD_URL = "https://api.rolimons.com/tradeads/v1/createad"
COOKIE_NAME = "_RoliVerification"
REQUEST_TAGS = (
    "any",
    "demand",
    "rares",
    "robux",
    "upgrade",
    "downgrade",
    "wishlist",
    "projecteds",
    "adds",
)
OFFER_PICKS = ("highest_value", "lowest_value", "random", "outbound", "manual")
# What "outbound" falls back to when there's no outbound to advertise
OUTBOUND_FALLBACK = "highest_value"
MAX_ITEMS_PER_SIDE = 4
# Rolimons only lets an account post one ad every 15 minutes
MIN_MINUTES_BETWEEN_ADS = 15
# Rolimons error codes for a missing / wrong verification cookie
COOKIE_ERROR_CODES = (4, 5)


def pick_offer_items(inventory: dict, count: int, pick: str, rng=random) -> list:
    """
    Item IDs (numbers, no "1:") to offer, from an account inventory
    (instance id -> {"item_id": "1:123", "total_value": ...}). Each item at most
    once. Bundles ("2:") can't go in a Rolimons ad.
    """
    items = {}
    for item in (inventory or {}).values():
        item_id = str(item.get("item_id", ""))
        if item_id.startswith("1:"):
            items[item_id] = item.get("total_value") or 0
    ids = list(items)
    if pick == "random":
        ids = rng.sample(ids, min(count, len(ids)))
    else:
        ids.sort(key=items.get, reverse=pick != "lowest_value")
        ids = ids[:count]
    return [int(item_id.split(":", 1)[1]) for item_id in ids]


def owned_items(inventory: dict, item_ids) -> list:
    """The item IDs (numbers) from item_ids that the account owns."""
    owned = {str(item.get("item_id")) for item in (inventory or {}).values()}
    return [i for i in item_ids if f"1:{i}" in owned]


def outbound_ads(account) -> list:
    """
    (trade id, our item IDs, their item IDs) for each open outbound the
    outbound checker has saved. Bundles are left out (Rolimons ads can't have them).
    """
    account_id = str(account.account_id)

    def asset_ids(offer):
        ids = []
        for item in offer.get("items") or []:
            target = item.get("itemTarget") or {}
            if (
                target.get("itemType") == "Asset"
                and str(target.get("targetId", "")).isdigit()
            ):
                item_id = int(target["targetId"])
                if item_id not in ids:
                    ids.append(item_id)
        return ids[:MAX_ITEMS_PER_SIDE]

    ads = []
    cache = getattr(account, "outbound_cache", None) or {}
    for trade_id, cached in sorted(cache.items(), key=lambda t: str(t[0])):
        trade_json = (cached or {}).get("json") or {}
        offers = [
            trade_json.get("participantAOffer") or {},
            trade_json.get("participantBOffer") or {},
        ]
        mine = [o for o in offers if str((o.get("user") or {}).get("id")) == account_id]
        theirs = [
            o for o in offers if str((o.get("user") or {}).get("id")) != account_id
        ]
        if len(mine) != 1 or len(theirs) != 1:
            continue
        offer_ids, request_ids = asset_ids(mine[0]), asset_ids(theirs[0])
        if offer_ids and request_ids:
            ads.append((trade_id, offer_ids, request_ids))
    return ads


def build_ad(player_id, offer_ids, request_ids, request_tags) -> dict:
    return {
        "player_id": int(player_id),
        "offer_item_ids": list(offer_ids),
        "request_item_ids": list(request_ids),
        "request_tags": list(request_tags),
    }


def post_trade_ad(rolimons_cookie: str, ad: dict, session=requests) -> None:
    """Raises RolimonsCookieInvalid, TradeAdRejected, RolimonsError or NetworkError."""
    try:
        response = session.post(
            CREATE_AD_URL,
            json=ad,
            cookies={COOKIE_NAME: rolimons_cookie},
            timeout=15,
        )
    except requests.RequestException as e:
        raise NetworkError(CREATE_AD_URL, e) from e
    try:
        data = response.json()
    except ValueError as e:
        raise RolimonsError(
            f"Trade ad API answered {response.status_code} without JSON"
        ) from e
    if data.get("success"):
        return
    message = data.get("message") or f"HTTP {response.status_code}"
    if data.get("code") in COOKIE_ERROR_CODES:
        raise RolimonsCookieInvalid(message)
    raise TradeAdRejected(message)


def check_rolimons_cookie(rolimons_cookie: str, session=requests) -> None:
    """
    Asks Rolimons if the cookie is valid by sending an empty ad, which can't be
    posted. Raises RolimonsCookieInvalid if Rolimons refuses the cookie.
    """
    try:
        post_trade_ad(rolimons_cookie, {}, session)
    except TradeAdRejected:
        pass  # the cookie was accepted; the empty ad wasn't


class TradeAdPoster:
    """Posts an ad for each account with a Rolimons cookie every few minutes."""

    def __init__(self, settings: dict, session=requests):
        self.settings = settings
        self.session = session
        self.next_post = {}  # account id -> unix time the next ad is due
        self.bad_cookie = set()  # account ids whose cookie Rolimons refused
        self.advertised = {}  # account id -> outbound trade ids already advertised

    def run_once(self, accounts, now=None) -> int:
        """Posts every ad that's due. Returns how many were posted."""
        now = time.time() if now is None else now
        posted = 0
        for account in accounts:
            if self._post_for(account, now):
                posted += 1
        return posted

    def _post_for(self, account, now) -> bool:
        cookie = getattr(account, "rolimons_cookie", None)
        key = str(account.account_id)
        if not cookie or key in self.bad_cookie or now < self.next_post.get(key, 0):
            return False

        offer, request = self._choose_items(account, key)
        if not offer:
            return False  # inventory not loaded yet, or nothing that can be listed

        # Tags fill whatever room the requested items leave
        room = max(0, MAX_ITEMS_PER_SIDE - len(request))
        ad = build_ad(
            account.account_id,
            offer,
            request,
            self.settings["Request_Tags"][:room],
        )
        minutes = max(self.settings["Post_Every_Minutes"], MIN_MINUTES_BETWEEN_ADS)
        self.next_post[key] = now + minutes * 60
        try:
            post_trade_ad(cookie, ad, self.session)
        except RolimonsCookieInvalid as e:
            self.bad_cookie.add(key)
            log(
                f"[TRADE ADS] Rolimons refused {account.username}'s cookie ({e}). "
                "Update it in Account Manager > Rolimons Cookies.",
                severityNum=3,
            )
            return False
        except (RolimonsError, NetworkError) as e:
            log(
                f"[TRADE ADS] Couldn't post an ad for {account.username}: {e}",
                severityNum=2,
            )
            return False
        log(f"[TRADE ADS] Posted an ad for {account.username}: {offer} for {request}")
        return True

    def _choose_items(self, account, key):
        """(offer item IDs, request item IDs) for the next ad."""
        pick = self.settings["Offer_Items_Using"]
        request = list(self.settings["Request_Items"])

        if pick == "manual":
            wanted = self.settings.get("Offer_Item_IDs") or []
            offer = owned_items(account.account_inventory, wanted)
            missing = [i for i in wanted if i not in offer]
            if missing and account.account_inventory:
                log(
                    f"[TRADE ADS] {account.username} doesn't own {missing} "
                    "(or they're on hold / in NFT), leaving them out",
                    dontPrint=True,
                )
            return offer, request

        if pick == "outbound":
            ads = outbound_ads(account)
            if ads:
                done = self.advertised.setdefault(key, set())
                fresh = [ad for ad in ads if ad[0] not in done]
                if not fresh:  # every outbound had a turn: start over
                    done.clear()
                    fresh = ads
                trade_id, offer, request = fresh[0]
                done.add(trade_id)
                return offer, request
            log(
                f"[TRADE ADS] No outbounds to advertise for {account.username} yet, "
                f"using {OUTBOUND_FALLBACK}",
                dontPrint=True,
            )
            pick = OUTBOUND_FALLBACK

        offer = pick_offer_items(
            account.account_inventory, self.settings["Offer_Items"], pick
        )
        return offer, request
