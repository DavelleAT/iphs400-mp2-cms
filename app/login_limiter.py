"""Login rate limiting (S2; SECURITY-CHECKLIST #2).

After MAX_FAILURES failed logins for one email within WINDOW_SECONDS, further
attempts for that email are refused, even with the right password, until the
oldest of those failures is WINDOW_SECONDS old.

Keyed on the account, not the client: one person's typos never lock out a
colleague on the same office network. Unknown emails are counted the same way,
so a lockout says nothing about whether an account exists. Kept in memory: a
restart clears it, which is fine for a console that runs on one machine
(ADR-001).
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60


class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        # Seconds. Tests replace it with a frozen clock.
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}

    @staticmethod
    def _key(email: str) -> str:
        return email.strip().lower()

    def _recent(self, key: str) -> deque[float]:
        """This key's failures inside the window; older ones are dropped."""
        failures = self._failures.get(key, deque())
        cutoff = self.clock() - WINDOW_SECONDS
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            self._failures.pop(key, None)
        return failures

    def is_locked(self, email: str) -> bool:
        return len(self._recent(self._key(email))) >= MAX_FAILURES

    def record_failure(self, email: str) -> None:
        key = self._key(email)
        self._failures[key] = self._recent(key)
        self._failures[key].append(self.clock())

    def record_success(self, email: str) -> None:
        self._failures.pop(self._key(email), None)

    def reset(self) -> None:
        self._failures.clear()


limiter = LoginLimiter()
