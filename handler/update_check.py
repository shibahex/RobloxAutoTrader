"""
Tells you when a newer TradebotRBX release is out, and how to update:
  - the .exe / Linux build: where to download it
  - running from a git clone: git pull (your config.cfg isn't in the repo,
    so pulling never touches it)
Runs once at startup, in the background; the main menu shows the message.
Never raises.
"""

import os
import re
import shutil
import subprocess
import sys
import threading

import requests

import version
from handler.handle_logs import log

REPO = "shibahex/RobloxAutoTrader"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases/latest"
# The update message once the check finds one (shown in the main menu)
message = None
_thread = None

SOURCE_ZIP = f"https://github.com/{REPO}"


def parse_version(tag: str):
    """
    'v2.0.1' -> ((2, 0, 1), 1), 'v2.0-beta' -> ((2, 0, 0), 0). The second
    number puts a stable release after a pre-release of the same version.
    None if it isn't a version.
    """
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)((?:-[A-Za-z0-9]+)*)", str(tag).strip())
    if not match:
        return None
    numbers = tuple(int(n) for n in match.group(1).split("."))
    numbers += (0,) * (3 - len(numbers))
    labels = [p.lower() for p in match.group(2).split("-") if p]
    stable = 0 if labels else 1
    return numbers, stable


def is_newer(tag: str, current: str = None, stage: str = None) -> bool:
    """True when the release tag is a newer version than the one running."""
    current = version.VERSION if current is None else current
    stage = version.STAGE if stage is None else stage
    latest = parse_version(tag)
    running = parse_version(f"v{current}-{stage}" if stage else f"v{current}")
    return bool(latest and running and latest > running)


def latest_release(get=requests.get) -> dict | None:
    """{"tag", "url"} of the newest stable release, or None if it can't tell."""
    try:
        response = get(
            LATEST_API, timeout=10, headers={"Accept": "application/vnd.github+json"}
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return {"tag": data["tag_name"], "url": data.get("html_url") or RELEASES}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def config_is_tracked(folder=".") -> bool:
    """True when this clone still has config.cfg in git (older versions did)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "config.cfg"],
            cwd=folder,
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pull_steps(config_tracked: bool, windows: bool) -> list[str]:
    """The commands to update a git clone without losing config.cfg."""
    if not config_tracked:
        steps = ["git pull"]
    elif windows:
        # Older clones have config.cfg in git: back it up, let the pull
        # remove it from git, then put yours back (git ignores it after)
        steps = [
            "copy config.cfg config.backup.cfg",
            "git checkout -- config.cfg",
            "git pull",
            "copy /Y config.backup.cfg config.cfg",
        ]
    else:
        steps = [
            "cp config.cfg config.backup.cfg",
            "git checkout -- config.cfg",
            "git pull",
            "cp config.backup.cfg config.cfg",
        ]
    return steps + ["pip install -r requirements.txt"]


def update_message(
    release: dict,
    frozen: bool,
    has_git: bool,
    config_tracked: bool,
    windows: bool,
) -> str:
    running = version.full_version()
    head = f"[UPDATE] TradebotRBX {release['tag'].lstrip('v')} is out (you have {running})."
    if frozen:
        return (
            f"{head}\nDownload it: {release['url']}\n"
            "Then move your config.cfg and the bot's .json/.jsonc files "
            "(accounts and settings) into the new folder."
        )
    if has_git:
        steps = pull_steps(config_tracked, windows)
        note = (
            "\nThis keeps your config.cfg (new versions don't have it in git, "
            "so after this git pull never touches it)."
            if config_tracked
            else "\nYour config.cfg isn't in git, so pulling never touches it."
        )
        return (
            f"{head}\nUpdate from the bot's folder:\n"
            + "\n".join(f"  {step}" for step in steps)
            + note
        )
    return f"{head}\nDownload the new version: {SOURCE_ZIP}"


def check(get=requests.get, folder=".") -> str | None:
    """Logs how to update when a newer release is out. Returns the message."""
    try:
        release = latest_release(get)
        if not release or not is_newer(release["tag"]):
            return None
        has_git = os.path.isdir(os.path.join(folder, ".git")) and bool(
            shutil.which("git")
        )
        message = update_message(
            release,
            frozen=bool(getattr(sys, "frozen", False)),
            has_git=has_git,
            config_tracked=has_git and config_is_tracked(folder),
            windows=os.name == "nt",
        )
        globals()["message"] = text = message
        log(text, dontPrint=True)
        return text
    except Exception as e:  # an update check must never stop the bot
        log(f"[UPDATE] Couldn't check for updates: {e}", dontPrint=True)
        return None


def check_in_background():
    global _thread
    if _thread is None:
        _thread = threading.Thread(target=check, name="update-check", daemon=True)
        _thread.start()


def wait(seconds: float):
    """Gives the startup check a moment to finish, so the menu can show it."""
    if _thread is not None:
        _thread.join(seconds)
