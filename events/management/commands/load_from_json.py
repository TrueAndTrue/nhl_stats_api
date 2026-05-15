"""
Load NHL play-by-play data from `scripts/ingest_output/` into the redesigned
schema (players_player, games_game, events_event).

    python manage.py load_from_json                  # full load, idempotent
    python manage.py load_from_json --reset          # wipe + reload from scratch
    python manage.py load_from_json --phase events   # only one phase
    python manage.py load_from_json --season 1942    # only one season
    python manage.py load_from_json --update-events  # refresh existing events

Phases run in order: players → games → events. Each is independently
restartable. Events are bulk-inserted with `ignore_conflicts=True` keyed on
`nhl_event_id` so re-runs don't dupe.

Run with `DATABASE_URL` pointed at whichever DB you want — local Docker
postgres for testing, Heroku for the real cutover.
"""
from __future__ import annotations

import json
import time as _time
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterator

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from events.models import Event
from games.models import Game
from players.models import Player

# scripts/ingest_output/  — relative to this file: events/management/commands → up 3
DEFAULT_ROOT = (
    Path(__file__).resolve().parents[3] / "scripts" / "ingest_output"
)

TRACKED_TYPES = {
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

# (primary, secondary, tertiary, goalie) — keys into the play's `details` dict.
# A None means that role doesn't apply for that event type.
PLAYER_ROLES: dict[str, tuple[str | None, ...]] = {
    Event.GOAL: ("scoringPlayerId", "assist1PlayerId", "assist2PlayerId", "goalieInNetId"),
    Event.SHOT_ON_GOAL: ("shootingPlayerId", None, None, "goalieInNetId"),
    Event.HIT: ("hittingPlayerId", "hitteePlayerId", None, None),
    Event.FACEOFF: ("winningPlayerId", "losingPlayerId", None, None),
    Event.GIVEAWAY: ("playerId", None, None, None),
    Event.TAKEAWAY: ("playerId", None, None, None),
    Event.PENALTY: ("committedByPlayerId", "drawnByPlayerId", "servedByPlayerId", None),
    Event.BLOCKED_SHOT: ("blockingPlayerId", "shootingPlayerId", None, None),
    Event.MISSED_SHOT: ("shootingPlayerId", None, None, "goalieInNetId"),
}


# ---- parsers ---------------------------------------------------------------

def _localized(d: dict | None) -> str | None:
    """NHL API often wraps strings as {'default': 'X', 'fr': 'Y', ...} — extract default."""
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.get("default")


def _parse_period_time(s: str | None) -> time | None:
    """'06:08' (mm:ss within a period) → time(0, 6, 8)."""
    if not s or ":" not in s:
        return None
    mm, ss = s.split(":")
    try:
        return time(0, int(mm), int(ss))
    except ValueError:
        return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # NHL gives "1942-11-01T00:30:00Z" — fromisoformat handles in Python 3.11+
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _truthy(v) -> bool:
    """The API uses 0/1 ints for booleans on inHHOF / inTop100AllTime."""
    return bool(v) if v is not None else False


# ---- field extractors ------------------------------------------------------

VALID_POSITIONS = {"C", "L", "R", "D", "G"}


def player_fields_from_payload(p: dict) -> dict | None:
    pid = p.get("playerId")
    if pid is None:
        return None
    first = _localized(p.get("firstName")) or ""
    last = _localized(p.get("lastName")) or ""
    pos = (p.get("position") or "").upper().strip()
    if pos not in VALID_POSITIONS:
        # API has occasionally returned something we don't recognise; skip
        # rather than violate the choices constraint.
        return None
    shoots = p.get("shootsCatches")
    if shoots not in ("L", "R", None, ""):
        shoots = None

    return {
        "nhl_api_id": int(pid),
        "first_name": first[:128],
        "last_name": last[:128],
        "full_name": f"{first} {last}".strip()[:256],
        "is_active": bool(p.get("isActive")),
        "sweater_number": p.get("sweaterNumber"),
        "position": pos,
        "shoots_catches": shoots or None,
        "headshot_url": p.get("headshot") or None,
        "hero_image_url": p.get("heroImage") or None,
        "birth_date": _parse_date(p.get("birthDate")),
        "birth_city": _localized(p.get("birthCity")),
        "birth_state_province": _localized(p.get("birthStateProvince")),
        "birth_country": p.get("birthCountry") or None,
        "height_cm": p.get("heightInCentimeters"),
        "weight_kg": p.get("weightInKilograms"),
        "in_hhof": _truthy(p.get("inHHOF")),
        "in_top_100": _truthy(p.get("inTop100AllTime")),
        "player_slug": p.get("playerSlug") or None,
    }


def game_fields_from_payload(g: dict) -> dict | None:
    gid = g.get("id")
    if gid is None:
        return None
    home = g.get("homeTeam") or {}
    away = g.get("awayTeam") or {}
    return {
        "id": int(gid),
        "season": int(g.get("season")) if g.get("season") is not None else None,
        "game_type": g.get("gameType"),
        "game_date": _parse_date(g.get("gameDate")),
        "start_time_utc": _parse_dt(g.get("startTimeUTC")),
        "home_team": (home.get("abbrev") or "")[:3],
        "away_team": (away.get("abbrev") or "")[:3],
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "venue": _localized(g.get("venue")),
        "game_state": g.get("gameState"),
    }


def _resolve_player(role_key: str | None, details: dict, known_ids: set[int],
                    missing: Counter) -> int | None:
    """
    Return the player's nhl_api_id (which is the FK target) if `role_key` is
    set on `details` AND that player exists in our DB. Else None.
    """
    if role_key is None:
        return None
    pid = details.get(role_key)
    if pid is None:
        return None
    pid = int(pid)
    if pid in known_ids:
        return pid
    missing[pid] += 1
    return None


def event_from_play(play: dict, game_id: int, known_player_ids: set[int],
                    missing_players: Counter) -> Event | None:
    type_desc = play.get("typeDescKey")
    if type_desc not in TRACKED_TYPES:
        return None

    details = play.get("details") or {}
    period_desc = play.get("periodDescriptor") or {}

    pri_key, sec_key, ter_key, goalie_key = PLAYER_ROLES[type_desc]

    nhl_event_id = f"{game_id}-{play.get('eventId')}"

    return Event(
        nhl_event_id=nhl_event_id,
        game_id=game_id,
        type_desc=type_desc,
        type_code=play.get("typeCode"),
        period=period_desc.get("number"),
        period_time=_parse_period_time(play.get("timeInPeriod")),
        period_type=period_desc.get("periodType"),
        coord_x=details.get("xCoord"),
        coord_y=details.get("yCoord"),
        zone_code=details.get("zoneCode"),
        situation_code=play.get("situationCode"),
        primary_player_id=_resolve_player(pri_key, details, known_player_ids, missing_players),
        secondary_player_id=_resolve_player(sec_key, details, known_player_ids, missing_players),
        tertiary_player_id=_resolve_player(ter_key, details, known_player_ids, missing_players),
        goalie_id=_resolve_player(goalie_key, details, known_player_ids, missing_players),
        shot_type=details.get("shotType"),
        penalty_type=details.get("descKey") if type_desc == Event.PENALTY else None,
        penalty_minutes=details.get("duration") if type_desc == Event.PENALTY else None,
        miss_reason=details.get("reason") if type_desc == Event.MISSED_SHOT else None,
        home_score=details.get("homeScore"),
        away_score=details.get("awayScore"),
    )


# ---- the command itself ----------------------------------------------------

class Command(BaseCommand):
    help = "Load ingest_output/ JSON into the redesigned schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--phase",
            choices=["players", "games", "events", "all"],
            default="all",
        )
        parser.add_argument(
            "--season", type=int, default=None,
            help="Only load games/events for this season (start year, e.g. 1942).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="TRUNCATE all 3 tables before loading.",
        )
        parser.add_argument(
            "--update-events", action="store_true",
            help="Update existing event rows on conflict (default: skip).",
        )
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)

    # -- phase 1 -----------------------------------------------------------

    PLAYER_UPDATE_FIELDS = [
        "first_name", "last_name", "full_name", "is_active", "sweater_number",
        "position", "shoots_catches", "headshot_url", "hero_image_url",
        "birth_date", "birth_city", "birth_state_province", "birth_country",
        "height_cm", "weight_kg", "in_hhof", "in_top_100", "player_slug",
    ]

    def load_players(self, root: Path, batch_size: int = 1000):
        players_dir = root / "players"
        if not players_dir.exists():
            self.stdout.write(self.style.WARNING(f"  no players dir at {players_dir}"))
            return 0, 0
        loaded = skipped = 0
        files = sorted(players_dir.glob("*.json"))
        self.stdout.write(f"  {len(files)} player JSONs to process")
        t0 = _time.monotonic()
        batch: list[Player] = []

        def flush():
            nonlocal loaded
            if not batch:
                return
            Player.objects.bulk_create(
                batch, batch_size=batch_size,
                update_conflicts=True,
                unique_fields=["nhl_api_id"],
                update_fields=self.PLAYER_UPDATE_FIELDS,
            )
            loaded += len(batch)
            batch.clear()

        for i, f in enumerate(files, 1):
            try:
                payload = json.loads(f.read_text())
            except json.JSONDecodeError:
                skipped += 1
                continue
            fields = player_fields_from_payload(payload)
            if not fields:
                skipped += 1
                continue
            batch.append(Player(**fields))
            if len(batch) >= batch_size:
                flush()
                rate = i / (_time.monotonic() - t0)
                self.stdout.write(f"    …{i}/{len(files)} · {rate:.0f}/s")
        flush()
        return loaded, skipped

    # -- phase 2 -----------------------------------------------------------

    def _game_files(self, root: Path, season: int | None) -> list[Path]:
        games_dir = root / "games"
        if not games_dir.exists():
            return []
        if season is None:
            return sorted(games_dir.glob("*.json"))
        # NHL game_id starts with the season's start year (e.g. 1942020001 → 1942)
        prefix = str(season)
        return sorted(p for p in games_dir.glob("*.json") if p.stem.startswith(prefix))

    GAME_UPDATE_FIELDS = [
        "season", "game_type", "game_date", "start_time_utc",
        "home_team", "away_team", "home_score", "away_score",
        "venue", "game_state",
    ]

    def load_games(self, root: Path, season: int | None, batch_size: int = 2000):
        files = self._game_files(root, season)
        self.stdout.write(f"  {len(files)} game JSONs to process")
        loaded = skipped = 0
        t0 = _time.monotonic()
        batch: list[Game] = []

        def flush():
            nonlocal loaded
            if not batch:
                return
            Game.objects.bulk_create(
                batch, batch_size=batch_size,
                update_conflicts=True,
                unique_fields=["id"],
                update_fields=self.GAME_UPDATE_FIELDS,
            )
            loaded += len(batch)
            batch.clear()

        for i, f in enumerate(files, 1):
            try:
                payload = json.loads(f.read_text())
            except json.JSONDecodeError:
                skipped += 1
                continue
            fields = game_fields_from_payload(payload)
            if not fields or fields.get("game_date") is None:
                skipped += 1
                continue
            batch.append(Game(**fields))
            if len(batch) >= batch_size:
                flush()
                rate = i / (_time.monotonic() - t0)
                self.stdout.write(f"    …{i}/{len(files)} · {rate:.0f}/s")
        flush()
        return loaded, skipped

    # -- phase 3 -----------------------------------------------------------

    def load_events(self, root: Path, season: int | None,
                    batch_size: int, update_events: bool):
        # Pre-load all known player & game IDs (both PKs are ints, so cheap)
        known_player_ids = set(Player.objects.values_list("nhl_api_id", flat=True))
        known_game_ids = set(Game.objects.values_list("id", flat=True))
        self.stdout.write(
            f"  pre-loaded {len(known_player_ids):,} player IDs · "
            f"{len(known_game_ids):,} game IDs"
        )

        files = self._game_files(root, season)
        self.stdout.write(f"  {len(files)} game JSONs to walk")

        type_counts: Counter[str] = Counter()
        missing_players: Counter[int] = Counter()
        skipped_no_game = 0
        events_inserted = 0
        batch: list[Event] = []
        t0 = _time.monotonic()

        update_kwargs: dict = {"ignore_conflicts": True}
        if update_events:
            update_kwargs = {
                "update_conflicts": True,
                "unique_fields": ["nhl_event_id"],
                "update_fields": [
                    "type_desc", "type_code", "period", "period_time",
                    "period_type", "coord_x", "coord_y", "zone_code",
                    "situation_code", "primary_player_id", "secondary_player_id",
                    "tertiary_player_id", "goalie_id", "shot_type",
                    "penalty_type", "penalty_minutes", "miss_reason",
                    "home_score", "away_score",
                ],
            }

        def flush():
            nonlocal events_inserted
            if not batch:
                return
            Event.objects.bulk_create(batch, batch_size=batch_size, **update_kwargs)
            events_inserted += len(batch)
            batch.clear()

        for i, f in enumerate(files, 1):
            try:
                payload = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            game_id = payload.get("id")
            if game_id is None or game_id not in known_game_ids:
                skipped_no_game += 1
                continue
            for play in payload.get("plays", []):
                ev = event_from_play(play, game_id, known_player_ids, missing_players)
                if ev is None:
                    type_counts["skipped:" + (play.get("typeDescKey") or "?")] += 1
                    continue
                type_counts[ev.type_desc] += 1
                batch.append(ev)
                if len(batch) >= batch_size:
                    flush()
            if i % 1000 == 0:
                rate = events_inserted / (_time.monotonic() - t0)
                self.stdout.write(
                    f"    …{i}/{len(files)} games · "
                    f"{events_inserted:,} events written · {rate:.0f}/s"
                )
        flush()

        return {
            "events_written": events_inserted,
            "type_breakdown": dict(type_counts),
            "missing_player_refs": sum(missing_players.values()),
            "missing_player_ids_unique": len(missing_players),
            "missing_player_top10": missing_players.most_common(10),
            "skipped_games_not_in_db": skipped_no_game,
        }

    # -- driver ------------------------------------------------------------

    def reset_tables(self):
        with connection.cursor() as c:
            c.execute(
                "TRUNCATE TABLE events_event, players_player, games_game "
                "RESTART IDENTITY CASCADE"
            )
        self.stdout.write(self.style.WARNING(
            "  TRUNCATE'd events_event, players_player, games_game"))

    def handle(self, *args, **opts):
        root: Path = opts["root"]
        if not root.exists():
            raise CommandError(f"ingest_output not found at {root}")

        if opts["reset"]:
            self.stdout.write(self.style.WARNING("\n=== RESET ===\n"))
            self.reset_tables()

        phase = opts["phase"]
        season = opts["season"]
        t_total = _time.monotonic()

        if phase in ("all", "players"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Phase 1: Players ==="))
            loaded, skipped = self.load_players(root)
            self.stdout.write(self.style.SUCCESS(
                f"  loaded={loaded:,} skipped={skipped:,}"))

        if phase in ("all", "games"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Phase 2: Games ==="))
            loaded, skipped = self.load_games(root, season)
            self.stdout.write(self.style.SUCCESS(
                f"  loaded={loaded:,} skipped={skipped:,}"))

        if phase in ("all", "events"):
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Phase 3: Events ==="))
            stats = self.load_events(
                root, season, opts["batch_size"], opts["update_events"]
            )
            self.stdout.write(self.style.SUCCESS(
                f"  events_written={stats['events_written']:,} · "
                f"missing_player_refs={stats['missing_player_refs']:,} "
                f"({stats['missing_player_ids_unique']:,} unique) · "
                f"games_not_in_db_skipped={stats['skipped_games_not_in_db']}"
            ))
            if stats["missing_player_top10"]:
                self.stdout.write("  top 10 unknown player IDs (likely refs/officials):")
                for pid, n in stats["missing_player_top10"]:
                    self.stdout.write(f"    {pid}: {n} refs")
            self.stdout.write("  type breakdown:")
            for t, n in sorted(stats["type_breakdown"].items()):
                self.stdout.write(f"    {t}: {n:,}")

        elapsed = _time.monotonic() - t_total
        self.stdout.write(self.style.SUCCESS(
            f"\nTotal elapsed: {elapsed/60:.1f} min"))
