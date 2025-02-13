import time
import traceback
from rolimons_api import RolimonAPI
from roblox_api import RobloxAPI
from trade_algorithm import TradeMaker
from handler import *
import threading
from datetime import datetime, timedelta
from handler.handle_json import JsonHandler
from account_manager import AccountManager
import config_manager
from handler.account_settings import HandleConfigs
import os
import sys
from whitelist_manager import WhitelistManager
from handler.handle_whitelist import Whitelist

"""
    have total value gain (total value of items traded)

    if account has no value items, maybe swatch to rap_config.cfg?
    have value_config.cfg

    fix outbound checking cancel outbounds thats above the max
    Fix bad imports and messy imports..


    1. multithread appending owners (bake in get inventory so multiple threads work on inventories)
    maybe have projected scanning in another thread somehow? dont let the whole program wait on 1 thread for projected scanning

    Rolimon ads and discord ads for more counters!

    Trade send thread should be seprate from scanning inventories threads bc ratelimit on resale-data
"""
class Doggo:
    def __init__(self):
        self.user_queue = {}
        self.cli = Terminal()
        self.json = JsonHandler(filename="cookies.json")
        self.rolimons = RolimonAPI()

        # NOTE: use roblo accounts trademaker
        #self.trader = TradeMaker()
        self.account_configs = HandleConfigs()

        self.discord_webhook = DiscordHandler()

        # Define a stop event that will be shared between threads
        self.stop_event = threading.Event()
        self.whitelist = Whitelist()
        self.whitelist_manager = WhitelistManager()

    def whitelist_thread(self):
        while True:
            time.sleep(300)
            try:
                if not os.path.isfile(".whitelist"):
                    sys.exit()
                data = self.whitelist_manager.json.read_data()
                if data and data.get('username') and data.get('password') and data.get('orderid'):
                    valid = self.whitelist.is_valid(username=data['username'], password=data['password'], orderid=data['orderid'])
                    if not valid:
                        print("Whitelist not valid")
                        sys.exit()
                else:
                    sys.exit()

            except Exception as e:
                print("Couldn't validate whitelist", e)
                sys.exit()
    def validate_whitelist(self):
        while True:
            try:
                if not os.path.isfile(".whitelist"):
                    print("sending to whitelist menu")
                    self.whitelist_manager.main()
                data = self.whitelist_manager.json.read_data()
                if data and data.get('username') and data.get('password') and data.get('orderid'):
                    if self.whitelist.is_valid(data['username'], data['password'], data['orderid']):
                        return True
                    else:
                        return False
                else:
                    self.whitelist_manager.main()
            except Exception as e:
                print(e)
                pass


    def main(self):
        while True:
            self.cli.clear_console()
            self.display_main_menu()
    
    def display_main_menu(self):
        options = (
            (1, "Account Manager"),
            (2, "Config Manager"),
            (3, "Execute Trader"),
            (4, "Whitelist Menu")
        )
        self.cli.print_menu("Main Menu", options)
        try:
            answer = int(self.cli.input_prompt("Enter Option"))
            self.handle_menu_selection(answer)
        except ValueError as e:
            self.cli.print_error(f"ERROR: {e}")
    
    def handle_menu_selection(self, selection):
        match selection:
            case 1:
                AccountManager().main()
            case 2:
                # Trade Manager functionality can be implemented here
                config_manager.AccountSettings()
               
                pass
            case 3:
                self.start_trader()

    def queue_traders(self, roblox_account: RobloxAPI()):
        try:
            while not self.stop_event.is_set():
                if len(self.user_queue) > 20:
                    print("user queue is above 20")
                    time.sleep(40)
                    continue
                random_item = self.rolimons.return_item_to_scan()['item_id']

                owners=[]
                roblox_account.get_active_traders(random_item, owners)
                print("fetched new owners", owners, "\n","*"*30)


                for owner in owners:
                    if int(owner) in roblox_account.all_cached_traders:
                            print("already traded with player, skipping")
                            continue

                    print("checking if can trade")
                    roblox_account.all_cached_traders.add(owner)
                    if roblox_account.check_can_trade(owner):
                        print("can trade with", owner, "checking invetory..")
                        inventory = roblox_account.fetch_inventory(owner)
                        print("fetched inventory for", owner)
                        self.user_queue[owner] = inventory
                    time.sleep(.15) 
        except Exception as e:
            tb = traceback.format_exc()  # Capture the full traceback
            print(e, tb)
            with open("log.txt", "a") as log_file:
                log_file.write(f"Error in queue_traders: {e}, {tb}\n")


    def merge_lists(self, list1, list2):
        # Use set to merge and remove duplicates
        return list(set(list1) | set(list2))

    def update_data_thread(self):
        while True:
            time.sleep(1)
            self.rolimons.update_data()      
            roblox_accounts = self.load_roblox_accounts()

            for account in roblox_accounts:
                account.outbound_api_checker()
                account.check_completeds()
                # NOTE: off bc i have a good inbound
                #account.counter_trades()


    def start_trader(self):
        if not self.validate_whitelist():
            print("Whitelist not valid")
            return False
        roblox_accounts = self.load_roblox_accounts()
        outbound_thread = threading.Thread(target=self.update_data_thread)
        outbound_thread.daemon = True
        outbound_thread.start()

        time.sleep(1)
        while True:
            threads = []
            if roblox_accounts == []:
                input("No active accounts found!")
                break
            for current_account in roblox_accounts:
                # Check if all accounts are rate-limited
                # TODO: EDIT ratelimited function to not count disabled accounts
                if self.json.is_all_ratelimited():
                    print("All cookies are ratelimited. Waiting for 20 minutes...")
                    time.sleep(20 * 60)
                    break  # retry loop

                if self.json.check_ratelimit_cookie(current_account.cookies['.ROBLOSECURITY']):
                    print(current_account.username, "ratelimited continuing to next acc")
                    continue

                # Get inventory
                current_account.refresh_self_inventory()

                if not current_account.account_inventory:
                    print(current_account.username, "has no tradeable inventory")
                    time.sleep(5)
                    continue
                if current_account.check_premium(current_account.account_id) == False:
                    print(current_account.username, "is not premium")
                    time.sleep(5)
                    continue

                current_account.get_recent_traders()  

                # TODO: add max days inactive in cfg and parse as arg

                #print("trading with:", current_account.username, "auth code", current_account.auth_secret, current_account.account_id, "cookie=", current_account.request_handler.Session.cookies.get_dict())

                # to make the threads run even after stop event is called and another thread starts
                self.stop_event.clear()
                queue_thread = threading.Thread(target=self.queue_traders, args=(current_account,))
                queue_thread.daemon = True
                queue_thread.start()

                threads.append((queue_thread))

                # After queuing, start processing trades for the account (is a while true)
                self.process_trades_for_account(current_account)

                # Wait for all threads to finish before moving to next iteration
                print("Stopping threads...")
                self.stop_event.set()  # Signal all threads to stop

                for thread in threads:
                    thread.join()
            time.sleep(60)


    def process_trades_for_account(self, account):
        while True:
            try:
                account_inventory = account.account_inventory

                # Check if user queue is empty
                while not self.user_queue:
                    time.sleep(10)

                #current_user_queue = self.user_queue.copy()
                
                for trader in list(self.user_queue.keys()):  # Using list() creates a copy of the keys
                    print("trading with", trader)
                    trader_inventory = self.user_queue[trader]
                    
                        
                    # Delete the key from the dictionary
                    self.user_queue.pop(trader, None)  # Safely remove the key using pop
                    
                    print("popped trader")
                    # Generate and send trade if there are items to trade
                    if account_inventory and trader_inventory:
                        print("generating trade for", account.username)
                        generated_trade = account.TradeMaker.generate_trade(account_inventory, trader_inventory)


                        if not generated_trade:
                            print("no generated trade for", account.username)
                            break

                        print(f"Generated trade: {generated_trade}", account.username)

                        # Extract trade details
                        self_side = generated_trade['self_side']
                        their_side = generated_trade['their_side']
                        self_robux = generated_trade['self_robux']

                        send_trade_response = account.send_trade(trader, self_side, their_side, self_robux=self_robux)

                        if send_trade_response == 429:  # Rate-limited
                            print("Roblox account limited")
                            self.json.add_ratelimit_timestamp(account.cookies['.ROBLOSECURITY'])
                            return False

                        # Handle webhook
                        if send_trade_response:
                            def get_duplicate_items(side: tuple, inventory: dict) -> list:
                                assetids = []
                                for asset_id in side:
                                    valid_item = inventory.get(asset_id)
                                    if valid_item:
                                        assetids.append(valid_item['item_id'])
                                return assetids

                            # Get duplicated item_ids from asset_ids
                            self_items = get_duplicate_items(self_side, account_inventory)
                            trader_items = get_duplicate_items(their_side, trader_inventory)

                            generated_trade['self_side_item_ids'] = self_items
                            generated_trade['their_side_item_ids'] = trader_items

                            embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(generated_trade, self.rolimons.item_data, self.rolimons.projected_json.read_data())

                            embed = self.discord_webhook.setup_embed(title=f"Sent a trade with {total_profit} total profit", color=1, user_id=trader, embed_fields=embed_fields, footer="Frick shedletsky")
                            self.discord_webhook.send_webhook(embed, "https://discord.com/api/webhooks/1311127129731108944/RNlwYAMpLH1tJmwSTNDfuFOb9id2EmfC9AEvwSu5Gh-RNKcze35Pnp8asRBGt7dRsUaI")                    # Send trade request
                            pass
            except Exception as e:
                print("Error in process_trades_for_account:", e)
                #exc_type, exc_obj, exc_tb = sys.exc_info()
                #fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                #print(exc_type, fname, exc_tb.tb_lineno)
                log_file = open("log.txt", "a")
                log_file.write(f"Error in process_trades_for_account: {e}\n")
                log_file.close()

                input("error in process_trades_for_account")



    def load_roblox_accounts(self):
        cookie_json = self.json.read_data()
        roblox_accounts = []

        for account in cookie_json['roblox_accounts']:
            # Dont use account if its disabled
            if account['use_account'] == False:
                continue

            roblox_cookie = {'.ROBLOSECURITY': account['cookie']}
            auth_secret = account['auth_secret']
            last_completed = account['last_completed']
            user_id = account['user_id']

            # TODO: ADD CUSTOM CONFIG
                
                
            roblox_account = RobloxAPI(cookie=roblox_cookie, auth_secret=auth_secret)
            user_config = self.account_configs.get_config(user_id)
            if user_config:
                roblox_account.config.trading = user_config
            else:
                print("no config for", user_id)
            roblox_accounts.append(roblox_account)

        return roblox_accounts
    
    def trade_ad_thread(self):
        trade_ad_API = "https://api.rolimons.com/tradeads/v1/createad"
        #{"player_id":1283171278,"offer_item_ids":[138844851,9255011,1609402609,111776247],"request_item_ids":[],"request_tags":["robux","upgrade","downgrade"]}

        data={"player_id":1283171278,"offer_item_ids":[138844851,9255011,1609402609,111776247],"request_item_ids":[],"request_tags":[]}

        #self.rolimon_account.requestAPI(trade_ad_API, method='post', data=)


# TODO: Check whitelist every 5 minutes

if __name__ == "__main__":
    doggo = Doggo()
    whitelist_thread = threading.Thread(target=doggo.whitelist_thread)
    whitelist_thread.start()
    if not Doggo().validate_whitelist():
        print("Whitelist not valid")
        time.sleep(1)
        Doggo().whitelist_manager.main()
    doggo.main()



