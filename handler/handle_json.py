import json
import threading
import os
import handler.handle_cli as handle_cli
#import handler.handle_cli
import time
from datetime import datetime, timedelta
# NOTE: I can optimize json reading and stuff by not having cookies.json a list of dicts
# rather it could be dicts with the keys as the userids

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
                self.cli.print_error(f"Error decoding JSON, returning empty data. {self.filename}")
                return {'roblox_accounts': []}

    def write_data(self, data: dict) -> None:
        """Writes data to the JSON file."""
        with self.lock:
            with open(self.filename, 'w') as file:
                json.dump(data, file, indent=4)

        print(f"Data successfully written to {self.filename}")


    def add_ratelimit_timestamp(self, cookie) -> None:
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                current_date = datetime.now()

                account['ratelimit_timestamp'] = current_date.isoformat()
                self.write_data(data)
                return True

    def return_name_from_id(self, user_id):
        data = self.read_data()
        
        for account in data['roblox_accounts']:
            if str(account.get('user_id')) == str(user_id):
                return account.get("username")
        
        return "Couldn't find username."


    def return_userid_from_index(self, index: int, check_config=False):
        index = int(index) - 1
        data = self.read_data()
        
        # Filter accounts based on `check_config`
        if check_config:
            with open("account_configs.jsonc", 'r') as file:
                settings_data = json.load(file)
            filtered_accounts = [
                account for account in data['roblox_accounts']
                if account['user_id'] not in settings_data.keys()
            ]
        else:
            filtered_accounts = data['roblox_accounts']

        # Check if the index is within bounds for the filtered list
        if 0 <= index < len(filtered_accounts):
            try:
                return filtered_accounts[index]['user_id']
            except:
                return False
        else:
            return False


    def toggle_cookie(self, index:int) -> None:
        data = self.read_data()
        if 0 <= index < len(data['roblox_accounts']):
            toggle = data['roblox_accounts'][index]['use_account']

            data['roblox_accounts'][index]['use_account'] = not toggle

            self.write_data(data)
            self.cli.print_success(f"Cookie toggled to {toggle}")
            time.sleep(1)
        else:
            self.cli.print_error("Invalid index. No cookie deleted.")

    def is_disabled(self, cookie):
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                print(account['use_account'], type(account['use_account']))
                return account['use_account']

        # for some reason if theres no use account value
        return False

    def is_all_ratelimited(self):
        
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account['use_account'] == True:
                current_date = datetime.now()

                ratelimit_timestamp = account['ratelimit_timestamp']
                # Parse the timestamp string into a datetime object
                try:
                    timestamp_date = datetime.fromisoformat(ratelimit_timestamp)
                except:
                    # Handle invalid timestamp format if needed
                    print(account)
                    return False
                


                if current_date - timestamp_date >= timedelta(hours=6):
                    # greater than 6 hours
                    account['ratelimit_timestamp'] = None
                    self.write_data(data)
                    print("wrote data for timestamp", current_date, "minus", timestamp_date, ">=", timedelta(hours=6))
                    return False

        return True

    def update_last_completed(self, cookie, last_completed: int or str) -> None:
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie and account.get("last_completed") != last_completed:
                account['last_completed'] = last_completed
                print("triggered update data for completeds")
                self.write_data(data)
                return True

    def get_last_completed(self, cookie) -> str or None:
        data = self.read_data()
        for account in data['roblox_accounts']:
            if account.get('cookie') == cookie:
                return account['last_completed']



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
                    print("write trigger  for check ratelimit cookie")
                    self.write_data(data)
                    return False
                
                return True

    def add_cookie(self, cookie, username, user_id, auth) -> None:
        data = self.read_data()
        
        # Check for duplicate cookies
        if not any(account['cookie'] == cookie for account in data['roblox_accounts']):
            data['roblox_accounts'].append({'username': username, "user_id": user_id, 'use_account': True, 'last_completed': None,'cookie': cookie, 'auth_secret': auth, 'ratelimit_timestamp': None})

            self.write_data(data)
            self.cli.print_success("Cookie added suscessfully")
            time.sleep(1)
        else:
            print("Cookie already exists.")
            time.sleep(1)

    def delete_cookie(self, index:int) -> None:
        data = self.read_data()
        if 0 <= index < len(data['roblox_accounts']):
            del data['roblox_accounts'][index]
            self.write_data(data)
            self.cli.print_success("Cookie deleted successfully.")
            time.sleep(1)
        else:
            self.cli.print_error("Invalid index. No cookie deleted.")

    
    def list_cookies(self, check_config=False) -> None:
        def ordinal(num):
            special_ordinals = {1: "first", 2: "second", 3: "third"}
            if num in special_ordinals:
                return special_ordinals[num]

            if 10 <= num % 100 <= 20:
                suffix = "th"
            else:
                suffixes = {1: "st", 2: "nd", 3: "rd"}
                suffix = suffixes.get(num % 10, "th")
            return f"{num}{suffix}"

        data = self.read_data()
        cookie_count = 0
        if data['roblox_accounts']:
            for account in data['roblox_accounts']:
                if check_config == True:
                    with open("account_configs.jsonc", 'r') as file:
                        settings_data = json.load(file)
                    if account['user_id'] in settings_data.keys():
                        continue

                cookie_count +=1
                title = f"{handle_cli.magenta}[{handle_cli.reset+str(cookie_count)+handle_cli.magenta}] {ordinal(cookie_count)} cookie{handle_cli.reset}"

                shorten_cookie = account['cookie'][:len(account['cookie']) // 6]
                cookie_info = f"\nusername: {account['username']},\n user id: {account['user_id']}\nratelimited: {account['ratelimit_timestamp']}\nenabled: {account['use_account']}\n\nshortened cookie: {shorten_cookie}\nauth secret: {account['auth_secret']}\n"


                print("---" + title + "---" + cookie_info )

        else:
            print("no cookies found.")


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

