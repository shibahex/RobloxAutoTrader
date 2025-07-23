import json
import random
from handler.handle_logs import log
from handler.handle_requests import RequestsHandler
from handler.handle_json import JsonHandler
from handler.handle_config import ConfigHandler

import roblox_api
from datetime import datetime


class Item:
    def __init__(self, item_id, item_name, asset_type_id, original_price, created,
                 first_timestamp, best_price, favorited, num_sellers, rap,
                 owners, bc_owners, copies, deleted_copies, bc_copies,
                 hoarded_copies, acronym,
                 value, demand, trend, projected,
                 hyped, rare, total_value, thumbnail_url_lg):
        self.item_id = item_id
        self.item_name = item_name
        self.asset_type_id = asset_type_id
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

    def __repr__(self):
        return self.to_dict()

    def to_dict(self):
        return {
            'item_id': self.item_id,
            'item_name': self.item_name,
            'asset_type_id': self.asset_type_id,
            'original_price': self.original_price,
            'created': self.created,
            'first_timestamp': self.first_timestamp,
            'best_price': self.best_price,
            'favorited': self.favorited,
            'num_sellers': self.num_sellers,
            'rap': self.rap,
            'owners': self.owners,
            'bc_owners': self.bc_owners,
            'copies': self.copies,
            'deleted_copies': self.deleted_copies,
            'bc_copies': self.bc_copies,
            'hoarded_copies': self.hoarded_copies,
            'acronym': self.acronym,
            # 'valuation_method': self.valuation_method,
            'value': self.value,
            'demand': self.demand,
            'trend': self.trend,
            'projected': self.projected,
            'hyped': self.hyped,
            'rare': self.rare,
            'total_value': self.total_value,
            'thumbnail_url_lg': self.thumbnail_url_lg
        }


class RolimonAPI():
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
        self.rolimon_account = RequestsHandler(
            use_proxies=False, cookie=cookie)
        self.rolimon_parser = RequestsHandler()
        self.projected_json = JsonHandler('projected_checker.json')
        self.config = ConfigHandler('config.cfg')
        self.update_data()
        # ItemID: Timestamp
        self.scanned_items_for_owners = {}
        # print(self.config.filter_users)

    def return_item_to_scan(self) -> str:
        minimum_value = self.config.scan_items['Minimum_Value_of_Item']
        minimum_rap = self.config.scan_items['Minimum_Rap_of_Item']
        minimum_owners = self.config.scan_items['Minimum_Owners_of_Item']
        minimum_demand = self.config.scan_items['Minimum_Demand_of_Item']
        minimum_trend = self.config.scan_items['Minimum_Trend_of_Item']
        scan_type = self.config.scan_items['Scan_Type']
        scan_rares = self.config.scan_items['Scan_Rares']

        if self.item_data == {}:
            self.update_data()
        # for item in self.item_data.values():
         #   print(item['item_name'], item['trend'])
        filtered_items = [
            item for item in self.item_data.values()
            if (
                (scan_type.lower() == "rap" and not item['value']) or
                (scan_type.lower() == "value" and item['value']) or
                (scan_type.lower() == "both" and
                 (
                 (scan_rares and item['rare']) or
                 (not scan_rares and not item['rare'])
                 )
                 )
            ) and (
                (item['value'] is None or item['value'] >= minimum_value) and
                (item['rap'] is None or item['rap'] >= minimum_rap) and
                (item['owners'] is None or item['owners'] >= minimum_owners) and
                (item['demand'] is None or item['demand'] >= minimum_demand) and
                (item['trend'] is None or item['trend'] >= minimum_trend)
            )
        ]

        if self.config.debug['show_scanning_users'] == True:
            log(f"[DOGGO] Picking random item from list size: {
                len(filtered_items)}"
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
                timestamp = projected_data[str(asset_id)]['timestamp']
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

            def big_price_change(assetid, project_data, threshold=.5):
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

                last_price = projected_data[str(asset_id)]['last_price']
                current_price = self.item_data[asset_id]['best_price']

                difference = abs(current_price - last_price)
                # avoid division by 0
                if difference == 0:
                    return False

                try:
                    percentage_change = difference / last_price
                    if percentage_change >= threshold:
                        return True  # There is a significant change
                except:
                    pass

                return False

            projected_data = self.projected_json.read_data()
            projected_ids = projected_data.keys()

            if str(asset_id) in projected_ids:
                recently_scanned = is_recently_scanned(
                    projected_data, asset_id)
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

        minimum_daily_sales = self.config.filter_items['MinDailySales']
        max_sales_gap = self.config.filter_items['MaxSalesGap']
        rap_algo_for_valued = self.config.trading['Rap_Algo_For_Valued']
        for item in inventory:
            asset_id = inventory[item]['item_id']
            collectibleItemId = inventory[item]['item_id']
            # total value reutns the RAP if theres no value
            rap = self.item_data[asset_id]['rap']

            # Make rap independent from value
            value = self.item_data[asset_id]['value']
            if value == rap or value == None:
                value = 0

            demand = self.item_data[asset_id]['demand']
            item_price = self.item_data[asset_id]['best_price']
            total_value = self.item_data[asset_id]['total_value']

            is_projected = False

            rap_algo_value = None
            item_volume = None

            if need_to_scan(asset_id) == True:
                roblox_api.RobloxAPI().is_projected_api(asset_id)

            if value != 0:
                if rap_algo_for_valued.lower() == "rolimon_value":
                    rap_algo_value = value
                elif rap_algo_for_valued.lower() == "zero_value":
                    rap_algo_value = 0
                elif rap_algo_for_valued.lower() == "rap_algo":
                    rap_algo_value = rap_algo_value
                else:
                    log(
                        "RAP Algorithm for Valued Items, isn't set right; using default of rap_algo")

            projected_data = self.projected_json.read_data()

            try:
                if asset_id in projected_data.keys():
                    is_projected = projected_data[asset_id]['is_projected']
                    rap_algo_value = projected_data[asset_id]['value']
                    item_volume = projected_data[asset_id]['volume']
                    sale_gap = projected_data[asset_id]['average_gap']
            except:
                log("Couldn't get projected data for item, continuing")
                continue

            if not is_self:
                if is_projected or item_volume == None or minimum_daily_sales == None or value == 0 and float(item_volume) < minimum_daily_sales or value == 0 and float(sale_gap) > max_sales_gap:
                    continue

            filtered_inventory[item] = {
                'item_id': asset_id,
                'value': value,
                'rap': rap,
                'demand': demand,
                'rap_algorithm': rap_algo_value,
                'total_value': total_value,
                'item_volume': item_volume
            }

        # apply more usefull info about the item
        return filtered_inventory

    def update_data(self) -> None:
        """
            scrapes rolimons.com/catalog item_details because the API doesn't show shit like owners 
        """

        page = self.rolimon_parser.requestAPI(
            "https://www.rolimons.com/catalog")
        if page.status_code == 200:
            item_details = json.loads(page.text.split(
                "var item_details = ")[1].split(";")[0])
            for item in item_details:
                item_info = item_details[item]
                # add in the itemID
                item_info.insert(0, item)
                self.item_data[item] = Item(*item_details[item]).to_dict()
        else:
            log("Couldnt get rolimon data")
            return False

    def return_trade_ads(self):
        """
            Returns rolimons recent trade ads
        """
        get_ads_response = self.rolimon_parser.requestAPI(
            "https://api.rolimons.com/tradeads/v1/getrecentads")
        response = get_ads_response.json()
        if response['success'] == False:
            return False

        return response['trade_ads']
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
