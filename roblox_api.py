from handler import *
import requests
import datetime
import os
from rolimons_api import RolimonAPI

class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie:dict=None, Proxies=None):
        self.request_handler = RequestsHandler(cookie=cookie)
        # no cookie
        self.parse_handler = RequestsHandler(Proxies) 
        self.rolimon_parser = RolimonAPI()

        self.account_id = self.fetch_userid()
        self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
        
        if not self.account_inventory:
            print(f"Account {self.account_id} has tradeable items")
        print(self.check_can_trade(6419225))

    def refresh_csrf(self):
        token_post = self.request_handler.requestAPI('https://catalog.roblox.com/v1/catalog/items/details', method="post")

        if 'x-csrf-token' in token_post.headers:
            return token_post.headers['x-csrf-token']
        else:
            print("Couldnt fetch x-csrf-token")
            return False
        pass

    def fetch_userid(self):
        auth_response = self.request_handler.requestAPI("https://users.roblox.com/v1/users/authenticated")
        if auth_response.status_code == 200: 
            return auth_response.json()['id']

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

print(RobloxAPI(cookie={'.ROBLOSECURITY': os.environ['cookie_secret']}).fetch_userid())
