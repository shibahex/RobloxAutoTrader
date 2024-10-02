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

    def __init__(self, cookie:dict=None, Proxies=None) -> None:
        self.request_handler = handle_requests.RequestsHandler(use_proxies=False, cookie=cookie)

