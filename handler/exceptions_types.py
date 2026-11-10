"""
Every error the bot raises on purpose lives here.

Catch `TradebotError` to handle anything the bot knows about. Anything that
is not a `TradebotError` is a bug and should be logged with a traceback.

TradebotError
├── NetworkError                 couldn't reach the server at all
├── InvalidResponse              server answered, but not in the shape we expected
├── RobloxAPIError               Roblox answered with an error
│   ├── BadRequest               400, carries Roblox error codes
│   │   └── TradeRejected        trade send/counter refused
│   │       ├── InsufficientRobux
│   │       ├── ItemsUnavailable
│   │       ├── RatioTooLow      their Trade Quality filter refused it
│   │       └── UserCannotTrade
│   ├── AuthError                401/403 that isn't fixable by retrying
│   │   └── CookieInvalid        cookie expired or logged out
│   ├── ChallengeRequired        2FA challenge, carries the response to solve it
│   ├── Forbidden                403 (private inventory, blocked endpoint, ...)
│   ├── NotFound                 404
│   ├── RateLimited              429 after retries ran out
│   │   └── TradeLimit           account hit its daily trade limit
│   └── ServerError              5xx after retries ran out
├── TwoFactorError               solving a 2FA challenge failed
├── InventoryUnavailable         couldn't load a user's inventory
├── UnknownItem                  item isn't in Rolimons data yet
├── RolimonsError                Rolimons down or its page format changed
├── DataFileError                a local JSON file is unreadable
└── ConfigError                  config value missing or invalid
    └── NoItemsToScan            scan filters match no items
"""


class TradebotError(Exception):
    """Base class for every error the bot raises on purpose."""


class NetworkError(TradebotError):
    """Connection failed, timed out, or the proxy broke, after all retries."""

    def __init__(self, url: str, cause: Exception | None = None):
        self.url = url
        self.cause = cause
        super().__init__(f"Network error on {url}: {cause}")


class InvalidResponse(TradebotError):
    """The server answered but the body was missing fields or wasn't JSON."""

    def __init__(self, message: str, url: str | None = None):
        self.url = url
        super().__init__(f"{message} ({url})" if url else message)


class RobloxAPIError(TradebotError):
    """Roblox returned an error status. Holds the parsed Roblox error codes."""

    def __init__(self, response=None, message: str | None = None):
        self.response = response
        self.status_code = getattr(response, "status_code", None)
        self.url = getattr(response, "url", None)
        self.errors = parse_roblox_errors(response) if response is not None else []
        self.codes = [code for code, _ in self.errors]
        if message is None:
            detail = "; ".join(f"[{c}] {m}" for c, m in self.errors) or _short_text(
                response
            )
            message = f"{self.status_code} on {self.url}: {detail}"
        super().__init__(message)

    @property
    def code(self):
        """First Roblox error code, or None."""
        return self.codes[0] if self.codes else None

    def has_message(self, text: str) -> bool:
        text = text.lower()
        return any(text in (msg or "").lower() for _, msg in self.errors)


def short_error(error) -> str:
    """
    An error for the console: just Roblox's own message when it sent one
    ("Trade value ratio is not sufficient."), without the status and URL.
    """
    errors = getattr(error, "errors", None)
    messages = [m for _, m in errors or () if m]
    if messages:
        return "Roblox says: " + "; ".join(messages)
    return str(error)


class BadRequest(RobloxAPIError):
    """400: the payload was rejected."""


class TradeRejected(BadRequest):
    """Roblox refused to send or counter a trade."""


class InsufficientRobux(TradeRejected):
    """Robux offered is more than the account has (Roblox code 17)."""


class ItemsUnavailable(TradeRejected):
    """One or more items are no longer owned or tradeable (Roblox code 12)."""


class RatioTooLow(TradeRejected):
    """
    "Trade value ratio is not sufficient": the other user's trade quality
    filter only lets through trades close in value.
    """


class UserCannotTrade(TradeRejected):
    """The other user has trading off, or can't trade with this account."""


class AuthError(RobloxAPIError):
    """Authentication failed and retrying with a new CSRF token didn't help."""


class CookieInvalid(AuthError):
    """The .ROBLOSECURITY cookie is expired, invalid, or logged out."""


class ChallengeRequired(RobloxAPIError):
    """Roblox wants a 2FA challenge solved. `response` has the challenge headers."""


class Forbidden(RobloxAPIError):
    """403 that isn't a CSRF or 2FA problem."""


class NotFound(RobloxAPIError):
    """404."""


class RateLimited(RobloxAPIError):
    """429 that didn't clear after backing off."""


class TradeLimit(RateLimited):
    """The account sent too many trades and has to wait."""

    def __init__(self, response=None, message: str | None = None):
        super().__init__(response, message or "Account hit the trade send limit")


class ServerError(RobloxAPIError):
    """5xx that didn't clear after retrying."""


class TwoFactorError(TradebotError):
    """Couldn't solve a 2FA challenge (bad secret, missing metadata, or Roblox refused)."""


class InventoryUnavailable(TradebotError):
    """Couldn't load a user's inventory (private, banned, or API failing)."""

    def __init__(self, user_id, cause: Exception | None = None):
        self.user_id = user_id
        self.cause = cause
        super().__init__(f"Couldn't load inventory of {user_id}: {cause}")


class UnknownItem(TradebotError):
    """An item ID isn't in the Rolimons data yet."""

    def __init__(self, item_id):
        self.item_id = item_id
        super().__init__(f"{item_id} is not in Rolimons data yet")


class RolimonsError(TradebotError):
    """Rolimons couldn't be reached or its page/API format changed."""


class RolimonsCookieInvalid(RolimonsError):
    """The account's Rolimons verification cookie is missing, wrong or expired."""


class TradeAdRejected(RolimonsError):
    """Rolimons refused a trade ad (too soon since the last one, bad items...)."""


class DataFileError(TradebotError):
    """A local JSON data file couldn't be read or written."""


class ConfigError(TradebotError, ValueError):
    """A config value is missing or invalid. Also a ValueError for older callers."""


class NoItemsToScan(ConfigError):
    """The scan filters in config match no items."""


def parse_roblox_errors(response) -> list[tuple]:
    """
    Pulls (code, message) pairs out of a Roblox error body.
    Roblox uses two shapes: {"errors": [{"code":..,"message":..}]} and
    {"errors": {"field": "message"}}. Returns [] for anything else.
    """
    try:
        body = response.json()
    except ValueError:
        return []
    if not isinstance(body, dict):
        return []

    errors = body.get("errors")
    if isinstance(errors, list):
        parsed = []
        for err in errors:
            if isinstance(err, dict):
                parsed.append((err.get("code"), str(err.get("message", ""))))
            else:
                parsed.append((None, str(err)))
        return parsed
    if isinstance(errors, dict):
        return [(key, str(msg)) for key, msg in errors.items()]
    return []


def _short_text(response, limit: int = 200) -> str:
    text = getattr(response, "text", "") or ""
    return text[:limit]
