from __future__ import annotations

import logging
import os
import threading

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

_SET_UP_LOGGERS = set()
_ADDITIONAL_HANDLERS = []

# Console instance used by all SWE-ReX loggers.
# Defaults to a dedicated stderr Console. Call ``set_console()`` *before* the
# first ``get_logger()`` call to share a Console with Rich Live and avoid
# garbled output in batch mode.
_swerex_logging_console: Console | None = None


def set_console(console: Console) -> None:
    """Override the Console used by all future ``get_logger()`` calls.

    Call this early (before any SWE-ReX logger is created) to share a single
    Console with Rich ``Live``, so that log output is rendered above the Live
    area instead of clobbering it.
    """
    global _swerex_logging_console
    _swerex_logging_console = console


def _get_console() -> Console:
    """Return the current logging Console, creating a default if needed."""
    global _swerex_logging_console
    if _swerex_logging_console is None:
        _swerex_logging_console = Console(stderr=True)
    return _swerex_logging_console


def _interpret_level_from_env(level: str | None, *, default=logging.DEBUG) -> int:
    if not level:
        return default
    level = level.strip()
    if not level:
        return default
    try:
        return int(level)
    except ValueError:
        interpreted_level = getattr(logging, level.upper(), None)
        if isinstance(interpreted_level, int):
            return interpreted_level
        return default


_STREAM_LEVEL = _interpret_level_from_env(os.environ.get("SWE_REX_LOG_STREAM_LEVEL"))
_INCLUDE_LOGGER_NAME_IN_STREAM_HANDLER = False


def set_stream_level(level: int) -> None:
    """Change the stream (RichHandler) level for all existing and future SWE-ReX loggers.

    Call this in batch mode to reduce console noise while Rich Live is active.
    """
    global _STREAM_LEVEL
    _STREAM_LEVEL = level
    for name in list(_SET_UP_LOGGERS):
        logger = logging.getLogger(name)
        for handler in logger.handlers:
            if isinstance(handler, RichHandler):
                handler.setLevel(level)

_THREAD_NAME_TO_LOG_SUFFIX: dict[str, str] = {}


def register_thread_name(name: str) -> None:
    thread_name = threading.current_thread().name
    _THREAD_NAME_TO_LOG_SUFFIX[thread_name] = name


class _RichHandlerWithEmoji(RichHandler):
    def __init__(self, emoji: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not emoji.endswith(" "):
            emoji += " "
        self.emoji = emoji

    def get_level_text(self, record: logging.LogRecord) -> Text:
        level_name = record.levelname
        return Text.styled((self.emoji + level_name).ljust(10), f"logging.level.{level_name.lower()}")


def get_logger(name: str, *, emoji: str = "🦖") -> logging.Logger:
    """Get logger. Use this instead of `logging.getLogger` to ensure
    that the logger is set up with the correct handlers.
    """
    thread_name = threading.current_thread().name
    if thread_name != "MainThread":
        name = name + "-" + _THREAD_NAME_TO_LOG_SUFFIX.get(thread_name, thread_name)
    logger = logging.getLogger(name)
    if name in _SET_UP_LOGGERS:
        # Already set up by this module
        return logger
    handler = _RichHandlerWithEmoji(
        emoji=emoji,
        console=_get_console(),
        show_time=bool(os.environ.get("SWE_AGENT_LOG_TIME", False)),
        show_path=False,
    )
    handler.setLevel(_STREAM_LEVEL)
    logger.setLevel(_STREAM_LEVEL)
    logger.addHandler(handler)
    logger.propagate = False
    _SET_UP_LOGGERS.add(name)
    for handler in _ADDITIONAL_HANDLERS:
        logger.addHandler(handler)
    return logger
