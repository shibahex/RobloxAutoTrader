"""
Prints and saves the bot's messages.

Every line reads the same in any terminal, with or without color:

     1:02:11 PM  Inbound      tisiallyyy: countered 5, declined 12, kept 1
     1:02:15 PM  Requests     WARNING: Roblox is rate limiting, waiting 20s

A message that starts with a tag like "[INBOUND]" gets it moved into the tag
column. Warnings and errors always say so in words; color only adds to that.
Color is off when NO_COLOR is set or the output isn't a terminal.
"""

import logging
import os
import re
import sys
import time

TAG_WIDTH = 12

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


def format_line(msg, severity=0, color=False, clock=None) -> str:
    """One console line (continuation lines are indented under the message)."""
    tag, text = split_tag(str(msg))
    level = 5 if tag.lower() in ("debug", "debugging") else severity
    word, level_color = LEVELS.get(level, ("", ""))
    if level == 5 and tag.lower() in ("debug", "debugging"):
        tag = ""
    stamp = clock or clock_time()
    lead = f"{stamp}  {tag:<{TAG_WIDTH}} "
    if word:
        text = f"{word}: {text}"
    text = text.replace("\n", "\n" + " " * len(lead))
    if not color:
        return lead + text
    tag_part = f"{DIM}{stamp}{RESET}  {tag:<{TAG_WIDTH}} "
    if level_color:
        return tag_part + level_color + text + RESET
    return tag_part + text


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
            line = format_line(msg, severityNum, color=use_color())
            try:
                print(line, flush=True)
            except UnicodeEncodeError:
                # Old Windows consoles can't show some item names
                encoding = getattr(sys.stdout, "encoding", None) or "ascii"
                print(line.encode(encoding, "replace").decode(encoding), flush=True)

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
