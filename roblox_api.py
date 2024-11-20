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

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, auth_secret=None, auth_ticket=None, Proxies=False):

        self.parse_handler = RequestsHandler(Session=requests.Session(), use_proxies=True) 
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
            self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
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
        self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
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

    def fetch_inventory(self, userid, apply_NFT=False):
        #TODO: use roblox API
        return self.rolimon.get_inventory(userid, apply_NFT)

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

    def send_trade(self, trader_id, trade_send, trade_recieve):
        """
            Send Trader ID Then the list of items (list of assetids)
        """
        trade_payload = {"offers":[
            {"userId":trader_id,"userAssetIds":trade_recieve,
            "robux":None},
            {"userId":self.account_id,"userAssetIds":trade_send,
            "robux":None}]}


        validation_headers = None
        while True:
            trade_response = self.request_handler.requestAPI("https://trades.roblox.com/v1/trades/send", "post", payload=trade_payload, additional_headers=validation_headers)
            
            if trade_response.status_code == 200:
                print("Trade sent!", trade_response.text)
                return trade_response.json()['id']
            elif trade_response.status_code == 403:
                print("403 error:", trade_response.json())
                if 'rblx-challenge-id' in trade_response.headers:
                    print("doing 2fa shit")
                    validation = self.validate_2fa(trade_response)
                    if validation == False:
                        return None
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

        #trade_response = self.TradeSendSession.post("https://trades.roblox.com/v1/trades/send", proxies=self.SendProxy, json=data, headers=self.headers, timeout=60)

        pass

    def outbound_checker(self):
        """
            Scans Json for trades then cancel trades that dont fit into the config
        """
        outbounds = self.json.get_outbounds(cookie=self.cookies['.ROBLOSECURITY'])
        if outbounds:
            for trade in outbounds:
                trade_id = trade['trade_id']

                account_items = trade['self_items']
                account_rap = 0
                account_value = 0

                for item in account_items:
                    account_rap += self.rolimon.item_data[item]['rap']
                    account_value += self.rolimon.item_data[item]['total_value']


                trader_items = trade['their_items']
                trader_rap = 0
                trader_value = 0
                for item in trader_items:
                    trader_rap += self.rolimon.item_data[item]['rap']
                    trader_value += self.rolimon.item_data[item]['total_value']
                
                timestamp = trade['timestamp']
                timestamp_date = datetime.datetime.fromtimestamp(timestamp)
                
                current_date = datetime.datetime.now()
                valid_trade = TradeMaker().validate_trade(account_rap, account_value, trader_rap, trader_value)

                if not TradeMaker().validate_trade(account_rap, account_value, trader_rap, trader_value) or current_date - timestamp_date >= datetime.timedelta(days=5):
                    # Cancel
                    #https://trades.roblox.com/v1/trades/3534001725946517/decline
                    url = f"https://trades.roblox.com/v1/trades/{trade_id}/decline"

                    cancel_request = self.request_handler.requestAPI(url, method="post")
          #          print(cancel_request.status_code, "outbound")
                    if cancel_request.status_code == 200 or cancel_request.status_code == 400:
                        self.json.remove_trade(cookie=self.cookies['.ROBLOSECURITY'], trade_id=trade_id)
         #               print("Cleared losing outbound...")
                    else:
                        print(cancel_request.text)

    def check_can_trade(self, userid):
        """
            Checks if /trade endpoint is valid for userid
        """
        # TODO: Handle this pls tmr next priority
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
    
    def is_projected(self, item_id):
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

        if value != rap:
            return False

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
            #print(resale_data.json())
            data_points = resale_data.json()['priceDataPoints']

            for data in data_points:
                if data['value'] == 1:
                    data_points.remove(data)
            # If doesnt have enough sale data just mark it as projected
            if len(data_points) < 100:
                return True

            current_data = int(data_points[0]['value'])

            amount_of_sales = config_projected['AmountofSalestoScan']

            #print(data_points, current_data)
            for data_point in range(1, amount_of_sales+1):
                rap_data_point = int(data_points[data_point]['value'])
                is_in_range = self.config.check_gain(rap_data_point, current_data, min_gain=min_graph_difference, max_gain=max_graph_difference) 
                #print(rap_data_point - current_data,  ": minimum", min_graph_difference, "max", max_graph_difference, is_in_range)

                if is_in_range == False:
                    return True
            
            #for volume_data in resale_data.json()['volumeDataPoints']:
            volume_data_points = resale_data.json().get('volumeDataPoints', [])[:30]
            if self.analyze_volume_data(volume_data_points) == False:
                return True


        return False

    def analyze_volume_data(self, volume_data_points):
        """
            Scans volume date and sees how active an item is selling and if theres large gaps of 7 days between sales it returns False
        """
        # Function to calculate date differences in days
        def calculate_date_diff(dates):
            date_diffs = []
            for i in range(1, len(dates)):
                # Parse the previous and current date string to datetime objects
                prev_date = datetime.datetime.strptime(dates[i - 1], "%Y-%m-%dT%H:%M:%SZ")
                curr_date = datetime.datetime.strptime(dates[i], "%Y-%m-%dT%H:%M:%SZ")
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

        while len(owners) < 5:
            inventory_api = f"https://inventory.roblox.com/v2/assets/{item_id}/owners?sortOrder=Asc&cursor={next_page_cursor}&limit=100"
            
            response = self.request_handler.requestAPI(inventory_api)

            for asset in response.json()['data']:
                if asset['owner'] == None:
                    print("null owner")
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
                    print("appended owner")
                    owners.append(asset['owner'])



            if response.status_code != 200:
                print("Got API response", response.text, "on", response.url, "Trying again")
                continue
        
        return owners
    
#while True:
#    hat = input("enter id > ")
#    if RobloxAPI().is_projected(hat) == True:
#        print("Is projected")
#    else:
#        print("Not projected")
    



