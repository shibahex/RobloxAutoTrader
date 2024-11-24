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

from handler.price_algorithm import SalesVolumeAnalyzer

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, auth_secret=None, auth_ticket=None, Proxies=False):

        self.outbounds_userids = []


        # For rolimon Trade Ads
        self.last_outbound = None
        # TODO:
        # put this in cookies.json
        self.tradead_timestamp = None


        #TODO: USE PROXIES
        self.parse_handler = RequestsHandler(Session=requests.Session(), use_proxies=False) 
        self.config = ConfigHandler('config.cfg')

        self.rolimon = rolimons_api.RolimonAPI()


        if cookie != None:
            self.cookies = cookie
            self.authenticator = pyotp.TOTP(auth_secret)
            self.auth_ticket = auth_ticket
            self.request_handler = RequestsHandler(cookie=self.cookies, use_proxies=False)
            self.json = JsonHandler('cookies.json')
            self.auth_handler = AuthHandler()


            self.account_id, self.username = self.fetch_userid_and_name()
            self.account_inventory = self.fetch_inventory(self.account_id)
            if self.account_id == False:
                print("Failed to get userid for cookie", cookie)
                raise ValueError("Invalid account or cookie.")

            if not self.account_inventory:
                print(f"{self.username} has no tradeable items")
                raise ValueError("Account has no tradeable items.")

            self.request_handler.headers.update({'X-CSRF-TOKEN': self.refresh_csrf()})

    
    # refresh current inventory
    def refresh_self_inventory(self):
        """
            Gets inventory of current .ROBLOSECURITY used on class
        """
        self.account_inventory = self.fetch_inventory(self.account_id)
        if self.account_inventory == False:
            raise ValueError("Account has no tradeable items")

    def refresh_csrf(self):
        """
            returns CSRF token to validate next request
        """
        token_post = self.request_handler.requestAPI('https://catalog.roblox.com/v1/catalog/items/details', method="post")

        if 'x-csrf-token' in token_post.headers:
            print("returning",token_post.headers['x-csrf-token'])
            return token_post.headers['x-csrf-token']
        else:
            print("Couldnt fetch x-csrf-token")
            return False
        pass

    def fetch_userid_and_name(self):
        """
            Gets info on the current account to self class
        """
        auth_response = self.request_handler.requestAPI("https://users.roblox.com/v1/users/authenticated")
        if auth_response.status_code == 200: 
            return auth_response.json()['id'], auth_response.json()['name']
        else:
            raise ValueError("Couldnt login with cookie", self.cookies)

    def fetch_inventory(self, userid):
        #TODO: use roblox API
        cursor = ""
        inventory = {}
        while cursor != None:
            inventory_API = f"https://inventory.roblox.com/v1/users/{userid}/assets/collectibles?cursor={cursor}"
            response = self.request_handler.requestAPI(inventory_API)
            if response.status_code != 200:
                print("inventory API error", inventory_API, response.status_code, response.text)
                return False
            
            for item in response.json()['data']:
                if item['isOnHold'] == True:
                    continue
                # TODO: APPLY NFT
                # TODO: IF USERID = SELF.USERID THEN DONT APPLY NFT
                uaid = str(item['userAssetId'])
                itemId = str(item['assetId'])
                inventory[uaid] = {"item_id": itemId}

            return self.rolimon.add_data_to_inventory(inventory)



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
        verification_token = self.auth_handler.verify_request(self.request_handler, senderid, metadata_challengeid, self.authenticator.now())

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
        cursor = ""
        page_count = 0
        trades = {}
        while cursor != None:
            if page_count and page_count >= limit_pages:
                break

            response = self.request_handler.requestAPI(f"{page_url}&cursor={cursor}")
            if response.status_code == 200:
                trades.update(self.return_trade_details(response.json()['data']))
                cursor = response.json()['nextPageCursor']
                page_count += 1

        return trades  

    def counter_trades(self):
        # TODO: make the counter kind of like the original trade
        # Get info about trade
        trades = self.get_trades("https://trades.roblox.com/v1/trades/inbound?limit=100&sortOrder=Desc")
        for trade_id, trade_info in trades.items():
            trader_id = trade_info['user_id']
            trade_id = trade_info['trade_id']

            trader_inventory = self.fetch_inventory(trader_id)

            generated_trade = TradeMaker().generate_trade_with_timeout(self.account_inventory, trader_inventory, counter_trade=True)

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

    def send_trade(self, trader_id, trade_send, trade_recieve, self_robux=None, counter_trade=False, counter_id=None):
        """
            Send Trader ID Then the list of items (list of assetids)
        """
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
                return trade_response.status_code
            elif trade_response.status_code == 403:
                print("403 error:", trade_response.json())
                if 'rblx-challenge-id' in trade_response.headers:
                    print("doing 2fa shit")
                    validation = self.validate_2fa(trade_response)
                    if validation == False:
                        return 403
                    validation_headers = validation
                    continue
               
                else:
                    print("getting csrf")
                    newtoken = self.refresh_csrf()
                    if newtoken:
                        self.request_handler.headers.update({'X-CSRF-TOKEN': newtoken})
                        print("update x csrf token", self.request_handler.headers)
                    else: 
                        print("got error getting token")
                        break
                    print("got 403 sending trade, trying to generate csrf")
            else:
                print("errored at trade")
                print(trade_response.text)
                break


    def get_recent_traders(self, max_days_since=5):
        """
            Sends a list of your last inbounds and outbounds
            TODO: make it have dates too so we can have cooldowns on users
        """

        recently_traded = []
        check_urls = ["https://trades.roblox.com/v1/trades/inactive?limit=100&sortOrder=Desc", "https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Asc", "https://trades.roblox.com/v1/trades/inbound?cursor=&limit=100&sortOrder=Desc"]

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
                    recently_traded.append(trader_id)

        return recently_traded

    def outbound_api_checker(self):
        """
            Scans the outbound API for bad trades then cancels them.
            Json way is more messy and not needed for this bot
        """

        trades = self.get_trades("https://trades.roblox.com/v1/trades/outbound?limit=100&sortOrder=Asc")
        def return_items(user_assets):
            asset_ids = []
            for asset in user_assets:
                asset_ids.append(asset['assetId'])
            return asset_ids
            

        def calculate_gains(items):
            account_rap = 0
            account_value = 0
            account_algorithm_value = 0
            projected_data = self.rolimon.projected_json.read_data()

            for item in items:
                if str(item) in projected_data.keys():
                    account_algorithm_value += projected_data[str(item)]['value']
                else:
                    account_algorithm_value += self.rolimon.item_data[str(item)]['total_value']

                account_rap += self.rolimon.item_data[str(item)]['rap']
                account_value += self.rolimon.item_data[str(item)]['total_value']

            return account_rap, account_value, account_algorithm_value


        # Loop through outbounds
        for trade_id, trade_info in trades.items():
            trader_id = trade_info['user_id']
            if trader_id not in self.outbounds_userids:
                self.outbounds_userids.append(trader_id)

            trade_id = trade_info['trade_id']
            
            print("scanning outbound")
            trade_info = self.request_handler.requestAPI(f"https://trades.roblox.com/v1/trades/{trade_id}")
            if trade_info.status_code != 200:
                print("trade info api", trade_info.status_code, trade_info.text)
                return False

            data = trade_info.json() 

            self_offer = data['offers'][0]
            self_robux = self_offer['robux']
            self_items = return_items(self_offer['userAssets'])

            trader_offer = data['offers'][1]
            trader_items = return_items(trader_offer['userAssets'])

            self_rap, self_value, self_algorithm_value = calculate_gains(self_items)
            trader_rap, trader_value, trader_algorithm_value = calculate_gains(trader_items)

            valid_trade = TradeMaker().validate_trade(self_rap, self_algorithm_value, self_value, trader_rap, trader_algorithm_value, trader_value, robux=self_robux)

            if not valid_trade:
                url = f"https://trades.roblox.com/v1/trades/{trade_id}/decline"

                print(self_rap, trader_rap, "cancel raps", "robux:",self_robux, "Values:", self_value, trader_value)
                cancel_request = self.request_handler.requestAPI(url, method="post")
                time.sleep(1)
                if cancel_request.status_code == 200 or cancel_request.status_code == 400:
                    print("Cleared losing outbound...")
                else:
                    print(cancel_request.text)
            else:
                print("Valid trade")

    def check_can_trade(self, userid):
        """
            Checks if /trade endpoint is valid for userid
        """
        if int(userid) not in self.outbounds_userids:
            self.outbounds_userids.append(int(userid))


        validation_headers = None
        can_trade = self.request_handler.requestAPI(f"https://www.roblox.com/users/{userid}/trade", additional_headers=validation_headers)
        if can_trade.status_code == 403:
            if "rblx-challenge-id" in can_trade.headers:
                print(can_trade.headers, can_trade.text)
                validation = self.validate_2fa(can_trade)
                if validation == False:
                    return None
                validation_headers = validation

            return False
        if "NewLogin" in can_trade.url:
            return False
        return True
    
    def median(self, lst):
        """
            Pmethod wrote this and im lazy
        """
        print(lst)
        n = len(lst)
        if n < 1:
            return None
        if n % 2 == 1:
            return sorted(lst)[n // 2]
        else:
            return sum(sorted(lst)[n // 2 - 1:n // 2 + 1]) / 2.0

    def is_projected_api(self, item_id):
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

        #TODO: ADD MIN AND MAX DIFFERENCE
        #if not self.config.check_gain(int(rap), int(price), min_gain=min_price_difference, max_gain=max_price_difference):
        #    print("projected due to price difference")
        #    return True

        # Check graph for projecteds
        resale_data = self.parse_handler.requestAPI(f"https://economy.roblox.com/v1/assets/{item_id}/resale-data")

        if resale_data.status_code == 200:

            is_projected = False

            def parse_api_data(data_points):
                return sorted(
                    [{"value": point["value"], "date": datetime.strptime(point["date"], "%Y-%m-%dT%H:%M:%SZ").timestamp()}
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
            for data in data_points:
                if data['value'] < 5:
                    data_points.remove(data)

            if len(data_points) < 50:
                return None

            today = datetime.utcnow()
            three_months_ago = today - timedelta(days=90)
            
            current_price = int(data_points[0]['value'])
            amount_of_sales = config_projected['AmountofSalestoScan']

            recent_data_points = [
                point for point in data_points
                if datetime.strptime(point['date'], "%Y-%m-%dT%H:%M:%SZ") > three_months_ago
            ]

            sum_of_price = 0
            for num, data in enumerate(recent_data_points):
                loop_price = int(data['value'])
                percentage_change = (current_price - loop_price)/current_price

                if percentage_change < -0.4 and percentage_change > 0.4:
                    print("projected", item_id)
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
#           #if self.analyze_volume_data(volume_data_points) == False:
                #is_projected = True


        return {f"{item_id}": {"is_projected": is_projected, "value": result_value, "volume": result_volume, "timestamp":result_timestamp, "last_price": self.rolimon.item_data[item_id]['best_price']}}
        #return False

    def analyze_volume_data(self, volume_data_points):
        """
            Scans volume date and sees how active an item is selling and if theres large gaps of 7 days between sales it returns False
        """
        # Function to calculate date differences in days
        def calculate_date_diff(dates):
            date_diffs = []
            for i in range(1, len(dates)):
                # Parse the previous and current date string to datetime objects
                prev_date = datetime.strptime(dates[i - 1], "%Y-%m-%dT%H:%M:%SZ")
                curr_date = datetime.strptime(dates[i], "%Y-%m-%dT%H:%M:%SZ")
                # Calculate the difference in days between the two dates
                diff = abs((curr_date - prev_date).days)
                date_diffs.append(diff)
            return date_diffs
        
        values = [point['value'] for point in volume_data_points]
        dates = [point['date'] for point in volume_data_points]

        avg_value = sum(values) / len(values) if values else 0
        print(f"Average Value: {avg_value:.2f}")

        date_diffs = calculate_date_diff(dates)

        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
        print(f"Average Date Difference (in days): {avg_date_diff:.2f}")

        large_gaps = [diff for diff in date_diffs if diff > 7]

        # Optionally, print the large gaps for debugging purposes
        if large_gaps:
            print("Large gaps between dates (in days):", large_gaps)
            return False

    def get_active_traders(self, item_id):
        """
            Scan atleast 3 pages of owners and append new owners
            If less than 5 owners isn't found it will contintue to the next pages
        """
        owners = []
        next_page_cursor = ""

        while len(owners) < 5 and next_page_cursor != None:
            inventory_api = f"https://inventory.roblox.com/v2/assets/{item_id}/owners?sortOrder=Asc&cursor={next_page_cursor}&limit=100"
            
            response = self.request_handler.requestAPI(inventory_api)

            if response.status_code != 200:
                print("Got API response", response.text, "on", response.url, "Trying again")
                continue

            next_page_cursor = response.json()['nextPageCursor']
            for asset in response.json()['data']:
                if asset['owner'] == None:
                    continue
                owner_since = asset['updated']

                # Assuming owner_since is a string like "2024-11-15T12:00:00Z"
                given_date = datetime.fromisoformat(owner_since.replace("Z", "+00:00"))

                # Remove timezone from given_date to make it naive
                given_date_naive = given_date.replace(tzinfo=None)

                # Get today's date and time (naive by default)
                today = datetime.now()

                # Calculate the difference between today and the given date
                time_diff = today - given_date_naive

                if time_diff < timedelta(days=7):
                    print("appended owner", asset['owner'])
                    owners.append(asset['owner']['id'])



        print("return", owners) 
        return owners
    
#while True:
#    hat = input("enter id > ")
#    if RobloxAPI().is_projected(hat) == True:
#        print("Is projected")
#    else:
#        print("Not projected")
    



