import json
import threading
import os
import handler.handle_cli as handle_cli
import time
from datetime import datetime, timedelta

class JsonHandler:
    def __init__(self, filename):
        self.filename = filename
        self.lock = threading.Lock()
        self.cli = handle_cli.Terminal()
        if self.filename == "cookies.json" and not os.path.exists(self.filename):
            initial_data = {
                "roblox_accounts": []
            }
            self.write_data(initial_data)

        if self.filename == "projected_checker.json" and not os.path.exists(self.filename):
            initial_data = {}
            self.write_data(initial_data)

    def read_data(self) -> dict:
        """Reads data from the JSON file."""
        with self.lock:
            try:
                with open(self.filename, 'r') as file:
                    return json.load(file)
            except FileNotFoundError:
                return {'roblox_accounts': []}
            except json.JSONDecodeError:
                self.cli.print_error("Error decoding JSON, returning empty data.")
                return {'roblox_accounts': []}

    def write_data(self, data: dict) -> None:
        """Writes data to the JSON file."""
        with self.lock:
            with open(self.filename, 'w') as file:
                json.dump(data, file, indent=4)

    def add_trade(self, cookie, trade_dict):
        """Adds a trade to the specified Roblox account."""
        data = self.read_data()

        # Check if the account already exists
        account_found = False
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                # If account exists, append the trade_dict to its trades
                if 'trades' not in account:
                    account['trades'] = []
                account['trades'].append(trade_dict)
                account_found = True
                break

        # If account does not exist, create a new entry
        if not account_found:
            new_account = {
                'cookie': cookie,
                'trades': [trade_dict],
                'ratelimit_timestamp': None
            }
            data['roblox_accounts'].append(new_account)

        # Write the updated data back to the file
        self.write_data(data)

    def add_ratelimit_timestamp(self, cookie) -> None:
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                current_date = datetime.now()

                account['ratelimit_timestamp'] = current_date.isoformat()
                self.write_data(data)
                return True

        pass

    def is_all_ratelimited(self):
        
        data = self.read_data()
        for account in data['roblox_accounts']:
            current_date = datetime.now()

            ratelimit_timestamp = account['ratelimit_timestamp']
            # Parse the timestamp string into a datetime object
            try:
                timestamp_date = datetime.fromisoformat(ratelimit_timestamp)
            except:
                # Handle invalid timestamp format if needed
                return False
            


            if current_date - timestamp_date >= timedelta(hours=6):
                # greater than 6 hours
                account['ratelimit_timestamp'] = None
                self.write_data(data)
                return False

        return True

    def check_ratelimit_cookie(self, cookie) -> None:
        """
            Checks if the cookie is ratelimited or not
        """

        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                ratelimit_timestamp = account['ratelimit_timestamp']
                if ratelimit_timestamp == None:
                    return False

                
                timestamp = account['ratelimit_timestamp']
                # Parse the timestamp string into a datetime object
                try:
                    timestamp_date = datetime.fromisoformat(ratelimit_timestamp)
                except:
                    # Handle invalid timestamp format if needed
                    return False

                current_date = datetime.now()

                if current_date - timestamp_date >= timedelta(hours=6):
                    # greater than 1 day
                    account['ratelimit_timestamp'] = None
                    self.write_data(data)
                    return False
                
                return True

    def add_cookie(self, cookie, auth, auth_ticket) -> None:
        data = self.read_data()
        
        # Check for duplicate cookies
        if not any(account['cookie'] == cookie for account in data['roblox_accounts']):
            data['roblox_accounts'].append({'cookie': cookie, 'auth_secret': auth, 'auth_ticket': auth_ticket, 'ratelimit_timestamp': None})

            self.write_data(data)
            self.cli.print_success("Cookie added suscessfully")
            time.sleep(1)
        else:
            print("Cookie already exists.")

    def delete_cookie(self, index:int) -> None:
        data = self.read_data()
        if 0 <= index < len(data['roblox_accounts']):
            del data['roblox_accounts'][index]
            self.write_data(data)
            self.cli.print_success("Cookie deleted successfully.")
            time.sleep(1)
        else:
            self.cli.print_error("Invalid index. No cookie deleted.")

    def get_outbounds(self, cookie) -> dict:
        data = self.read_data()
        account_found = False
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                if 'trades' not in account:
                    break

                return account["trades"]
        return False


    def remove_trade(self, cookie, trade_id):
        data = self.read_data()

        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                if 'trades' not in account:
                    break
                trades = account['trades']
                for trade in trades:
                    if trade['trade_id'] == trade_id:
                        trades.remove(trade)
                        self.write_data(data)
                        break

                    
                    


    
    def list_cookies(self) -> None:
        def ordinal(num):
            special_ordinals = {1: "First", 2: "Second", 3: "Third"}
            if num in special_ordinals:
                return special_ordinals[num]

            if 10 <= num % 100 <= 20:
                suffix = "th"
            else:
                suffixes = {1: "st", 2: "nd", 3: "rd"}
                suffix = suffixes.get(num % 10, "th")
            return f"{num}{suffix}"

        data = self.read_data()
        if data['roblox_accounts']:
            for i, account in enumerate(data['roblox_accounts'], 1):
                title = f"{handle_cli.magenta}[{handle_cli.reset+str(i)+handle_cli.magenta}] {ordinal(i)} Cookie{handle_cli.reset}"

                shorten_cookie = account['cookie'][:len(account['cookie']) // 6]
                cookie_info = f"\nShortened Cookie: {shorten_cookie}\n\nAuth Secret: {account['auth_secret']}\nAuth Ticket: {account['auth_ticket']}\n"


                print("---" + title + "---" + cookie_info )

        else:
            print("No cookies found.")


    def update_projected_status(self, item_id:int or str, projected_status: bool, current_price: int or str) -> None:
        """Updates the projected status of a specific item ID."""
        data = self.read_data()
        now_time = datetime.now()

        data[item_id] = {
            'is_projected': projected_status, 
            'timestamp': now_time.timestamp(),
            'last_price': current_price
        }
        self.write_data(data)

