"""The harness's exit codes, as one enum.

Every command handler returns a member of :class:`ExitCode`, never a bare
number. What each command means by each member is in
``skills/_shared/references/exit-codes.md`` — the one table; docstrings name
members and point there instead of repeating it.
"""

from __future__ import annotations

import enum


class ExitCode(enum.IntEnum):
    OK = 0
    # A Python traceback always exits 1, so 1 means one thing: an exception
    # nobody handled. No handler returns it; it is here to be documented.
    CRASH = 1
    REFUSED = 2
    INCOMPLETE = 3
    UNKNOWN = 4
    NOOP = 5
    FINDINGS = 6
