"""
Prints and saves the bot's messages.

Every line reads the same in any terminal, with or without color:

     1:02:11 PM Inbound   tisiallyyy: countered 5, declined 12, kept 1
     1:02:15 PM Requests  WARNING: Roblox is rate limiting, waiting 20s

A message that starts with a tag like "[INBOUND]" gets it moved into the tag
column. Warnings and errors always say so in words; color only adds to that.
Color is off when NO_COLOR is set or the output isn't a terminal.
"""

import logging
import os
import re
import shutil
import sys
import textwrap
import threading
import time

TAG_WIDTH = 9
PRINT_LOCK = threading.Lock()

# severityNum -> (word shown before the message, color)
LEVELS = {
    0: ("", ""),
    1: ("NOTICE", "\033[36m"),  # cyan
    2: ("WARNING", "\033[33m"),  # yellow
    3: ("ERROR", "\033[31m"),  # red
    4: ("CRITICAL", "\033[1;31m"),  # bold red
    5: ("DEBUG", "\033[2m"),  # dim
}
DIM = "\033[2m"
RESET = "\033[0m"

TAG = re.compile(r"^\[([A-Za-z][\w .:-]{0,24})\]\s*")


def use_color(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def clock_time() -> str:
    """12-hour time, same width all day: ' 3:08:32 PM', '11:08:32 AM'."""
    return time.strftime("%I:%M:%S %p", time.localtime()).lstrip("0").rjust(11)


def split_tag(msg: str):
    """'[INBOUND] text' -> ('Inbound', 'text'). Shouting tags are calmed down."""
    match = TAG.match(msg)
    if not match:
        return "", msg
    words = match.group(1).split()
    tag = " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in words)
    return tag, msg[match.end() :]


def wrap(text: str, width: int | None, indent: str) -> list[str]:
    """Wraps each line to width; wrapped parts get the indent (plus their own)."""
    if not width:
        return text.split("\n")
    out = []
    for line in text.split("\n"):
        own = " " * (len(line) - len(line.lstrip(" ")))
        out += textwrap.wrap(
            line,
            width=max(20, width),
            subsequent_indent=own + "  ",
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
    return out


def format_line(msg, severity=0, color=False, clock=None, width=None) -> str:
    """
    One message: "time  Tag       text". Lines after the first start under the
    tag, so they stay readable on small terminals. width: wrap to this many
    columns (the terminal's), None = don't wrap (log file).
    """
    tag, text = split_tag(str(msg))
    if " " in tag:  # "[ACCOUNT two]" -> tag Account, "two: ..." in the text
        tag, who = tag.split(" ", 1)
        text = f"{who}: {text}"
    level = severity
    if tag.lower() in ("debug", "debugging"):
        level, tag = 5, ""
    word, level_color = LEVELS.get(level, ("", ""))
    stamp = clock or clock_time()
    if word:
        text = f"{word}: {text}"

    lead = f"{stamp} {tag:<{TAG_WIDTH}} "
    indent = " " * (len(stamp) + 1)
    first, *rest = text.split("\n")
    lines = wrap(first, width and width - len(lead), "")
    lines[1:] = [indent + line for line in lines[1:]]
    for line in rest:
        lines += [indent + part for part in wrap("  " + line, width and width - len(indent), "")]
    body = lines[0] + "".join("\n" + line for line in lines[1:])

    if not color:
        return lead + body
    lead = f"{DIM}{stamp}{RESET} {tag:<{TAG_WIDTH}} "
    return lead + (level_color + body + RESET if level_color else body)


def terminal_width() -> int | None:
    try:
        return shutil.get_terminal_size((0, 0)).columns or None
    except (OSError, ValueError):
        return None


class Logging:
    """Prints messages and saves them to logs/<start time>.log."""

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        current_time = time.strftime("%I-%M-%S-%p-%m-%d-%Y")
        log_file = os.path.join(self.log_dir, f"{current_time}.log")
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(message)s",
            encoding="utf-8",
        )

    def log(self, msg, dontPrint=False, severityNum=0) -> None:
        """
        Prints a message (unless dontPrint) and always saves it to the log file.
        severityNum: 0 info, 1 notice, 2 warning, 3 error, 4 critical, 5 debug.
        Start the message with a tag like "[INBOUND]" to show where it's from.
        """
        if severityNum not in LEVELS:
            severityNum = 0

        if dontPrint is not True:
            color = use_color()
            line = format_line(
                msg, severityNum, color=color, width=terminal_width() if color else None
            )
            # One write per message, so threads can't mix their lines
            with PRINT_LOCK:
                try:
                    sys.stdout.write(line + "\n")
                except UnicodeEncodeError:
                    # Old Windows consoles can't show some item names
                    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
                    sys.stdout.write(
                        line.encode(encoding, "replace").decode(encoding) + "\n"
                    )
                sys.stdout.flush()

        saved = format_line(
            msg, severityNum, clock=time.strftime("%Y-%m-%d ") + clock_time().strip()
        )
        logging.info(saved)

    @staticmethod
    def cleanupLogs(log_dir="logs", maxLogs=5):
        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
        log_files = sorted(
            log_files,
            key=lambda x: os.path.getmtime(os.path.join(log_dir, x)),
            reverse=True,
        )
        for file in log_files[maxLogs:]:
            os.remove(os.path.join(log_dir, file))


# Instantiate the logger globally
logger = Logging()
log = logger.log
logger.cleanupLogs()
