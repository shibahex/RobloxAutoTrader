"""
Shared setup for the test suite.

The bot reads and writes files relative to the working directory (config.cfg,
cookies.json, projected_checker.json, logs/). Tests run inside a temp folder with
a copy of config.cfg so they never touch your real files.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import types

import pytest
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_FILE = os.path.join(REPO_ROOT, "tests", ".roblox_cookie")

# --- isolate the working directory before any bot module is imported ---------
_WORKDIR = tempfile.mkdtemp(prefix="tradebot-tests-")
shutil.copy(os.path.join(REPO_ROOT, "config.cfg"), _WORKDIR)
with open(os.path.join(_WORKDIR, "cookies.json"), "w") as f:
    json.dump({"roblox_accounts": []}, f)
with open(os.path.join(_WORKDIR, "projected_checker.json"), "w") as f:
    json.dump({}, f)
os.chdir(_WORKDIR)
sys.path.insert(0, REPO_ROOT)


# --- selenium is only needed for browser login; stub it if not installed -----
def _stub_selenium():
    try:
        import seleniumwire  # noqa: F401
        import selenium  # noqa: F401
        import webdriver_manager  # noqa: F401

        return
    except ImportError:
        pass
    names = [
        "selenium",
        "selenium.webdriver",
        "selenium.webdriver.common",
        "selenium.webdriver.common.by",
        "selenium.webdriver.firefox",
        "selenium.webdriver.firefox.service",
        "selenium.webdriver.support",
        "selenium.webdriver.support.ui",
        "selenium.webdriver.support.expected_conditions",
        "selenium.common",
        "selenium.common.exceptions",
        "seleniumwire",
        "webdriver_manager",
        "webdriver_manager.firefox",
    ]
    for name in names:
        sys.modules[name] = types.ModuleType(name)
    m = sys.modules
    m["selenium.webdriver.common.by"].By = object
    m["selenium.webdriver.firefox.service"].Service = object
    m["selenium.webdriver.support.ui"].WebDriverWait = object
    m["selenium.webdriver.support"].expected_conditions = m[
        "selenium.webdriver.support.expected_conditions"
    ]
    m["selenium.common.exceptions"].WebDriverException = Exception
    m["seleniumwire"].webdriver = types.SimpleNamespace()
    m["webdriver_manager.firefox"].GeckoDriverManager = object


_stub_selenium()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: talks to real Roblox/Rolimons (needs a cookie for most)"
    )


def _skip_if_rate_limited(item, outcome):
    """Live tests share rate limits with a running bot: a 429 means skip, not fail."""
    if item.get_closest_marker("live") is None or outcome.excinfo is None:
        return
    from handler.exceptions_types import RateLimited

    error = outcome.excinfo[1]
    if isinstance(error, RateLimited):
        outcome.force_exception(
            pytest.skip.Exception(f"Rate limited (bot probably running): {error}")
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    outcome = yield
    _skip_if_rate_limited(item, outcome)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    _skip_if_rate_limited(item, outcome)


def pytest_sessionfinish(session, exitstatus):
    os.chdir(REPO_ROOT)
    shutil.rmtree(_WORKDIR, ignore_errors=True)


# --- fake HTTP for offline tests ---------------------------------------------
def make_response(
    status=200, body=None, text=None, headers=None, url="https://x.test/"
):
    r = requests.Response()
    r.status_code = status
    if body is not None:
        text = json.dumps(body)
    r._content = (text or "").encode()
    r.headers.update(headers or {})
    r.url = url
    return r


ITEM_FIELDS = 26  # Rolimons item_details fields after the item id


def rolimons_item(name, rap, value=None):
    fields = [None] * ITEM_FIELDS
    fields[0] = name  # item_name
    fields[1] = "asset:8"  # asset_type
    fields[5] = rap  # best_price
    fields[8] = rap  # rap
    fields[16] = value  # value
    fields[17] = 3  # demand
    fields[22] = value or rap  # total_value
    fields[25] = 123  # original_asset_id
    return fields


FAKE_CATALOG = (
    "var item_details = "
    + json.dumps(
        {"1:1": rolimons_item("Hat", 1000), "1:2": rolimons_item("Face", 500, 600)}
    )
    + ";"
)


class FakeRouter:
    """
    Answers requests from a queue per URL prefix. The last queued item repeats.
    Queue an exception instance to have the request raise it.
    """

    def __init__(self):
        self.routes = {}
        self.calls = []

    def set(self, prefix, *items):
        self.routes[prefix] = list(items)

    def __call__(self, handler, method, URL, headers, payload, proxy_dict):
        self.calls.append((method, URL))
        # Most specific (longest) matching prefix wins
        for prefix, items in sorted(self.routes.items(), key=lambda r: -len(r[0])):
            if URL.startswith(prefix) and items:
                item = items.pop(0) if len(items) > 1 else items[0]
                if isinstance(item, BaseException):
                    raise item
                item.url = URL
                return item
        raise AssertionError(f"No fake route for {URL}")


@pytest.fixture
def router(monkeypatch):
    """Routes all bot HTTP through a FakeRouter and makes sleeps instant."""
    from handler.handle_requests import RequestsHandler
    from rolimons_api import RolimonAPI

    fake = FakeRouter()
    fake.set("https://www.rolimons.com/catalog", make_response(text=FAKE_CATALOG))
    monkeypatch.setattr(RequestsHandler, "_send", lambda self, *a: fake(self, *a))
    monkeypatch.setattr(RequestsHandler, "generate_csrf", lambda self: True)
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

    # Rolimons is a singleton; give each test a fresh one on fake data
    RolimonAPI._instance = None
    yield fake
    RolimonAPI._instance = None


# --- real cookie for live tests ----------------------------------------------
@pytest.fixture(scope="session")
def roblox_cookie():
    """
    Reads the cookie from the ROBLOX_COOKIE env var or tests/.roblox_cookie.
    Skips live tests if neither is set. Never printed.
    """
    cookie = os.environ.get("ROBLOX_COOKIE", "").strip()
    if not cookie and os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, encoding="utf-8") as f:
            cookie = f.read().strip()
    if not cookie:
        pytest.skip("No cookie: put it in tests/.roblox_cookie or set ROBLOX_COOKIE")
    return cookie
