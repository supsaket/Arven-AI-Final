"""Proactive assistant engine.

Produces genuinely useful, low-noise suggestions from real signals:
* enabled-gate (PROACTIVE_ENABLED + initiative preference)
* quiet-hours suppression (PROACTIVE_QUIET_HOURS_START / END)
* per-scope snooze and resume
* duplicate prevention per scope (a suggestion is not re-offered twice)
* throttled context providers with isolation (a bad provider never breaks)
* integration with the scheduler store for upcoming reminders
* stats for observability
"""

import datetime
import threading
import time

from config import get_settings
from core.logging import logger


def _parse_clock(value, default="09:00"):
    try:
        hh, mm = str(value).split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        try:
            return int(str(default).replace(":", "")) if False else 0
        except Exception:
            return 0


class ProactiveEngine:

    def __init__(self, settings=None, providers=None, now_fn=None):
        self.settings = settings or get_settings()
        self.now_fn = now_fn or (lambda: datetime.datetime.now())
        self._providers = providers if providers is not None else [self._clock_provider]
        self._lock = threading.Lock()
        self._snoozes = {}
        self._last_suggestions = {}
        self._calls = 0
        self._failures = 0
        self._suggestion_count = 0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def _bool(self, name, default):
        try:
            return bool(self.settings.get(name, default))
        except Exception:
            return default

    def _int(self, name, default):
        try:
            return int(self.settings.get(name, default))
        except Exception:
            return default

    @property
    def enabled(self):
        if not self._bool("PROACTIVE_ENABLED", True):
            return False
        initiative = self._int("PROACTIVE_INITIATIVE", 1)
        return initiative > 0

    def quiet_hours_window(self, now=None):
        start = self._int("PROACTIVE_QUIET_HOURS_START_MINUTES", 0)
        end = self._int("PROACTIVE_QUIET_HOURS_END_MINUTES", 0)
        if start == 0 and end == 0:  # no window configured
            return None
        minutes = (now or self.now_fn()).hour * 60 + (now or self.now_fn()).minute
        if start <= end:
            return start <= minutes < end
        return minutes >= start or minutes < end

    def _permitted(self, scope):
        blocked = {"disabled", "blocked"}
        return str(scope or "").lower() not in blocked

    # ------------------------------------------------------------------
    # Context providers
    # ------------------------------------------------------------------
    def _clock_provider(self, now):
        """Real time-based signals (kept minimal and non-spammy)."""
        hour = now.hour
        suggestions = []
        if hour >= 22 or hour < 6:
            suggestions.append({
                "text": "It's quite late — remind me if you want to wrap up.",
                "scope": "wind_down",
                "priority": 5,
            })
        if hour >= 7 and hour < 9:
            suggestions.append({
                "text": "Morning — want me to check upcoming reminders?",
                "scope": "morning_brief",
                "priority": 6,
            })
        return suggestions

    def _scheduler_provider(self, now):
        """Feed upcoming scheduled items (isolated from scheduler failures)."""
        try:
            from core.scheduler import scheduler_store  # lazy import
            items = scheduler_store.upcoming(limit=5)
            suggestions = []
            for item in items:
                suggestions.append({
                    "text": f"Upcoming reminder: {item.get('summary') or item.get('text')} "
                            f"at {item.get('when') or item.get('time', '')}",
                    "scope": "scheduler",
                    "priority": 7,
                })
            return suggestions
        except Exception as exc:
            logger.warning("proactive.scheduler", f"scheduler suggestion failed: {exc}")
            self._failures += 1
            return []

    # ------------------------------------------------------------------
    # Suggestion generation
    # ------------------------------------------------------------------
    def suggest(self, max_suggestions=3):
        with self._lock:
            if not self.enabled:
                return []
            quiet = self.quiet_hours_window()
            if quiet:
                return []

            now = self.now_fn()
            now_ts = time.monotonic()
            suggestions = []
            for provider in self._providers:
                try:
                    items = provider(now) or []
                except Exception as exc:
                    logger.error("proactive.provider", f"context provider failed: {exc}")
                    self._failures += 1
                    continue
                for item in items:
                    scope = str(item.get("scope", "default"))
                    if not self._permitted(scope):
                        continue
                    expiry = self._snoozes.get(scope, 0)
                    if expiry > time.monotonic():
                        continue  # snoozed scope stays quiet
                    if scope in self._last_suggestions:
                        continue  # duplicate prevention by scope
                    self._last_suggestions[scope] = str(item.get("text", ""))
                    suggestions.append(item)

            suggestions.sort(key=lambda i: i.get("priority", 0), reverse=True)
            suggestions = suggestions[: max(1, int(max_suggestions))]
            for suggestion in suggestions:
                self._suggestion_count += 1
            self._calls += 1
            return suggestions

    # ------------------------------------------------------------------
    # Snooze / resume
    # ------------------------------------------------------------------
    def snooze(self, scope, seconds=1800):
        with self._lock:
            self._snoozes[str(scope)] = time.monotonic() + float(seconds)
            return True

    def resume(self, scope):
        with self._lock:
            scope = str(scope)
            if scope in self._snoozes:
                del self._snoozes[scope]
            if scope in self._last_suggestions:
                del self._last_suggestions[scope]
            return True

    def status(self):
        with self._lock:
            quiet = self.quiet_hours_window()
            snoozed = {s: round(expiry - time.monotonic(), 1)
                       for s, expiry in self._snoozes.items()
                       if expiry > time.monotonic()}
            return {
                "enabled": self.enabled,
                "message": ("Active." if self.enabled else
                            "Disabled (preference/initiative off)."),
                "quiet_hours_active": bool(quiet),
                "snoozed_scopes": snoozed,
                "calls": self._calls,
                "provider_failures": self._failures,
                "suggestions_offered": self._suggestion_count,
            }

    def stats(self):
        with self._lock:
            return {
                "calls": self._calls,
                "provider_failures": self._failures,
                "suggestions_offered": self._suggestion_count,
                "enabled": self.enabled,
            }


proactive_engine = ProactiveEngine()

__all__ = ["ProactiveEngine", "proactive_engine"]