"""Single-file API surface for the redesigned anhls frontend.

Every endpoint returns JSON. Queries run against the post-redesign schema
(players_player, games_game, events_event). No serializers — these views
are thin enough to inline the dict construction.
"""

from datetime import date
from typing import Any

from django.db.models import Count, Q, Sum, F, Min, Max, Avg
from django.db.models.functions import Cast
from django.db.models import IntegerField
from django.http import JsonResponse, HttpResponseBadRequest, Http404, HttpRequest

from events.models import Event
from games.models import Game
from players.models import Player


# ───────────────────────── helpers ─────────────────────────


def _team_abbrev_from_headshot(url: str | None) -> str | None:
    # NHL headshots are like https://assets.nhle.com/mugs/nhl/20252026/WSH/8471214.png
    # The team abbrev sits between two slashes before the file name.
    if not url:
        return None
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    candidate = parts[-2]
    return candidate if len(candidate) == 3 and candidate.isalpha() else None


def _player_brief(p: Player) -> dict[str, Any]:
    return {
        "id": p.nhl_api_id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "full_name": p.full_name,
        "slug": p.player_slug,
        "position": p.position,
        "sweater_number": p.sweater_number,
        "is_active": p.is_active,
        "headshot_url": p.headshot_url,
        "team_abbrev": _team_abbrev_from_headshot(p.headshot_url),
        "in_hhof": p.in_hhof,
        "in_top_100": p.in_top_100,
    }


def _season_label(season: int) -> str:
    # 19421943 → "1942-43"
    if not season:
        return ""
    start = season // 10000
    end = season % 10000
    return f"{start}-{str(end)[-2:]}"


def _season_year(season: int) -> int:
    return season // 10000


# ───────────────────────── /api/landing/ ─────────────────────────


def landing(request: HttpRequest) -> JsonResponse:
    # Counts + era buckets + ledger come from materialized views refreshed
    # nightly by `manage.py refresh_landing_mvs`. See ingest/migrations/0001.
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT total_events, total_games, total_players, shots_with_coords, "
            "total_seasons, hhof, active FROM mv_site_counts"
        )
        (
            total_events,
            total_games,
            total_players,
            shots_with_coords,
            total_seasons,
            hhof,
            active,
        ) = cur.fetchone()

        cur.execute("SELECT era, events, games FROM mv_era_buckets ORDER BY ord")
        era_buckets = [{"era": e, "events": ev, "games": g} for e, ev, g in cur.fetchall()]

    # tonight — games today, or fall back to the most recent gameday
    today = date.today()
    tonight_qs = Game.objects.filter(game_date=today).order_by("start_time_utc")
    tonight_fallback = False
    fallback_date = None
    if not tonight_qs.exists():
        last = (
            Game.objects.filter(game_date__lte=today, game_state__in=["OFF", "FINAL", "OVER"])
            .order_by("-game_date")
            .values_list("game_date", flat=True)
            .first()
        )
        if last:
            tonight_qs = Game.objects.filter(game_date=last).order_by("start_time_utc")
            tonight_fallback = True
            fallback_date = last
    tonight_qs = tonight_qs[:8]
    tonight = [
        {
            "id": g.id,
            "away": g.away_team,
            "home": g.home_team,
            "away_score": g.away_score,
            "home_score": g.home_score,
            "state": g.game_state,
            "start_time_utc": g.start_time_utc.isoformat() if g.start_time_utc else None,
            "venue": g.venue,
        }
        for g in tonight_qs
    ]

    # current-season scoring leaders — single CTE replaces the 21-query N+1.
    # Team is inferred from score-delta on the player's most recent goal this
    # season (events_event has no team FK).
    current_season = Game.objects.aggregate(s=Max("season"))["s"] or 0
    with connection.cursor() as cur:
        cur.execute(
            """
            WITH season_goals AS (
                SELECT e.primary_player_id, e.game_id, e.period, e.period_time,
                       e.home_score, e.away_score, g.game_date
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
            last_goal AS (
                SELECT sg.*
                FROM (
                    SELECT sg.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY sg.primary_player_id
                               ORDER BY sg.game_date DESC, sg.period DESC, sg.period_time DESC
                           ) AS rn
                    FROM season_goals sg
                    JOIN goal_counts gc ON gc.primary_player_id = sg.primary_player_id
                ) sg
                WHERE rn = 1
            ),
            with_prev AS (
                SELECT lg.primary_player_id, lg.game_id, lg.home_score, lg.away_score,
                       (SELECT e2.home_score FROM events_event e2
                        WHERE e2.game_id = lg.game_id
                          AND (e2.period < lg.period
                               OR (e2.period = lg.period AND e2.period_time < lg.period_time))
                        ORDER BY e2.period DESC, e2.period_time DESC LIMIT 1) AS prev_home,
                       (SELECT e2.away_score FROM events_event e2
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
                   COALESCE(wp.prev_home, 0), COALESCE(wp.prev_away, 0)
            FROM goal_counts gc
            JOIN with_prev wp ON wp.primary_player_id = gc.primary_player_id
            JOIN players_player p ON p.nhl_api_id = gc.primary_player_id
            JOIN games_game g ON g.id = wp.game_id
            ORDER BY gc.goals DESC
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

    # ledger — top in 4 metrics, from mv_ledger
    _LEDGER_ORDER = ["goal", "faceoff", "hit", "blocked-shot"]
    with connection.cursor() as cur:
        cur.execute(
            "SELECT type_desc, metric, player_id, first_name, last_name, value, is_active "
            "FROM mv_ledger"
        )
        by_type = {
            row[0]: {
                "metric": row[1],
                "id": row[2],
                "first_name": row[3],
                "last_name": row[4],
                "value": row[5],
                "active": row[6],
            }
            for row in cur.fetchall()
        }
    ledger = [by_type.get(t) for t in _LEDGER_ORDER]

    return JsonResponse(
        {
            "counts": {
                "events": total_events,
                "games": total_games,
                "players": total_players,
                "shot_coords": shots_with_coords,
                "seasons": total_seasons,
                "hhof": hhof,
                "active": active,
            },
            "era_buckets": era_buckets,
            "tonight": tonight,
            "tonight_fallback": tonight_fallback,
            "tonight_fallback_date": fallback_date.isoformat() if fallback_date else None,
            "current_season": current_season,
            "current_season_label": _season_label(current_season),
            "leaders": leaders,
            "ledger": ledger,
        }
    )


# ───────────────────────── /api/players/<id>/ ─────────────────────────


def _goalie_profile(p: Player) -> JsonResponse:
    """Goalie-specific profile shape — saves/SV%/shutouts instead of goals/shots."""
    # All shots faced (where this goalie is the goalie FK)
    against = Event.objects.filter(goalie=p)
    shots_against = against.filter(type_desc=Event.SHOT_ON_GOAL).count()
    goals_against = against.filter(type_desc=Event.GOAL).count()
    missed_against = against.filter(type_desc=Event.MISSED_SHOT).count()
    total_shots = shots_against + goals_against
    saves = shots_against  # SOG that didn't become goals
    sv_pct = round(100 * saves / total_shots, 2) if total_shots else 0.0
    gaa_total = goals_against  # raw

    # Per-season stats
    season_rows = (
        against.filter(type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL])
        .values("game__season")
        .annotate(
            sa=Count("id"),
            ga=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("game__season")
    )

    gp_rows = (
        Event.objects.filter(goalie=p)
        .values("game__season")
        .annotate(gp=Count("game", distinct=True))
    )
    season_to_gp = {r["game__season"]: r["gp"] for r in gp_rows}

    career_arc = []
    for r in season_rows:
        season = r["game__season"]
        sa = r["sa"]
        ga = r["ga"]
        sv = sa - ga
        career_arc.append(
            {
                "season": season,
                "season_label": _season_label(season),
                "year": _season_year(season),
                "gp": season_to_gp.get(season, 0),
                "g": sv,  # treat saves as the "g" so frontend chart still works
                "a": ga,
                "pts": sv,
                "shots": sa,
                "sh_pct": round(100 * sv / sa, 1) if sa else 0.0,
                "saves": sv,
                "goals_against": ga,
                "sv_pct": round(100 * sv / sa, 2) if sa else 0.0,
            }
        )

    # Shutout count — games where this goalie faced ≥1 shot and gave up 0 goals
    shutout_rows = (
        against.filter(type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL])
        .values("game_id")
        .annotate(
            sa=Count("id"),
            ga=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
    )
    shutouts = sum(1 for r in shutout_rows if r["sa"] >= 1 and r["ga"] == 0)

    # Top shooters faced
    top_shooters = (
        against.filter(
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            primary_player__isnull=False,
        )
        .values("primary_player", "primary_player__first_name", "primary_player__last_name")
        .annotate(
            shots=Count("id"),
            goals=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("-shots")[:5]
    )

    peak_season = max(career_arc, key=lambda r: r["saves"]) if career_arc else None
    current_arc = career_arc[-1] if career_arc else None
    games_played = sum(r["gp"] for r in career_arc)

    return JsonResponse(
        {
            "player": _player_brief(p),
            "is_goalie": True,
            "bio": {
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "birth_city": p.birth_city,
                "birth_country": p.birth_country,
                "height_cm": p.height_cm,
                "weight_kg": p.weight_kg,
                "shoots_catches": p.shoots_catches,
            },
            "kpis": {
                "saves": saves,
                "goals_against": gaa_total,
                "shots_against": total_shots,
                "sv_pct": sv_pct,
                "shutouts": shutouts,
                "games_played": games_played,
            },
            "career_arc": career_arc,
            "peak_season": peak_season,
            "current_arc": current_arc,
            "shutouts": shutouts,
            "faced_shooters": [
                {
                    "id": r["primary_player"],
                    "first_name": r["primary_player__first_name"],
                    "last_name": r["primary_player__last_name"],
                    "shots": r["shots"],
                    "goals": r["goals"],
                }
                for r in top_shooters
            ],
        }
    )


def player_profile(request: HttpRequest, player_id: int) -> JsonResponse:
    try:
        p = Player.objects.get(nhl_api_id=player_id)
    except Player.DoesNotExist:
        raise Http404(f"player {player_id}")

    if p.position == "G":
        return _goalie_profile(p)

    # Bulk-fetch counts per type_desc where primary_player=p
    type_counts = dict(
        Event.objects.filter(primary_player=p)
        .values_list("type_desc")
        .annotate(n=Count("id"))
        .values_list("type_desc", "n")
    )
    goals = type_counts.get(Event.GOAL, 0)
    shots = type_counts.get(Event.SHOT_ON_GOAL, 0) + goals  # shots-on-goal incl. goals
    a1 = Event.objects.filter(secondary_player=p, type_desc=Event.GOAL).count()
    a2 = Event.objects.filter(tertiary_player=p, type_desc=Event.GOAL).count()
    assists = a1 + a2
    points = goals + assists

    # Shot map (sample) — shots-on-goal + goals with coords
    shot_events = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            coord_x__isnull=False,
            coord_y__isnull=False,
        )
        .values("coord_x", "coord_y", "type_desc", "shot_type")
    )
    shot_map = list(shot_events[:6000])

    # Per-season aggregation (career arc + season ledger)
    season_rows = (
        Event.objects.filter(primary_player=p, type_desc=Event.GOAL)
        .values("game__season")
        .annotate(g=Count("id"))
        .order_by("game__season")
    )
    season_to_g = {r["game__season"]: r["g"] for r in season_rows}

    assist_rows_1 = (
        Event.objects.filter(secondary_player=p, type_desc=Event.GOAL)
        .values("game__season")
        .annotate(a=Count("id"))
    )
    assist_rows_2 = (
        Event.objects.filter(tertiary_player=p, type_desc=Event.GOAL)
        .values("game__season")
        .annotate(a=Count("id"))
    )
    season_to_a: dict[int, int] = {}
    for r in assist_rows_1:
        season_to_a[r["game__season"]] = season_to_a.get(r["game__season"], 0) + r["a"]
    for r in assist_rows_2:
        season_to_a[r["game__season"]] = season_to_a.get(r["game__season"], 0) + r["a"]

    shot_season_rows = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
        )
        .values("game__season")
        .annotate(s=Count("id"))
    )
    season_to_s = {r["game__season"]: r["s"] for r in shot_season_rows}

    # games played per season — count distinct games where player appears
    gp_rows = (
        Event.objects.filter(
            Q(primary_player=p) | Q(secondary_player=p) | Q(tertiary_player=p) | Q(goalie=p)
        )
        .values("game__season")
        .annotate(gp=Count("game", distinct=True))
    )
    season_to_gp = {r["game__season"]: r["gp"] for r in gp_rows}

    seasons = sorted(set(list(season_to_g.keys()) + list(season_to_a.keys()) + list(season_to_gp.keys())))
    career_arc = []
    for s in seasons:
        g = season_to_g.get(s, 0)
        a = season_to_a.get(s, 0)
        sog = season_to_s.get(s, 0)
        gp = season_to_gp.get(s, 0)
        career_arc.append(
            {
                "season": s,
                "season_label": _season_label(s),
                "year": _season_year(s),
                "gp": gp,
                "g": g,
                "a": a,
                "pts": g + a,
                "shots": sog,
                "sh_pct": round(100 * g / sog, 1) if sog else 0.0,
            }
        )

    # Shot type breakdown
    shot_types = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            shot_type__isnull=False,
        )
        .values("shot_type")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    # Most-faced goalies (top 5)
    faced_goalies = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL, Event.MISSED_SHOT],
            goalie__isnull=False,
        )
        .values("goalie", "goalie__first_name", "goalie__last_name")
        .annotate(
            shots=Count("id"),
            goals=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("-shots")[:5]
    )

    # Period heat — goals by period:minute bucket (1..60)
    period_heat_raw = (
        Event.objects.filter(primary_player=p, type_desc=Event.GOAL, period__isnull=False, period_time__isnull=False)
        .values("period", "period_time")
    )
    buckets = [0] * 60
    for ev in period_heat_raw:
        per = ev["period"]
        if per is None or per > 3:
            continue
        pt = ev["period_time"]
        if pt is None:
            continue
        minute_in_period = pt.minute  # period_time is TimeField from 00:00 → 20:00
        idx = (per - 1) * 20 + min(minute_in_period, 19)
        if 0 <= idx < 60:
            buckets[idx] += 1
    period_heat = buckets

    peak_season = max(career_arc, key=lambda r: r["g"]) if career_arc else None
    avg_goals = round(sum(r["g"] for r in career_arc) / len(career_arc), 1) if career_arc else 0.0
    current_g = career_arc[-1]["g"] if career_arc else 0

    # Office %: fraction of shots within 25ft of either net & off-center
    office_shots = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            coord_x__isnull=False,
        )
        .filter(Q(coord_x__gte=55) | Q(coord_x__lte=-55))
        .count()
    )
    total_coord_shots = (
        Event.objects.filter(
            primary_player=p,
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            coord_x__isnull=False,
        ).count()
    )
    office_pct = round(100 * office_shots / total_coord_shots, 1) if total_coord_shots else 0.0

    return JsonResponse(
        {
            "player": _player_brief(p),
            "bio": {
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "birth_city": p.birth_city,
                "birth_country": p.birth_country,
                "height_cm": p.height_cm,
                "weight_kg": p.weight_kg,
                "shoots_catches": p.shoots_catches,
            },
            "kpis": {
                "goals": goals,
                "assists": assists,
                "points": points,
                "shots": shots,
                "office_pct": office_pct,
            },
            "career_arc": career_arc,
            "peak_season": peak_season,
            "avg_goals": avg_goals,
            "current_goals": current_g,
            "shot_map": shot_map,
            "shot_types": [{"type": r["shot_type"], "n": r["n"]} for r in shot_types],
            "faced_goalies": [
                {
                    "id": r["goalie"],
                    "first_name": r["goalie__first_name"],
                    "last_name": r["goalie__last_name"],
                    "shots": r["shots"],
                    "goals": r["goals"],
                }
                for r in faced_goalies
            ],
            "period_heat": period_heat,
        }
    )


# ───────────────────────── /api/players/search/?q= ─────────────────────────


def player_search(request: HttpRequest) -> JsonResponse:
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    qs = (
        Player.objects.filter(full_name__icontains=q)
        .order_by("-is_active", "last_name", "first_name")[:25]
    )
    return JsonResponse({"results": [_player_brief(p) for p in qs]})


# ───────────────────────── /api/players/ — directory ─────────────────────────


_PLAYER_SORT_KEYS = {
    "last_name": ("last_name", "first_name"),
    "first_name": ("first_name", "last_name"),
    "sweater": ("-sweater_number", "last_name"),
    "debut": ("birth_date", "last_name"),  # rough proxy
    "active": ("-is_active", "last_name"),
}


def player_directory(request: HttpRequest) -> JsonResponse:
    """Paginated player directory. Filters: q, position, status, band, country, sort, page."""
    q = request.GET.get("q", "").strip()
    position = request.GET.get("position", "").strip().upper()
    status = request.GET.get("status", "").strip().lower()  # all|active|retired
    band = request.GET.get("band", "").strip().lower()  # all|hof|top100
    country = request.GET.get("country", "").strip().upper()
    sort = request.GET.get("sort", "last_name").strip().lower()
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    page_size = 60

    qs = Player.objects.all()
    if q:
        qs = qs.filter(full_name__icontains=q)
    if position in {"C", "L", "R", "D", "G"}:
        qs = qs.filter(position=position)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "retired":
        qs = qs.filter(is_active=False)
    if band == "hof":
        qs = qs.filter(in_hhof=True)
    elif band == "top100":
        qs = qs.filter(in_top_100=True)
    if country:
        qs = qs.filter(birth_country=country)

    total = qs.count()
    order = _PLAYER_SORT_KEYS.get(sort, _PLAYER_SORT_KEYS["last_name"])
    qs = qs.order_by(*order)[(page - 1) * page_size : page * page_size]

    # Facets — counts that respect every filter except the one being faceted.
    base = Player.objects.all()
    if q:
        base = base.filter(full_name__icontains=q)
    pos_facets = list(
        base.values("position").annotate(n=Count("nhl_api_id")).order_by("position")
    )
    country_facets = list(
        base.exclude(birth_country__isnull=True)
        .exclude(birth_country="")
        .values("birth_country")
        .annotate(n=Count("nhl_api_id"))
        .order_by("-n")[:10]
    )
    return JsonResponse(
        {
            "filters": {
                "q": q,
                "position": position or None,
                "status": status or "all",
                "band": band or "all",
                "country": country or None,
                "sort": sort,
                "page": page,
                "page_size": page_size,
            },
            "total": total,
            "page_count": (total + page_size - 1) // page_size,
            "facets": {
                "position": pos_facets,
                "country": country_facets,
                "active": base.filter(is_active=True).count(),
                "hof": base.filter(in_hhof=True).count(),
                "top100": base.filter(in_top_100=True).count(),
            },
            "results": [
                {
                    **_player_brief(p),
                    "birth_country": p.birth_country,
                    "birth_year": p.birth_date.year if p.birth_date else None,
                }
                for p in qs
            ],
        }
    )


# ───────────────────────── /api/games/ — directory ─────────────────────────


def games_directory(request: HttpRequest) -> JsonResponse:
    """Paginated games directory. Filters: season, game_type, team, state, date, sort, page."""
    season = request.GET.get("season", "").strip()
    game_type = request.GET.get("game_type", "").strip()  # 1..4 or empty
    team = request.GET.get("team", "").strip().upper()
    state = request.GET.get("state", "").strip().upper()  # OFF/FINAL/LIVE/FUT
    date_str = request.GET.get("date", "").strip()  # YYYY-MM-DD exact
    sort = request.GET.get("sort", "date_desc").strip().lower()
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    page_size = 50

    qs = Game.objects.all()
    if season:
        try:
            qs = qs.filter(season=int(season))
        except ValueError:
            pass
    if game_type:
        try:
            qs = qs.filter(game_type=int(game_type))
        except ValueError:
            pass
    if team:
        qs = qs.filter(Q(home_team=team) | Q(away_team=team))
    if state:
        qs = qs.filter(game_state=state)
    if date_str:
        try:
            from datetime import datetime
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            qs = qs.filter(game_date=d)
        except ValueError:
            pass

    total = qs.count()

    if sort == "date_asc":
        qs = qs.order_by("game_date", "start_time_utc")
    elif sort == "score_high":
        qs = qs.annotate(_total=F("home_score") + F("away_score")).order_by(
            F("_total").desc(nulls_last=True), "-game_date"
        )
    else:  # date_desc default
        qs = qs.order_by("-game_date", "-start_time_utc")

    qs = qs[(page - 1) * page_size : page * page_size]

    seasons = list(
        Game.objects.values_list("season", flat=True).distinct().order_by("-season")
    )
    teams = sorted(
        set(Game.objects.values_list("home_team", flat=True).distinct())
        | set(Game.objects.values_list("away_team", flat=True).distinct())
    )

    rows = []
    for g in qs:
        rows.append(
            {
                "id": g.id,
                "season": g.season,
                "season_label": _season_label(g.season),
                "game_type": g.game_type,
                "game_date": g.game_date.isoformat() if g.game_date else None,
                "home_team": g.home_team,
                "away_team": g.away_team,
                "home_score": g.home_score,
                "away_score": g.away_score,
                "venue": g.venue,
                "game_state": g.game_state,
            }
        )

    return JsonResponse(
        {
            "filters": {
                "season": int(season) if season.isdigit() else None,
                "game_type": int(game_type) if game_type.isdigit() else None,
                "team": team or None,
                "state": state or None,
                "date": date_str or None,
                "sort": sort,
                "page": page,
                "page_size": page_size,
            },
            "total": total,
            "page_count": (total + page_size - 1) // page_size,
            "facets": {
                "seasons": seasons,
                "teams": teams,
                "game_types": list(
                    Game.objects.values("game_type").annotate(n=Count("id")).order_by("game_type")
                ),
            },
            "results": rows,
        }
    )


# ───────────────────────── /api/comparison/ ─────────────────────────


def _game_type_filter(game_type: str | None) -> dict:
    """Return a queryset filter dict for game_type."""
    if game_type == "regular":
        return {"game__game_type": 2}
    if game_type == "playoffs":
        return {"game__game_type": 3}
    return {}


def _player_stats_block(p: Player, gt_filter: dict | None = None) -> dict[str, int | float]:
    gt = gt_filter or {}
    base = Event.objects.filter(primary_player=p, **gt)
    counts = dict(
        base.values_list("type_desc").annotate(n=Count("id")).values_list("type_desc", "n")
    )
    goals = counts.get(Event.GOAL, 0)
    sog = counts.get(Event.SHOT_ON_GOAL, 0) + goals
    a1 = Event.objects.filter(secondary_player=p, type_desc=Event.GOAL, **gt).count()
    a2 = Event.objects.filter(tertiary_player=p, type_desc=Event.GOAL, **gt).count()
    assists = a1 + a2
    hits_delivered = counts.get(Event.HIT, 0)
    hits_taken = Event.objects.filter(secondary_player=p, type_desc=Event.HIT, **gt).count()
    fo_wins = counts.get(Event.FACEOFF, 0)
    fo_losses = Event.objects.filter(secondary_player=p, type_desc=Event.FACEOFF, **gt).count()
    fo_pct = round(100 * fo_wins / (fo_wins + fo_losses), 1) if (fo_wins + fo_losses) else 0.0
    blocked = Event.objects.filter(secondary_player=p, type_desc=Event.BLOCKED_SHOT, **gt).count()
    missed = counts.get(Event.MISSED_SHOT, 0)
    pen_taken = counts.get(Event.PENALTY, 0)
    pen_drawn = Event.objects.filter(secondary_player=p, type_desc=Event.PENALTY, **gt).count()
    giveaways = counts.get(Event.GIVEAWAY, 0)
    takeaways = counts.get(Event.TAKEAWAY, 0)
    return {
        "goals": goals,
        "assists": assists,
        "points": goals + assists,
        "sog": sog,
        "sh_pct": round(100 * goals / sog, 1) if sog else 0.0,
        "hits_delivered": hits_delivered,
        "hits_taken": hits_taken,
        "faceoff_wins": fo_wins,
        "faceoff_pct": fo_pct,
        "blocked": blocked,
        "missed_shots": missed,
        "pen_taken": pen_taken,
        "pen_drawn": pen_drawn,
        "giveaways": giveaways,
        "takeaways": takeaways,
    }


def _shot_coords(p: Player, limit: int = 4000, gt_filter: dict | None = None) -> list[dict]:
    qs = Event.objects.filter(
        primary_player=p,
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
        coord_x__isnull=False,
        coord_y__isnull=False,
        **(gt_filter or {}),
    )
    return list(qs.values("coord_x", "coord_y", "type_desc")[:limit])


def _career_arc(p: Player, gt_filter: dict | None = None) -> list[dict]:
    rows = (
        Event.objects.filter(primary_player=p, type_desc=Event.GOAL, **(gt_filter or {}))
        .values("game__season")
        .annotate(g=Count("id"))
        .order_by("game__season")
    )
    return [{"season": r["game__season"], "year": _season_year(r["game__season"]), "g": r["g"]} for r in rows]


def comparison(request: HttpRequest) -> JsonResponse:
    try:
        a_id = int(request.GET.get("a", ""))
        b_id = int(request.GET.get("b", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("a and b player ids required")
    try:
        a = Player.objects.get(nhl_api_id=a_id)
        b = Player.objects.get(nhl_api_id=b_id)
    except Player.DoesNotExist:
        raise Http404("player not found")
    game_type = request.GET.get("game_type", "all")
    gt_filter = _game_type_filter(game_type)
    return JsonResponse(
        {
            "a": _player_brief(a),
            "b": _player_brief(b),
            "filters": {"game_type": game_type},
            "a_stats": _player_stats_block(a, gt_filter),
            "b_stats": _player_stats_block(b, gt_filter),
            "a_shots": _shot_coords(a, gt_filter=gt_filter),
            "b_shots": _shot_coords(b, gt_filter=gt_filter),
            "a_arc": _career_arc(a, gt_filter),
            "b_arc": _career_arc(b, gt_filter),
        }
    )


# ───────────────────────── /api/versus/ ─────────────────────────


def versus(request: HttpRequest) -> JsonResponse:
    try:
        skater_id = int(request.GET.get("skater", ""))
        goalie_id = int(request.GET.get("goalie", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("skater and goalie ids required")
    try:
        skater = Player.objects.get(nhl_api_id=skater_id)
        goalie = Player.objects.get(nhl_api_id=goalie_id)
    except Player.DoesNotExist:
        raise Http404("player not found")

    game_type = request.GET.get("game_type", "all")
    gt_filter = _game_type_filter(game_type)
    shots_against = Event.objects.filter(primary_player=skater, goalie=goalie, **gt_filter)
    sog = shots_against.filter(type_desc=Event.SHOT_ON_GOAL).count()
    goals = shots_against.filter(type_desc=Event.GOAL).count()
    missed = shots_against.filter(type_desc=Event.MISSED_SHOT).count()
    total_shots = sog + goals
    sv_pct = round(100 * sog / total_shots, 1) if total_shots else 0.0
    conv = round(100 * goals / total_shots, 1) if total_shots else 0.0
    seasons_count = (
        shots_against.values_list("game__season", flat=True).distinct().count()
    )

    # Weapon-of-choice — shot type breakdown
    weapon_rows = (
        shots_against.filter(shot_type__isnull=False)
        .values("shot_type")
        .annotate(
            total=Count("id"),
            goals=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("-total")
    )

    # Goals by period
    period_breakdown = (
        shots_against.filter(type_desc=Event.GOAL)
        .values("period")
        .annotate(n=Count("id"))
        .order_by("period")
    )

    # Shot coords for the map
    shot_map = list(
        shots_against.filter(coord_x__isnull=False, coord_y__isnull=False)
        .values("coord_x", "coord_y", "type_desc", "shot_type", "period")
    )

    # Goal log (every goal)
    goal_log_qs = (
        shots_against.filter(type_desc=Event.GOAL)
        .select_related("game", "secondary_player", "tertiary_player")
        .order_by("game__game_date", "period", "period_time")
    )
    goal_log = []
    for idx, e in enumerate(goal_log_qs[:200]):
        assists = []
        if e.secondary_player_id:
            assists.append(e.secondary_player.last_name)
        if e.tertiary_player_id:
            assists.append(e.tertiary_player.last_name)
        # describe strength via situation_code (e.g. "1551" = 5v5)
        strength = None
        if e.situation_code and len(e.situation_code) == 4:
            try:
                hs = int(e.situation_code[1]); as_ = int(e.situation_code[2])
                if hs == as_:
                    strength = "EV" if hs == 5 else (f"{hs}v{as_}")
                elif hs > as_:
                    strength = f"{hs}v{as_}"
                else:
                    strength = f"{hs}v{as_}"
            except ValueError:
                pass
        goal_log.append({
            "n": idx + 1,
            "game_id": e.game_id,
            "date": e.game.game_date.isoformat() if e.game.game_date else None,
            "season": _season_label(e.game.season),
            "venue": e.game.venue,
            "period": e.period,
            "period_type": e.period_type,
            "period_time": e.period_time.strftime("%M:%S") if e.period_time else None,
            "shot_type": e.shot_type,
            "strength": strength,
            "assists": assists,
            "home_team": e.game.home_team,
            "away_team": e.game.away_team,
        })

    return JsonResponse(
        {
            "skater": _player_brief(skater),
            "goalie": _player_brief(goalie),
            "filters": {"game_type": game_type},
            "totals": {
                "shots": total_shots,
                "goals": goals,
                "missed": missed,
                "sv_pct": sv_pct,
                "conv_pct": conv,
                "seasons": seasons_count,
            },
            "weapon": [
                {
                    "shot_type": w["shot_type"],
                    "total": w["total"],
                    "goals": w["goals"],
                    "pct": round(100 * w["goals"] / w["total"], 1) if w["total"] else 0.0,
                }
                for w in weapon_rows
            ],
            "by_period": [{"period": r["period"], "goals": r["n"]} for r in period_breakdown],
            "shot_map": shot_map,
            "goal_log": goal_log,
            "goal_log_total": goal_log_qs.count(),
        }
    )


# ───────────────────────── /api/records/ ─────────────────────────


_RECORD_CATEGORIES = {
    "goals": (Event.GOAL, "primary_player", "Career goals"),
    "assists": (Event.GOAL, "secondary_player", "Career assists (primary)"),
    "hits": (Event.HIT, "primary_player", "Career hits delivered"),
    "blocks": (Event.BLOCKED_SHOT, "primary_player", "Career shot blocks"),
    "faceoffs": (Event.FACEOFF, "primary_player", "Career faceoff wins"),
    "penalties_drawn": (Event.PENALTY, "secondary_player", "Career penalties drawn"),
    "shots": (Event.SHOT_ON_GOAL, "primary_player", "Career shots on goal"),
}


def records(request: HttpRequest) -> JsonResponse:
    category = request.GET.get("category", "goals")
    if category not in _RECORD_CATEGORIES:
        return HttpResponseBadRequest(f"unknown category {category}")
    type_desc, role, label = _RECORD_CATEGORIES[category]
    band = request.GET.get("band", "all")  # all | hof | active

    qs = Event.objects.filter(type_desc=type_desc).values(
        role,
        f"{role}__first_name",
        f"{role}__last_name",
        f"{role}__position",
        f"{role}__is_active",
        f"{role}__in_hhof",
    ).annotate(n=Count("id")).order_by("-n")

    if band == "hof":
        qs = qs.filter(**{f"{role}__in_hhof": True})
    elif band == "active":
        qs = qs.filter(**{f"{role}__is_active": True})

    rows = list(qs[:30])

    # career span (min/max season) per top-N
    ids = [r[role] for r in rows if r[role]]
    spans = {
        r["primary_player"]: (r["start"], r["end"])
        for r in Event.objects.filter(primary_player_id__in=ids)
        .values("primary_player")
        .annotate(start=Min("game__season"), end=Max("game__season"))
    }

    leaderboard = []
    for i, r in enumerate(rows):
        pid = r[role]
        if not pid:
            continue
        start_season, end_season = spans.get(pid, (None, None))
        leaderboard.append(
            {
                "rank": i + 1,
                "id": pid,
                "first_name": r[f"{role}__first_name"],
                "last_name": r[f"{role}__last_name"],
                "position": r[f"{role}__position"],
                "active": r[f"{role}__is_active"],
                "hhof": r[f"{role}__in_hhof"],
                "value": r["n"],
                "start_year": _season_year(start_season) if start_season else None,
                "end_year": _season_year(end_season) + 1 if end_season else None,
            }
        )

    return JsonResponse({"category": category, "label": label, "band": band, "leaderboard": leaderboard})


# ───────────────────────── /api/records/overview/ ─────────────────────────


def records_overview(request: HttpRequest) -> JsonResponse:
    """Sidebar overview: per-category #1 leader + goal-type breakdown."""
    leaders = []
    for category, (type_desc, role, label) in _RECORD_CATEGORIES.items():
        top = (
            Event.objects.filter(type_desc=type_desc, **{f"{role}__isnull": False})
            .values(role)
            .annotate(n=Count("id"))
            .order_by("-n")[:1]
        )
        top = list(top)
        if not top:
            continue
        pid = top[0][role]
        n = top[0]["n"]
        try:
            p = Player.objects.get(nhl_api_id=pid)
            player_brief = _player_brief(p)
        except Player.DoesNotExist:
            player_brief = None
        leaders.append(
            {
                "category": category,
                "label": label,
                "player": player_brief,
                "value": n,
            }
        )

    goal_type_rows = (
        Event.objects.filter(type_desc=Event.GOAL, shot_type__isnull=False)
        .values("shot_type")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    goal_types = [{"shot_type": r["shot_type"], "count": r["n"]} for r in goal_type_rows]

    return JsonResponse({"leaders": leaders, "goal_types": goal_types})


# ───────────────────────── /api/games/<id>/ ─────────────────────────


def game_center(request: HttpRequest, game_id: int) -> JsonResponse:
    try:
        g = Game.objects.get(id=game_id)
    except Game.DoesNotExist:
        raise Http404(f"game {game_id}")

    events = list(
        Event.objects.filter(game=g)
        .select_related("primary_player", "secondary_player", "tertiary_player", "goalie")
        .order_by("period", "period_time")
    )

    # line score: goals per period per team
    line = {"home": [0, 0, 0, 0, 0], "away": [0, 0, 0, 0, 0]}  # P1,P2,P3,OT,SO
    for e in events:
        if e.type_desc != Event.GOAL or e.period is None:
            continue
        # determine if scorer is home or away via score deltas
        # We don't have a roster-per-game; infer team from score progression
        pass  # filled below via score deltas

    # Use home_score/away_score running tallies to attribute each goal
    prev_home = 0
    prev_away = 0
    for e in events:
        if e.type_desc != Event.GOAL:
            continue
        h = e.home_score if e.home_score is not None else prev_home
        a = e.away_score if e.away_score is not None else prev_away
        period_idx = min((e.period or 1) - 1, 4)
        if h > prev_home:
            line["home"][period_idx] += 1
        elif a > prev_away:
            line["away"][period_idx] += 1
        prev_home, prev_away = h, a

    # PBP feed (compact)
    pbp = []
    for e in events:
        primary = e.primary_player
        secondary = e.secondary_player
        desc = ""
        if e.type_desc == Event.GOAL and primary:
            assists = []
            if secondary:
                assists.append(secondary.last_name)
            if e.tertiary_player:
                assists.append(e.tertiary_player.last_name)
            assist_str = f" (assists: {', '.join(assists)})" if assists else ""
            desc = f"GOAL — {primary.first_name} {primary.last_name}{assist_str}"
        elif primary:
            desc = f"{e.type_desc.replace('-', ' ')} — {primary.first_name} {primary.last_name}"
        else:
            desc = e.type_desc.replace("-", " ")
        pbp.append(
            {
                "id": e.nhl_event_id,
                "period": e.period,
                "period_time": e.period_time.strftime("%M:%S") if e.period_time else None,
                "type": e.type_desc,
                "x": e.coord_x,
                "y": e.coord_y,
                "desc": desc,
                "shot_type": e.shot_type,
                "penalty_type": e.penalty_type,
                "penalty_minutes": e.penalty_minutes,
                "home_score": e.home_score,
                "away_score": e.away_score,
                "primary_id": primary.nhl_api_id if primary else None,
            }
        )

    # Scoring summary
    scoring = [p for p in pbp if p["type"] == Event.GOAL]
    penalties = [p for p in pbp if p["type"] == Event.PENALTY]

    # Box top performers — top 3 by event count per team-ish (we lack roster)
    perf_qs = (
        Event.objects.filter(game=g, primary_player__isnull=False)
        .values(
            "primary_player",
            "primary_player__first_name",
            "primary_player__last_name",
            "primary_player__position",
        )
        .annotate(
            n=Count("id"),
            goals=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("-goals", "-n")[:8]
    )
    top_performers = [
        {
            "id": r["primary_player"],
            "first_name": r["primary_player__first_name"],
            "last_name": r["primary_player__last_name"],
            "position": r["primary_player__position"],
            "events": r["n"],
            "goals": r["goals"],
        }
        for r in perf_qs
    ]

    return JsonResponse(
        {
            "game": {
                "id": g.id,
                "season": _season_label(g.season),
                "date": g.game_date.isoformat() if g.game_date else None,
                "venue": g.venue,
                "home_team": g.home_team,
                "away_team": g.away_team,
                "home_score": g.home_score,
                "away_score": g.away_score,
                "state": g.game_state,
                "game_type": g.game_type,
            },
            "line_score": line,
            "pbp": pbp,
            "scoring": scoring,
            "penalties": penalties,
            "top_performers": top_performers,
        }
    )


# ───────────────────────── /api/rink-lab/ ─────────────────────────


def _bin(x: int | None, y: int | None, size: int) -> tuple[int, int] | None:
    if x is None or y is None:
        return None
    return ((x // size) * size, (y // size) * size)


def rink_lab(request: HttpRequest) -> JsonResponse:
    bin_size = int(request.GET.get("bin", "4"))
    era = request.GET.get("era", "modern")  # modern (2005+), all
    qs = Event.objects.filter(
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
        coord_x__isnull=False,
        coord_y__isnull=False,
    )
    if era == "modern":
        qs = qs.filter(game__season__gte=20052006)

    # We have ~1.16M shots — too many to fetch each row.
    # SQL-level binning via integer division.
    rows = qs.extra(
        select={
            "bx": f"(coord_x / {bin_size}) * {bin_size}",
            "by": f"(coord_y / {bin_size}) * {bin_size}",
        }
    ).values("bx", "by").annotate(
        n=Count("id"),
        g=Count("id", filter=Q(type_desc=Event.GOAL)),
    ).order_by("-n")[:1200]

    bins = [{"x": r["bx"], "y": r["by"], "n": r["n"], "g": r["g"]} for r in rows]

    # ── distance-from-net histogram (10ft bins, 0..80+) ───────────────────────
    # Distance from nearer net at (±89, 0) — limit to offensive-zone shots in modern era.
    dist_qs = Event.objects.filter(
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
        coord_x__isnull=False,
        coord_y__isnull=False,
        zone_code="O",
        game__season__gte=20052006,
    )
    # SQL-side distance bin: floor(sqrt((89 - abs(x))^2 + y^2) / 10) * 10, capped at 80
    dist_rows = dist_qs.extra(
        select={
            "dbin": (
                "CASE WHEN (CAST(SQRT(POWER(89 - ABS(coord_x), 2) + POWER(coord_y, 2)) AS INTEGER) / 10) * 10 > 80 "
                "THEN 80 "
                "ELSE (CAST(SQRT(POWER(89 - ABS(coord_x), 2) + POWER(coord_y, 2)) AS INTEGER) / 10) * 10 END"
            )
        }
    ).values("dbin").annotate(
        shots=Count("id"),
        goals=Count("id", filter=Q(type_desc=Event.GOAL)),
    ).order_by("dbin")
    dist_map = {r["dbin"]: r for r in dist_rows}
    dist_histogram = []
    for bft in [0, 10, 20, 30, 40, 50, 60, 70, 80]:
        r = dist_map.get(bft)
        dist_histogram.append({
            "bin_ft": bft,
            "shots": r["shots"] if r else 0,
            "goals": r["goals"] if r else 0,
        })

    # ── decade histogram of goals ─────────────────────────────────────────────
    decade_rows = (
        Event.objects.filter(type_desc=Event.GOAL)
        .extra(select={"decade": "((season / 10000) / 10) * 10"})
        .values("decade")
        .annotate(goals=Count("id"))
        .order_by("decade")
    )
    # season lives on game, not event — need to join via game__season:
    decade_rows = (
        Event.objects.filter(type_desc=Event.GOAL, game__season__isnull=False)
        .extra(select={"decade": "((games_game.season / 10000) / 10) * 10"})
        .values("decade")
        .annotate(goals=Count("id"))
        .order_by("decade")
    )
    decade_histogram = [
        {"decade": r["decade"], "goals": r["goals"]}
        for r in decade_rows
        if r["decade"] is not None
    ]

    return JsonResponse({
        "bins": bins,
        "bin_size": bin_size,
        "era": era,
        "dist_histogram": dist_histogram,
        "decade_histogram": decade_histogram,
    })


def rink_bin(request: HttpRequest) -> JsonResponse:
    try:
        x = int(request.GET.get("x", ""))
        y = int(request.GET.get("y", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("x and y required")
    size = int(request.GET.get("bin", "4"))
    qs = Event.objects.filter(
        type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
        coord_x__gte=x,
        coord_x__lt=x + size,
        coord_y__gte=y,
        coord_y__lt=y + size,
    )
    n = qs.count()
    goals = qs.filter(type_desc=Event.GOAL).count()
    top = (
        qs.filter(primary_player__isnull=False)
        .values("primary_player", "primary_player__first_name", "primary_player__last_name")
        .annotate(
            shots=Count("id"),
            goals=Count("id", filter=Q(type_desc=Event.GOAL)),
        )
        .order_by("-shots")[:5]
    )
    types = (
        qs.filter(shot_type__isnull=False)
        .values("shot_type")
        .annotate(n=Count("id"), g=Count("id", filter=Q(type_desc=Event.GOAL)))
        .order_by("-n")
    )
    return JsonResponse(
        {
            "bin": {"x": x, "y": y, "size": size},
            "shots": n,
            "goals": goals,
            "conv_pct": round(100 * goals / n, 1) if n else 0.0,
            "top_shooters": [
                {
                    "id": r["primary_player"],
                    "first_name": r["primary_player__first_name"],
                    "last_name": r["primary_player__last_name"],
                    "shots": r["shots"],
                    "goals": r["goals"],
                }
                for r in top
            ],
            "shot_types": [
                {"type": r["shot_type"], "n": r["n"], "g": r["g"]} for r in types
            ],
        }
    )


# ───────────────────────── /api/eras/ ─────────────────────────


_ERAS = [
    {
        "label": "Pre-modern", "from": 19171918, "to": 19411942, "accent": "ice",
        "description": "Forward passing was illegal until 1929. Goalies stayed on their feet. The puck was offense; the rink, a duel.",
    },
    {
        "label": "Original Six", "from": 19421943, "to": 19661967, "accent": "ice",
        "description": "Six teams played each other 14 times a year. Rivalries calcified. Howe and Richard set the template for the modern winger.",
    },
    {
        "label": "Expansion", "from": 19671968, "to": 19781979, "accent": "red",
        "description": "The league doubled, then doubled again. Goaltending was still nearly maskless. Goals followed the talent dilution.",
    },
    {
        "label": "Run-and-Gun", "from": 19791980, "to": 19921993, "accent": "red",
        "description": "The Edmonton dynasty rewired the league. Five future Hall of Famers on one power play. Gretzky scored 92 in 80 games.",
    },
    {
        "label": "Dead-puck", "from": 19931994, "to": 20032004, "accent": "ice",
        "description": "Neutral-zone trap. Goalie equipment ballooned. Goals fell to a generational low — 5.1/GP at the trough.",
    },
    {
        "label": "Post-lockout", "from": 20052006, "to": 20112012, "accent": "red",
        "description": "Two-line pass, smaller pads, shootouts. Crosby, Ovechkin, Malkin arrived together. Scoring rebounded.",
    },
    {
        "label": "Analytics", "from": 20122013, "to": 20192020, "accent": "ice",
        "description": "Corsi, expected goals, line-matching. Defense-first systems compressed the slot. McDavid still played like the rules didn't apply.",
    },
    {
        "label": "Slot shot", "from": 20202021, "to": 20992100, "accent": "red",
        "description": "High-volume slot scoring is the new orthodoxy. Goalies stop more pucks than ever. The shots that count come from one place.",
    },
]


def eras(request: HttpRequest) -> JsonResponse:
    # season-by-season G/GP curve
    season_rows = (
        Game.objects.filter(game_type=2)
        .values("season")
        .annotate(
            games=Count("id"),
            goals=Sum(F("home_score") + F("away_score")),
        )
        .order_by("season")
    )
    curve = [
        {
            "season": r["season"],
            "year": _season_year(r["season"]),
            "games": r["games"],
            "gpg": round((r["goals"] or 0) / r["games"], 2) if r["games"] else 0.0,
        }
        for r in season_rows
    ]

    # Era cards
    era_cards = []
    for e in _ERAS:
        rows = [r for r in curve if e["from"] <= r["season"] <= e["to"]]
        if not rows:
            continue
        total_games = sum(r["games"] for r in rows)
        total_goals = sum(int(r["gpg"] * r["games"]) for r in rows)
        gpg = round(total_goals / total_games, 2) if total_games else 0.0

        # Hero: top goal scorer in this era
        hero_row = (
            Event.objects.filter(
                type_desc=Event.GOAL,
                game__season__gte=e["from"],
                game__season__lte=e["to"],
                primary_player__isnull=False,
            )
            .values(
                "primary_player",
                "primary_player__first_name",
                "primary_player__last_name",
                "primary_player__full_name",
            )
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if hero_row:
            hero_name = hero_row.get("primary_player__full_name") or (
                f"{hero_row['primary_player__first_name']} {hero_row['primary_player__last_name']}"
            )
            hero_goals = hero_row["n"]
            hero_id = hero_row["primary_player"]
        else:
            hero_name = None
            hero_goals = None
            hero_id = None

        era_cards.append(
            {
                "label": e["label"],
                "year_start": _season_year(e["from"]),
                "year_end": _season_year(e["to"]) if e["to"] < 20992100 else _season_year(rows[-1]["season"]),
                "gpg": gpg,
                "games": total_games,
                "accent": e["accent"],
                "hero": hero_name,
                "hero_goals": hero_goals,
                "hero_id": hero_id,
                "description": e.get("description", ""),
            }
        )

    # Spatial drift — sample shot coord distance to nearer net per era (3 snapshots)
    snapshots = [(1994, 19941995), (2009, 20092010), (2024, 20242025)]
    drift = []
    for year, season in snapshots:
        bin_size = 4
        qs = Event.objects.filter(
            type_desc__in=[Event.SHOT_ON_GOAL, Event.GOAL],
            coord_x__isnull=False,
            coord_y__isnull=False,
            game__season=season,
        )
        rows = qs.extra(
            select={
                "bx": f"(coord_x / {bin_size}) * {bin_size}",
                "by": f"(coord_y / {bin_size}) * {bin_size}",
            }
        ).values("bx", "by").annotate(n=Count("id")).order_by("-n")[:300]
        drift.append(
            {
                "year": year,
                "season_label": _season_label(season),
                "bins": [{"x": r["bx"], "y": r["by"], "n": r["n"]} for r in rows],
            }
        )

    # Peak seasons per decade — top point-scoring season per decade band
    # (proxy: top goals season per decade band, joined w/ assists)
    peaks = []
    decade_bands = [
        (1970, 19701971, 19791980),
        (1980, 19801981, 19891990),
        (1990, 19901991, 19992000),
        (2000, 20002001, 20092010),
        (2020, 20202021, 20992100),
    ]
    for label, lo, hi in decade_bands:
        top = (
            Event.objects.filter(type_desc=Event.GOAL, game__season__gte=lo, game__season__lt=hi)
            .values(
                "primary_player",
                "primary_player__first_name",
                "primary_player__last_name",
                "game__season",
            )
            .annotate(g=Count("id"))
            .order_by("-g")
            .first()
        )
        if not top:
            continue
        pid = top["primary_player"]
        season = top["game__season"]
        # add assists for same player in same season
        a1 = Event.objects.filter(secondary_player_id=pid, type_desc=Event.GOAL, game__season=season).count()
        a2 = Event.objects.filter(tertiary_player_id=pid, type_desc=Event.GOAL, game__season=season).count()
        peaks.append(
            {
                "decade": label,
                "season": _season_label(season),
                "first_name": top["primary_player__first_name"],
                "last_name": top["primary_player__last_name"],
                "id": pid,
                "goals": top["g"],
                "assists": a1 + a2,
                "points": top["g"] + a1 + a2,
            }
        )

    # Peak / trough of the G/GP curve
    if curve:
        peak = max(curve, key=lambda r: r["gpg"])
        trough = min((r for r in curve if r["gpg"] > 0), key=lambda r: r["gpg"])
    else:
        peak = trough = None

    return JsonResponse(
        {
            "curve": curve,
            "era_cards": era_cards,
            "drift": drift,
            "peaks": peaks,
            "peak": peak,
            "trough": trough,
        }
    )
