import time

import random
import requests
import re
from handler.handle_logs import log


class RequestsHandler:
    def __init__(self, Session: requests.Session = requests.Session(), use_proxies=False, cookie: dict = None) -> None:
        self.use_proxies = use_proxies
        self.proxies = []
        self.proxy_timeout = {}
        self.timeout_duration = 60

        if self.use_proxies == True:
            self.load_proxies()

        self.Session = Session

        # URL = Consecutive Limits
        self.ratelimit_urls = {}

        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            # Can be adjusted based on your preferred language
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',  # Mimicking a referer header
            'Cache-Control': 'max-age=0',
            'Content-Type': 'application/json',
            'x-csrf-token': None,
        }

    def rate_limit(self, proxy):
        """
        Add proxy to timeout and waits.
        """
        log(f"Rate limit hit for proxy {proxy}, switching proxy...")
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
        """
        Posts the auth API and grabs the csrf and sets the Class headers as the csrf
        The API response has a failure status code, but we still get the token.
        """
        try:
            response = self.Session.post(
                'https://auth.roblox.com/v2/login', data={})
        except:
            log("Failed to post csrf token. returning none", severityNum=3)
            return None

        if 'x-csrf-token' in response.headers:
            self.headers['x-csrf-token'] = response.headers['x-csrf-token']
            return True

        else:
            log(f'[ERROR] Invalidated cookie returned in generate_csrf; {
                response.headers}', severityNum=3)

    def requestAPI(self, URL, method="get", payload=None, additional_headers=None) -> requests.Response:
        """
        Handles the requests and returns the response if its successful.
        You can pass through requests.Session() with Roblox Cookies.
        """

        """
        Proxy Managment
        """

        if not self.proxies:
            self.use_proxies = False

        consecutive_rate_limits = 0
        retries = 0
        refreshed_csrf = False
        while True:

            headers = self.headers.copy()  # Create a copy of the original headers
            if additional_headers:
                # Add the additional headers temporarily
                headers.update(additional_headers)

            if self.cookie:
                self.Session.cookies.update(self.cookie)

            proxy_dict = self.return_proxy() if self.use_proxies else None

            if proxy_dict is None and self.use_proxies:
                print("No available proxies, waiting...")
                time.sleep(self.timeout_duration)
                continue
            try:
                if method.lower() == "get":
                    # print(URL)
                    Response = self.Session.get(
                        URL, headers=headers, proxies=proxy_dict, timeout=30)
                elif method.lower() == "post":
                    Response = self.Session.post(
                        URL, headers=headers, json=payload, proxies=proxy_dict, timeout=30)
            except Exception as e:  # except requests.exceptions.ProxyError:
                if self.use_proxies != False:
                    log(f"Proxy  Error {proxy_dict['http']}.. blacklisting")
                    self.rate_limit(proxy_dict['http'])
                else:
                    log(f"Got Error getting/posting API {e}", severityNum=2)
                    self.Session.close()
                    time.sleep(10)
                    # Recreate the session to avoid stale connections
                    self.Session = requests.Session()
                continue

            """
            Status Code Managment
            """
            if Response.status_code != 429:
                retries += 1
            if retries > 3:
                return Response

            if Response.status_code == 429:
                log(f"hit ratelimit on url {URL}")
                if self.use_proxies != False:
                    self.rate_limit(proxy_dict['http'])
                    time.sleep(5)
                    return Response
                else:
                    # If this API is hard ratelimited then return 429
                    if "https://trades.roblox.com/v1/trades/send" == URL:
                        if "you are sending too many trade requests" in Response.json()['errors'][0]['message'].lower():
                            return Response

                    if URL not in self.ratelimit_urls:
                        self.ratelimit_urls[URL] = 1
                    else:
                        self.ratelimit_urls[URL] += 1

                    consecutive_rate_limits = self.ratelimit_urls[URL]
                    wait_time = 10 * (2 ** consecutive_rate_limits)
                    log(f"Rate limited {
                        URL} without proxies, waiting {wait_time} secs.")
                    time.sleep(wait_time)
                    if consecutive_rate_limits > 4:
                        del self.ratelimit_urls[URL]
                        return Response
                    continue

            if Response.status_code == 200:
                # Because roblox API is weird and sometimes returns 200 with errors
                try:
                    if "errors" in Response.json():
                        Response.status_code = 500
                        return Response
                except:
                    pass
                return Response

            elif Response.status_code == 403 or Response.status_code == 401 or Response.status_code == 500:
                # print("Unathorized API, waiting 10 seconds then handling")
                # time.sleep(10)

                log(f"Unauthorized debug: {Response.text} {
                    Response.status_code} {Response.url}")

                if "XSRF token invalid" in Response.text:
                    gen_status = self.generate_csrf()
                    log(f"Refreshing CSRF Token: {gen_status}")
                    continue

                # This API doesn't work for some items
                if 'inventory' in Response.url:
                    return Response

                if 'Challenge is required' not in Response.text:
                    log(f"Request Auth Failed, seeing what to do for request Text: {
                        Response.text} Url: {Response.url}  Status Code{
                        Response.status_code}\nResponse Headers: {Response.headers}", severityNum=0, dontPrint=True)

                # print(self.headers, "\nresponse headers:", Response.headers, "\n[Cookie]", self.Session.cookies, "\nPassed through cookies:", self.cookie)

                if "trade" not in Response.url and Response.status_code == 500:
                    log(f"API failed to respond {URL}", severityNum=2)

                # If x-csrf-token is invalid apparently the response will provide you with a new one
                # if 'x-csrf-token' in Response.headers:
                #     print("Sucessfully gotten new token from headers",
                #           Response.headers['x-csrf-token'], "Old token:", self.headers['x-csrf-token'])
                    # self.headers['x-csrf-token'] = Response.headers['x-csrf-token']
                # else:
                #     self.generate_csrf()

                # Retry with new csrf once IF there is no 2fa prompt
                if 'rblx-challenge-id' not in Response.headers:
                    refreshed_csrf = True
                    continue
                else:
                    return Response

            elif Response.status_code == 400:
                log(f"Requests payload error, Response: Data{Response.text}, {payload}\n Returning Response",
                    severityNum=1)
                return Response
            elif Response.status_code == 429:
                # NOTE: Handled above..
                continue
            else:
                log(f"Unknown Error Code on {URL} {
                    Response.status_code} {Response.text}", severityNum=4)
                return Response

            # return None

    def load_proxies(self, file_path='proxies.txt'):
        try:
            with open(file_path, 'r') as file:
                self.proxies = ["http://" + line.strip()
                                for line in file if line.strip()]
        except Exception as e:
            log("No proxy file, returning None.", e)

    def refresh_proxies(self, file_path='proxies.txt'):
        self.load_proxies(file_path)
