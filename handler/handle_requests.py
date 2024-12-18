import time

import random
import requests



class RequestsHandler:

    def __init__(self, Session: requests.Session = requests.Session(), use_proxies=False, cookie:dict=None) -> None:
        self.use_proxies = use_proxies
        self.proxies = []
        self.proxy_timeout = {}
        self.timeout_duration = 60

        if self.use_proxies == True:
            self.load_proxies()

        self.Session = Session

        if cookie:
            self.Session.cookies.update(cookie)
            #print("Updated cookie")

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',  # Can be adjusted based on your preferred language
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',  # Mimicking a referer header
            'Cache-Control': 'max-age=0'

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
        try:
            token_post = self.Session.post('https://catalog.roblox.com/v1/catalog/items/details')

            if 'x-csrf-token' in token_post.headers:
                #print("returning",token_post.headers['x-csrf-token'])
                self.Session.headers["x-csrf-token"] = token_post.headers['x-csrf-token']
                return True
            else:
                print("Couldnt fetch x-csrf-token")
                return False
        except:
            print("Couldnt fetch x-csrf-token")
            return False

    def requestAPI(self, URL, method="get", payload=None, additional_headers=None) -> requests.Response:
        """
        Handles the requests and returns the response if its successful.
        You can pass through requests.Session() with Roblox Cookies.
        """

        """
        Proxy Managment
        """

        headers = self.headers.copy()  # Create a copy of the original headers
        
        if additional_headers:
            headers.update(additional_headers)  # Add the additional headers temporarily
        
        if not self.proxies:
            self.use_proxies = False
        
        consecutive_rate_limits = 0  
        
        while True:
            proxy_dict = self.return_proxy() if self.use_proxies else None

            if proxy_dict is None and self.use_proxies:
                print("No available proxies, waiting...")
                time.sleep(self.timeout_duration)
                continue
            try:
                if method.lower() == "get":
                    #print(URL)
                    Response = self.Session.get(
                        URL, headers=headers, proxies=proxy_dict, timeout=30)
                elif method.lower() == "post":
                    Response = self.Session.post(
                        URL, headers=headers, json=payload, proxies=proxy_dict, timeout=30)
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

            if Response.status_code == 429:
                print("hit ratelimit on url", URL, Response.json())
                if self.use_proxies:
                    self.rate_limit(proxy_dict['http'])
                else:
                    wait_time = 60 * (2 ** consecutive_rate_limits)
                    print(f"Rate limited without proxies, waiting {wait_time} secs.", URL)
                    time.sleep(wait_time)
                    consecutive_rate_limits += 1

                    # If this API isnt hard ratelimited then contiue to try, if it is return 429 after 5 tries
                    if "errors" in Response.json():
                        if "too many requests" in Response.json()['errors'][0]['message'].lower():
                            print("Too many request continuing", Response.json())
                            continue

                    if consecutive_rate_limits > 5:
                        return 429
            else:
                consecutive_rate_limits = 0


            if Response.status_code == 200:
                #print("200", URL)
                return Response
            elif Response.status_code == 403:
                new_token = self.generate_csrf()
                if new_token:
                    print("got new token for requests")
                else:
                    print("couldn't get token", URL, self.Session.cookies.get_dict())
                    return Response
                continue

                # TODO: FIX EDGE CASE
                # <LeftMouse>
                # debug purposes also items/details returns 403 on purpose
                if URL != "https://catalog.roblox.com/v1/catalog/items/details":
                    print("Error code 403: Authorization declined on url", URL)
                    #print(proxy_dict)
                try:
                    if "errors" in Response.json():
                        if "Token Validation Failed" in Response.json()['errors'][0]['message'].lower():
                            print("Generating new token")
                            self.headers['x-csrf-token'] = self.generate_csrf()
                            continue
                except:
                    pass

                return Response
            elif Response.status_code == 500:
                print("API failed to respond..", URL)
                return Response
            elif Response.status_code == 400:
                print("Requests payload error, returning", Response.text, payload)
                return Response
            else:
                print("Unknown Error Code on", URL, Response.status_code, Response.text)
                return Response

            # return None


    def load_proxies(self, file_path='proxies.txt'):
        try:
            with open(file_path, 'r') as file:
                self.proxies = ["http://" + line.strip() for line in file if line.strip()]
        except Exception as e:
            print("No proxy file, returning None.", e)

    def refresh_proxies(self, file_path='proxies.txt'):
        self.load_proxies(file_path)
