import handle_requests
import requests
import datetime


class RolimonAPI():
    def __init__(self, cookie):
        self.Session = requests.Session()

    def return_item_api(page_text):
        data = page_text.text.split("bc_copies_data")
        [1].split('[')[1].split("]")[0]

        owners = data.split(',')
        start_date = datetime.datetime.now().isoformat() + "Z"
        today = start_date.split("T")[0].split("-")[-2]
        return owners, today


class RobloxAPI():
    """
        Pass in Cookie if you want it to be an account
    """

    def __init__(self, cookie=None, Proxies=None) -> None:
        self.Session = requests.Session()

        if cookie:
            self.Session[".ROBLOSECURITY"] = cookie
            self.Account = handle_requests.RequestsHandler(
                self.Session, Proxies
            )
        else:
            self.Account = handle_requests.RequestsHandler(
                None, Proxies
            )
