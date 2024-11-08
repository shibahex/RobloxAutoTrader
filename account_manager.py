from handler import *
class AccountManager:
    def __init__(self):
        self.json_handler = JsonHandler('cookies.json')
        self.cli = Terminal()
        pass

    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                ("1", "Add Account (Firefox)"),
                ("2", "Add Account (Manual)"),
                ("3", "Remove Accounts"),
                ("4", "Back to Main Menu")
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
                    break


    def remove_accounts(self):
        while True:
            self.json_handler.list_cookies()
            try:
                index = self.cli.input_prompt("Enter the number of the cookie to delete (Press enter to stop)")
                self.json_handler.delete_cookie(int(index))
            except ValueError:
                self.cli.print_error(f"Invalid input: '{index}' is not a valid number.")
            except Exception as e:
                self.cli.print_error(f"got execption {e} trying to delete cookie")
                break

    def manually_add_account(self):
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        try:
            auth_code = AuthHandler().verify_auth_key(auth_secret)
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            return None 

        acc_cookie = self.cli.input_prompt("Enter Cookie (include warning)")

        if cookie_warning not in acc_cookie:
            self.cli.print_error("Invalid cookie format try again")
            return None

        try:
            roblox_login = RobloxAPI(cookie=cookie_payload)
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            return None

        auth_ticket = self.cli.input_prompt("enter auth ticket")
        self.json_handler.add_cookie(acc_cookie, auth_secret, auth_ticket)


    def add_account(self):
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        firefox = FirefoxLogin()
        try:
            auth_code = AuthHandler().verify_auth_key(auth_secret)
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            return None 
        try:
            cookie, auth_ticket = firefox.roblox_login(auth_secret)
            firefox.stop()
        except ValueError as e:
            self.cli.print_error(f"{e}\nSkipping account...")
            firefox.stop()
            return None
        self.json_handler.add_cookie(cookie, auth_secret, auth_ticket)


