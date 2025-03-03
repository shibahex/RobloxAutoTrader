from handler import *
import requests
from datetime import datetime, timedelta
import time
import os
import pyotp
import json
import base64

import rolimons_api
from handler.handle_json import JsonHandler
from handler.handle_2fa import AuthHandler
from trade_algorithm import TradeMaker
from handler.account_settings import HandleConfigs

from handler.price_algorithm import SalesVolumeAnalyzer
"""
Fix the internal error code like 400 or 500 for getting trades:
hint it might be csxrf token?

"""

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, auth_secret=None, Proxies=False):
        self.all_cached_traders = set()
        self.auth_secret = auth_secret

        self.account_configs = HandleConfigs()

        self.json = JsonHandler('cookies.json')
        # For rolimon Trade Ads
        self.last_outbound = None
        # TODO:
        # put this in cookies.json
        self.tradead_timestamp = None

        #TODO: USE PROXIES
        self.parse_handler = RequestsHandler(Session=requests.Session(), use_proxies=False) 
        self.config = ConfigHandler('config.cfg')
        self.rolimon = rolimons_api.RolimonAPI()
        self.discord_webhook = DiscordHandler()
        self.last_sent_trade = time.time()
        self.last_generated_csrf_timer = time.time()
        self.cookies = None
        if cookie != None:
            self.cookies = cookie
            self.last_completed_scanned = self.json.get_last_completed(cookie['.ROBLOSECURITY'])

            self.authenticator = pyotp.TOTP(self.auth_secret)
            self.request_handler = RequestsHandler(cookie=self.cookies, use_proxies=False, Session=requests.Session())
            self.auth_handler = AuthHandler()

            self.account_id, self.username = self.fetch_userid_and_name()
            user_config = self.account_configs.get_config(str(self.account_id))
            if user_config:
                self.config.trading = user_config
            else:
                pass
            self.trade_maker = TradeMaker(config=self.config)
            self.outbound_trader = TradeMaker(config=self.config, is_outbound_checker=True)

            # print("getting self")
            self.refresh_self_inventory()
            # print("done getting self")

            self.account_robux = 0
            self.get_robux()
            
            if self.account_id == False:
                print("Failed to get userid for cookie", cookie)
                raise ValueError("Invalid account or cookie.")

            self.check_completeds()

            self.request_handler.generate_csrf()
            self.last_generated_csrf_timer = time.time()

            #self.request_handler.headers.update({'X-CSRF-TOKEN': self.refresh_csrf()})

    def check_premium(self, userid):
        """
        checks if the account is premium
        """
        premium_api = f"https://premiumfeatures.roblox.com/v1/users/{userid}/validate-membership"
        response = self.request_handler.requestAPI(premium_api)
        if response.status_code == 200:
            if response.text == "true":
                return True
            else:
                return False
        else:
            print("errored at premium", response.status_code, response.text)

    # refresh current inventory
    def refresh_self_inventory(self):
        # TODO: make this refresh if a trade gets completed
        """
            Gets inventory of current .ROBLOSECURITY used on class
        """
        self.account_inventory = self.fetch_inventory(self.account_id)
        #self.account_inventory = self.fetch_inventory(121642019)
        #NOTE: False = no tradeable inventory
        if not self.account_inventory:
            if self.account_inventory == False:
                print(self.username, "Has no tradeable inventory")
                return False
            else:
                print("Couldnt get self inventory retrying,")
                self.refresh_self_inventory()


    def fetch_userid_and_name(self):
        """
            Gets info on the current account to self class
        """
        auth_response = self.request_handler.requestAPI("https://users.roblox.com/v1/users/authenticated")
        if auth_response.status_code == 200: 
            return auth_response.json()['id'], auth_response.json()['name']
        else:
            raise ValueError(f"Couldnt login with cookie {self.cookies}")

    def fetch_inventory(self, userid):
        # NOTE: switch to v2 when they add ishold to API
        cursor = ""
        inventory = {}
        is_self = False
        while cursor != None:
            # https://inventory.roblox.com/v2/users/6410566/inventory/8?cursor=&limit=100&sortOrder=Desc

            inventory_API = f"https://inventory.roblox.com/v1/users/{userid}/assets/collectibles?cursor={cursor}&limit=100"

            response = self.request_handler.requestAPI(inventory_API)
            if response.status_code != 200:
                print("inventory API error", inventory_API, response.status_code, response.text)
                time.sleep(30)
                #return False
            
            try:
                cursor = response.json()['nextPageCursor']
            except Exception as e:
                print("Couldnt get cursor", response.json(), response.text)
                with open("error.json", "w") as f:
                    f.write(response.text)
                cursor = None
                break

            for item in response.json()['data']:
                if item['isOnHold'] == True:
                    continue
                # TODO: APPLY NFT
                # TODO: IF USERID = SELF.USERID THEN DONT APPLY NFT
                    
                uaid = str(item['userAssetId'])
                itemId = str(item['assetId'])
                if str(userid) == str(self.account_id):
                    is_self = True
                    nft_list = self.config.trading['NFT']
                    if nft_list and itemId in nft_list:
                        continue
                    inventory[uaid] = {"item_id": itemId}
                else:
                    try:
                        current_demand = self.rolimon.item_data[itemId]['demand']
                    except:
                        # bad item
                        continue
                    if current_demand != None and int(current_demand) < self.config.trading['MinDemand']:
                        #print(current_demand, itemId, "skipped")
                        continue

                    nfr_list = self.config.trading['NFR']
                    if itemId not in nfr_list:
                        inventory[uaid] = {"item_id": itemId}



                    # TODO: min demand

        minimum_items = self.config.filter_users['Minimum_Total_Items']
        if not is_self:
            if len(inventory.keys()) < minimum_items:
                return False

        if inventory == {}:
            return False

        return self.rolimon.add_data_to_inventory(inventory, is_self=is_self)



        #return self.rolimon.get_inventory(userid, apply_NFT)

    # NOTE: Payload:
    # {"offers":[{"userId":4486142832,"userAssetIds":[672469540],"robux":null},{"userId":1283171278,"userAssetIds":[1310053014],"robux":null}]}
    def validate_2fa(self, response):
        cookie_json = self.json.read_data()
        
        challengeid = response.headers["rblx-challenge-id"]
        metadata = json.loads(base64.b64decode(response.headers["rblx-challenge-metadata"]))
        try:
            metadata_challengeid = metadata["challengeId"]
        except Exception as e:
            print("couldnt get meta data challengeid from", metadata, "scraping from", response.headers, "for meta data", response.url)
            return False
        try:
            senderid = metadata["userId"]
        except Exception as e:
            print("couldnt get userid from", metadata, "scraping from", response.headers, "for meta data", response.url)
            return False

        # send the totp verify request to roblox
        verification_token = self.auth_handler.verify_request(self.request_handler, senderid, metadata_challengeid, self.authenticator)

        # send the continue request, its really important
        self.auth_handler.continue_request(self.request_handler, challengeid, verification_token, metadata_challengeid)

        # before sending the final payout request, add verification information to headers
        return{
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
        if self.cookies == None:
            input("NOOO COOKIE!!"*300)
        cursor = ""
        page_count = 0
        trades = {}
        while cursor != None and self.cookies !=None:
            if limit_pages and page_count >= limit_pages:
                break

            # Assuming the URL already has page limit = 100
            response = self.request_handler.requestAPI(f"{page_url}&cursor={cursor}")
            if response.status_code == 200:
                trades.update(self.return_trade_details(response.json()['data']))
                cursor = response.json()['nextPageCursor']
                page_count += 1
            elif response.status_code == 429:
                print("get trades ratelimited")
                time.sleep(30)
            elif response.status_code == 401:

                pass
                # changed = self.request_handler.generate_csrf()
                # if changed == False:
                #     print("Couldnt regen csrf token")
                # else:
                #     self.last_generated_csrf_timer = time.time()

            else:
                print("getting trades for gettin trades error", response.status_code, response.text, response.json())

        return trades  

    def counter_trades(self):
        # TODO: make the counter kind of like the original trade
        # Get info about trade
        trades = self.get_trades("https://trades.roblox.com/v1/trades/inbound?limit=100&sortOrder=Desc")
        for trade_id, trade_info in trades.items():
            trader_id = trade_info['user_id']
            trade_id = trade_info['trade_id']
            trader_inventory = self.fetch_inventory(trader_id)
        
            if not self.check_can_trade(trader_id):
                continue
            if not self.account_inventory:
                print(f"[DEBUG] In counter, {self.username} has no tradeable inv refreshing inventory")
                self.refresh_self_inventory()
                break

            if not trader_inventory:
                continue

            generated_trade = self.trade_maker.generate_trade(self.account_inventory, trader_inventory, counter_trade=True)
        
            if not generated_trade:
                print("couldnt generate trade for counter")
                continue
        
            their_side = generated_trade['their_side']
        
            self_side = generated_trade['self_side']
            self_robux = generated_trade['self_robux']

            send_trade_response = self.send_trade(trader_id, self_side, their_side, counter_trade=True, counter_id=trade_id, self_robux=self_robux)
            if send_trade_response == 429:
                print("ratelimit countering")
            if send_trade_response:
                print("sent counter")
            else:
                print("None counter erro")

    def handle_auth_failed(self, response):
        """
            For when you get 403, it will try to generate 2fa or generate token
            403 = Errored even after making the 2fa code
            False = Wasn't 2fa problem and csrf token erroed
        """
        #print(response.text, response.url, response.status_code, self.request_handler.headers)
        if 'rblx-challenge-id' in response.headers:
            print("doing 2fa")
            validation = self.validate_2fa(response)
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

        trade_payload = {"offers":[
            {"userId":trader_id,"userAssetIds":trade_recieve,
            "robux":None},
            {"userId":self.account_id,"userAssetIds":trade_send,
            "robux":self_robux}]}


        trade_api = "https://trades.roblox.com/v1/trades/send"
        if counter_trade == True and counter_id != None:
            trade_api = f"https://trades.roblox.com/v1/trades/{counter_id}/counter"


        validation_headers = None
        while True:
            trade_response = self.request_handler.requestAPI(trade_api, "post", payload=trade_payload, additional_headers=validation_headers)
            # this is a very ratelimited API so dont spam
            time.sleep(1)
            
            if trade_response.status_code == 200:
                print("Trade sent!", trade_response.text)
                return trade_response.json()['id']
            elif trade_response.status_code == 429:
                if "errors" in trade_response.json():
                    if "you are sending too many trade requests" in trade_response.json()['errors'][0]['message'].lower():
                        #pass
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


                    {"errors":[{"code":12,"message":"One or more userAssets are invalid. See fieldData for details.","userFacingMessage":"Something went wrong","field":"userAssetIds","fieldData":[{"userAssetId":13003706,"reason":"NotOwned"},{"userAssetId":30456875,"reason":"NotOwned"}]}]}

                """
                # Error code 17 = Not enough robux
                # Error code 12 = Someone doesn't own the robux anymore
                error = trade_response.json()['errors'][0]
                error_code = error['code']
                self.get_robux()

                if error_code == 12:
                    # Check if its our inventory erroring
                    if self.handle_invalid_ids(error_data=trade_response.json()):
                        continue
                    else:
                        break
                elif error_code == 17:
                    self.get_robux()
                    continue
                else:
                    print("Counter user doesn't have trading on")
                    break
            else:
                print("errored at trade", trade_response.status_code, trade_response.text)
                #print(trade_response.text)
                break

    def handle_invalid_ids(self, error_data):
        missing_asset_ids = [entry["userAssetId"] for entry in error_data["errors"][0]["fieldData"]]

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
        robux_api = f"https://economy.roblox.com/v1/users/{self.account_id}/currency"

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

        check_urls = ["https://trades.roblox.com/v1/trades/inactive?limit=100&sortOrder=Desc", "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Desc", "https://trades.roblox.com/v1/trades/inbound?cursor=&limit=100&sortOrder=Desc"]

        for url in check_urls:
            trades = self.get_trades(url, limit_pages=6)

            for trade_id, trade_info in trades.items():
                trader_id = trade_info['user_id']
                trade_id = trade_info['trade_id']
                created = trade_info['created']

                timestamp_format = datetime.fromisoformat(created.replace("Z", "+00:00"))
                timestamp_format = timestamp_format.replace(tzinfo=None)
                current_time = datetime.utcnow()

                time_difference = current_time - timestamp_format
                

                if time_difference < timedelta(days=max_days_since):
                    self.all_cached_traders.add(trader_id)


    def format_trade_api(self, trade_json):
        # TODO: If this function is only used for webhook reasons, scrap it and remake it,
        # Because grouping up RAP as a total value then VALUE has a total value to get webhook totals don't work because  they shouldnt be added together to get a value of an item
        self_offer = trade_json['offers'][0]
        self_user = self_offer['user']['id']
        self_assets = [asset['assetId'] for asset in self_offer['userAssets']]  # Extract only the asset IDs

        # Assign the second offer to trader_offer
        trader_offer = trade_json['offers'][1]
        trader_assets = [asset['assetId'] for asset in trader_offer['userAssets']]  # Extract only the asset IDs

        self_rap, self_value, self_algorithm_value, self_overall = self.calculate_gains(self_assets)
        trader_rap, trader_value, trader_algorithm_value, trader_overall = self.calculate_gains(trader_assets)
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
        #if sendtrade api gets error check completeds 
        
        
        trades = self.get_trades("https://trades.roblox.com/v1/trades/completed?limit=100&sortOrder=Desc", limit_pages=1)

        # if trades are empty return None
        if trades == {}:
            return None

        # get new trades not logged
        
        trades_items = list(reversed(trades.items()))
        unlogged_trades = []
        found_start = False

        for trade_id, trade_data in trades_items:
            if found_start:
                print("Found start appending")
                unlogged_trades.append(trade_id)
            elif trade_id == self.last_completed_scanned:
                found_start = True  



        first_trade = next(iter(trades))
        self.last_completed_scanned = first_trade
        self.json.update_last_completed(self.cookies['.ROBLOSECURITY'], self.last_completed_scanned)

        if unlogged_trades != []:
            # print("getting self2")
            self.account_inventory = self.refresh_self_inventory()
            # print("done getting self2")
            for trade_id in unlogged_trades:
                trade_info = self.request_handler.requestAPI(f"https://trades.roblox.com/v1/trades/{trade_id}")

                if trade_info.status_code == 200:
                    trade_json = trade_info.json()
                    try:
                        formatted_trade = self.format_trade_api(trade_json)
                        embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(formatted_trade, self.rolimon.item_data, self.rolimon.projected_json.read_data())

                        embed = self.discord_webhook.setup_embed(title=f"Trade Completed ({total_profit} profit)", color=2, user_id=formatted_trade['their_id'], embed_fields=embed_fields, footer="Frick shedletsk")

                        self.discord_webhook.send_webhook(embed, "https://discord.com/api/webhooks/1311127315316478053/Pz_ZrnTRWqCuJoKfnv6W4F9vo04xFVS6pKolHUiP16ByUeGgm-jyHMht9ZF68lStg1v2")   
                    except Exception as e:
                        print("Couldn't format and post webhook.. skipping")
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
                account_algorithm_value += self.rolimon.item_data[str(item)]['rap']
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

        print("getting outbound trades..")
        trades = self.get_trades("https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Asc")
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
            
            #print("scanning outbound")
            trade_info_req = self.request_handler.requestAPI(f"https://trades.roblox.com/v1/trades/{trade_id}")
            if trade_info_req.status_code != 200:
                print("trade info api", trade_info_req.status_code, trade_info_req.text, "response headerS:", trade_info_req.headers, "try to go on", trade_info_req.url, "with the session cookie and headers:", self.request_handler.Session.cookies, self.request_handler.Session.headers, "account:", self.username)
                #self.request_handler.generate_csrf()
                self.last_generated_csrf_timer = time.time()

                time.sleep(10)
                continue

            data = trade_info_req.json() 

            self_offer = data['offers'][0]
            self_robux = self_offer['robux']
            self_items = return_items(self_offer['userAssets'])

            trader_offer = data['offers'][1]
            trader_items = return_items(trader_offer['userAssets'])

            try:
                self_rap, self_value, self_algorithm_value, self_overall = self.calculate_gains(self_items)
                trader_rap, trader_value, trader_algorithm_value, trader_overall = self.calculate_gains(trader_items)
            except Exception as e:
                print("Couldnt calculate gains", e)
                return None

            valid_trade, reason = self.outbound_trader.validate_trade(self_rap, self_algorithm_value, self_value, trader_rap, trader_algorithm_value, trader_value, self_overall, trader_overall, robux=self_robux)

            if not valid_trade:
                print("Canceling Outbound trade for reason:", reason)
                url = f"https://trades.roblox.com/v1/trades/{trade_id}/decline"

                print(f"Self RAP: {self_rap}, Trader RAP: {trader_rap} | Robux: {self_robux}")
                print(f"Self Algo: {self_algorithm_value}, Their Algo: {trader_algorithm_value}")
                print(f"Values - Self: {self_value}, Trader: {trader_value}")

                cancel_request = self.request_handler.requestAPI(url, method="post")
                time.sleep(1)
                if cancel_request.status_code == 200 or cancel_request.status_code == 400:
                    print("Cleared losing outbound...")

    def check_can_trade(self, userid):
        """
            Checks if /trade endpoint is valid for userid
        """
        if int(userid) not in self.all_cached_traders:
            self.all_cached_traders.add(int(userid))


        validation_headers = None
        can_trade = self.request_handler.requestAPI(f"https://www.roblox.com/users/{userid}/trade", additional_headers=validation_headers)
        if can_trade.status_code == 403:
            if "rblx-challenge-id" in can_trade.headers:
                print(can_trade.headers, can_trade.text, "can trade debug")
                validation = self.validate_2fa(can_trade)
                if validation == False:
                    return None
                validation_headers = validation
            return False

        if "NewLogin" in can_trade.url:
            return False

        if can_trade.status_code == 500:
            print("500 error on can trade")
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
            date_str = date_str.split('.')[0] + '.' + date_str.split('.')[1][:6]  # Ensure only 6 digits for microseconds
        
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
        min_graph_difference  = config_projected['MinimumGraphDifference']
        max_graph_difference = config_projected['MaximumGraphDifference']
        min_price_difference = config_projected['MinPriceDifference']
        use_rolimons_projected = config_projected['Detect_Rolimons_Projecteds']
        #TODO: ADD MIN AND MAX DIFFERENCE
        #if not self.config.check_gain(int(rap), int(price), min_gain=min_price_difference, max_gain=max_price_difference):
        #    print("projected due to price difference")
        #    return True


        is_projected = False
        if self.rolimon.item_data[item_id]['projected'] == True and use_rolimons_projected:
            is_projected = True


        while True:
            if collectibleItemId != None:
                url = f"https://apis.roblox.com/marketplace-sales/v1/item/{collectibleItemId}/resale-data"
                "/marketplace-sales/v1/item/5060a9f2-cae0-4123-88c6-0eab5e2e2b59/resale-data"
            else:
                url = f"https://economy.roblox.com/v1/assets/{item_id}/resale-data?limit=100"

            resale_data = self.parse_handler.requestAPI(url)

            if resale_data.status_code == 429:
                print("ratelimited resale data")
                time.sleep(30)
            elif resale_data.status_code == 400:
                print("[ERROR] reslate data 400 handling for", item_id, "please report this if spammed\n", url)
                # Get new id
                details_url = f"https://catalog.roblox.com/v1/catalog/items/{item_id}/details?itemType=asset"
                detail_api = self.parse_handler.requestAPI(details_url)
                if detail_api.status_code == 200:
                    detail_data = detail_api.json()
                    if "collectibleItemId" in detail_data:
                        print(detail_data['collectibleItemId'], "resending back")
                        collectibleItemId=detail_data['collectibleItemId']
                    else:
                        print("the frick collect")
                elif detail_api.status_code == 429:
                    print("Ratelimited detail api")
                    time.sleep(30)
                else:
                    print("Couldn't get details on after 400", item_id, "skipping item", resale_data.text, resale_data.status_code)
                    break
            elif resale_data.status_code == 200:
                if collectibleItemId != None:
                    print("Successfully resolved 400 for resale data")
                break
            else:
                print("Couldn't get details on", item_id, resale_data.text, resale_data.status_code)
                break

        if resale_data.status_code == 200:
            def parse_api_data(data_points):
                return sorted(
                    [{"value": point["value"], "date": self.parse_date(point["date"]).timestamp()}
                        for point in data_points],
                    key=lambda x: x["date"],
                )

            sales_data = parse_api_data(resale_data.json()["priceDataPoints"])
            volume_data = parse_api_data(resale_data.json()["volumeDataPoints"])

            # Instantiate and process the analyzer
            result = SalesVolumeAnalyzer(sales_data, volume_data, item_id).process()

            result_value = result['value']
            result_volume = result['volume']
            result_timestamp = result['timestamp']
            #{'value': 558.2293577981651, 'volume': 84.825, 'timestamp': 1732423848.2720559, 'age': 63157848.272055864} 1609402609


            data_points = resale_data.json()['priceDataPoints']
            # for data in data_points:
            #     if data['value'] < 5:
            #         data_points.remove(data)
            #
            # if len(data_points) < 50:
            #     print("Item has les than 50")
            #     is_projected = True
            #
            today = datetime.utcnow()
            three_months_ago = today - timedelta(days=90)
            
            current_price = int(data_points[0]['value'])
            amount_of_sales = config_projected['AmountofSalestoScan']

            recent_data_points = [
                point for point in data_points
                if self.parse_date(point["date"]) > three_months_ago
            ]

            sum_of_price = 0
            for num, data in enumerate(recent_data_points):
                loop_price = int(data['value'])
                percentage_change = (current_price - loop_price)/current_price

                if percentage_change < -0.4 and percentage_change > 0.4:
                    is_projected = True


            #for data_point in range(1, amount_of_sales+1):
                # TODO: THIS IS BROKEN 
            
            #   rap_data_point = int(data_points[data_point]['value'])
              #  print(rap_data_point, current_data)
               # is_in_range = self.config.check_gain(rap_data_point, current_data, min_gain=min_graph_difference, max_gain=max_graph_difference) 
                #print(rap_data_point - current_data,  ": minimum", min_graph_difference, "max", max_graph_difference, is_in_range)

                #if is_in_range == False:
                 #   print("is projected")
                  #  is_projected = True
                   # break

            volume_data_points = resale_data.json().get('volumeDataPoints', [])[:30]
            # If it has no sale data 

            data = self.rolimon.projected_json.read_data()
            data.update({f"{item_id}": {"is_projected": is_projected, "value": result_value, "volume": result_volume, "timestamp":result_timestamp, "last_price": self.rolimon.item_data[item_id]['best_price']}})
            self.rolimon.projected_json.write_data(data)

#           #if self.analyze_volume_data(volume_data_points) == False:
                #is_projected = True






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
            inventory_api = f"https://inventory.roblox.com/v2/assets/{item_id}/owners?sortOrder=Asc&cursor={next_page_cursor}&limit=100"
            
            response = self.request_handler.requestAPI(inventory_api)

            if response.status_code == 403:
                return None
            elif response.status_code != 200:
                print("Got API response", response.text, "on", response.url, "Trying again, for GTETITING OWNERS")
                continue

            next_page_cursor = response.json()['nextPageCursor']
            for asset in response.json()['data']:
                if asset['owner'] == None:
                    continue
                #print(asset['owner'])
                if int(asset['owner']['id']) in self.all_cached_traders:
                    print("Already in cached traders, scraping active traders")
                    continue
                # else:
                #     print("appending", asset['owner']['id'], "if date is good")
                owner_since = asset['updated']

                # Assuming owner_since is a string like "2024-11-15T12:00:00Z"
                given_date = datetime.fromisoformat(owner_since.replace("Z", "+00:00"))

                # Remove timezone from given_date to make it naive
                given_date_naive = given_date.replace(tzinfo=None)

                # Get today's date and time (naive by default)
                today = datetime.now()

                # Calculate the difference between today and the given date
                time_diff = today - given_date_naive

                # If the owner has had the item for less than 7 days and is not already in the owners or all_cached_traders list, add them
                if time_diff < timedelta(days=7) and asset['owner']['id'] not in owners and int(asset['owner']['id']) not in self.all_cached_traders:
                    print("Scraping active traders.")
                    owners.append(asset['owner']['id'])
        print("owners", owners)
        return owners
    
#while True:
#    hat = input("enter id > ")
#    if RobloxAPI().is_projected(hat) == True:
#        print("Is projected")
#    else:
#        print("Not projected")
    




