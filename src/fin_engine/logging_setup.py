"""Structured logging for fin-engine (v1.5.3, observability).

Library-correct logging: the package attaches a ``NullHandler`` to its root
logger so importing fin-engine never forces log output on the host application.
Call :func:`configure_logging` (the REPL/demos do) to actually see logs.

Privacy rule (report "avoid logging confidential information" + the project's
no-personal-info rule): log EVENTS and COUNTS, never monetary amounts, account
balances or transaction descriptions. A log line may say "pnl computed for 7
accounts", never the revenue figure.
"""

from __future__ import annotations

import logging
import os

_ROOT = "fin_engine"

# Attach a NullHandler once so library use is silent unless the app configures
# logging. Safe to import repeatedly.
logging.getLogger(_ROOT).addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``fin_engine`` namespace.

    ``name`` is usually ``__name__``; a module's logger is a child of the
    package root, so one ``configure_logging`` call controls them all.
    """
    return logging.getLogger(name if name.startswith(_ROOT) else f"{_ROOT}.{name}")


def configure_logging(level: str | None = None) -> None:
    """Send fin-engine logs to the console at the given level.

    Level comes from the ``level`` argument, else the ``FIN_ENGINE_LOG_LEVEL``
    env var, else ``WARNING`` (quiet by default). Call once from an application
    entry point (REPL, demo); library code must not call this.
    """
    lvl_name = (level or os.getenv("FIN_ENGINE_LOG_LEVEL") or "WARNING").upper()
    lvl = getattr(logging, lvl_name, logging.WARNING)
    root = logging.getLogger(_ROOT)
    root.setLevel(lvl)
    # Add a stream handler only once, even if called more than once.
    if not any(isinstance(h, logging.StreamHandler)
               and not isinstance(h, logging.NullHandler) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
        root.addHandler(handler)
