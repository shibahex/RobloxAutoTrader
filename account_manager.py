from roblox_api import RobloxAPI
from handler.handle_json import JsonHandler
from handler.handle_cli import Terminal
from handler.handle_2fa import AuthHandler
from handler.handle_login import FirefoxLogin

COOKIE_WARNING = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|"

# TODO: Add support for adding rolimon cookies


class AccountManager:
    def __init__(self):
        self.json_handler = JsonHandler('cookies.json')
        self.cli = Terminal()
        pass

    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                ("1", "Add Account (Firefox Required)"),
                ("2", "Add Account (Manual)"),
                ("3", "Remove Accounts"),
                ("4", "Toggle Accounts"),
                ("5", "Back to Main Menu")
            )
            self.cli.print_menu("Account Manager", options)
            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

            match answer:
                case 1:
                    self.add_account()
                case 2:
                    self.manually_add_account()
                case 3:
                    self.remove_accounts()
                case 4:
                    self.toggle_accounts()
                case 5:
                    break

    def toggle_accounts(self):
        while True:
            self.cli.clear_console()
            self.json_handler.list_cookies()
            try:
                index = self.cli.input_prompt(
                    "Enter the number of the cookie to toggle (Press enter to stop)")
                self.json_handler.toggle_cookie(int(index)-1)
            except ValueError:
                if index.lower() == " " or index.lower() == "":
                    break

                self.cli.print_error(f"Invalid input: '{
                                     index}' is not a valid number.")
            except Exception as e:
                self.cli.print_error(
                    f"got execption {e} trying to delete cookie")
                break

    def remove_accounts(self):
        while True:
            self.cli.clear_console()
            self.json_handler.list_cookies()
            try:
                index = self.cli.input_prompt(
                    "Enter the number of the cookie to delete (Press enter to stop)")
                self.json_handler.delete_cookie(int(index)-1)
            except ValueError:
                if index.lower() == " " or index.lower() == "":
                    break
                self.cli.print_error(f"Invalid input: '{
                                     index}' is not a valid number.")
            except Exception as e:
                self.cli.print_error(
                    f"got execption {e} trying to delete cookie")
                break

    def manually_add_account(self):
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        if not AuthHandler().verify_auth_secret(auth_secret):
            self.cli.print_error(
                "Auth secret isn't right Skipping account...")
            return None

        acc_cookie = self.cli.input_prompt("Enter Cookie (include warning)")

        if COOKIE_WARNING not in acc_cookie:
            self.cli.print_error("Invalid cookie format try again")
            return None

        try:
            roblox_login = RobloxAPI(cookie={".ROBLOSECURITY": acc_cookie})
        except ValueError as error:
            self.cli.print_error(f"{error}\nSkipping account...")
            return None

        self.json_handler.add_cookie(
            acc_cookie, roblox_login.username, roblox_login.account_id, auth_secret)

    def add_account(self):
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        if not AuthHandler().verify_auth_secret(auth_secret):
            self.cli.print_error("AUTH CODE INVALID, skipping")
            return None

        firefox = FirefoxLogin()

        try:
            cookie, username, user_id = firefox.roblox_login(auth_secret)
            firefox.stop()
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            firefox.stop()
            return None
        self.json_handler.add_cookie(cookie, username, user_id, auth_secret)
