"""Upsert helpers — translate NHL API payloads into our DB rows.

Mapping rules for events are documented on Event.__doc__; this module is the
inverse direction (NHL JSON → ORM dict). The three upsert functions are
idempotent: re-running the same day is safe and cheap.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime
from typing import Any, Iterable

from django.db import transaction

from events.models import Event
from games.models import Game
from players.models import Player

log = logging.getLogger(__name__)


# ── Event type mapping ───────────────────────────────────────────────────────

# typeDescKey values we ingest. Everything else (stoppage, period-start,
# period-end, delayed-penalty, game-end) is skipped — they're flow markers,
# not stats events.
_EVENT_TYPES = {
    Event.GOAL,
    Event.SHOT_ON_GOAL,
    Event.HIT,
    Event.FACEOFF,
    Event.GIVEAWAY,
    Event.TAKEAWAY,
    Event.PENALTY,
    Event.BLOCKED_SHOT,
    Event.MISSED_SHOT,
}


def _role_player_ids(type_desc: str, details: dict[str, Any]) -> dict[str, int | None]:
    """Returns {primary, secondary, tertiary, goalie} per the role table in
    Event.__doc__. Missing roles come back as None."""
    d = details or {}
    if type_desc == Event.GOAL:
        return {
            "primary": d.get("scoringPlayerId"),
            "secondary": d.get("assist1PlayerId"),
            "tertiary": d.get("assist2PlayerId"),
            "goalie": d.get("goalieInNetId"),
        }
    if type_desc == Event.SHOT_ON_GOAL:
        return {"primary": d.get("shootingPlayerId"), "secondary": None, "tertiary": None, "goalie": d.get("goalieInNetId")}
    if type_desc == Event.HIT:
        return {"primary": d.get("hittingPlayerId"), "secondary": d.get("hitteePlayerId"), "tertiary": None, "goalie": None}
    if type_desc == Event.FACEOFF:
        return {"primary": d.get("winningPlayerId"), "secondary": d.get("losingPlayerId"), "tertiary": None, "goalie": None}
    if type_desc == Event.GIVEAWAY:
        return {"primary": d.get("playerId"), "secondary": None, "tertiary": None, "goalie": None}
    if type_desc == Event.TAKEAWAY:
        return {"primary": d.get("playerId"), "secondary": None, "tertiary": None, "goalie": None}
    if type_desc == Event.PENALTY:
        return {
            "primary": d.get("committedByPlayerId"),
            "secondary": d.get("drawnByPlayerId"),
            "tertiary": d.get("servedByPlayerId"),
            "goalie": None,
        }
    if type_desc == Event.BLOCKED_SHOT:
        return {"primary": d.get("blockingPlayerId"), "secondary": d.get("shootingPlayerId"), "tertiary": None, "goalie": None}
    if type_desc == Event.MISSED_SHOT:
        return {"primary": d.get("shootingPlayerId"), "secondary": None, "tertiary": None, "goalie": d.get("goalieInNetId")}
    return {"primary": None, "secondary": None, "tertiary": None, "goalie": None}


def _parse_period_time(s: str | None) -> dtime | None:
    """'02:04' (MM:SS) → time(0, 2, 4)."""
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        m, sec = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return dtime(hour=0, minute=m, second=sec)


# ── Players ──────────────────────────────────────────────────────────────────


def upsert_player_from_landing(payload: dict[str, Any]) -> Player | None:
    """Full bio. Used for new players seen in PBP."""
    pid = payload.get("playerId")
    if not pid:
        return None
    first = (payload.get("firstName") or {}).get("default", "")
    last = (payload.get("lastName") or {}).get("default", "")
    pos = payload.get("position") or ""
    birth_city = (payload.get("birthCity") or {}).get("default")
    birth_state = (payload.get("birthStateProvince") or {}).get("default")

    headshot = payload.get("headshot")
    hero = payload.get("heroImage")
    bday = payload.get("birthDate")

    defaults = {
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}".strip(),
        "player_slug": _slug(first, last, pid),
        "is_active": bool(payload.get("isActive")),
        "sweater_number": payload.get("sweaterNumber"),
        "position": pos,
        "shoots_catches": payload.get("shootsCatches") or None,
        "headshot_url": headshot,
        "hero_image_url": hero,
        "birth_date": date.fromisoformat(bday) if bday else None,
        "birth_city": birth_city,
        "birth_state_province": birth_state,
        "birth_country": payload.get("birthCountry"),
        "height_cm": payload.get("heightInCentimeters"),
        "weight_kg": payload.get("weightInKilograms"),
        "in_hhof": bool(payload.get("inHHOF")),
        "in_top_100": bool(payload.get("inTop100AllTime")),
    }
    obj, _ = Player.objects.update_or_create(nhl_api_id=pid, defaults=defaults)
    return obj


def upsert_player_minimal(roster_spot: dict[str, Any]) -> Player | None:
    """Lightweight upsert from a PBP rosterSpots entry. Only inserts if the
    player doesn't exist yet — never overwrites richer bio data we already have."""
    pid = roster_spot.get("playerId")
    if not pid:
        return None
    first = (roster_spot.get("firstName") or {}).get("default", "")
    last = (roster_spot.get("lastName") or {}).get("default", "")
    pos = roster_spot.get("positionCode") or ""
    obj, created = Player.objects.get_or_create(
        nhl_api_id=pid,
        defaults={
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}".strip(),
            "player_slug": _slug(first, last, pid),
            "sweater_number": roster_spot.get("sweaterNumber"),
            "position": pos,
            "headshot_url": roster_spot.get("headshot"),
        },
    )
    return obj


def _slug(first: str, last: str, pid: int) -> str:
    base = f"{first}-{last}-{pid}".lower()
    return "".join(c if (c.isalnum() or c == "-") else "-" for c in base)


# ── Games ────────────────────────────────────────────────────────────────────


def upsert_game_from_schedule(g: dict[str, Any], day_date: date) -> Game:
    """Upsert from a schedule.gameWeek[].games[] entry."""
    start = g.get("startTimeUTC")
    return Game.objects.update_or_create(
        id=g["id"],
        defaults={
            "season": g["season"],
            "game_type": g["gameType"],
            "game_date": day_date,
            "start_time_utc": datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None,
            "home_team": g["homeTeam"]["abbrev"],
            "away_team": g["awayTeam"]["abbrev"],
            "home_score": g["homeTeam"].get("score"),
            "away_score": g["awayTeam"].get("score"),
            "venue": (g.get("venue") or {}).get("default"),
            "game_state": g.get("gameState"),
        },
    )[0]


# ── Events ───────────────────────────────────────────────────────────────────


@transaction.atomic
def upsert_pbp(game_id: int, pbp: dict[str, Any]) -> tuple[int, int]:
    """Upsert all stat-bearing events for a single game.

    Strategy: idempotent replace-per-game. We delete the game's existing
    events and re-insert from the current PBP payload. This is safe because
    nhl_event_id is globally unique and PBP is the source of truth — when the
    NHL revises a game, the only thing we can do is mirror it.

    Returns (events_inserted, players_skipped_missing).
    """
    # roster spots → ensure players exist (lightweight insert)
    for rs in pbp.get("rosterSpots") or []:
        upsert_player_minimal(rs)

    plays = pbp.get("plays") or []
    rows: list[Event] = []
    missing_player_skips = 0

    for p in plays:
        td = p.get("typeDescKey")
        if td not in _EVENT_TYPES:
            continue
        details = p.get("details") or {}
        roles = _role_player_ids(td, details)

        # If the primary player ID is unknown to us (no roster spot, no prior
        # data) skip rather than fail the whole game. Counts as a soft miss.
        if roles["primary"] and not Player.objects.filter(nhl_api_id=roles["primary"]).exists():
            missing_player_skips += 1
            continue

        period_desc = p.get("periodDescriptor") or {}
        rows.append(
            Event(
                nhl_event_id=f"{game_id}-{p['eventId']}",
                game_id=game_id,
                type_desc=td,
                type_code=p.get("typeCode"),
                period=period_desc.get("number"),
                period_time=_parse_period_time(p.get("timeInPeriod")),
                period_type=period_desc.get("periodType"),
                coord_x=details.get("xCoord"),
                coord_y=details.get("yCoord"),
                zone_code=details.get("zoneCode"),
                situation_code=p.get("situationCode"),
                primary_player_id=roles["primary"],
                secondary_player_id=roles["secondary"],
                tertiary_player_id=roles["tertiary"],
                goalie_id=roles["goalie"],
                shot_type=details.get("shotType"),
                penalty_type=details.get("descKey") if td == Event.PENALTY else None,
                penalty_minutes=details.get("duration") if td == Event.PENALTY else None,
                miss_reason=details.get("reason") if td == Event.MISSED_SHOT else None,
                home_score=details.get("homeScore"),
                away_score=details.get("awayScore"),
            )
        )

    Event.objects.filter(game_id=game_id).delete()
    Event.objects.bulk_create(rows, batch_size=500)
    return len(rows), missing_player_skips


def collect_unknown_player_ids(pbp: dict[str, Any]) -> set[int]:
    """Player IDs referenced by PBP that aren't in players_player or rosterSpots.
    The caller should fetch /player/<id>/landing for each before upserting events."""
    in_roster = {rs["playerId"] for rs in pbp.get("rosterSpots") or [] if rs.get("playerId")}
    referenced: set[int] = set()
    for p in pbp.get("plays") or []:
        td = p.get("typeDescKey")
        if td not in _EVENT_TYPES:
            continue
        for pid in _role_player_ids(td, p.get("details") or {}).values():
            if pid:
                referenced.add(pid)
    missing = referenced - in_roster
    if not missing:
        return set()
    existing = set(
        Player.objects.filter(nhl_api_id__in=missing).values_list("nhl_api_id", flat=True)
    )
    return missing - existing
