"""Time each section of the /api/landing/ view against the live DB.

Runs each block twice — first call is "cold" (no connection warmup, no buffers),
second is "warm". Reports both. Use:

    source venv/bin/activate
    export DATABASE_URL=...  DJANGO_DEBUG=1
    python3 scripts/bench_landing.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection, reset_queries  # noqa: E402
from django.db.models import Count, Max, Q  # noqa: E402

from events.models import Event  # noqa: E402
from games.models import Game  # noqa: E402
from players.models import Player  # noqa: E402


def _time(label: str, fn, runs: int = 2) -> None:
    times = []
    for _ in range(runs):
        reset_queries()
        t0 = time.perf_counter()
        result = fn()
        dt = (time.perf_counter() - t0) * 1000
        nq = len(connection.queries) if connection.queries else 0
        times.append((dt, nq))
        # consume any querysets
        if hasattr(result, "__iter__") and not isinstance(result, (dict, str)):
            list(result)
    cold_dt, cold_q = times[0]
    warm_dt, warm_q = times[-1]
    print(f"  {label:<50} cold={cold_dt:>7.1f}ms ({cold_q} queries)  warm={warm_dt:>7.1f}ms ({warm_q} queries)")


def section(name: str) -> None:
    print(f"\n── {name} ─────────────────────────────────────")


# ────────── original implementation (copied from views.py) ──────────


def original_counts():
    total_events = Event.objects.count()
    total_games = Game.objects.count()
    total_players = Player.objects.count()
    shots_with_coords = Event.objects.filter(
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL, Event.MISSED_SHOT, Event.BLOCKED_SHOT],
        coord_x__isnull=False,
    ).count()
    total_seasons = Game.objects.values("season").distinct().count()
    hhof = Player.objects.filter(in_hhof=True).count()
    active = Player.objects.filter(is_active=True).count()
    return (total_events, total_games, total_players, shots_with_coords, total_seasons, hhof, active)


def original_era_buckets():
    era_bounds = [
        ("1917-29", 19171918, 19291930),
        ("1930-49", 19301931, 19491950),
        ("1950-69", 19501951, 19691970),
        ("1970-89", 19701971, 19891990),
        ("1990-99", 19901991, 19991999),
        ("2000-09", 20001999, 20091999),
        ("2010-19", 20101999, 20191999),
        ("2020-26", 20201999, 20991999),
    ]
    buckets = []
    for label, lo, hi in era_bounds:
        events = Event.objects.filter(game__season__gte=lo, game__season__lte=hi).count()
        games = Game.objects.filter(season__gte=lo, season__lte=hi).count()
        buckets.append({"era": label, "events": events, "games": games})
    return buckets


def original_tonight():
    today = date.today()
    qs = Game.objects.filter(game_date=today).order_by("start_time_utc")
    if not qs.exists():
        last = (
            Game.objects.filter(game_date__lte=today, game_state__in=["OFF", "FINAL", "OVER"])
            .order_by("-game_date")
            .values_list("game_date", flat=True)
            .first()
        )
        if last:
            qs = Game.objects.filter(game_date=last).order_by("start_time_utc")
    return list(qs[:8])


def original_leaders():
    current_season = Game.objects.aggregate(s=Max("season"))["s"] or 0
    leaders_qs = (
        Event.objects.filter(type_desc=Event.GOAL, game__season=current_season)
        .values(
            "primary_player",
            "primary_player__first_name",
            "primary_player__last_name",
            "primary_player__sweater_number",
        )
        .annotate(goals=Count("id"))
        .order_by("-goals")[:10]
    )
    leaders = []
    for row in leaders_qs:
        pid = row["primary_player"]
        if not pid:
            continue
        last_goal = (
            Event.objects.filter(primary_player_id=pid, type_desc=Event.GOAL, game__season=current_season)
            .select_related("game")
            .order_by("-game__game_date", "-period", "-period_time")
            .first()
        )
        team = "—"
        if last_goal and last_goal.game_id:
            g = last_goal.game
            prev = (
                Event.objects.filter(game=g)
                .filter(
                    Q(period__lt=last_goal.period)
                    | Q(period=last_goal.period, period_time__lt=last_goal.period_time)
                )
                .order_by("-period", "-period_time")
                .values("home_score", "away_score")
                .first()
            )
            prev_h = (prev or {}).get("home_score") or 0
            prev_a = (prev or {}).get("away_score") or 0
            if last_goal.home_score is not None and last_goal.home_score > prev_h:
                team = g.home_team
            elif last_goal.away_score is not None and last_goal.away_score > prev_a:
                team = g.away_team
            else:
                team = g.home_team
        leaders.append({"id": pid, "goals": row["goals"], "team": team})
    return leaders


def original_ledger():
    def _top1(qs):
        return (
            qs.values("primary_player", "primary_player__first_name", "primary_player__last_name")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )

    return [
        _top1(Event.objects.filter(type_desc=Event.GOAL)),
        _top1(Event.objects.filter(type_desc=Event.FACEOFF)),
        _top1(Event.objects.filter(type_desc=Event.HIT)),
        _top1(Event.objects.filter(type_desc=Event.BLOCKED_SHOT)),
    ]


# ────────── optimized variants ──────────


def opt_counts_parallel():
    """Run the 7 counts concurrently from a thread pool."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    def run(fn):
        try:
            return fn()
        finally:
            connections.close_all()

    funcs = [
        lambda: Event.objects.count(),
        lambda: Game.objects.count(),
        lambda: Player.objects.count(),
        lambda: Event.objects.filter(
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL, Event.MISSED_SHOT, Event.BLOCKED_SHOT],
            coord_x__isnull=False,
        ).count(),
        lambda: Game.objects.values("season").distinct().count(),
        lambda: Player.objects.filter(in_hhof=True).count(),
        lambda: Player.objects.filter(is_active=True).count(),
    ]
    with ThreadPoolExecutor(max_workers=len(funcs)) as ex:
        return list(ex.map(lambda f: run(f), funcs))


def opt_counts_pg_class():
    """Use pg_class.reltuples (planner estimate) for the giant tables.

    These approximations are *exact* for static tables right after VACUUM/ANALYZE,
    and within ~1% otherwise. For event/game counts that are stable between
    nightly ingests, this is fine.
    """
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT relname, reltuples::bigint
            FROM pg_class
            WHERE relname IN ('events_event', 'games_game', 'players_player')
            """
        )
        approx = dict(cur.fetchall())
    # exact counts only for cheap queries
    shots_with_coords = Event.objects.filter(
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL, Event.MISSED_SHOT, Event.BLOCKED_SHOT],
        coord_x__isnull=False,
    ).count()
    seasons = Game.objects.values("season").distinct().count()
    hhof = Player.objects.filter(in_hhof=True).count()
    active = Player.objects.filter(is_active=True).count()
    return (
        approx.get("events_event", 0),
        approx.get("games_game", 0),
        approx.get("players_player", 0),
        shots_with_coords,
        seasons,
        hhof,
        active,
    )


def opt_era_buckets_one_query():
    """Single CASE-based GROUP BY for events; single one for games."""
    from django.db import connection
    from django.db.models import Case, IntegerField, Value, When

    era_bounds = [
        ("1917-29", 19171918, 19291930),
        ("1930-49", 19301931, 19491950),
        ("1950-69", 19501951, 19691970),
        ("1970-89", 19701971, 19891990),
        ("1990-99", 19901991, 19991999),
        ("2000-09", 20001999, 20091999),
        ("2010-19", 20101999, 20191999),
        ("2020-26", 20201999, 20991999),
    ]

    # Build a single SQL: events grouped by era label via game JOIN
    case_sql = "CASE\n" + "\n".join(
        f"  WHEN g.season BETWEEN {lo} AND {hi} THEN '{label}'" for label, lo, hi in era_bounds
    ) + "\nEND"

    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT era, COUNT(*) AS n
            FROM events_event e
            JOIN games_game g ON g.id = e.game_id
            WHERE g.season BETWEEN 19171918 AND 20991999
            GROUP BY 1
            """.replace("era", case_sql + " AS era") if False else f"""
            SELECT {case_sql} AS era, COUNT(*) AS n
            FROM events_event e
            JOIN games_game g ON g.id = e.game_id
            GROUP BY 1
            """
        )
        events_by_era = dict(cur.fetchall())

        cur.execute(
            f"""
            SELECT {case_sql.replace('g.season', 'season')} AS era, COUNT(*) AS n
            FROM games_game g
            GROUP BY 1
            """
        )
        games_by_era = dict(cur.fetchall())

    return [
        {"era": label, "events": events_by_era.get(label, 0), "games": games_by_era.get(label, 0)}
        for label, _, _ in era_bounds
    ]


def opt_ledger_parallel():
    """Fan out the 4 ledger top-1 queries to threads."""
    from concurrent.futures import ThreadPoolExecutor
    from django.db import connections

    def top1(type_desc):
        try:
            return (
                Event.objects.filter(type_desc=type_desc)
                .values("primary_player", "primary_player__first_name", "primary_player__last_name")
                .annotate(n=Count("id"))
                .order_by("-n")
                .first()
            )
        finally:
            connections.close_all()

    types = [Event.GOAL, Event.FACEOFF, Event.HIT, Event.BLOCKED_SHOT]
    with ThreadPoolExecutor(max_workers=len(types)) as ex:
        return list(ex.map(top1, types))


def opt_leaders_window():
    """Compute leaders + team in a single SQL using window functions.

    Strategy: rank goals per player in current season, then for each top-10 player
    take the most recent goal and infer team from score delta in a single CTE.
    """
    from django.db import connection

    current_season = Game.objects.aggregate(s=Max("season"))["s"] or 0

    with connection.cursor() as cur:
        cur.execute(
            """
            WITH season_goals AS (
                SELECT e.primary_player_id, e.game_id, e.period, e.period_time,
                       e.home_score, e.away_score
                FROM events_event e
                JOIN games_game g ON g.id = e.game_id
                WHERE e.type_desc = 'goal'
                  AND g.season = %s
                  AND e.primary_player_id IS NOT NULL
            ),
            goal_counts AS (
                SELECT primary_player_id, COUNT(*) AS goals
                FROM season_goals
                GROUP BY primary_player_id
                ORDER BY goals DESC
                LIMIT 10
            ),
            ranked AS (
                SELECT sg.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY sg.primary_player_id
                           ORDER BY sg.game_id DESC, sg.period DESC, sg.period_time DESC
                       ) AS rn
                FROM season_goals sg
                JOIN goal_counts gc ON gc.primary_player_id = sg.primary_player_id
            ),
            last_goal AS (
                SELECT * FROM ranked WHERE rn = 1
            ),
            with_prev AS (
                SELECT lg.primary_player_id, lg.game_id, lg.home_score, lg.away_score,
                       (SELECT home_score FROM events_event e2
                        WHERE e2.game_id = lg.game_id
                          AND (e2.period < lg.period
                               OR (e2.period = lg.period AND e2.period_time < lg.period_time))
                        ORDER BY e2.period DESC, e2.period_time DESC LIMIT 1) AS prev_home,
                       (SELECT away_score FROM events_event e2
                        WHERE e2.game_id = lg.game_id
                          AND (e2.period < lg.period
                               OR (e2.period = lg.period AND e2.period_time < lg.period_time))
                        ORDER BY e2.period DESC, e2.period_time DESC LIMIT 1) AS prev_away
                FROM last_goal lg
            )
            SELECT gc.primary_player_id, gc.goals,
                   p.first_name, p.last_name,
                   g.home_team, g.away_team,
                   wp.home_score, wp.away_score,
                   COALESCE(wp.prev_home, 0) AS prev_home,
                   COALESCE(wp.prev_away, 0) AS prev_away
            FROM goal_counts gc
            JOIN with_prev wp ON wp.primary_player_id = gc.primary_player_id
            JOIN players_player p ON p.nhl_api_id = gc.primary_player_id
            JOIN games_game g ON g.id = wp.game_id
            ORDER BY gc.goals DESC;
            """,
            [current_season],
        )
        rows = cur.fetchall()

    leaders = []
    for pid, goals, fn, ln, home_team, away_team, h_score, a_score, prev_h, prev_a in rows:
        if h_score is not None and h_score > prev_h:
            team = home_team
        elif a_score is not None and a_score > prev_a:
            team = away_team
        else:
            team = home_team
        leaders.append({"id": pid, "first_name": fn, "last_name": ln, "team": team, "goals": goals})
    return leaders


def opt_all_parallel():
    """Fan out the five top-level blocks (counts, era, tonight, leaders, ledger) concurrently."""
    from concurrent.futures import ThreadPoolExecutor
    from django.db import connections

    def wrap(fn):
        try:
            return fn()
        finally:
            connections.close_all()

    funcs = [
        opt_counts_pg_class,
        opt_era_buckets_one_query,
        original_tonight,
        opt_leaders_window,
        opt_ledger_parallel,
    ]
    with ThreadPoolExecutor(max_workers=len(funcs)) as ex:
        return list(ex.map(wrap, funcs))


def main() -> None:
    print(f"DB: {connection.settings_dict.get('HOST')}")
    print("(cold = first call, warm = second call — same process, Postgres buffers warm)\n")

    section("Counts (7 little COUNT queries)")
    _time("original_counts", original_counts)

    section("Era buckets (8x COUNT with JOIN)")
    _time("original_era_buckets", original_era_buckets)

    section("Tonight slate")
    _time("original_tonight", original_tonight)

    section("Current-season leaders (1 + 2×10 = 21 queries)")
    _time("original_leaders", original_leaders)

    section("Ledger (4x GROUP BY on 7M-row table)")
    _time("original_ledger", original_ledger)
    _time("opt_ledger_parallel (4 threads)", opt_ledger_parallel)

    section("Counts — optimized")
    _time("opt_counts_parallel (threads)", opt_counts_parallel)
    _time("opt_counts_pg_class (planner estimate)", opt_counts_pg_class)

    section("Era buckets — optimized")
    _time("opt_era_buckets_one_query (2 queries)", opt_era_buckets_one_query)

    section("Leaders — optimized")
    _time("opt_leaders_window (single SQL)", opt_leaders_window)

    section("ALL blocks fanned out in parallel")
    _time("opt_all_parallel", opt_all_parallel)


if __name__ == "__main__":
    main()
