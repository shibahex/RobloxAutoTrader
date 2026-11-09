"""
Logs an account into Rolimons with its Roblox cookie, no browser needed.

rolimons.com/verify has a "Login with Roblox" button (Roblox OAuth). The bot
does the same thing: it approves Rolimons on Roblox's OAuth API as the
account, then opens the link Roblox returns, and Rolimons answers with its
_RoliVerification cookie.
"""

import requests

from handler.exceptions_types import NetworkError, RolimonsError
from handler.handle_trade_ads import COOKIE_NAME

AUTHORIZE_URL = "https://apis.roblox.com/oauth/v1/authorizations"
# Rolimons' Roblox OAuth app, from the button on rolimons.com/verify
CLIENT_ID = "3367241575729602289"
REDIRECT_URI = "https://api.rolimons.com/auth/v1/robloxoauth"
SCOPES = ("openid", "profile")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def rolimons_login(request_handler, user_id, session=requests) -> str:
    """
    Returns a fresh _RoliVerification cookie for this Roblox account.
    request_handler: the account's RequestsHandler (sends its Roblox cookie).
    Raises RolimonsError or NetworkError, or a Roblox error from requestAPI.
    """
    body = {
        "clientId": CLIENT_ID,
        "redirectUri": REDIRECT_URI,
        "responseTypes": ["Code"],
        "scopes": [{"scopeType": s, "operations": ["read"]} for s in SCOPES],
        "resourceInfos": [
            {"owner": {"id": str(user_id), "type": "User"}, "resources": {}}
        ],
    }
    response = request_handler.requestAPI(
        AUTHORIZE_URL,
        "post",
        payload=body,
        additional_headers={
            "Origin": "https://www.roblox.com",
            "Referer": "https://www.roblox.com/",
        },
    )
    try:
        location = response.json()["location"]
    except (ValueError, KeyError, TypeError) as e:
        raise RolimonsError("Roblox didn't return a Rolimons login link") from e
    if not str(location).startswith(REDIRECT_URI):
        raise RolimonsError("Roblox sent the login somewhere other than Rolimons")

    try:
        answer = session.get(
            location,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException as e:
        raise NetworkError(REDIRECT_URI, e) from e
    cookie = answer.cookies.get(COOKIE_NAME)
    if not cookie:
        raise RolimonsError(
            f"Rolimons didn't log in (HTTP {answer.status_code}, no {COOKIE_NAME})"
        )
    return cookie
