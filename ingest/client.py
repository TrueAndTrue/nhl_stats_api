"""Thin client for the NHL public API at api-web.nhle.com/v1/.

Only the three endpoints the daily ingest needs: weekly schedule, game
play-by-play, player landing (bio). Rate-limited at ~8 req/sec because that's
what the league tolerates sustained — see CLAUDE.md gotcha #3.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE = "https://api-web.nhle.com/v1"

# 8 req/sec sustained ceiling — anything higher gets 429s
_MIN_INTERVAL_S = 1.0 / 8.0
_lock = threading.Lock()
_last_call = 0.0


def _throttled_get(url: str, retries: int = 3) -> requests.Response:
    global _last_call
    for attempt in range(retries + 1):
        with _lock:
            wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
        r = requests.get(url, timeout=30)
        if r.status_code == 429:
            backoff = float(r.headers.get("Retry-After", 2 ** attempt))
            log.warning("429 from %s; sleeping %.1fs", url, backoff)
            time.sleep(backoff)
            continue
        if r.status_code == 404:
            return r  # caller handles
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def fetch_week_schedule(date_str: str) -> dict[str, Any]:
    """Returns a week of schedule starting from `date_str` (YYYY-MM-DD).

    Response shape: {gameWeek: [{date, games: [...]}], nextStartDate, previousStartDate}.
    """
    r = _throttled_get(f"{BASE}/schedule/{date_str}")
    return r.json()


def fetch_play_by_play(game_id: int) -> dict[str, Any] | None:
    """Full PBP including rosterSpots. Returns None if the API 404s
    (happens for cancelled / preseason / never-played games)."""
    r = _throttled_get(f"{BASE}/gamecenter/{game_id}/play-by-play")
    if r.status_code == 404:
        return None
    return r.json()


def fetch_player_landing(player_id: int) -> dict[str, Any] | None:
    r = _throttled_get(f"{BASE}/player/{player_id}/landing")
    if r.status_code == 404:
        return None
    return r.json()
