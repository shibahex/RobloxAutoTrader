import time
from rolimons_api import RolimonAPI
from roblox_api import RobloxAPI
from trade_algorithm import TradeMaker
from handler import *
import threading
from datetime import datetime, timedelta
from handler.handle_json import JsonHandler

"""
    1. multithread appending owners (bake in get inventory so multiple threads work on inventories)
    maybe have projected scanning in another thread somehow? dont let the whole program wait on 1 thread for projected scanning

    also make ratelimit consecutively be on a timer since last ratelimit and if its not been 1minute keep multiplying?

    Projected scanner is always checking for my inventory i think, so somethings off wehre it scans the same item, maybe it doesnt change the last price?

    Rolimon ads and discord ads for more counters!
"""
class Doggo:
    def __init__(self):
        self.user_queue = {}
        self.cli = Terminal()
        self.json = JsonHandler(filename="cookies.json")
        self.rolimons = RolimonAPI()
        self.trader = TradeMaker()
        self.all_cached_traders = []

        # Define a stop event that will be shared between threads
        self.stop_event = threading.Event()

    def main(self):
        while True:
            self.cli.clear_console()
            self.display_main_menu()
            time.sleep(30)

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
            merged = self.merge_lists(self.all_cached_traders, roblox_account.outbounds_userids)
            self.all_cached_traders = merged

            if len(self.user_queue) > 20:
                time.sleep(60)
                continue
            random_item = self.rolimons.return_item_to_scan()['item_id']
            owners = roblox_account.get_active_traders(random_item)

            accounts = self.json.read_data()
            for owner in owners:
                # Uncomment the following line if user validation is needed
                # if self.rolimons.validate_user(owner):
                if int(owner) in self.all_cached_traders:
                    print("already traded with player, skipping")
                    continue

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
                account.counter_trades()


    def start_trader(self):
        roblox_accounts = self.load_roblox_accounts()
        outbound_thread = threading.Thread(target=self.update_data_thread)
        outbound_thread.daemon = True
        outbound_thread.start()

        time.sleep(1)
        while True:
            threads = []
            for account in roblox_accounts:

                # Check if all accounts are rate-limited
                if self.json.is_all_ratelimited():
                    print("All cookies are ratelimited. Waiting for 20 minutes...")
                    time.sleep(20 * 60)  # Wait for 20 minutes before retrying
                    break  # Skip to the next account if rate-limited

                if self.json.check_ratelimit_cookie(account.cookies['.ROBLOSECURITY']):
                    print("account ratelimited continuing to next acc")
                    continue

                print("Scanning inactive trades")
                # TODO: add max days inactive in cfg and parse as arg

                # Put all the traders that declined our trades into the cached traders
                self.all_cached_traders = self.merge_lists(account.inactive_trades_list(), self.all_cached_traders)

                queue_thread = threading.Thread(target=self.queue_traders, args=(account,))
                queue_thread.daemon = True
                queue_thread.start()

                threads.append((queue_thread))

                # After queuing, start processing trades for the account (is a while true)
                self.process_trades_for_account(account)

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
                print("No users to trade with. Waiting 60 seconds...")
                time.sleep(60)  # Wait before checking again

            current_user_queue = self.user_queue.copy()

            for trader, trader_inventory in current_user_queue.items():

                # Generate and send trade if there are items to trade
                if account_inventory and trader_inventory:
                    generated_trade = self.trader.generate_trade_with_timeout(account_inventory, trader_inventory)

                    if not generated_trade:
                        break

                    print(f"Generated trade: {generated_trade}")

                    # Extract trade details
                    self_side = generated_trade['self_side']
                    self_robux = generated_trade['self_robux']
                    their_side = generated_trade['their_side']

                    # Send trade request
                    print("SEWND ROBUX!!!", self_robux)
                    send_trade_response = account.send_trade(trader, self_side, their_side, self_robux=self_robux)

                    if send_trade_response == 429:  # Rate-limited
                        print("Roblox account limited")
                        self.json.add_ratelimit_timestamp(account.cookies['.ROBLOSECURITY'])
                        return False

                    # Cache trade info if sent successfully
                    if send_trade_response:
                        now_time = datetime.now()
                        trade_dict = {
                            'trader_id': trader,
                            'trade_id': send_trade_response,
                            'self_items': [account_inventory[key]['item_id'] for key in self_side],
                            'their_items': [trader_inventory[key]['item_id'] for key in their_side],
                            'timestamp': now_time.timestamp()
                        }
                        self.json.add_trade(account.cookies['.ROBLOSECURITY'], trade_dict)
                        print(f"Trade recorded: {trade_dict}")

                del self.user_queue[trader]  # Remove trader from user queue after trade   

    def load_roblox_accounts(self):
        cookie_json = self.json.read_data()
        roblox_accounts = []

        for account in cookie_json['roblox_accounts']:
            roblox_cookie = {'.ROBLOSECURITY': account['cookie']}
            auth_secret = account['auth_secret']
            auth_ticket = account['auth_ticket']
            print("auth:secret", auth_secret, "auth ticket:", auth_ticket)
            roblox_accounts.append(RobloxAPI(cookie=roblox_cookie, auth_secret=auth_secret, auth_ticket=auth_ticket))

        return roblox_accounts


if __name__ == "__main__":
    doggo = Doggo()
    doggo.main()

