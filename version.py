"""
The bot's version. Changing VERSION or STAGE here (and pushing to main or
refactor-branch) makes GitHub Actions build the Windows .exe and Linux
binary and publish them as a release.
"""

import importlib.util
import sys

VERSION = "2.0"
# "BETA", or "" for a stable release
STAGE = ""


def edition() -> str:
    """'-community' for the private build (it has the community features)."""
    try:
        has_community = (
            "community_values" in sys.modules
            or importlib.util.find_spec("community_values") is not None
        )
    except (ImportError, ValueError):
        has_community = False
    return "-community" if has_community else ""


def full_version() -> str:
    """For the startup log, e.g. "2.0 (BETA)" or "2.0-community (BETA)"."""
    text = VERSION + edition()
    return f"{text} ({STAGE})" if STAGE else text


def release_tag() -> str:
    """Git tag for the release, e.g. "v2.0-beta" or "v2.0-community-beta"."""
    tag = "v" + VERSION + edition()
    return f"{tag}-{STAGE.lower()}" if STAGE else tag
