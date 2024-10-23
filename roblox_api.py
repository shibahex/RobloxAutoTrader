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

        self.request_handler.headers['x-csrf-token'] = self.refresh_csrf()
        self.authenticator = None
        #print(self.check_can_trade(6419225))

    def verify_correct_auth(self):
        json_file = self.json_handler.read_data()
        account_list = json_file['roblox_accounts']
        # find the account in cookies.json then fetch the auth token then return the Auth code
        for account in account_list:
            if account['cookie'] == self.cookies['.ROBLOSECURITY']:
                try:
                    self.authenticator = pyotp.TOTP(account['auth'])
                    return self.authenticator
                except:
                    print("Couldnt get auth")
                    raise ValueError("Authentication failed..")

    
    def validate_authorization(self, challenge_id):
        #if self.authenticator == None:
            #self.authenticator = self.verify_correct_auth()
        # NOTE: this is for testing purposes because i dont have multiple cookies setup yet
        self.authenticator = pyotp.TOTP("X3N5BTXMDWKELMK3W5DNBUA3FA")

        # Challenge ID is from a ticket from a bounded cookie
        # To get a new token for a cookie you have to use the login API
        # With selenium I should be able to get this token though.
        # by 1. putting cookie in and 2. requesting to trade and then listening for an API
        data = {"challengeId":"b07994e5-56e3-43c0-8ab4-e88a8b67c424","actionType":"Generic","code":f"{self.authenticator.now()}"}

        response = self.request_handler.requestAPI("https://twostepverification.roblox.com/v1/users/1283171278/challenges/authenticator/verify", "post", payload=data)
        
        print(response.text)
        print("now doing continue")
        if response.status_code == 200:
            verify_token = response.json()['verificationToken']


            verify_payload = {
                "challengeId": f"{challenge_id}",
                "challengeMetadata": f'{{"verificationToken":"{verify_token}","rememberDevice":false,"challengeId":"{challenge_id}","actionType":"Generic"}}',
                "challengeType": "twostepverification"
            }

            continue_api = self.request_handler.requestAPI("https://apis.roblox.com/challenge/v1/continue", "post", verify_payload)
            print(continue_api.text, ("blablalfalfalfla"))
            
            return verify_token

    # refresh current inventory
    def refresh_self_inventory(self):
        self.account_inventory = self.fetch_inventory(self.account_id, apply_NFT=True)
        if self.account_inventory == False:
            raise ValueError("Account has no tradeable items")

    def refresh_csrf(self):
        token_post = self.request_handler.requestAPI('https://catalog.roblox.com/v1/catalog/items/details', method="post")

        if 'x-csrf-token' in token_post.headers:
            print("returning",token_post.headers['x-csrf-token'])

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
            {"userId":trader_id,"userAssetIds":trade_recieve,
            "robux":None},
            {"userId":self.account_id,"userAssetIds":trade_send,
            "robux":None}]}


        while True:
            trade_response = self.request_handler.requestAPI("https://trades.roblox.com/v1/trades/send", "post", payload=trade_payload)
            
            if trade_response.status_code == 200:
                print("Trade sent!")
                return True
            elif trade_response.status_code == 403:
                if "challenge" in trade_response.text.lower():
                    print("solving 2fa..")
                    challenge_ID = trade_response.headers['rblx-challenge-id']
                    verify_token = self.validate_authorization(challenge_ID)
                    # put verify token in headers I think
                    # self.request_handler.headers['lna'] = verify_token
                    break
                else:
                    newtoken = self.refresh_csrf()
                    if newtoken:
                        self.request_handler.headers['x-csrf-token'] = self.refresh_csrf()
                    else: 
                        print("got error getting token")
                        break
            else:
                print("errored at trade")
                print(trade_response.text)
                break

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
