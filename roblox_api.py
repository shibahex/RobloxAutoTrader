import requests
from datetime import datetime, timedelta
import time
import pyotp
import json
import base64
import rolimons_api
from handler.handle_requests import RequestsHandler
from handler.handle_discord import DiscordHandler
from handler.handle_config import ConfigHandler
from handler.handle_json import JsonHandler
from handler.handle_2fa import AuthHandler
from trade_algorithm import TradeMaker
from handler.account_settings import HandleConfigs
from handler.handle_logs import log

from handler.price_algorithm import SalesVolumeAnalyzer
SECONDS_IN_DAY = 86400


class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie: dict = None, auth_secret=None, Proxies=False):
        self.all_cached_traders = set()
        self.auth_secret = auth_secret
        self.counter_timer = time.time()

        self.account_configs = HandleConfigs()

        self.json = JsonHandler('cookies.json')
        # For rolimon Trade Ads
        self.last_outbound = None
        # TODO:
        # put this in cookies.json
        self.tradead_timestamp = None

        # TODO: USE PROXIES
        self.parse_handler = RequestsHandler(
            Session=requests.Session(), use_proxies=False)
        self.config = ConfigHandler('config.cfg')
        self.rolimon = rolimons_api.RolimonAPI()
        self.discord_webhook = DiscordHandler()
        self.last_sent_trade = time.time()
        self.last_generated_csrf_timer = time.time()
        self.cookies = None
        if cookie is not None:
            self.cookies = cookie
            self.last_completed_scanned = self.json.get_last_completed(
                cookie['.ROBLOSECURITY'])

            self.authenticator = pyotp.TOTP(self.auth_secret)
            self.request_handler = RequestsHandler(
                cookie=self.cookies, use_proxies=False, Session=requests.Session())
            self.auth_handler = AuthHandler()
            self.account_id, self.username = self.fetch_userid_and_name()

            user_config = self.account_configs.get_config(str(self.account_id))
            if user_config:
                self.config.trading = user_config
            else:
                pass
            self.trade_maker = TradeMaker(config=self.config)
            self.outbound_trader = TradeMaker(
                config=self.config, is_outbound_checker=True)

            # log("getting self")
            self.self_duplicates = {}
            self.refresh_self_inventory()
            # log("done getting self")

            self.account_robux = 0
            self.get_robux()

            if self.account_id is False:
                log(f"Failed to get userid for cookie {cookie}", severityNum=4)
                raise ValueError("Invalid account or cookie.")

            self.check_completeds()

            self.request_handler.generate_csrf()
            self.last_generated_csrf_timer = time.time()

    def check_premium(self, userid):
        """
        checks if the account is premium
        """
        premium_api = f"https://premiumfeatures.roblox.com/v1/users/{
            userid}/validate-membership"
        response = self.request_handler.requestAPI(premium_api)
        if response.status_code == 200:
            if response.text == "true":
                return True
            else:
                return False
        else:
            log(f"errored at premium {response.status_code} {
                response.text}", severityNum=3)

    # refresh current inventory
    def refresh_self_inventory(self):
        """
            Gets inventory of current .ROBLOSECURITY used on class
        """
        self.self_duplicates = {}
        self.account_inventory = self.fetch_inventory(self.account_id)
        # self.account_inventory = self.fetch_inventory(121642019)
        # NOTE: False = no tradeable inventory
        if not self.account_inventory:
            if self.account_inventory is False:
                log(f"{self.username} Has no tradeable inventory")
                return False
            else:
                log("Couldnt get self inventory retrying,")
                self.refresh_self_inventory()

    def fetch_userid_and_name(self):
        """
            Gets info on the current account to self class
        """
        auth_response = self.request_handler.requestAPI(
            "https://users.roblox.com/v1/users/authenticated")
        if auth_response.status_code == 200:
            return auth_response.json()['id'], auth_response.json()['name']
        else:
            raise ValueError(f"Couldnt login with cookie {self.cookies}")

    def fetch_inventory(self, userid):
        """
        Returns a dict of items from the user, will return False if there no scrapable items.
        """
        def add_to_duplicates(duplicates: dict, itemId: str):
            if itemId not in duplicates:
                duplicates[itemId] = 0
            else:
                duplicates[itemId] += 1
            return duplicates

        # NOTE: switch to v2 when they add ishold to API

        cursor = ""
        inventory = {}

        trader_duplicates = {}
        # for ['Trade_for_Duplicate_Items']

        is_self = False
        while cursor is not None:
            # https://inventory.roblox.com/v2/users/6410566/inventory/8?cursor=&limit=100&sortOrder=Desc
            inventory_API = f"https://inventory.roblox.com/v1/users/{
                userid}/assets/collectibles?cursor={cursor}&limit=100"

            response = self.request_handler.requestAPI(inventory_API)
            if response.status_code != 200:
                log(f"inventory API error {inventory_API}, {
                    response.status_code} {response.text}", severityNum=2)
                time.sleep(30)
                # return False
            elif response.status_code == 403:
                log(f"Cant view inventory of {userid}")
                return None

            try:
                cursor = response.json()['nextPageCursor']
            except Exception as e:
                log(f"Couldnt get cursor {response.json()}, {
                    response.text} error: {e}", severityNum=3)
                cursor = None
                break

            for item in response.json()['data']:
                itemId = str(item['assetId'])

                # Check for duplicates
                if str(userid) == str(self.account_id):
                    self.self_duplicates = add_to_duplicates(
                        self.self_duplicates, itemId)
                else:
                    trader_duplicates = add_to_duplicates(
                        trader_duplicates, itemId)

                if item['isOnHold'] == True:
                    continue

                # TODO: APPLY NFT
                # TODO: IF USERID = SELF.USERID THEN DONT APPLY NFT
                uaid = str(item['userAssetId'])
                if str(userid) == str(self.account_id):
                    is_self = True
                    nft_list = self.config.filter_items['NFT']

                    if nft_list and itemId in nft_list:
                        if self.config.debug['show_scanning_inventory'] == True:
                            log(f"{itemId} in NFT list, skipping it")
                        continue

                    inventory[uaid] = {"item_id": itemId}
                else:

                    try:
                        current_demand = self.rolimon.item_data[itemId]['demand']
                    except:
                        # bad item
                        continue
                    if current_demand != None and int(current_demand) < self.config.filter_items['MinDemand']:
                        # log(current_demand, itemId, "skipped")
                        continue

                    # NOTE: Dont trade for items you already have
                    if str(itemId) in self.self_duplicates and self.self_duplicates[str(itemId)] >= self.config.filter_items['Maximum_Amount_of_Duplicate_Items']:
                        if self.config.debug['show_scanning_inventory'] == True:
                            log(f"[Inventory {userid}] Not trading for",
                                itemId, "because duplicates setting")
                        continue

                    # NOTE: Dont allow trade to have multiple duplicates of items (OWNED OR NOT)
                    # log(itemId, trader_duplicates, userid)
                    if str(itemId) in trader_duplicates and trader_duplicates[str(itemId)] > self.config.filter_items['Maximum_Amount_of_Trader_Duplicate_Items']:
                        if self.config.debug['show_scanning_inventory'] == True:
                            log(f"[Inventory {userid}] Not allowing to trade for another {
                                itemId}")
                        continue

                    # NOTE: Dont trade for items in NFR and dont let the end trade have duplicate items
                    nfr_list = self.config.filter_items['NFR']
                    if itemId not in nfr_list:
                        inventory[uaid] = {"item_id": itemId}
                    else:
                        if self.config.debug['show_scanning_inventory'] == True:
                            log(f"{itemId} in NFR list, skipping it")

                    # TODO: min demand

        minimum_items = self.config.filter_users['Minimum_Total_Items']
        if not is_self:
            if len(inventory.keys()) < minimum_items:
                if self.config.debug['show_scanning_inventory'] == True:
                    log(f"[Inventory {
                        userid}] User doesn't match minimum items")
                return False

        if inventory == {}:
            return False

        return self.rolimon.add_data_to_inventory(inventory, is_self=is_self)

        # return self.rolimon.get_inventory(userid, apply_NFT)

    # NOTE: Payload:
    # {"offers":[{"userId":4486142832,"userAssetIds":[672469540],"robux":null},{"userId":1283171278,"userAssetIds":[1310053014],"robux":null}]}

    def validate_2fa(self, response):
        """
        This function takes a 401 error response and then returns the 2fa response if there is one
        """
        print(response.url, "2fa required for this")
        cookie_json = self.json.read_data()

        challengeid = response.headers["rblx-challenge-id"]
        metadata = json.loads(base64.b64decode(
            response.headers["rblx-challenge-metadata"]))
        try:
            metadata_challengeid = metadata["challengeId"]
        except Exception as e:
            log(f"couldnt get meta data challengeid from {metadata} scraping from {
                response.headers} url {response.url}", severityNum=3)
            return False
        try:
            senderid = metadata["userId"]
        except Exception as e:
            log(f"couldnt get userid from {metadata} scraping from {
                response.headers} url: {response.url}", severityNum=3)
            return False

        # send the totp verify request to roblox
        verification_token = self.auth_handler.verify_request(
            self.request_handler, senderid, metadata_challengeid, self.authenticator)

        # send the continue request, its really important
        self.auth_handler.continue_request(
            self.request_handler, challengeid, verification_token, metadata_challengeid)

        # before sending the final payout request, add verification information to headers
        # self.request_handler.headers.update({
        #     'rblx-challenge-id': challengeid,
        #     'rblx-challenge-metadata': base64.b64encode(json.dumps({
        #         "rememberdevice": True,
        #         "actiontype": "generic",
        #         "verificationtoken": verification_token,
        #         "challengeid": metadata_challengeid
        #     }).encode()).decode(),
        #     'rblx-challenge-type': "twostepverification"
        # })
        #
        return {
            'rblx-challenge-id': challengeid,
            'rblx-challenge-metadata': base64.b64encode(json.dumps({
                "rememberdevice": True,
                "actiontype": "generic",
                "verificationtoken": verification_token,
                "challengeid": metadata_challengeid
            }).encode()).decode(),
            'rblx-challenge-type': "twostepverification"
        }

    def return_trade_details(self, data):
        """
            For APIs like inbounds, outbounds and inactive, scrapes the data and returns it formatted
        """
        trades = {}
        for trade in data:
            trade_id = trade.get("id", None)
            created = trade.get("created", None)
            user = trade.get('user', None)
            if user is None:
                continue
            user_id = user.get("id", None)

            if trade_id is None or user_id is None or created is None:
                continue

            trades[trade['id']] = {
                "trade_id": trade['id'],
                "user_id": trade['user']['id'],
                "created": trade['created']
            }
        return trades

    def get_trades(self, page_url, limit_pages=None) -> list:
        """
            Get every trade_id from trade pages from APIs: inbounds, outbounds and inactive
            Make sure cursor isn't in the URL arg as the func adds it for you
        """
        if self.cookies is None:
            return None

        cursor = ""
        page_count = 0
        trades = {}
        while cursor != None and self.cookies != None:
            if limit_pages and page_count >= limit_pages:
                break

            # Assuming the URL already has page limit = 100
            response = self.request_handler.requestAPI(
                f"{page_url}&cursor={cursor}")

            if response.status_code == 200:
                data = response.json().get("data", None)
                if data is not None:
                    trades.update(self.return_trade_details(
                        response.json()['data']))
                else:
                    continue
                cursor = response.json()['nextPageCursor']
                page_count += 1
            elif response.status_code == 429:
                log("get trades ratelimited")
                time.sleep(30)
            elif response.status_code == 401:

                pass
                # changed = self.request_handler.generate_csrf()
                # if changed == False:
                #     log("Couldnt regen csrf token")
                # else:
                #     self.last_generated_csrf_timer = time.time()

            else:
                log(f"getting trades for gettin trades error {response.status_code} {
                    response.text} {response.json()}", severityNum=2)

        return trades

    def counter_trades(self):
        """
        Gets the recent inbound trades and will generate a response trade and the function will send the trade,
        Returns Nothing
        """
        # TODO: make the counter kind of like the original trade
        # Get info about trade
        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/inbound?limit=100&sortOrder=Desc")
        for trade_id, trade_info in trades.items():
            trader_id = trade_info['user_id']
            trade_id = trade_info['trade_id']
            trader_inventory = self.fetch_inventory(trader_id)

            if not self.check_can_trade(trader_id):
                continue

            if self.config.inbounds['Dont_Counter_Wins'] == True:
                # If its a win then continue and dont counter
                trade_info = self.request_handler.requestAPI(
                    f"https://trades.roblox.com/v1/trades/{trade_id}")
                if trade_info.status_code == 200:
                    trade_json = trade_info.json()
                    formatted_trade = self.format_trade_api(trade_json)
                    if formatted_trade['self_overall_value'] - formatted_trade['their_overall_value'] < 0:
                        continue

            if not self.account_inventory:
                log(f"[DEBUG] In counter, {
                    self.username} has no tradeable inv refreshing inventory")
                self.refresh_self_inventory()
                return False

            if not trader_inventory:
                continue

            generated_trade = self.trade_maker.generate_trade(
                self.account_inventory, trader_inventory, counter_trade=True)

            if not generated_trade:
                log("couldnt generate trade for counter")
                continue

            their_side = generated_trade['their_side']

            self_side = generated_trade['self_side']
            self_robux = generated_trade['self_robux']

            send_trade_response = self.send_trade(
                trader_id, self_side, their_side, counter_trade=True, counter_id=trade_id, self_robux=self_robux)
            if send_trade_response == 429:
                log("ratelimit countering")
            if send_trade_response:
                log("sent counter")
            else:
                log("None counter erro")

    def handle_auth_failed(self, response):
        """
            For when you get 403, it will try to generate 2fa or generate token
            403 = Errored even after making the 2fa code
            False = Wasn't 2fa problem and csrf token erroed
        """
        # log(response.text, response.url, response.status_code, self.request_handler.headers)
        if 'rblx-challenge-id' in response.headers:
            validation = self.validate_2fa(response)
            log(f"Auth Handled response {validation}")
            time.sleep(10)
            print("returning")
            if validation == False:
                return 403
            return validation

    def send_trade(self, trader_id, trade_send, trade_recieve, self_robux=None, counter_trade=False, counter_id=None):
        """
            Send Trader ID Then the list of items (list of assetids)
        """
        if self_robux and self_robux >= self.account_robux:
            self_robux = self.account_robux
            if self_robux > 1:
                self_robux -= 1

        trade_payload = {"offers": [
            {"userId": trader_id, "userAssetIds": trade_recieve,
             "robux": None},
            {"userId": self.account_id, "userAssetIds": trade_send,
             "robux": self_robux}]}

        trade_api = "https://trades.roblox.com/v1/trades/send"
        if counter_trade == True and counter_id != None:
            trade_api = f"https://trades.roblox.com/v1/trades/{
                counter_id}/counter"

        validation_headers = None
        while True:
            trade_response = self.request_handler.requestAPI(
                trade_api, "post", payload=trade_payload, additional_headers=validation_headers)
            # this is a very ratelimited API so dont spam
            time.sleep(1)

            if trade_response.status_code == 200:
                log("Trade sent!")  # , trade_response.text)
                return trade_response.json()['id']
            elif trade_response.status_code == 429:
                if "errors" in trade_response.json():
                    if "you are sending too many trade requests" in trade_response.json()['errors'][0]['message'].lower():
                        # pass
                        return False

                return trade_response.status_code
            elif trade_response.status_code == 403:
                auth_response = self.handle_auth_failed(trade_response)
                if auth_response == 403:
                    continue
                if auth_response == False:
                    break
            elif trade_response.status_code == 400:
                """
                    https://trades.roblox.com/v1/trades/send 400 {"errors":[{"code":17,"message":"You have insufficient Robux to make this offer.","userFacingMessage":"Something went wrong"}]}


                    {"errors":[{"code":12,"message":"One or more userAssets are invalid. See fieldData for details.","userFacingMessage":"Something went wrong",
                        "field":"userAssetIds","fieldData":[{"userAssetId":13003706,"reason":"NotOwned"},{"userAssetId":30456875,"reason":"NotOwned"}]}]}

                """
                # Error code 17 = Not enough robux
                # Error code 12 = Someone doesn't own the robux anymore
                error = trade_response.json()['errors'][0]
                error_code = error['code']
                self.get_robux()

                if error_code == 12:
                    # Check if its our inventory erroring
                    self.check_completeds()
                    break
                elif error_code == 17:
                    self.get_robux()
                    continue
                else:
                    log("Counter user doesn't have trading on")
                    break
            else:
                log(f"errored at trade {trade_response.status_code} {
                    trade_response.text}", severityNum=2)
                # log(trade_response.text)
                break

    # NOTE: this func isnt doing what its suppose to, test it
    # EXAMPLE RESPONSE PAYLOAD
    """
    Requests payload error, returning Already in cached traders, scraping active traders{"errors":[{"code":12,"message":"One or more userAssets
    are invalid. See fieldData for details.","userFacingMessage":"Something went wrong","field":"userAssetIds","fieldData":[{"userAssetId":334790336,"reason":"NotOwned"}]}]}
     {'offers': [{'userId': 1335379174, 'userAssetIds': ('13124557550',), 'robux': None}, {'userId': 1283171278, 'userAssetIds': ('334790336', '378058412', '3790416539', '166680335625'), 'robux': 186}]}
    """

    def handle_invalid_ids(self, error_data):
        missing_asset_ids = [entry["userAssetId"]
                             for entry in error_data["errors"][0]["fieldData"]]

        def is_in_inventory():
            for user_asset_id in missing_asset_ids:
                if user_asset_id in self.account_inventory:
                    return True

        if is_in_inventory():
            self.check_completeds()
            return True
        else:
            return False

    def get_robux(self):
        robux_api = f"https://economy.roblox.com/v1/users/{
            self.account_id}/currency"

        response = self.request_handler.requestAPI(robux_api)

        if response.status_code == 200:
            self.account_robux = response.json()['robux']
        else:
            self.account_robux = 0

    def get_recent_traders(self, max_days_since=5):
        """
            Sends a list of your last inbounds and outbounds
            TODO: make it have dates too so we can have cooldowns on users
        """

        check_urls = ["https://trades.roblox.com/v1/trades/inactive?limit=100&sortOrder=Desc",
                      "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Desc", "https://trades.roblox.com/v1/trades/inbound?cursor=&limit=100&sortOrder=Desc"]

        self.all_cached_traders = set()
        for url in check_urls:
            trades = self.get_trades(url, limit_pages=6)

            for trade_id, trade_info in trades.items():
                trader_id = trade_info['user_id']
                trade_id = trade_info['trade_id']
                created = trade_info['created']

                timestamp_format = datetime.fromisoformat(
                    created.replace("Z", "+00:00"))
                timestamp_format = timestamp_format.replace(tzinfo=None)
                current_time = datetime.utcnow()

                time_difference = current_time - timestamp_format

                if time_difference < timedelta(days=max_days_since) and trader_id not in self.all_cached_traders:
                    self.all_cached_traders.add(trader_id)

    def format_trade_api(self, trade_json):
        # TODO: If this function is only used for webhook reasons, scrap it and remake it,
        # Because grouping up RAP as a total value then VALUE has a total value to get webhook totals don't work because  they shouldnt be added together to get a value of an item
        self_offer = trade_json['offers'][0]
        self_user = self_offer['user']['id']
        # Extract only the asset IDs
        self_assets = [asset['assetId'] for asset in self_offer['userAssets']]

        # Assign the second offer to trader_offer
        trader_offer = trade_json['offers'][1]
        # Extract only the asset IDs
        trader_assets = [asset['assetId']
                         for asset in trader_offer['userAssets']]

        self_rap, self_value, self_algorithm_value, self_overall = self.calculate_gains(
            self_assets)
        trader_rap, trader_value, trader_algorithm_value, trader_overall = self.calculate_gains(
            trader_assets)
        trade = {
            "their_id": trader_offer['user']['id'],
            "their_side_item_ids": trader_assets,
            "their_value": trader_value,
            "their_rap": trader_rap,
            "their_rap_algo": trader_algorithm_value,
            "their_overall_value": trader_overall,
            "self_robux": self_offer['robux'],
            "self_rap": self_rap,
            "self_id": self_user,
            "self_value": self_value,
            "self_rap_algo": self_algorithm_value,
            "self_side_item_ids": self_assets,
            "self_overall_value": self_overall

        }

        return trade

    def check_completeds(self):
        # TODO: DO SOMETHING WITH UNLOGGED TRADES, AKA SEND THROUGH WEBHOOK ALSO MAYBE MAKE IT RUN WITH THE UPDATE DATA THREAD
        # if sendtrade api gets error check completeds

        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/completed?limit=100&sortOrder=Desc", limit_pages=1)

        # if trades are empty return None
        if trades == {}:
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
            self.cookies['.ROBLOSECURITY'], self.last_completed_scanned)

        if unlogged_trades != []:
            # log("getting self2")
            self.account_inventory = self.refresh_self_inventory()
            # log("done getting self2")
            for trade_id in unlogged_trades:
                trade_info = self.request_handler.requestAPI(
                    f"https://trades.roblox.com/v1/trades/{trade_id}")

                if trade_info.status_code == 200:
                    trade_json = trade_info.json()
                    try:
                        formatted_trade = self.format_trade_api(trade_json)
                        embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(
                            formatted_trade, self.rolimon.item_data, self.rolimon.projected_json.read_data())

                        embed = self.discord_webhook.setup_embed(title=f"Trade Completed ({
                                                                 total_profit} profit)", color=2, user_id=formatted_trade['their_id'], embed_fields=embed_fields, footer="Frick shedletsk")

                        self.discord_webhook.send_webhook(
                            embed, self.config.discord_settings['Completed_Webhook']
                        )
                    except Exception as e:
                        log("Couldn't format and post webhook.. skipping",
                            severityNum=2)
                elif trade_info.status_code == 500:
                    continue
                else:
                    time.sleep(2)
                    continue

        return unlogged_trades

    def calculate_gains(self, item_ids):
        # TODO: COMPLETELY REMAKE THIS AND IMMITATE THE TRADE ALGORITHM
        # OR DRAW THIS MATH OUT, THE MAIN ISSUE IM HAVING IS TELL IF I SHOULD
        # SEPERATE VALUE AND RAP OR KEEP THEM ADDED TOGETHER?
        # I DONT THINK TRADE ALGORITHM GROUPS THEM TOGETHER BECAUSE VALUE WOULD BE 0 FOR AN RAP ITEM  BUT VALUE SILL HAS RAP I THINK HOW DO  I SEPERATE THEM
        # after thinking I should cant just add value and rap together, make another function for this for webhooks for combining them.

        # I THINK THE MAIN PROBLEM IM HAVING IS IM COMBINING VALUE AND RAP IN THE WEBHOOKS WHEN ITS NOT THAT SIMPLE

        account_rap = 0
        account_value = 0
        account_algorithm_value = 0
        account_overall_value = 0
        try:
            projected_data = self.rolimon.projected_json.read_data()
        except Exception as e:
            raise ValueError(e)

        account_total = 0
        for item in item_ids:
            if str(item) not in projected_data:
                account_algorithm_value += self.rolimon.item_data[str(
                    item)]['rap']
            else:
                account_algorithm_value += projected_data[str(item)]['value']
            rap = self.rolimon.item_data[str(item)]['rap']
            value = self.rolimon.item_data[str(item)]['value']
            overall_value = self.rolimon.item_data[str(item)]['total_value']

            if not value:
                value = 0
            account_rap += rap
            account_value += value
            account_overall_value += overall_value

        return account_rap, account_value, account_algorithm_value, account_overall_value

    def outbound_api_checker(self):
        """
            Scans the outbound API for bad trades then cancels them.
            Json way is more messy and not needed for this bot
        """

        log("getting outbound trades..")
        trades = self.get_trades(
            "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Asc")

        def return_items(user_assets):
            asset_ids = []
            for asset in user_assets:
                asset_ids.append(asset['assetId'])
            return asset_ids

        # Loop through outbounds
        for trade_id, trade_info in trades.items():
            trader_id = trade_info['user_id']
            if trader_id not in self.all_cached_traders:
                self.all_cached_traders.add(trader_id)

            trade_id = trade_info['trade_id']

            trade_info_req = self.request_handler.requestAPI(
                f"https://trades.roblox.com/v1/trades/{trade_id}")
            # Handle error
            if trade_info_req.status_code != 200:
                log(f"trade info api {trade_info_req.status_code}, {trade_info.text}, Response Headers: {trade_info_req.headers} Url: {trade_info_req.url} Session Cookies: {
                    self.request_handler.Session.cookies} Headers: {self.request_handler.Session.headers} account {self.username}", severityNum=3)
                # self.request_handler.generate_csrf()
                self.last_generated_csrf_timer = time.time()

                time.sleep(10)
                continue

            data = trade_info_req.json()
            formatted_trade = self.format_trade_api(data)
            url = f"https://trades.roblox.com/v1/trades/{trade_id}/decline"

            # NOTE: Check for duplicates
            for itemId in formatted_trade['their_side_item_ids']:
                if str(itemId) in self.self_duplicates and self.self_duplicates[str(itemId)] >= self.config.filter_items['Maximum_Amount_of_Duplicate_Items']:
                    log(f"[OUTBOUND] Cancel trade for {
                        itemId} because duplicates")
                    cancel_request = self.request_handler.requestAPI(
                        url, method="post")
                    time.sleep(1.5)
                    if cancel_request.status_code == 200 or cancel_request.status_code == 400:
                        log("Cleared outbound...")

            valid_trade, reason = self.outbound_trader.validate_trade(
                self_rap=formatted_trade['self_rap'],
                self_rap_algo=formatted_trade['self_rap_algo'],
                self_value=formatted_trade['self_value'],
                self_overall_value=formatted_trade['self_overall_value'],
                their_rap=formatted_trade['their_rap'],
                their_rap_algo=formatted_trade['their_rap_algo'],
                their_value=formatted_trade['their_value'],
                their_overall_value=formatted_trade['their_overall_value'],
                robux=formatted_trade['self_robux']
            )

            if not valid_trade:
                log(f"Canceling Outbound trade for reason: {reason}")

                log(f"Self RAP: {formatted_trade['self_rap']}, Trader RAP: {
                    formatted_trade['their_rap']} | Robux: {formatted_trade['self_robux']}")
                log(f"Self Algo: {formatted_trade['self_rap_algo']}, Their Algo: {
                    formatted_trade['their_rap_algo']}")
                log(f"Values - Self: {formatted_trade['self_value']
                                      }, Trader: {formatted_trade['their_value']}")
                log(f"Overall Values - Self: {formatted_trade['self_overall_value']}, Trader: {
                    formatted_trade['their_overall_value']}")

                cancel_request = self.request_handler.requestAPI(
                    url, method="post")
                time.sleep(1)
                if cancel_request.status_code == 200 or cancel_request.status_code == 400:
                    log("Cleared losing outbound...")

    def check_can_trade(self, userid):
        """
            Checks if /trade endpoint is valid for userid
        """
        if int(userid) not in self.all_cached_traders:
            self.all_cached_traders.add(int(userid))

        validation_headers = None
        can_trade = self.request_handler.requestAPI(
            f"https://www.roblox.com/users/{userid}/trade", additional_headers=validation_headers)
        if can_trade.status_code == 403:
            if "rblx-challenge-id" in can_trade.headers:
                log(
                    f"{can_trade.headers} {can_trade.text} can trade 403", severityNum=5, dontPrint=True
                )
                validation = self.validate_2fa(can_trade)
                if validation == False:
                    return None
                validation_headers = validation
            return False

        if "NewLogin" in can_trade.url:
            return False

        if can_trade.status_code == 500:
            log("500 error on can trade", severityNum=2)
            time.sleep(10)
            validation_headers = None
            return False

        if can_trade.status_code == 200:
            return True

        return False

    def parse_date(self, date_str):
        # Define the possible time formats
        time_formats = [
            "%Y-%m-%dT%H:%M:%SZ",       # Format with 'Z' (UTC indicator)
            "%Y-%m-%dT%H:%M:%S.%fZ",    # Format with fractional seconds and 'Z'
            "%Y-%m-%dT%H:%M:%S.%f",     # Format with fractional seconds, no 'Z'
        ]

        # Check if there is a '.' to handle microsecond truncation
        if '.' in date_str:
            # Ensure only 6 digits for microseconds
            date_str = date_str.split(
                '.')[0] + '.' + date_str.split('.')[1][:6]

        # Try each format in sequence
        for time_format in time_formats:
            try:
                return datetime.strptime(date_str, time_format)
            except ValueError:
                continue  # Try the next format if the current one fails

        # Return None if all formats fail
        return None

    def is_projected_api(self, item_id, collectibleItemId=None):
        """
        Check rolimons projected API, scan the price chart and determain the value of an item and if its projected
        then update all the data to the projected_checker.json
        """
        # TODO: GET the dates and see how much the item sells so we dont trade dead items or we can
        # see how active an item is
        # TODO: Delete all the value: "1" from data points
        """
        Takes itemID and returns if its projected,
        projected detection should have a cooldown so you dont spam the URL, 
        so dont scan the same item over and over again, and dont scan value items
        """
        # Check if RAP - Price is correct min price difference
        # TODO: scan detect rolimon projecteeds
        rap = self.rolimon.item_data[item_id]['rap']
        value = self.rolimon.item_data[item_id]['total_value']
        price = self.rolimon.item_data[item_id]['best_price']

        config_projected = self.config.projected_detection
        min_graph_difference = config_projected['MinimumGraphDifference']
        max_graph_difference = config_projected['MaximumGraphDifference']
        min_price_difference = config_projected['MinPriceDifference']
        use_rolimons_projected = config_projected['Detect_Rolimons_Projecteds']
        # TODO: ADD MIN AND MAX DIFFERENCE
        # if not self.config.check_gain(int(rap), int(price), min_gain=min_price_difference, max_gain=max_price_difference):
        #    log("projected due to price difference")
        #    return True

        is_projected = False
        if self.rolimon.item_data[item_id]['projected'] == True and use_rolimons_projected:
            is_projected = True

        while True:
            if collectibleItemId != None:
                url = f"https://apis.roblox.com/marketplace-sales/v1/item/{
                    collectibleItemId}/resale-data"
                # "/marketplace-sales/v1/item/5060a9f2-cae0-4123-88c6-0eab5e2e2b59/resale-data"
            else:
                url = f"https://economy.roblox.com/v1/assets/{
                    item_id}/resale-data?limit=100"

            resale_data = self.parse_handler.requestAPI(url)

            if resale_data.status_code == 429:
                log("ratelimited resale data")
                time.sleep(30)
            elif resale_data.status_code == 400:
                log(f"reslate data 400 handling for {
                    item_id}, please report if this is spammed \n{url}", severityNum=2)
                # Get new id
                details_url = f"https://catalog.roblox.com/v1/catalog/items/{
                    item_id}/details?itemType=asset"
                detail_api = self.parse_handler.requestAPI(details_url)
                if detail_api.status_code == 200:
                    detail_data = detail_api.json()
                    if "collectibleItemId" in detail_data:
                        log(f"{detail_data['collectibleItemId']
                               } resending back", dontPrint=True)
                        collectibleItemId = detail_data['collectibleItemId']
                    else:
                        log("v2 Catalog API didnt work", severityNum=3)
                elif detail_api.status_code == 429:
                    log("Ratelimited detail api")
                    time.sleep(30)
                else:
                    log(f"Couldn't get details on after 400 {item_id}, skipping item, {
                        resale_data}, {resale_data.status_code}", severityNum=2)
                    break
            elif resale_data.status_code == 200:
                if collectibleItemId is not None:
                    log("Successfully resolved 400 for resale data")
                break
            else:
                log(f"Couldn't get details on {item_id} {resale_data.text} {
                    resale_data.status_code}", severityNum=2)
                break

        if resale_data.status_code == 200:
            def parse_api_data(data_points):
                return sorted(
                    [{"value": point["value"], "date": self.parse_date(point["date"]).timestamp(), "date_string": point['date']}
                        for point in data_points],
                    key=lambda x: x["date"],
                    reverse=True
                )

            sales_data = parse_api_data(resale_data.json()["priceDataPoints"])
            volume_data = parse_api_data(
                resale_data.json()["volumeDataPoints"])

            # Instantiate and process the analyzer
            result = SalesVolumeAnalyzer(
                sales_data, volume_data, item_id).process()

            result_value = result['value']
            result_volume = result['volume']
            result_timestamp = result['timestamp']
            # {'value': 558.2293577981651, 'volume': 84.825, 'timestamp': 1732423848.2720559, 'age': 63157848.272055864} 1609402609
            if len(volume_data) > 1:
                timestamp_gaps = [
                    volume_data[i]["date"] - volume_data[i + 1]["date"]
                    for i in range(len(volume_data) - 1)
                ]
                # Calculate the average gap
                average_gap = (sum(timestamp_gaps) /
                               len(timestamp_gaps)) / SECONDS_IN_DAY
                largest_gap = max(timestamp_gaps) if timestamp_gaps else 0
            else:
                average_gap = 0
                largest_gap = 0

            today = datetime.utcnow()
            three_months_ago = today - timedelta(days=90)
            current_price = int(sales_data[0]['value'])

            recent_data_points = [
                point for point in sales_data
                if self.parse_date(point["date_string"]) > three_months_ago
            ]

            sum_of_price = 0
            for num, data in enumerate(recent_data_points):
                loop_price = int(data['value'])
                percentage_change = (current_price - loop_price)/current_price

                if percentage_change < -0.4 and percentage_change > 0.4:
                    is_projected = True

            data = self.rolimon.projected_json.read_data()
            data.update({f"{item_id}": {"is_projected": is_projected, "value": result_value, "volume": result_volume,
                        "timestamp": result_timestamp, "last_price": self.rolimon.item_data[item_id]['best_price'], "average_gap": average_gap}})
            self.rolimon.projected_json.write_data(data)

    def get_active_traders(self, item_id, owners):
        """
            Scan atleast 3 pages of owners and append new owners
            If less than 5 owners isn't found it will contintue to the next pages
        """
        # TODO: Maybe add a date to recently scraped owners in projecteds.json to  avoid scraping the same item
        next_page_cursor = ""

        while len(owners) < 20:
            if next_page_cursor == None:
                break
            inventory_api = f"https://inventory.roblox.com/v2/assets/{
                item_id}/owners?sortOrder=Asc&cursor={next_page_cursor}&limit=100"

            response = self.request_handler.requestAPI(inventory_api)

            if response.status_code == 403:
                return None
            elif response.status_code != 200:
                log(f"Got API response {response.text} on {
                    response.url} Trying to get active traders again..", severityNum=2)
                continue

            next_page_cursor = response.json()['nextPageCursor']
            for asset in response.json()['data']:
                if asset['owner'] == None:
                    continue
                # log(asset['owner'])
                if int(asset['owner']['id']) in self.all_cached_traders:
                    if self.config.debug['show_scanning_users'] == True:
                        log("Already Traded with User, skipping.")
                    continue
                # else:
                #     log("appending", asset['owner']['id'], "if date is good")
                owner_since = asset['updated']

                # Assuming owner_since is a string like "2024-11-15T12:00:00Z"
                given_date = datetime.fromisoformat(
                    owner_since.replace("Z", "+00:00"))

                # Remove timezone from given_date to make it naive
                given_date_naive = given_date.replace(tzinfo=None)

                # Get today's date and time (naive by default)
                today = datetime.now()

                # Calculate the difference between today and the given date
                time_diff = today - given_date_naive

                # If the owner has had the item for less than 7 days and is not already in the owners or all_cached_traders list, add them
                if time_diff < timedelta(days=7) and asset['owner']['id'] not in owners and int(asset['owner']['id']) not in self.all_cached_traders:
                    # log("Appending Active User")
                    owners.append(asset['owner']['id'])
        if self.config.debug['show_scanning_users'] == True:
            log(f"owners: {owners}")
        return owners

# while True:
#    hat = input("enter id > ")
#    if RobloxAPI().is_projected(hat) == True:
#        log("Is projected")
#    else:
#        log("Not projected")
