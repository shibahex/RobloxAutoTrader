from handler.account_settings import HandleConfigs
from handler.handle_cli import Terminal


class AccountSettings():
    def __init__(self):
        self.account_settings = HandleConfigs()
        self.cli = Terminal()

        self.main()

    def main(self):
        while True:
            self.cli.clear_console()
            options = (
                ("1", "Change Config"),
                ("2", "Show Account Configs"),
                ("3", "Add Account Configs"),
                ("4", "Edit Account Configs"),
                ("5", "Remove Account Configs"),
                ("6", "Check for missing settings for user configs"),
                ("7", "Back to Main Menu"),
            )
            self.cli.print_menu("Config Manager", options)

            try:
                answer = int(self.cli.input_prompt("Enter Option"))
            except ValueError:
                self.cli.print_error("Invalid input. Please enter a number.")
                continue

            match answer:
                case 1:
                    self.cli.clear_console()
                    self.account_settings.show_presets()
                case 2:
                    self.account_settings.show_config()
                    input("Press enter to continue..")
                case 3:

                    self.account_settings.create_config()
                case 4:
                    self.account_settings.edit_config()
                case 5:
                    self.account_settings.delete_config()
                case 6:
                    self.account_settings.check_for_updates()
                case 7:
                    break
