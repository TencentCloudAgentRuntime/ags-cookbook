from __future__ import annotations

import logging
import logging.handlers
import queue
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# Console instance shared across all minisweagent loggers.
_logging_console: Console | None = None

# The underlying RichHandler (consumed by the QueueListener, not attached to
# the root logger directly).
_actual_rich_handler: RichHandler | None = None

# The handler attached to the root logger.  In queue mode this is a
# QueueHandler; in simple mode it is the RichHandler itself.
_root_handler: logging.Handler | None = None

# Queue-based logging infrastructure for thread-safe Rich output.
_log_queue: queue.Queue | None = None
_queue_listener: logging.handlers.QueueListener | None = None


def _ensure_setup() -> Console:
    """Lazily set up the root logger with a default Console if not yet done."""
    if _logging_console is not None:
        return _logging_console

    return setup_logging()


def setup_logging(console: Console | None = None) -> Console:
    """Initialise (or re-initialise) the root ``minisweagent`` logger.

    Args:
        console: Rich Console to use for log output.  If *None* a new
                 stderr Console is created (suitable for non-batch / interactive
                 use).

    Returns:
        The Console instance attached to the logger.

    When called with a *console* argument after the logger has already been
    set up (e.g. at import time), the existing handler is replaced so that all
    subsequent log output goes through the new Console.  This allows batch
    runners to call ``setup_logging(shared_console)`` **after** imports and
    have the shared Console take effect.

    In batch mode (when a shared Console is provided), a ``QueueHandler`` /
    ``QueueListener`` pair is used so that only a single listener thread ever
    calls ``Console.print()``, avoiding lock contention with Rich ``Live``.
    """
    global _logging_console, _actual_rich_handler, _root_handler
    global _log_queue, _queue_listener

    if console is None:
        if _logging_console is not None:
            # Already initialised with defaults, nothing to do.
            return _logging_console
        console = Console(stderr=True, force_terminal=True)

    root = logging.getLogger("minisweagent")
    root.setLevel(logging.DEBUG)

    # Tear down previous setup.
    shutdown_logging()
    if _root_handler is not None:
        root.removeHandler(_root_handler)

    # Build the RichHandler (the real sink).
    rich_handler = RichHandler(
        console=console,
        show_path=False,
        show_time=False,
        show_level=False,
        markup=True,
    )
    formatter = logging.Formatter("%(name)s: %(levelname)s: %(message)s")
    rich_handler.setFormatter(formatter)

    # Route log records through a queue so only the listener thread touches the
    # Console — this eliminates contention between worker threads and the Rich
    # Live refresh thread.
    _log_queue = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(_log_queue)
    root.addHandler(queue_handler)

    _queue_listener = logging.handlers.QueueListener(
        _log_queue, rich_handler, respect_handler_level=True,
    )
    _queue_listener.start()

    _logging_console = console
    _actual_rich_handler = rich_handler
    _root_handler = queue_handler

    return console


def shutdown_logging() -> None:
    """Stop the QueueListener (if running).

    Call this after the Rich ``Live`` context exits to flush remaining log
    records and release the listener thread.
    """
    global _queue_listener
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None


def get_logging_console() -> Console | None:
    """Return the Console currently used for logging (or *None*)."""
    return _logging_console


def set_stream_level(level: int) -> None:
    """Adjust the Rich stream handler level without affecting file handlers."""
    if _actual_rich_handler is not None:
        _actual_rich_handler.setLevel(level)


def add_file_handler(path: Path | str, level: int = logging.DEBUG, *, print_path: bool = True) -> None:
    root = logging.getLogger("minisweagent")
    handler = logging.FileHandler(path)
    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    if print_path:
        root.info(f"Logging to '{path}'")


# Auto-setup with default Console so that ``from minisweagent.utils.log import logger``
# works without an explicit ``setup_logging()`` call (e.g. interactive mode).
# Batch runners can later call ``setup_logging(shared_console)`` to switch to a
# shared Console before any worker threads start.
_ensure_setup()
logger = logging.getLogger("minisweagent")


__all__ = ["logger", "setup_logging", "shutdown_logging", "get_logging_console", "set_stream_level", "add_file_handler"]
