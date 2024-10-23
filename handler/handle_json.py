import json
import threading
import os

class JsonHandler:
    def __init__(self, filename):
        self.filename = filename
        self.lock = threading.Lock()
        if self.filename == "cookies.json" and not os.path.exists(self.filename):
            initial_data = {
                "roblox_accounts": []
            }
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
                print("Error decoding JSON, returning empty data.")
                return {'roblox_accounts': []}

    def write_data(self, data: dict) -> None:
        """Writes data to the JSON file."""
        with self.lock:
            with open(self.filename, 'w') as file:
                json.dump(data, file, indent=4)

    def add_cookie(self, cookie, auth) -> None:
        data = self.read_data()
        
        # Check for duplicate cookies
        if not any(account['cookie'] == cookie for account in data['roblox_accounts']):
            data['roblox_accounts'].append({'cookie': cookie, 'auth': auth})
            self.write_data(data)
            print("Cookie added successfully.")
        else:
            print("Cookie already exists.")

    def delete_cookie(self, index) -> None:
        data = self.read_data()
        if 0 <= index < len(data['roblox_accounts']):
            del data['roblox_accounts'][index]
            self.write_data(data)
            print("Cookie deleted successfully.")
        else:
            print("Invalid index. No cookie deleted.")

    def list_cookies(self) -> None:
        data = self.read_data()
        if data['roblox_accounts']:
            for i, account in enumerate(data['roblox_accounts']):
                print(f"{i}: Cookie: {account['cookie']}, Auth: {account['auth']}")
        else:
            print("No cookies found.")


