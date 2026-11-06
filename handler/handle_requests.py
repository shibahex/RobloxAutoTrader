import time

import random
import requests
from handler.handle_logs import log
from handler import exceptions_types

MAX_NETWORK_RETRIES = 4
MAX_SERVER_RETRIES = 3
MAX_CSRF_RETRIES = 2
MAX_RATE_LIMIT_RETRIES = 4
TRADE_SEND_PREFIX = "https://trades.roblox.com/v2/trades/"


class RequestsHandler:
    def __init__(
        self,
        Session: requests.Session | None = None,
        use_proxies=False,
        cookie: dict = None,
    ) -> None:
        self.use_proxies = use_proxies
        self.proxies = []
        self.proxy_timeout = {}
        self.timeout_duration = 60

        if self.use_proxies:
            self.load_proxies()

        # Each handler gets its own session so cookies never leak between accounts
        self.Session = Session if Session is not None else requests.Session()

        # URL = Consecutive Limits
        self.ratelimit_urls = {}

        self.cookie = cookie
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            # Can be adjusted based on your preferred language
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",  # Mimicking a referer header
            "Cache-Control": "max-age=0",
            "Content-Type": "application/json",
            "x-csrf-token": None,
        }

    def rate_limit(self, proxy):
        """
        Add proxy to timeout and waits.
        """
        log(f"[REQUESTS] Proxy {proxy} is rate limited, switching proxy")
        self.proxy_timeout[proxy] = time.time() + self.timeout_duration

    def blacklist_proxy(self, proxy):
        self.proxies.remove(proxy)

    def return_proxy(self):
        """
        Returns Proxy that isn't in Timeout. Returns None if None are Available
        """
        available_proxies = [
            proxy
            for proxy in self.proxies
            if proxy not in self.proxy_timeout
            or time.time() >= self.proxy_timeout[proxy]
        ]
        if not available_proxies:
            return None

        proxy = random.choice(available_proxies)
        proxy_dict = {"http": proxy, "https": proxy}
        return proxy_dict

    def generate_csrf(self) -> bool:
        """
        Posts the auth API and grabs the csrf and sets the Class headers as the csrf
        The API response has a failure status code, but we still get the token.
        Returns True if a token was set.
        """
        try:
            response = self.Session.post(
                "https://auth.roblox.com/v2/login", data={}, timeout=30
            )
        except requests.RequestException as e:
            log(f"[REQUESTS] Couldn't get a CSRF token: {e}", severityNum=3)
            return False

        token = response.headers.get("x-csrf-token")
        if token:
            self.headers["x-csrf-token"] = token
            return True

        log(
            "[REQUESTS] Roblox didn't return a CSRF token, the cookie may be invalid",
            severityNum=3,
        )
        return False

    def _send(self, method, URL, headers, payload, proxy_dict) -> requests.Response:
        method = method.lower()
        if method == "get":
            return self.Session.get(
                URL, headers=headers, proxies=proxy_dict, timeout=30
            )
        if method == "post":
            return self.Session.post(
                URL, headers=headers, json=payload, proxies=proxy_dict, timeout=30
            )
        raise ValueError(f"Unsupported request method: {method}")

    def _refresh_csrf_from(self, response) -> bool:
        """Roblox sends a fresh token on a failed CSRF check; use it, else ask for one."""
        token = response.headers.get("x-csrf-token")
        if token and token != self.headers.get("x-csrf-token"):
            self.headers["x-csrf-token"] = token
            return True
        return self.generate_csrf()

    @staticmethod
    def _is_csrf_failure(response) -> bool:
        text = response.text or ""
        return "XSRF token invalid" in text or "Token Validation Failed" in text

    def requestAPI(
        self, URL, method="get", payload=None, additional_headers=None
    ) -> requests.Response:
        """
        Sends the request and returns the Response only if it succeeded (2xx).

        Retries network errors, 5xx, rate limits and CSRF refreshes on its own.
        Anything it can't fix is raised as a typed error from handler.exceptions_types:
        NetworkError, RateLimited/TradeLimit, ChallengeRequired, CookieInvalid,
        AuthError, Forbidden, NotFound, BadRequest, ServerError, RobloxAPIError.
        """
        if not self.proxies:
            self.use_proxies = False

        network_failures = 0
        server_failures = 0
        csrf_refreshes = 0
        proxy_rate_limits = 0

        while True:
            headers = self.headers.copy()
            if additional_headers:
                headers.update(additional_headers)

            if self.cookie:
                self.Session.cookies.update(self.cookie)

            proxy_dict = self.return_proxy() if self.use_proxies else None
            if proxy_dict is None and self.use_proxies:
                log("[REQUESTS] No proxies free, waiting...")
                time.sleep(self.timeout_duration)
                continue

            try:
                Response = self._send(method, URL, headers, payload, proxy_dict)
            except requests.RequestException as e:
                network_failures += 1
                if network_failures > MAX_NETWORK_RETRIES:
                    raise exceptions_types.NetworkError(URL, e) from e

                if self.use_proxies:
                    log(f"[REQUESTS] Proxy {proxy_dict['http']} failed, pausing it")
                    self.rate_limit(proxy_dict["http"])
                else:
                    log(
                        f"[REQUESTS] Network error on {URL.split('?')[0]} ({network_failures}/{MAX_NETWORK_RETRIES}): {e}",
                        severityNum=2,
                    )
                    self.Session.close()
                    time.sleep(10)
                    # Recreate the session to avoid stale connections
                    self.Session = requests.Session()
                continue

            status = Response.status_code

            # Rate limits
            if status == 429:
                error = exceptions_types.RateLimited(Response)
                if URL.startswith(TRADE_SEND_PREFIX) and error.has_message(
                    "too many trade requests"
                ):
                    raise exceptions_types.TradeLimit(Response)

                log(f"hit ratelimit on url {URL}", dontPrint=True)
                if self.use_proxies:
                    proxy_rate_limits += 1
                    self.rate_limit(proxy_dict["http"])
                    if proxy_rate_limits > MAX_RATE_LIMIT_RETRIES:
                        raise error
                    time.sleep(5)
                    continue

                self.ratelimit_urls[URL] = self.ratelimit_urls.get(URL, 0) + 1
                consecutive_rate_limits = self.ratelimit_urls[URL]
                if consecutive_rate_limits > MAX_RATE_LIMIT_RETRIES:
                    del self.ratelimit_urls[URL]
                    raise error

                wait_time = 10 * (2**consecutive_rate_limits)
                log(f"[REQUESTS] Roblox is rate limiting, waiting {wait_time:g}s ({URL.split('?')[0]})")
                time.sleep(wait_time)
                continue

            self.ratelimit_urls.pop(URL, None)

            # Success, but Roblox sometimes returns 200 with an error body
            if 200 <= status < 300:
                if exceptions_types.parse_roblox_errors(Response):
                    raise exceptions_types.RobloxAPIError(Response)
                return Response

            # Auth problems
            if status in (401, 403):
                log(
                    f"Auth failure debug: {status} {Response.url} {Response.text[:300]}",
                    dontPrint=True,
                )
                # 2FA is detected by header, never by message text (Roblox changes
                # the wording). Checked first so a challenge is never mistaken
                # for a CSRF failure.
                if "rblx-challenge-id" in Response.headers:
                    raise exceptions_types.ChallengeRequired(Response)

                if self._is_csrf_failure(Response) or (
                    status == 403 and "x-csrf-token" in Response.headers
                ):
                    csrf_refreshes += 1
                    if csrf_refreshes > MAX_CSRF_RETRIES:
                        raise exceptions_types.AuthError(
                            Response, f"CSRF token kept failing on {URL}"
                        )
                    if self._refresh_csrf_from(Response):
                        log("Refreshed CSRF token", dontPrint=True)
                    else:
                        log(
                            "Failed refreshing CSRF token",
                            severityNum=3,
                            dontPrint=True,
                        )
                    continue

                if status == 401:
                    if self.cookie:
                        raise exceptions_types.CookieInvalid(Response)
                    raise exceptions_types.AuthError(Response)

                raise exceptions_types.Forbidden(Response)

            if status == 400:
                log(
                    f"Request payload error, Response: {Response.text}, Data: {payload}, URL: {Response.url}",
                    severityNum=1,
                    dontPrint=True,
                )
                raise exceptions_types.BadRequest(Response)

            if status == 404:
                raise exceptions_types.NotFound(Response)

            if status >= 500:
                server_failures += 1
                if server_failures > MAX_SERVER_RETRIES:
                    raise exceptions_types.ServerError(Response)
                log(
                    f"Server error {status} on {URL}, retrying ({server_failures}/{MAX_SERVER_RETRIES})",
                    dontPrint=True,
                )
                time.sleep(2 * server_failures)
                continue

            log(
                f"[REQUESTS] Unexpected {status} from {URL.split('?')[0]}: {Response.text[:300]}",
                severityNum=3,
            )
            raise exceptions_types.RobloxAPIError(Response)

    def load_proxies(self, file_path="proxies.txt"):
        try:
            with open(file_path, "r") as file:
                self.proxies = [
                    "http://" + line.strip() for line in file if line.strip()
                ]
        except OSError as e:
            log("[REQUESTS] No proxy file, not using proxies")

    def refresh_proxies(self, file_path="proxies.txt"):
        self.load_proxies(file_path)
