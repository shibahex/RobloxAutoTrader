import json
import random
from handler.handle_logs import log
from handler.handle_requests import RequestsHandler
from handler.handle_json import JsonHandler
from handler.handle_config import ConfigHandler
from handler.exceptions_types import (
    TradebotError,
    RolimonsError,
    NoItemsToScan,
)

import roblox_api
from datetime import datetime


class Item:
    def __init__(
        self,
        item_id,
        item_name,
        asset_type,
        original_price,
        created,
        first_timestamp,
        best_price,
        favorited,
        num_sellers,
        rap,
        owners,
        bc_owners,
        copies,
        deleted_copies,
        bc_copies,
        hoarded_copies,
        acronym,
        value,
        demand,
        trend,
        projected,
        hyped,
        rare,
        total_value,
        thumbnail_url_lg,
        category_id,
        original_asset_id,
    ):
        self.item_id = item_id
        self.item_name = item_name
        self.asset_type = asset_type
        self.original_price = original_price
        self.created = created
        self.first_timestamp = first_timestamp
        self.best_price = best_price
        self.favorited = favorited
        self.num_sellers = num_sellers
        self.rap = rap
        self.owners = owners
        self.bc_owners = bc_owners
        self.copies = copies
        self.deleted_copies = deleted_copies
        self.bc_copies = bc_copies
        self.hoarded_copies = hoarded_copies
        self.acronym = acronym
        # self.valuation_method = valuation_method
        self.value = value
        self.demand = demand
        self.trend = trend
        self.projected = projected
        self.hyped = hyped
        self.rare = rare
        self.total_value = total_value
        self.thumbnail_url_lg = thumbnail_url_lg
        self.category_id = category_id
        self.original_asset_id = original_asset_id

    def __repr__(self):
        return self.to_dict()

    def to_dict(self):
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "asset_type": self.asset_type,
            "original_price": self.original_price,
            "created": self.created,
            "first_timestamp": self.first_timestamp,
            "best_price": self.best_price,
            "favorited": self.favorited,
            "num_sellers": self.num_sellers,
            "rap": self.rap,
            "owners": self.owners,
            "bc_owners": self.bc_owners,
            "copies": self.copies,
            "deleted_copies": self.deleted_copies,
            "bc_copies": self.bc_copies,
            "hoarded_copies": self.hoarded_copies,
            "acronym": self.acronym,
            # 'valuation_method': self.valuation_method,
            "value": self.value,
            "demand": self.demand,
            "trend": self.trend,
            "projected": self.projected,
            "hyped": self.hyped,
            "rare": self.rare,
            "total_value": self.total_value,
            "thumbnail_url_lg": self.thumbnail_url_lg,
            "category_id": self.category_id,
            "original_asset_id": self.original_asset_id,
        }


class RolimonAPI:
    # make it so its only one instance
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(RolimonAPI, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, cookie: dict = None):
        if self.__initialized:
            return
        self.__initialized = True  # Avoid reinitialization
        self.item_data = {}
        self.rolimon_account = RequestsHandler(use_proxies=False, cookie=cookie)
        self.rolimon_parser = RequestsHandler()
        self.projected_json = JsonHandler("projected_checker.json")
        self.config = ConfigHandler("config.cfg")
        try:
            self.update_data()
        except RolimonsError as e:
            log(
                f"Couldn't load Rolimons data at startup, will retry: {e}",
                severityNum=3,
            )
        # ItemID: Timestamp
        self.scanned_items_for_owners = {}
        # print(self.config.filter_users)

    def return_item_to_scan(self) -> Item:
        minimum_value = self.config.scan_items["Minimum_Value_of_Item"]
        minimum_rap = self.config.scan_items["Minimum_Rap_of_Item"]
        minimum_owners = self.config.scan_items["Minimum_Owners_of_Item"]
        minimum_demand = self.config.scan_items["Minimum_Demand_of_Item"]
        minimum_trend = self.config.scan_items["Minimum_Trend_of_Item"]
        scan_type = self.config.scan_items["Scan_Type"]
        scan_rares = self.config.scan_items["Scan_Rares"]

        if not self.item_data:
            # Raises RolimonsError if it still can't load
            self.update_data()
        # for item in self.item_data.values():
        #   print(item['item_name'], item['trend'])
        filtered_items = [
            item
            for item in self.item_data.values()
            if (
                (scan_type.lower() == "rap" and not item["value"])
                or (scan_type.lower() == "value" and item["value"])
                or (
                    scan_type.lower() == "both"
                    and (
                        (scan_rares and item["rare"])
                        or (not scan_rares and not item["rare"])
                    )
                )
            )
            and (
                (item["value"] is None or item["value"] >= minimum_value)
                and (item["rap"] is None or item["rap"] >= minimum_rap)
                and (item["owners"] is None or item["owners"] >= minimum_owners)
                and (item["demand"] is None or item["demand"] >= minimum_demand)
                and (item["trend"] is None or item["trend"] >= minimum_trend)
            )
        ]

        if self.config.debug["show_scanning_users"]:
            log(f"[DOGGO] Picking random item from list size: {len(filtered_items)}")

        if not filtered_items:
            raise NoItemsToScan(
                f"No items match the [Scan Items] filters (scan type {scan_type}); loosen them in config.cfg"
            )

        # TODO: add into table with timestamp and if we get the same item check if the time has been 30 minutes and if it has remove and return it
        return random.choice(filtered_items)
        # print(filtered_items)

    def add_data_to_inventory(self, inventory, is_self=False) -> dict:
        """
        Returns inventory with rolimon data appended into it
        also scans for projecteds

        basically post processing of the inventory after getting it from roblox API
        """

        filtered_inventory = {}

        def need_to_scan(asset_id):
            """
            Checks if item is already cached as projected then checks if its projected.
            if its not in cache we check if its projected then save it

            """

            # TODO: this doesnt get followed properly
            def is_recently_scanned(projected_data, asset_id):
                timestamp = projected_data[str(asset_id)].get("timestamp")
                if timestamp is None:
                    return False
                timestamp_datetime = datetime.utcfromtimestamp(timestamp)
                current_datetime = datetime.utcnow()

                # Calculate the difference between the current time and the timestamp
                time_difference = current_datetime - timestamp_datetime

                # Get the number of days in the time difference
                days_ago = time_difference.days

                # Check if it's been more than 2 day
                # print(days_ago, "days ago")
                if days_ago > 2:
                    return False
                return True

            def big_price_change(assetid, project_data, threshold=0.5):
                """
                The threshold is set to 1.0 (100%), which represents a "double" in price.
                If the percentage change is 1.0 (100%), the price has doubled.
                If the percentage change is greater than 1.0, the price has more than doubled.
                If the percentage change is less than 1.0, the price has not doubled yet.

                For example:
                A price change from 200 to 400 has a 100% increase, or 1.0 (doubling).
                A price change from 100 to 150 has a 50% increase, or 0.5 (not double).
                A price change from 100 to 200 has a 100% increase, or 1.0 (doubling).
                """

                last_price = projected_data[str(asset_id)].get("last_price")
                current_price = self.item_data[asset_id]["best_price"]

                # No price on either side (no sellers), can't compare
                if not last_price or current_price is None:
                    return False

                difference = abs(current_price - last_price)
                return difference / last_price >= threshold

            projected_data = self.projected_json.read_cached()
            projected_ids = projected_data.keys()

            if str(asset_id) in projected_ids:
                recently_scanned = is_recently_scanned(projected_data, asset_id)
                price_change = big_price_change(asset_id, projected_data)

                # print(f"recently scanned: {recently_scanned} (should be true) big price change (should be false): {price_change}")

                # Scan if not recently scanned or if there's a big price change
                # print("recently scanned:", recently_scanned, "big price change:", price_change)
                if not recently_scanned or price_change:
                    return True
                else:
                    return False
            else:
                # print("item not in projected data")
                return True

                # Commented out so value items can have rap algo value
                # Skip scanning if the item is valued
                # return self.item_data[str(asset_id)]['rap'] != self.item_data[str(asset_id)]['value']

        minimum_daily_sales = self.config.filter_items["MinDailySales"]
        max_sales_gap = self.config.filter_items["MaxSalesGap"]
        rap_algo_for_valued = self.config.trading["Rap_Algo_For_Valued"]
        for item in inventory:
            asset_id = inventory[item]["item_id"]
            if asset_id not in self.item_data:
                log(f"{asset_id} not on Rolimons yet, leaving it out", dontPrint=True)
                continue
            # total value reutns the RAP if theres no value
            rap = self.item_data[asset_id]["rap"]

            # Make rap independent from value
            value = self.item_data[asset_id]["value"]
            if value == rap or value is None:
                value = 0

            demand = self.item_data[asset_id]["demand"]
            # item_price = self.item_data[asset_id]["best_price"]
            total_value = self.item_data[asset_id]["total_value"]

            is_projected = False

            rap_algo_value = None
            item_volume = None
            sale_gap = None

            if need_to_scan(asset_id):
                try:
                    roblox_api.RobloxAPI().is_projected_api(
                        item_id=asset_id,
                        collectibleId=inventory[item]["collectibleItemId"],
                    )
                except TradebotError as e:
                    log(f"Projected check failed for {asset_id}: {e}", severityNum=2)

            projected_data = self.projected_json.read_cached()

            projected_entry = projected_data.get(asset_id)
            if projected_entry is not None:
                try:
                    is_projected = projected_entry["is_projected"]
                    rap_algo_value = projected_entry["value"]
                    item_volume = projected_entry["volume"]
                    sale_gap = projected_entry["average_gap"]
                except (KeyError, TypeError) as e:
                    log(
                        f"Projected data for {asset_id} is incomplete ({e}), skipping item"
                    )
                    continue

            # Applied after the scan data so the setting isn't overwritten by
            # the scanned algorithm value
            if value != 0:
                mode = (rap_algo_for_valued or "rap_algo").lower()
                if mode == "rolimon_value":
                    rap_algo_value = value
                elif mode == "zero_value":
                    rap_algo_value = 0
                elif mode != "rap_algo":
                    log(
                        "RAP Algorithm for Valued Items, isn't set right; using default of rap_algo"
                    )

            if not is_self:
                if (
                    is_projected
                    or item_volume is None
                    or minimum_daily_sales is None
                    or value == 0
                    and float(item_volume) < minimum_daily_sales
                    or value == 0
                    and sale_gap is not None
                    and float(sale_gap) > max_sales_gap
                ):
                    continue

            filtered_inventory[item] = {
                "item_id": asset_id,
                "value": value,
                "rap": rap,
                "demand": demand,
                "rap_algorithm": rap_algo_value,
                "total_value": total_value,
                "item_volume": item_volume,
            }

        # apply more usefull info about the item
        return filtered_inventory

    def update_data(self) -> None:
        """
        scrapes rolimons.com/catalog item_details because the API doesn't show shit like owners
        Keeps the old data and raises RolimonsError if the page can't be loaded or parsed.
        """
        try:
            page = self.rolimon_parser.requestAPI("https://www.rolimons.com/catalog")
        except TradebotError as e:
            raise RolimonsError(f"Couldn't reach rolimons catalog: {e}") from e

        try:
            raw = page.text.split("var item_details = ")[1].split(";")[0]
            item_details = json.loads(raw)
        except (IndexError, ValueError) as e:
            raise RolimonsError(
                f"Rolimons catalog page format changed, couldn't find item_details: {e}"
            ) from e

        new_data = {}
        for item_id, item_info in item_details.items():
            try:
                new_data[item_id] = Item(item_id, *item_info).to_dict()
            except TypeError as e:
                raise RolimonsError(
                    f"Rolimons item format changed ({len(item_info)} fields for {item_id}): {e}"
                ) from e

        if not new_data:
            raise RolimonsError("Rolimons catalog returned no items")
        # Swap in one step so other threads never see half-loaded data
        self.item_data = new_data

    def return_trade_ads(self):
        """
        Returns rolimons recent trade ads
        """
        try:
            get_ads_response = self.rolimon_parser.requestAPI(
                "https://api.rolimons.com/tradeads/v1/getrecentads"
            )
            response = get_ads_response.json()
        except (TradebotError, ValueError) as e:
            raise RolimonsError(f"Couldn't get trade ads: {e}") from e
        if not response.get("success"):
            return False

        return response.get("trade_ads", [])
        # 6 downgrade
        # 1 demand
        # 5 upgrade
        # 10 adds

    # Check config to see if we need to filter this user

    def activity_algorithm(self, userid):
        pass

    def validate_user(self, userid):
        # If can trade
        # Last Online
        # Last Traded
        # Min total value and items
        # Rolimon verified badge
        # Have an algorithm to check how much a person trades (take into fact their graph and how many of their items is owned since)
        pass
