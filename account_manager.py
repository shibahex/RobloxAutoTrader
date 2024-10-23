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
                self.json_handler.delete_cookie(index)
            except:
                break

    def manually_add_account(self):
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        try:
            auth_code = AuthHandler().verify_auth_key(auth_secret)
        except ValueError as e:
            print(e)
            self.cli.print_error("Not using account...")
            return None 

        acc_cookie = self.cli.input_prompt("Enter Cookie (include warning)")
        cookie_payload = {'.ROBLOSECURITY': acc_cookie}

        if cookie_warning not in acc_cookie:
            self.cli.print_error("Invalid cookie format try again")
            return None

        try:
            roblox_login = RobloxAPI(cookie=cookie_payload)
        except ValueError as e:
            print(e)  # This will print the error message
            self.cli.print_error("Not using roblox account...")
            return None

        auth_ticket = self.cli.input_prompt("enter auth ticket")

    def add_account(self):
        # TODO: dont ask for auth_secret if its in cookies.json somehow
        auth_secret = self.cli.input_prompt("Enter the authorization key")

        try:
            auth_code = AuthHandler().verify_auth_key(auth_secret)
        except ValueError as e:
            print(e)
            self.cli.print_error("Not using account...")
            return None 
        try:
            cookie, ticket = FirefoxLogin().roblox_login(auth_secret)
        except ValueError as e:
            print(e)
            self.cli.print_error("Not using account..")
            return None
        print(cookie, ticket)


