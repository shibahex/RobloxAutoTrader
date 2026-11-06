"""Fixes for the packaged (PyInstaller) build. Run before anything else."""

import os
import sys
import warnings


def restore_child_library_path(environ=os.environ, frozen=None):
    """
    The packaged Linux build points LD_LIBRARY_PATH at its own bundled
    libraries. Programs the bot starts (sh to clear the screen, Firefox,
    Sober...) inherit that and can crash, e.g. "sh: symbol lookup error".
    Put back the user's own value (PyInstaller saves it as LD_LIBRARY_PATH_ORIG).
    The bot itself keeps working: the library path is only read when a
    program starts.
    """
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    if not frozen:
        return
    original = environ.get("LD_LIBRARY_PATH_ORIG")
    if original is not None:
        environ["LD_LIBRARY_PATH"] = original
    else:
        environ.pop("LD_LIBRARY_PATH", None)


def hide_library_warnings():
    # selenium-wire still uses pkg_resources; the warning isn't ours to fix
    warnings.filterwarnings(
        "ignore", message="pkg_resources is deprecated", category=UserWarning
    )


restore_child_library_path()
hide_library_warnings()
