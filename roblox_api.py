import handle_requests
import requests
import datetime
import rolimons_api



def main():
    rolimons_api.RolimonAPI().scan_owners()
main()

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
