"""Daily ingest orchestration — fetches the gap between DB and yesterday."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Max

from games.models import Game

from . import client, upsert

log = logging.getLogger(__name__)

# Game states that mean "completed, has play-by-play".
_COMPLETED_STATES = {"OFF", "FINAL", "OVER"}


@dataclass
class IngestReport:
    days_fetched: int = 0
    games_fetched: int = 0
    games_skipped_incomplete: int = 0
    games_failed: list[int] = field(default_factory=list)
    events_inserted: int = 0
    new_players: int = 0
    missing_player_skips: int = 0


def run_daily_ingest(through: date | None = None, max_days: int | None = None) -> IngestReport:
    """Catch up the DB from its latest completed game date through yesterday.

    Args:
        through: end date (exclusive of today by default).
        max_days: safety cap on how many days to fetch in one run. None = no cap.
    """
    today = date.today()
    end = through or (today - timedelta(days=1))

    latest = Game.objects.filter(game_state__in=_COMPLETED_STATES).aggregate(d=Max("game_date"))["d"]
    if latest is None:
        # cold DB — bail out instead of trying to ingest all of NHL history
        raise RuntimeError(
            "No completed games found in DB. Daily ingest is for incremental catch-up; "
            "do an initial backfill first."
        )

    start = latest + timedelta(days=1)
    if start > end:
        log.info("DB already current through %s — nothing to fetch", latest)
        return IngestReport()

    if max_days is not None:
        gap = (end - start).days + 1
        if gap > max_days:
            raise RuntimeError(
                f"Gap of {gap} days exceeds max_days={max_days}. "
                f"Latest game: {latest}. Run with --no-cap or do a manual backfill."
            )

    log.info("ingesting %s through %s", start, end)
    report = IngestReport()

    # Schedule endpoint returns 7 days per call — walk in week-sized strides
    cursor = start
    seen_game_ids: set[int] = set()
    while cursor <= end:
        week = client.fetch_week_schedule(cursor.isoformat())
        for day in week.get("gameWeek") or []:
            day_date_str = day.get("date")
            if not day_date_str:
                continue
            day_date = date.fromisoformat(day_date_str)
            if day_date < start or day_date > end:
                continue
            report.days_fetched += 1
            for g in day.get("games") or []:
                gid = g["id"]
                if gid in seen_game_ids:
                    continue
                seen_game_ids.add(gid)

                state = g.get("gameState")
                if state not in _COMPLETED_STATES:
                    report.games_skipped_incomplete += 1
                    continue

                # Upsert the Game row first so the FK target exists for events
                upsert.upsert_game_from_schedule(g, day_date)
                try:
                    _ingest_game_pbp(gid, report)
                except Exception:
                    log.exception("failed ingesting game %s", gid)
                    report.games_failed.append(gid)
        # advance — use the API's nextStartDate to avoid mis-stepping
        next_start = week.get("nextStartDate")
        if next_start:
            cursor = date.fromisoformat(next_start)
        else:
            cursor += timedelta(days=7)

    return report


def _ingest_game_pbp(game_id: int, report: IngestReport) -> None:
    pbp = client.fetch_play_by_play(game_id)
    if not pbp:
        log.warning("no PBP for %s", game_id)
        return

    # First-pass: fetch full bios for any player IDs the PBP references that
    # we've never seen before AND that aren't in rosterSpots (rare — usually
    # historical penalty server-of-record etc.)
    for pid in upsert.collect_unknown_player_ids(pbp):
        bio = client.fetch_player_landing(pid)
        if bio:
            upsert.upsert_player_from_landing(bio)
            report.new_players += 1

    # rosterSpots inserts (handled inside upsert_pbp) cover the common case
    inserted, skipped = upsert.upsert_pbp(game_id, pbp)
    report.events_inserted += inserted
    report.missing_player_skips += skipped
    report.games_fetched += 1
