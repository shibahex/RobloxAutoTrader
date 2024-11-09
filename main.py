import time
from rolimons_api import RolimonAPI
from roblox_api import RobloxAPI
from trade_algorithm import TradeMaker
from handler import *
import threading
from datetime import datetime, timedelta
from handler.handle_json import JsonHandler
"""
    1. Outbound Checker
    2. dont send duplicate traders to users
    (also make it so it only sends to active users)
    3. check if can trade before trading maybe?
    4. Remove projects from json if timestamp is greater than a week
    5. remove outbounds if timestamp is like 5 days
    6. Auth system
    7. add price to projected.json and scan it again if the price difference is huge
    8. Use https://inventory.roblox.com/v2/assets/128208025/owners?sortOrder=Asc&limit=100 to get active users instead of rolimons
            (and dont use rolimons to get inventory use roblox inventory API)
        so get random item ID then use the owner API to get one random player that owned within like a week and see if you can trade with them
    
"""
class Doggo:
    def __init__(self):
        self.user_queue = {}
        self.cli = Terminal()
        self.json = JsonHandler(filename="cookies.json")
        self.rolimons = RolimonAPI()
        self.trader = TradeMaker()

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
        while True:
            if len(self.user_queue) > 20:
                time.sleep(20)
                continue
            random_item = self.rolimons.return_item_to_scan()['item_id']
            owners = self.rolimons.return_formatted_owners(random_item)

            accounts = self.json.read_data()
            all_cached_traders = []
            for account in accounts['roblox_accounts']:
                all_cached_traders.extend([str(trade["trader_id"]) for trade in account["trades"]])


            for owner in owners:
                # Uncomment the following line if user validation is needed
                # if self.rolimons.validate_user(owner):
                if str(owner) in all_cached_traders:
                    continue

                if roblox_account.check_can_trade(owner) == True:
                    inventory = self.rolimons.get_inventory(owner)
                    self.user_queue[owner] = inventory  
                time.sleep(.1)  # Delay between iterations

    def start_trader(self):
        roblox_accounts = self.load_roblox_accounts()
        threading.Thread(target=self.queue_traders, daemon=True, args=(roblox_accounts[0],)).start()  # Daemon thread for user queue
        time.sleep(1)

        # Infinite loop to continuously process trades
        while True:
            for account in roblox_accounts:
                account.outbound_checker()
                #time.sleep(600)
                account_inventory = account.account_inventory
                if not self.user_queue:  # Check if user_queue is empty
                    print("No users to trade with. Waiting...")
                    time.sleep(15)  # Wait before checking again
                    continue
                
                # Create a temporary copy of the user queue to avoid dictionary size change error
                current_user_queue = self.user_queue.copy()

                for trader, trader_inventory in current_user_queue.items():
                    # generate and send trade
                    if account_inventory and trader_inventory:
                        generated_trade = self.trader.generate_trade_with_timeout(account_inventory, trader_inventory)
                        #generated_trade = self.trader.generate_trade(account_inventory, trader_inventory)
                        if not generated_trade:
                            continue
                        self_side, their_side = generated_trade
                        send_trade_response = account.send_trade(trader, self_side, their_side)
                        
                        # Save to cache for outbound checker
                        self_item_ids = [account_inventory[key]['item_id'] for key in self_side]
                        their_item_ids = [trader_inventory[key]['item_id'] for key in their_side]
                        if send_trade_response:
                            now_time = datetime.now()

                            trade_dict = {'trader_id': trader,'trade_id': send_trade_response, 'self_items': self_item_ids, 'their_items': their_item_ids, 'timestamp': now_time.timestamp()}

                            self.json.add_trade(account.cookies['.ROBLOSECURITY'], trade_dict)
                            print('append trade here', trade_dict)
                            pass
                            #

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

