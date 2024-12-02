import handler.account_settings
from handler import *
import time

class AccountSettings():
    def __init__(self):
        self.account_settings = handler.account_settings.HandleConfigs() 
        self.cli = Terminal()

        self.main()


    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                ("1", "Show Account Configs"),
                ("2", "Add Account Configs"),
                ("3", "Edit Account Configs"),
                ("4", "Remove Account Configs"),
                ("5", "Back to Main Menu")
            )
            self.cli.print_menu("Configs Manager", options)

            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

            match answer:
                case 1:
                    self.account_settings.show_config()
                    input("Press enter to continue..")
                case 2:
                    self.account_settings.create_config()
                case 3:
                    self.account_settings.edit_config()
                case 4:
                    self.account_settings.delete_config()
                case 5:
                    break
            

