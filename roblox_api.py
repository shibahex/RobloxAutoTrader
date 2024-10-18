from handler import *
import requests
import datetime
import os
import pyotp
from rolimons_api import RolimonAPI

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, Proxies=None):
        self.cookies = cookie

        self.request_handler = RequestsHandler(cookie=self.cookies)
        # no cookie
        self.parse_handler = RequestsHandler(Proxies) 
        self.rolimon_parser = RolimonAPI()
        
        self.json_handler = JsonHandler('cookies.json')

        self.account_id, self.username = self.fetch_userid_and_name()
        self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
        if self.account_id == False:
            print("Failed to get userid for cookie", cookie)
            raise ValueError("Invalid account or cookie.")

        if not self.account_inventory:
            print(f"{self.username} has no tradeable items")
            raise ValueError("Account has no tradeable items.")
        #print(self.check_can_trade(6419225))

    def verify_auth(self):
        json_file = self.json_handler.read_data()
        account_list = json_file['roblox_accounts']
        # find the account in cookies.json then fetch the auth token then return the Auth code
        for account in account_list:
            if account['cookie'] == self.cookies['.ROBLOSECURITY']:
                try:
                    authentcator = pyotp.TOTP(account['auth'])
                    return authentcator.now()
                except:
                    print("Couldnt get auth")
                    raise ValueError("Authentication failed..")

    # refresh current inventory
    def refresh_self_inventory(self):
        self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
        if self.account_inventory == False:
            raise ValueError("Account has no tradeable items")

    def refresh_csrf(self):
        token_post = self.request_handler.requestAPI('https://catalog.roblox.com/v1/catalog/items/details', method="post")

        if 'x-csrf-token' in token_post.headers:
            return token_post.headers['x-csrf-token']
        else:
            print("Couldnt fetch x-csrf-token")
            return False
        pass

    def fetch_userid_and_name(self):
        auth_response = self.request_handler.requestAPI("https://users.roblox.com/v1/users/authenticated")
        if auth_response.status_code == 200: 
            return auth_response.json()['id'], auth_response.json()['name']
        else:
            raise ValueError("Couldnt login with cookie", self.cookies)
    def fetch_inventory(self, userid, apply_NFT=False):
        return self.rolimon_parser.get_inventory(userid, apply_NFT)


    # NOTE: Payload:
    # {"offers":[{"userId":4486142832,"userAssetIds":[672469540],"robux":null},{"userId":1283171278,"userAssetIds":[1310053014],"robux":null}]}
    def send_trade(self, trader_id, trade_send, trade_recieve):
        """
            Send Trader ID Then the list of items (list of assetids)
        """
        trade_payload = {"offers":[
            {"userId":trader_id,"userAssetIds":[trade_recieve],
            "robux":null},
            {"userId":self.account_id,"userAssetIds":[trade_send],
            "robux":null}]}

        #trade_response = self.TradeSendSession.post("https://trades.roblox.com/v1/trades/send", proxies=self.SendProxy, json=data, headers=self.headers, timeout=60)

        pass

    def check_can_trade(self, userid):
        # TODO: Handle this pls tmr next priority
        can_trade = self.request_handler.requestAPI(f"https://www.roblox.com/users/{userid}/trade")
        if "NewLogin" in can_trade.url:
            return False
        return True
#RobloxAccount = RobloxAPI().fetch_userid()

#print(RobloxAPI(cookie={'.ROBLOSECURITY': os.environ['cookie_secret']}).fetch_userid_and_name()())
