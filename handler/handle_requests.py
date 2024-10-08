import time
import random
import requests


class RequestsHandler:
    proxies = []

    def __init__(self, Session: requests.Session = requests.Session(), use_proxies=False, cookie:dict=None) -> None:
        self.use_proxies = use_proxies
        if self.use_proxies and not RequestsHandler.proxies:
            RequestsHandler.load_proxies()

        self.proxy_timeout = {}
        self.timeout_duration = 60
        self.Session = Session
        if cookie:
            self.Session.cookies.update(cookie)
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'

        }

    def rate_limit(self, proxy):
        """
        Add proxy to timeout and waits.
        """
        print(f"Rate limit hit for proxy {proxy}, switching proxy...")
        self.proxy_timeout[proxy] = time.time() + self.timeout_duration

    def blacklist_proxy(self, proxy):
        self.proxies.remove(proxy)

    def return_proxy(self):
        """
        Returns Proxy that isn't in Timeout. Returns None if None are Available
        """
        available_proxies = [proxy for proxy in self.proxies if proxy not in self.proxy_timeout or time.time(
        ) >= self.proxy_timeout[proxy]]
        if not available_proxies:
            return None

        proxy = random.choice(available_proxies)
        proxy_dict = {"http": proxy, "https": proxy}
        return proxy_dict

    def generate_csrf(self):
        response = self.Session.post(
            'https://auth.roblox.com/v2/login', data={})
        if 'x-csrf-token' in response.headers:
            self.Session.headers["x-csrf-token"] = response.headers["x-csrf-token"]
            # return response.headers['x-csrf-token']
        else:
            print(f'Invalidated cookie returned in generate_csrf; {response.headers}')
            return False

    def requestAPI(self, URL, method="get", payload=None) -> requests.Response:
        """
        Handles the requests and returns the response if its successful.
        You can pass through requests.Session() with Roblox Cookies.
        """

        """
        Proxy Managment
        """
        while True:
            if not self.proxies:
                self.use_proxies = False
            proxy_dict = self.return_proxy() if self.use_proxies else None

            if proxy_dict is None and self.use_proxies:
                print("No available proxies, waiting...")
                time.sleep(self.timeout_duration)
                continue
            try:
                if method.lower() == "get":
                    print(URL)
                    Response = self.Session.get(
                        URL, headers=self.headers, proxies=proxy_dict, timeout=30)
                elif method.lower() == "post":
                    Response = self.Session.post(
                        URL, headers=self.headers, json=payload, proxies=proxy_dict, timeout=30)
            except Exception as  e:  # except requests.exceptions.ProxyError:
                if self.use_proxies:
                    print(f"Proxy  Error {proxy_dict['http']}.. blacklisting")
                    self.rate_limit(proxy_dict['http'])
                else: 
                    print("Got Error getting/posting API", e)
                continue

            """
            Status Code Managment
            """
            if Response.status_code == 200:
                return Response
            elif Response.status_code == 403:
                print("Error code 403: Authorization declined")
#                print("Trying to retrieve auth token...")
#                new_token = self.generate_csrf()
#                if new_token:
#                    self.headers['x-csrf-token'] = new_token
#                continue
                return Response
            elif Response.status_code == 429:
                if self.use_proxies:
                    self.rate_limit(proxy_dict['http'])
                else:
                    print("Rate limited without proxies, waiting 45 secs.")
                    time.sleep(45)
            elif Response.status_code == 500:
                print("API failed to respond..")
                return Response
            else:
                print("Unknown Error Code", Response.status_code, Response.text)
                return Response

            # return None

    @classmethod
    def load_proxies(cls, file_path:str='proxies.txt'):
        """
        Loads all proxies for class
        """
        try:
            with open(file_path, 'r') as file:
                cls.proxies = ["http://" + line.strip()
                               for line in file if line.strip()]
        except:
            print("No proxy file, returning None.")
            return None

    @classmethod
    def refresh_proxies(cls, file_path:str='proxies.txt'):
        cls.load_proxies(file_path)
