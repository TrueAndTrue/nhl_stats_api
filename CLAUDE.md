# nhl_stats_api — Django backend

Django 4.2.7 · Python 3.12 · Postgres · Gunicorn on Heroku app **`nhl-api`**.

```
nhl_stats_api/
  config/              Django project package — settings, root urls, wsgi/asgi
  api/                 ★ Thin JSON API surface — single views.py + urls.py, no models
  players/             Player model + (stub) legacy views
  games/               Game model + (stub) legacy views
  events/              Event model + legacy stash (*_legacy.py)
  scripts/             Standalone ingestion scripts (not part of Django)
  manage.py
  Procfile             gunicorn config.wsgi:application
  requirements.txt
```

**Heads up:** the project package is `config/`, **not** `nhl_stats_api/` — `DJANGO_SETTINGS_MODULE` is `config.settings`.

---

## Status (May 2026)

The redesigned frontend (`../nhl-stats/`) is fully wired to this backend via the `api/` package.

What's done:
- ✅ Schema redesigned (`players_player`, `games_game`, `events_event` — see below) and migrated to prod
- ✅ Full historical re-ingest loaded: 8,660 players · 69,712 games · 7,112,166 events · 2.42M shot coords · 107 seasons
- ✅ `api/` package with 10 JSON endpoints powering every screen of the redesigned frontend
- ✅ Goalie profile branch — `/api/players/<id>/` auto-detects and returns saves/SV%/GA/shutouts instead of skater stats when `position='G'`
- ✅ Comparison `game_type` filter wired end-to-end (regular / playoffs / all)
- ✅ Versus same — `game_type` filter affects shot map, weapon breakdown, goal log
- ✅ Records leaderboards with `band=all|hof|active` filter across 7 categories

What's pending:
- Stats not currently aggregated by the eras endpoint: Shots/GP, Save %, PP% (frontend pills are disabled until backend computes them)
- Filters not yet wired beyond `game_type`: strength (5v5/PP), zone, period, opponent (frontend has the UI but uses placeholder/static state)
- No write endpoints — entire API is read-only. Data refresh happens via scripts (see ingestion section), then a loader populates Postgres.

---

## The `api/` package

A non-app Python package — no models, no migrations, just `__init__.py` + `urls.py` + `views.py`. Mounted at `/api/` in `config/urls.py`. All endpoints return JSON.

### Endpoints

| Path | View | Purpose |
|---|---|---|
| `GET /api/landing/` | `landing` | counts, 8 era buckets, tonight slate (+ fallback to last gameday), current-season scoring leaders, 4-metric ledger (goals/FOW/hits/blocks) |
| `GET /api/players/<id>/` | `player_profile` | skater bundle: bio, KPIs, career arc, shot map (≤6k coords), per-season ledger, faced goalies, period heat, milestones. **Auto-dispatches to `_goalie_profile` when `position='G'`** |
| `GET /api/players/search/?q=` | `player_search` | name prefix search, top 25 by `(is_active DESC, last_name, first_name)`. Requires `len(q) >= 2`. |
| `GET /api/comparison/?a=&b=&game_type=` | `comparison` | 15-stat block × 2 players + shot coords + arcs. `game_type` ∈ {all, regular, playoffs} |
| `GET /api/versus/?skater=&goalie=&game_type=` | `versus` | every shot the skater took at that goalie — totals, weapon breakdown, by-period split, shot coords (with `type_desc`), full goal log (capped at 200) |
| `GET /api/records/?category=&band=` | `records` | top-30 leaderboard. `category` ∈ {goals, assists, shots, hits, blocks, faceoffs, penalties_drawn}. `band` ∈ {all, hof, active}. Includes career span (start_year, end_year) per row. |
| `GET /api/games/<id>/` | `game_center` | scoreboard, 5-period line score (P1/P2/P3/OT/SO), full PBP (every event with coords), scoring summary, penalties, top performers |
| `GET /api/rink-lab/?bin=&era=` | `rink_lab` | SQL-binned hex heatmap (~1,200 cells). `bin` ∈ {2, 4, 8}. `era=modern` filters to 2005+; `era=all` includes all history. |
| `GET /api/rink-lab/bin/?x=&y=&bin=` | `rink_bin` | drill into one cell — shot count, goals, conversion, top-5 shooters, shot-type breakdown |
| `GET /api/eras/` | `eras` | full G/GP curve by season (107 points), 8 era cards, 3-snapshot spatial drift (1994/2009/2024), 5 peak-decade points-leaders |

### Real-data sanity checks (must reproduce)

These are baked into the design and the Playwright tests. If they don't reproduce, the **query** is wrong, not the design:

| Player / metric | Expected |
|---|---|
| Ovechkin (`8471214`) career goals | **1,038** |
| Crosby (`8471675`) career faceoff wins | **14,640** |
| Matt Martin (`8474709`) career hits delivered | **4,148** |
| John Carlson (`8474590`) career shot blocks | **2,425** |
| Records top 3 (`category=goals`) | Ovechkin 1,038 / Gretzky 1,029 / Howe 870 |
| Ovi peak season | **72 goals**, 2007-08 (NOT 65 — we count all game types per the brief; design's 65 is the official-stats figure) |
| `landing.counts` | 7,112,166 events · 69,712 games · 8,660 players |
| Ovi × Lundqvist (`8468685`) | 104 shots / 10 goals |

### Query patterns & performance

The `events_event` table is 7.11M rows. **Always rely on the indexes** in `events/models.py`:

```python
indexes = [
    models.Index(fields=["type_desc", "primary_player"]),
    models.Index(fields=["type_desc", "secondary_player"]),
    models.Index(fields=["type_desc", "goalie"]),
    models.Index(fields=["game", "period", "period_time"]),
]
```

**Patterns the existing endpoints use:**

- `Event.objects.filter(primary_player=p).values_list('type_desc').annotate(n=Count('id'))` — one round trip gives all per-type counts. See `_player_stats_block` (`api/views.py:580`).
- `Event.objects.filter(type_desc=Event.GOAL, primary_player=p).values('game__season').annotate(g=Count('id'))` — per-season aggregation. Used for career arc.
- For shot density: `qs.extra(select={'bx': '(coord_x / N) * N', 'by': '(coord_y / N) * N'}).values('bx', 'by').annotate(...)` — SQL-side binning. **Critical for rink-lab** — fetching individual rows is a non-starter at 1.16M shots. See `rink_lab` (`api/views.py:980`).
- Always include `goalie__isnull=False` (or whichever FK) when grouping by a nullable FK, or you'll get a phantom "None" row.

**Slowest endpoints (empirically):**
- `/api/rink-lab/` — ~80-150ms (SQL bin aggregation across all shots)
- `/api/eras/` — ~200ms (5 decade queries × `.first()` + 3 spatial-drift bin queries)
- `/api/players/<id>/` for Ovechkin — ~150ms (many sub-queries: counts per type_desc, career arc, shot map up to 6k rows, faced goalies)

If you add caching, the eras endpoint is the best candidate — its data only changes once per night.

### Shared helpers (top of `api/views.py`)

- `_player_brief(p)` — canonical player serialization (id, names, slug, position, sweater, is_active, headshot_url, flags)
- `_season_label(19421943)` → `"1942-43"`
- `_season_year(19421943)` → `1942`
- `_game_type_filter(game_type)` → `{}` | `{"game__game_type": 2}` | `{"game__game_type": 3}` — pass through `**gt` to ORM filters
- `_player_stats_block(p, gt_filter)` — 15-stat dict used by comparison
- `_shot_coords(p, limit, gt_filter)` — list of `{coord_x, coord_y, type_desc}` capped at `limit`
- `_career_arc(p, gt_filter)` — per-season goals series
- `_goalie_profile(p)` — full goalie response shape (separate code path from skater)

When adding new endpoints, lean on these — don't duplicate the player-serialization or season-label logic.

---

## Schema (post-redesign)

Three apps, three tables. The 2023-era 8-event-tables-and-string-player-names design is gone; legacy code preserved as `*_legacy.py` for reference (never imported).

### `players_player`

Keyed on `nhl_api_id` directly (no UUID, no autoincrement). Bio fields are nullable because old players' API responses are sparser.

Notable fields: `full_name` (denormalized for search), `position` (single letter `C/L/R/D/G`), `shoots_catches`, `birth_city/state_province/country`, `height_cm`, `weight_kg`, `in_hhof`, `in_top_100`, `player_slug`, `sweater_number`, `is_active`, `headshot_url`. Indexes on `(last_name, first_name)`, `player_slug`, `position`.

### `games_game`

Keyed on the NHL `game_id` (`YYYYTTNNNN`). Includes `season` (int, e.g. `19421943`), `game_type` (`1=preseason / 2=regular / 3=playoff / 4=all-star`), `game_date`, team abbrevs, scores, `venue`, `game_state` (`OFF/FINAL/LIVE/FUT`).

### `events_event`

**Single unified table** with a `type_desc` discriminator, replacing the 8 legacy `events_*` tables.

Each event has up to four player FKs (`primary_player`, `secondary_player`, `tertiary_player`, `goalie`). Their semantics depend on `type_desc`:

| `type_desc`    | `primary_player` | `secondary_player` | `tertiary_player` | `goalie`         |
|----------------|------------------|--------------------|-------------------|------------------|
| `goal`         | scorer           | assist1            | assist2           | goalie_against   |
| `shot-on-goal` | shooter          | —                  | —                 | goalie_against   |
| `hit`          | hitter           | hittee             | —                 | —                |
| `faceoff`      | winner           | loser              | —                 | —                |
| `giveaway`     | player           | —                  | —                 | —                |
| `takeaway`     | player           | —                  | —                 | —                |
| `penalty`      | committed_by     | drawn_by           | served_by         | —                |
| `blocked-shot` | blocker          | shooter            | —                 | —                |
| `missed-shot`  | shooter          | —                  | —                 | goalie_against   |

Plus type-specific fields (nullable): `shot_type`, `penalty_type`, `penalty_minutes`, `miss_reason`. Common fields: `period`, `period_time`, `period_type`, `coord_x/y`, `zone_code`, `situation_code` (4-digit string e.g. `"1551"`), `home_score`/`away_score` at event time. `nhl_event_id` is unique globally (string, not int — looks numeric but isn't).

### Migration history

```
players: 0001 → 0002 → 0003_drop_legacy_player → 0004_initial (new schema)
games:   0001 → 0002_drop_legacy_games → 0003_initial (new schema)
events:  0001 → ... → 0007_alter_event_id_max_length
                   → 0008_drop_legacy_event_models
                   → 0009_initial (Event)
```

**`migrations/` was gitignored** in the original repo — recovered from a personal backup in May 2026. **Do not re-add `migrations` to `.gitignore`.**

---

## Edge cases & data facts

These are facts about the underlying NHL data, not bugs in our code:

1. **Pre-2005 games have no shot/hit/faceoff/giveaway/takeaway/blocked/missed-shot data** — only `goal` and `penalty`. The NHL didn't record those events back then. Frontend has graceful degradation for pre-modern players (no shot map, "PRE-2005 · NO COORDINATES" placeholder).
2. **The 2004-05 lockout season returns no schedule** — ingestion skips it; doesn't appear in `games_game`.
3. **2012-13 was lockout-shortened** (806 games vs ~1,300 normal). 2019-20 was COVID-shortened.
4. **Ovi peak = 72 goals in 2007-08, not 65** — we count all game types (shootout/preseason/all-star) where official NHL stats don't. Same reason Ovi's career goals are 1,038 here vs 853 in the brief.
5. **`event_id` is `varchar`** — looks numeric (`191702000110249363`) but is a string. Don't cast.
6. **The 2025-26 season is in progress** — the API returns `gameState` of `OFF`/`FINAL`/`LIVE`/`FUT`. Ingest only fetches play-by-play for played games (`OFF`/`FINAL`).
7. **Coverage**: data goes back to 1917-18. 2005-06+ is the "modern era" with full PBP.
8. **NHL coords**: x ∈ [-100, 100], y ∈ [-42.5, 42.5]. The two nets sit at roughly (±89, 0). Frontend mirrors all shots to the right half so they collapse into a single offensive-zone heat map — but in raw data, a player's shots are split across both halves.

---

## Ingestion pipeline

Lives in `scripts/`, deliberately Django-free (just `requests` + threads). Writes JSON to disk; database loading is a separate later pass.

```
scripts/
  ingest_season.py     One-season fetch (schedule + play-by-play + player bios)
  ingest_all.py        Driver that calls ingest_season for every season the API knows
  ingest_status.py     Pretty-print current state of ingest_output/
  ingest_output/       Output dir (gitignored, ~4 GB)
    games/{id}.json    69k+ files, one per game, IDs are globally unique
    players/{id}.json  8k+ files, one per player, fetched once across seasons
    seasons/{YYYY-YYYY}/   per-season schedule.json + summary.json
    _state.json        run state for resume
    run.log
```

### Running an ingest

```bash
# one season
python3 scripts/ingest_season.py 1942

# every season the API knows about (resumable)
python3 scripts/ingest_all.py
python3 scripts/ingest_all.py --rate 5         # lower for fewer 429s
python3 scripts/ingest_all.py --retry-failed   # re-attempt seasons with stragglers
```

For long runs (the full 108-season backfill takes ~12-24 hours of wall clock):

```bash
caffeinate -dimsu nohup python3 scripts/ingest_all.py > /dev/null 2>&1 &
disown
```

`caffeinate -i` alone won't survive lid-close on battery. `-dimsu` blocks display/idle/disk/system/user-active sleep, but **only blocks system sleep on AC power** — keep the laptop plugged in.

### Rate limiting

The NHL API tolerates short bursts at >20 req/sec but throttles hard with 429s once you sustain >~10 req/sec. The script has a global `RateLimiter` capped at 8 req/sec with `Retry-After`-aware backoff. In practice we got ~0.7-2 games/sec sustained throughput. Going *lower* (e.g. `--rate 4`) is sometimes faster overall because it avoids the throttle.

### Resumability

The script is fully idempotent — game JSONs and player bios are skipped if already on disk. `_state.json` tracks per-season completion. The driver `ingest_all.py` skips seasons whose `summary.json` shows `games_failed=0` and `games_total>0`. (The `>0` check matters because a network blip can otherwise mark an empty bootstrap as "clean.")

### JSON → Postgres loader

A separate loader (TBD or in `scripts/`) walks `ingest_output/`, upserts via the natural keys (`nhl_api_id` for players, NHL `id` for games, `nhl_event_id` for events). Idempotent. Run against Heroku Postgres directly via `DATABASE_URL`.

---

## Database

Postgres on Heroku. Local dev uses Postgres in Docker.

```bash
# Heroku DB credentials (rotated periodically — re-export as needed)
export DATABASE_URL=$(heroku config:get DATABASE_URL -a nhl-api)
psql "$DATABASE_URL?sslmode=require"

# DBeaver: SSL mode `require`, leave cert fields blank.
# If validation fails, add Driver property:
#   sslfactory=org.postgresql.ssl.NonValidatingFactory
```

For local migration testing:

```bash
docker run -d --name anhls-pg-test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=anhls \
  -p 55432:5432 postgres:15
DJANGO_DEBUG=1 DATABASE_URL=postgres://postgres:test@127.0.0.1:55432/anhls \
  python3 manage.py migrate
```

**SQLite does not work** for migrations — `events.0006` defines `CharField` without `max_length`. Postgres tolerates it (treats as unlimited `varchar`); SQLite raises a syntax error. Always test against Postgres.

---

## Dev setup

```bash
cd nhl_stats_api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# minimum env vars
export DJANGO_DEBUG=1                                  # enables dev mode + dummy SECRET_KEY
export DATABASE_URL=$(heroku config:get DATABASE_URL -a nhl-api)
# or for local: postgres://postgres:test@127.0.0.1:55432/anhls

python3 manage.py check
python3 manage.py runserver 8000
```

Quick endpoint sanity:

```bash
curl -s http://127.0.0.1:8000/api/landing/ | python3 -m json.tool | head -30
curl -s http://127.0.0.1:8000/api/players/8471214/ | python3 -c "import sys,json; d=json.load(sys.stdin); print('ovi goals:', d['kpis']['goals'])"
```

`requirements.txt` is intentionally minimal — Django, cors-headers, dj-database-url, psycopg, gunicorn, python-dotenv, requests. The original file was UTF-16 encoded (!) and bundled `discord.py`, `aiohttp`, `multidict`, `bs4`, `pipenv` from another project. None of those are imported.

---

## Settings

`config/settings.py` reads:
- `DJANGO_SECRET_KEY` — required in prod, falls back to a dev-only placeholder when `DJANGO_DEBUG=1`
- `DJANGO_DEBUG` — `"1"` enables debug mode (default off)
- `DJANGO_ALLOWED_HOSTS` — comma-separated, appended to baseline of `nhl-api.herokuapp.com`, `127.0.0.1`, `localhost`
- `DATABASE_URL` — standard `dj_database_url` format

CORS allows `localhost:5173`, `nhl-stats.vercel.app`, `anhls.com`, `www.anhls.com`.

---

## Gotchas (for future agents)

1. **Project package is `config/`, not `nhl_stats_api/`** — `manage.py` and `Procfile` reference `config.settings` and `config.wsgi`.
2. **Don't add `migrations` back to `.gitignore`.**
3. **Heroku router 30s limit** — anything that scrapes the NHL API live cannot live behind an HTTP request. Make it a `manage.py` command or one-off dyno.
4. **`heroku config:get DATABASE_URL -a nhl-api` requires CLI auth as the gosummer.com account** — not `austin@virlo.ai`. If you get "You do not have access to the app nhl-api," run `heroku login` as `austin@gosummer.com`.
5. **`api/views.py` is intentionally one file** — endpoints are thin, share helpers, and the cohesion is worth more than a forced split. If it exceeds ~1500 lines, consider splitting by resource (`api/views/players.py`, etc.) but only then.
6. **Don't add DRF or serializers** — the API surface is small enough that inline `JsonResponse(...)` dicts are clearer and faster than a serializer hierarchy.
7. **Don't memoize per-request** — Django's QuerySet caching already handles within-request reuse. Add `cache_page` decorators if you need cross-request caching (e.g. eras endpoint).
8. **Adding a new filter** to comparison/versus: follow the `game_type` pattern — `_game_type_filter()` returns a `**kwargs` dict, threaded into every `Event.objects.filter()` call via `**gt`. Don't try to mutate the queryset at the call site.
9. **Pre-2005 player profile**: the schema returns empty `shot_map`, `shot_types`, `faced_goalies`. The frontend handles this — don't add backend padding/fake data.
10. **The `ledger` block on `/api/landing/`** queries top-1 per metric across the entire `events_event` table — runs ~250ms cold. If landing perf becomes an issue, cache this.
