from handler.handle_whitelist import Whitelist
from handler.handle_json import JsonHandler
from handler.handle_cli import Terminal
import handler.handle_cli
import time
class WhitelistManager:
    def __init__(self):
        self.cli = Terminal()
        self.Whitelist = Whitelist()
        self.json = JsonHandler(".whitelist")

    def get_info(self):
        order_id = str(input("Enter OrderID: "))
        username = str(input("Enter Username: "))
        password = str(input("Enter Password: "))
        return order_id, username, password

    def register_user(self):
        order_id, username, password = self.get_info()
        registered = self.Whitelist.register_user(username, password, order_id)
        if registered == True:
            self.json.write_data({'username': username, 'password': password, 'orderid': order_id})
            print("User sucessfully registered")
        else:
            print("User couldn't get registered..")

    def main(self):
        options=( 
            ("1", "Register New Order"),
            ("2", "Login Existing Order"),
            ("3", "Reset IP & HWID"),
            ("4", "Go Back to Main Menu")
        )
        while True:
            self.cli.clear_console()

            self.cli.print_menu("Whitelist Manager", options)
            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

            try:
                match answer:
                    case 1:
                        self.register_user()
                    case 2:
                        order_id, username, password = self.get_info()
                        valid = self.Whitelist.is_valid(username, password, order_id)
                        if valid:
                            self.json.write_data({'username': username, 'password': password, 'orderid': order_id})
                        else:
                            print("Try reseting the HWID and IP")
                    case 3:
                        data = self.json.read_data()
                        if data and data.get('username') and data.get('password') and data.get('orderid'):
                            username = data.get('username')
                            password = data.get('password')
                            order_id = data.get('orderid')
                        else:
                            order_id, username, password = self.get_info()
                        sucess = self.Whitelist.reset_ip(data['username'], data['password'], data['orderid'])
                        if sucess:
                            print("Sucesfully reset IP, please wait 90 minutes before reseting again")
                            time.sleep(2)
                        else:
                            print("Couldn't reset IP, whitelist invalid, delete .whitelist and try again, or wait 90 minutes")
                            time.sleep(3)
                    case 4:
                        break
            except Exception as e:
                self.cli.print_error(e)
                continue
