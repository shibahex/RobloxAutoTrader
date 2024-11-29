import time
from rolimons_api import RolimonAPI
from roblox_api import RobloxAPI
from trade_algorithm import TradeMaker
from handler import *
import threading
from datetime import datetime, timedelta
from handler.handle_json import JsonHandler
from account_manager import AccountManager

"""
PROBLEM WITH MULTI COOKIES, WHEN I WASO ON SHADOWKILLER IT HAD THE USERID OF DESIREDEDESIGNER IN THE ID, SO I THINK THE 2AUTHS ARENT SYCNED TO SWELECTED COOKIE
    1. multithread appending owners (bake in get inventory so multiple threads work on inventories)
    maybe have projected scanning in another thread somehow? dont let the whole program wait on 1 thread for projected scanning

    also make ratelimit consecutively be on a timer since last ratelimit and if its not been 1minute keep multiplying?

    Projected scanner is always checking for my inventory i think, so somethings off wehre it scans the same item, maybe it doesnt change the last price?

    Rolimon ads and discord ads for more counters!


    Trade send thread should be seprate from scanning inventories threads bc ratelimit on resale-data

"""
class Doggo:
    def __init__(self):
        self.user_queue = {}
        self.cli = Terminal()
        self.json = JsonHandler(filename="cookies.json")
        self.rolimons = RolimonAPI()
        self.trader = TradeMaker()
        self.all_cached_traders = []

        self.discord_webhook = DiscordHandler()

        # Define a stop event that will be shared between threads
        self.stop_event = threading.Event()

    def main(self):
        while True:
            self.cli.clear_console()
            self.display_main_menu()

    def display_main_menu(self):
        options = (
            (1, "Account Manager"),
            (2, "Trade Manager"),
            (3, "Execute Trader"),
        )
        self.cli.print_menu("Main Menu", options)
        try:
            answer = int(self.cli.input_prompt("Enter Option"))
            self.handle_menu_selection(answer)
        except ValueError as e:
            self.cli.print_error("Invalid input. Please enter a number. ERROR:", e)

    def handle_menu_selection(self, selection):
        match selection:
            case 1:
                
                AccountManager().main()
            case 2:
                # Trade Manager functionality can be implemented here
                pass
            case 3:
                self.start_trader()

    def queue_traders(self, roblox_account):
        while not self.stop_event.is_set():

            # Put all outbound users in cached traders so we dont double send

            if len(self.user_queue) > 20:
                time.sleep(60)
                continue
            random_item = self.rolimons.return_item_to_scan()['item_id']
            owners = roblox_account.get_active_traders(random_item)

            for owner in owners:
                # Uncomment the following line if user validation is needed
                # if self.rolimons.validate_user(owner):

                if int(owner) in self.all_cached_traders:
                    print("already traded with player, skipping")
                    continue

                self.all_cached_traders.append(owner)
                if roblox_account.check_can_trade(owner) == True:
                    inventory = roblox_account.fetch_inventory(owner)
                    self.user_queue[owner] = inventory  
                time.sleep(.1)  # Delay between iterations

    def merge_lists(self, list1, list2):
        # Use set to merge and remove duplicates
        return list(set(list1) | set(list2))

    def update_data_thread(self):
        while True:
            time.sleep(130)
            self.rolimons.update_data()      
            roblox_accounts = self.load_roblox_accounts()

            for account in roblox_accounts:
                account.outbound_api_checker()
                account.check_completeds()
                # NOTE: off bc i have a good inbound
                #account.counter_trades()


    def start_trader(self):
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

                self.all_cached_traders = list(set(current_account.get_recent_traders() + self.all_cached_traders)) 

                # TODO: add max days inactive in cfg and parse as arg

                print("trading with:", current_account.username, "auth code", current_account.auth_secret, current_account.account_id, "cookie=", current_account.request_handler.Session.cookies.get_dict())

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


    def process_trades_for_account(self, account):
        while True:
            account_inventory = account.account_inventory

            # Check if user queue is empty
            while not self.user_queue:
                print("No users to trade with. Waiting 10 second...")
                time.sleep(10)

            #current_user_queue = self.user_queue.copy()
            
            for trader in list(self.user_queue.keys()):  # Using list() creates a copy of the keys
                trader_inventory = self.user_queue[trader]
                
                # Delete the key from the dictionary
                self.user_queue.pop(trader, None)  # Safely remove the key using pop
                
                # Generate and send trade if there are items to trade
                if account_inventory and trader_inventory:
                    generated_trade = self.trader.generate_trade(account_inventory, trader_inventory)

                    if not generated_trade:
                        print("no generated trade")
                        break

                    print(f"Generated trade: {generated_trade}")

                    # Extract trade details
                    self_side = generated_trade['self_side']
                    their_side = generated_trade['their_side']
                    self_robux = generated_trade['self_robux']

                    print("SEND ROBUX!!!", self_robux)
                    send_trade_response = account.send_trade(trader, self_side, their_side, self_robux=self_robux)

                    if send_trade_response == 429:  # Rate-limited
                        print("Roblox account limited")
                        self.json.add_ratelimit_timestamp(account.cookies['.ROBLOSECURITY'])
                        return False

                    # Cache trade info if sent successfully
                    if send_trade_response:
                        embed_fields, total_profit = self.discord_webhook.embed_fields_from_trade(generated_trade, self.rolimons.item_data, self.rolimons.projected_json.read_data())

                        embed = self.discord_webhook.setup_embed(title=f"Sent a trade with {total_profit} total profit", color=1, user_id=trader, embed_fields=embed_fields, footer="Frick shedletsky")
                        self.discord_webhook.send_webhook(embed, "https://discord.com/api/webhooks/1311127129731108944/RNlwYAMpLH1tJmwSTNDfuFOb9id2EmfC9AEvwSu5Gh-RNKcze35Pnp8asRBGt7dRsUaI")                    # Send trade request
                        pass

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
                
            roblox_account = RobloxAPI(cookie=roblox_cookie, auth_secret=auth_secret)

            roblox_accounts.append(roblox_account)

        return roblox_accounts
    
    def trade_ad_thread(self):
        trade_ad_API = "https://api.rolimons.com/tradeads/v1/createad"
        #{"player_id":1283171278,"offer_item_ids":[138844851,9255011,1609402609,111776247],"request_item_ids":[],"request_tags":["robux","upgrade","downgrade"]}

        data={"player_id":1283171278,"offer_item_ids":[138844851,9255011,1609402609,111776247],"request_item_ids":[],"request_tags":[]}

        #self.rolimon_account.requestAPI(trade_ad_API, method='post', data=)


if __name__ == "__main__":
    doggo = Doggo()
    doggo.main()

