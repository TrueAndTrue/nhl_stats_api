"""Materialized views for /api/eras/, /api/rink-lab/, /api/records/.

Same pattern as 0001 — refreshed nightly by `manage.py refresh_landing_mvs`.

Eras (4 MVs): curve, cards, drift, peaks.
Rink-lab (3 MVs): bins (parameterized on bin_size + era), distance histogram, decade histogram.
Records (2 MVs): leaderboards (parameterized on category + band), goal-type breakdown.
"""

from django.db import migrations


CREATE_SQL = r"""
-- ═══════════════════════════════════════════════════════════════════════════
-- ERAS endpoint
-- ═══════════════════════════════════════════════════════════════════════════

-- ── mv_eras_curve ─────────────────────────────────────────────────────────
-- Season-by-season scoring curve (regular season only). 107 rows.
CREATE MATERIALIZED VIEW mv_eras_curve AS
SELECT
    season,
    (season / 10000)::int AS year,
    COUNT(*) AS games,
    ROUND(
        COALESCE(SUM(home_score + away_score), 0)::numeric
        / NULLIF(COUNT(*), 0),
        2
    )::float AS gpg
FROM games_game
WHERE game_type = 2
GROUP BY season
ORDER BY season;

CREATE UNIQUE INDEX mv_eras_curve_pk ON mv_eras_curve (season);


-- ── mv_eras_cards ─────────────────────────────────────────────────────────
-- 8 era cards: aggregated GPG + hero scorer (top goal scorer in era).
CREATE MATERIALIZED VIEW mv_eras_cards AS
WITH eras(ord, label, lo, hi, accent, description) AS (
    VALUES
        (1, 'Pre-modern',   19171918, 19411942, 'ice',
         'Forward passing was illegal until 1929. Goalies stayed on their feet. The puck was offense; the rink, a duel.'),
        (2, 'Original Six', 19421943, 19661967, 'ice',
         'Six teams played each other 14 times a year. Rivalries calcified. Howe and Richard set the template for the modern winger.'),
        (3, 'Expansion',    19671968, 19781979, 'red',
         'The league doubled, then doubled again. Goaltending was still nearly maskless. Goals followed the talent dilution.'),
        (4, 'Run-and-Gun',  19791980, 19921993, 'red',
         'The Edmonton dynasty rewired the league. Five future Hall of Famers on one power play. Gretzky scored 92 in 80 games.'),
        (5, 'Dead-puck',    19931994, 20032004, 'ice',
         'Neutral-zone trap. Goalie equipment ballooned. Goals fell to a generational low — 5.1/GP at the trough.'),
        (6, 'Post-lockout', 20052006, 20112012, 'red',
         'Two-line pass, smaller pads, shootouts. Crosby, Ovechkin, Malkin arrived together. Scoring rebounded.'),
        (7, 'Analytics',    20122013, 20192020, 'ice',
         'Corsi, expected goals, line-matching. Defense-first systems compressed the slot. McDavid still played like the rules didn''t apply.'),
        (8, 'Slot shot',    20202021, 20992100, 'red',
         'High-volume slot scoring is the new orthodoxy. Goalies stop more pucks than ever. The shots that count come from one place.')
),
gpg_per_era AS (
    SELECT
        e.ord,
        SUM(g.games) AS games,
        SUM(g.games * g.gpg) AS goals,
        ROUND(SUM(g.games * g.gpg)::numeric / NULLIF(SUM(g.games), 0), 2)::float AS gpg,
        MIN(g.year) AS year_start,
        MAX(g.year) AS year_end
    FROM eras e
    JOIN mv_eras_curve g ON g.season BETWEEN e.lo AND e.hi
    GROUP BY e.ord
),
hero_per_era AS (
    SELECT
        ord, primary_player_id, n,
        ROW_NUMBER() OVER (PARTITION BY ord ORDER BY n DESC) AS rn
    FROM (
        SELECT
            e.ord,
            ev.primary_player_id,
            COUNT(*) AS n
        FROM eras e
        JOIN games_game g ON g.season BETWEEN e.lo AND e.hi
        JOIN events_event ev ON ev.game_id = g.id
        WHERE ev.type_desc = 'goal'
          AND ev.primary_player_id IS NOT NULL
        GROUP BY e.ord, ev.primary_player_id
    ) sub
)
SELECT
    e.ord,
    e.label,
    e.accent,
    e.description,
    g.year_start,
    g.year_end,
    g.gpg,
    g.games,
    h.primary_player_id AS hero_id,
    p.full_name AS hero_name,
    h.n AS hero_goals
FROM eras e
LEFT JOIN gpg_per_era g ON g.ord = e.ord
LEFT JOIN hero_per_era h ON h.ord = e.ord AND h.rn = 1
LEFT JOIN players_player p ON p.nhl_api_id = h.primary_player_id;

CREATE UNIQUE INDEX mv_eras_cards_pk ON mv_eras_cards (ord);


-- ── mv_eras_drift ─────────────────────────────────────────────────────────
-- Spatial drift: top-300 (bin_size=4) shot coords for 3 specific seasons.
CREATE MATERIALIZED VIEW mv_eras_drift AS
WITH snapshots(year, season) AS (
    VALUES (1994, 19941995), (2009, 20092010), (2024, 20242025)
),
ranked AS (
    SELECT
        s.year,
        s.season,
        (e.coord_x / 4) * 4 AS bx,
        (e.coord_y / 4) * 4 AS by,
        COUNT(*) AS n
    FROM snapshots s
    JOIN games_game g ON g.season = s.season
    JOIN events_event e ON e.game_id = g.id
    WHERE e.type_desc IN ('shot-on-goal', 'goal')
      AND e.coord_x IS NOT NULL
      AND e.coord_y IS NOT NULL
    GROUP BY s.year, s.season, (e.coord_x / 4) * 4, (e.coord_y / 4) * 4
),
top300 AS (
    SELECT
        year, season, bx, by, n,
        ROW_NUMBER() OVER (PARTITION BY year ORDER BY n DESC) AS rn
    FROM ranked
)
SELECT year, season, bx, by, n
FROM top300
WHERE rn <= 300;

CREATE UNIQUE INDEX mv_eras_drift_pk ON mv_eras_drift (year, bx, by);


-- ── mv_eras_peaks ─────────────────────────────────────────────────────────
-- Top-scoring season per decade band (with assist counts for points total).
CREATE MATERIALIZED VIEW mv_eras_peaks AS
WITH decades(decade, lo, hi) AS (
    VALUES
        (1970, 19701971, 19791980),
        (1980, 19801981, 19891990),
        (1990, 19901991, 19992000),
        (2000, 20002001, 20092010),
        (2020, 20202021, 20992100)
),
goals_per_player_season AS (
    SELECT
        d.decade,
        g.season,
        ev.primary_player_id AS player_id,
        COUNT(*) AS g
    FROM decades d
    JOIN games_game g ON g.season >= d.lo AND g.season < d.hi
    JOIN events_event ev ON ev.game_id = g.id
    WHERE ev.type_desc = 'goal' AND ev.primary_player_id IS NOT NULL
    GROUP BY d.decade, g.season, ev.primary_player_id
),
top_per_decade AS (
    SELECT decade, season, player_id, g,
           ROW_NUMBER() OVER (PARTITION BY decade ORDER BY g DESC) AS rn
    FROM goals_per_player_season
),
peak AS (
    SELECT decade, season, player_id, g FROM top_per_decade WHERE rn = 1
)
SELECT
    pk.decade,
    pk.season,
    pk.player_id,
    p.first_name,
    p.last_name,
    pk.g AS goals,
    (
        SELECT COUNT(*) FROM events_event a1
        WHERE a1.type_desc = 'goal'
          AND a1.secondary_player_id = pk.player_id
          AND a1.game_id IN (SELECT id FROM games_game WHERE season = pk.season)
    ) + (
        SELECT COUNT(*) FROM events_event a2
        WHERE a2.type_desc = 'goal'
          AND a2.tertiary_player_id = pk.player_id
          AND a2.game_id IN (SELECT id FROM games_game WHERE season = pk.season)
    ) AS assists
FROM peak pk
JOIN players_player p ON p.nhl_api_id = pk.player_id;

CREATE UNIQUE INDEX mv_eras_peaks_pk ON mv_eras_peaks (decade);


-- ═══════════════════════════════════════════════════════════════════════════
-- RINK-LAB endpoint
-- ═══════════════════════════════════════════════════════════════════════════

-- ── mv_rink_bins ──────────────────────────────────────────────────────────
-- Top-1200 (x,y) bins per (bin_size, era) combination. 6 combos × ~1200 rows.
CREATE MATERIALIZED VIEW mv_rink_bins AS
WITH params(bin_size, era) AS (
    VALUES (2, 'all'), (2, 'modern'), (4, 'all'), (4, 'modern'), (8, 'all'), (8, 'modern')
),
binned AS (
    SELECT
        p.bin_size,
        p.era,
        (e.coord_x / p.bin_size) * p.bin_size AS bx,
        (e.coord_y / p.bin_size) * p.bin_size AS by,
        COUNT(*) AS n,
        COUNT(*) FILTER (WHERE e.type_desc = 'goal') AS g
    FROM params p
    JOIN events_event e ON e.type_desc IN ('shot-on-goal', 'goal')
                       AND e.coord_x IS NOT NULL
                       AND e.coord_y IS NOT NULL
    LEFT JOIN games_game gm ON gm.id = e.game_id
    WHERE p.era = 'all' OR gm.season >= 20052006
    GROUP BY p.bin_size, p.era, (e.coord_x / p.bin_size) * p.bin_size, (e.coord_y / p.bin_size) * p.bin_size
),
ranked AS (
    SELECT bin_size, era, bx, by, n, g,
           ROW_NUMBER() OVER (PARTITION BY bin_size, era ORDER BY n DESC) AS rn
    FROM binned
)
SELECT bin_size, era, bx, by, n, g
FROM ranked
WHERE rn <= 1200;

CREATE UNIQUE INDEX mv_rink_bins_pk ON mv_rink_bins (bin_size, era, bx, by);


-- ── mv_rink_distance ──────────────────────────────────────────────────────
-- Distance-from-nearer-net histogram (modern era, offensive zone only).
CREATE MATERIALIZED VIEW mv_rink_distance AS
WITH bins(bin_ft) AS (VALUES (0),(10),(20),(30),(40),(50),(60),(70),(80)),
raw AS (
    SELECT
        CASE
            WHEN (CAST(SQRT(POWER(89 - ABS(e.coord_x), 2) + POWER(e.coord_y, 2)) AS INTEGER) / 10) * 10 > 80
            THEN 80
            ELSE (CAST(SQRT(POWER(89 - ABS(e.coord_x), 2) + POWER(e.coord_y, 2)) AS INTEGER) / 10) * 10
        END AS dbin,
        e.type_desc
    FROM events_event e
    JOIN games_game g ON g.id = e.game_id
    WHERE e.type_desc IN ('shot-on-goal', 'goal')
      AND e.coord_x IS NOT NULL
      AND e.coord_y IS NOT NULL
      AND e.zone_code = 'O'
      AND g.season >= 20052006
),
agg AS (
    SELECT
        dbin,
        COUNT(*) AS shots,
        COUNT(*) FILTER (WHERE type_desc = 'goal') AS goals
    FROM raw
    GROUP BY dbin
)
SELECT
    b.bin_ft,
    COALESCE(a.shots, 0) AS shots,
    COALESCE(a.goals, 0) AS goals
FROM bins b
LEFT JOIN agg a ON a.dbin = b.bin_ft
ORDER BY b.bin_ft;

CREATE UNIQUE INDEX mv_rink_distance_pk ON mv_rink_distance (bin_ft);


-- ── mv_rink_decade ────────────────────────────────────────────────────────
-- Goal totals per decade. Decade derived from season (YYYY_YYYY+1) → YYYY.
CREATE MATERIALIZED VIEW mv_rink_decade AS
SELECT
    ((g.season / 10000) / 10) * 10 AS decade,
    COUNT(*) AS goals
FROM events_event e
JOIN games_game g ON g.id = e.game_id
WHERE e.type_desc = 'goal'
GROUP BY ((g.season / 10000) / 10) * 10
ORDER BY decade;

CREATE UNIQUE INDEX mv_rink_decade_pk ON mv_rink_decade (decade);


-- ═══════════════════════════════════════════════════════════════════════════
-- RECORDS endpoint
-- ═══════════════════════════════════════════════════════════════════════════

-- ── mv_records ────────────────────────────────────────────────────────────
-- Top-30 per (category, band). 7 categories × 3 bands × 30 = 630 rows.
-- `role_kind` distinguishes assists (secondary_player) from everything else.
CREATE MATERIALIZED VIEW mv_records AS
WITH cats(category, type_desc, role_kind, label) AS (
    VALUES
        ('goals',           'goal',         'primary',   'Career goals'),
        ('assists',         'goal',         'secondary', 'Career assists (primary)'),
        ('hits',            'hit',          'primary',   'Career hits delivered'),
        ('blocks',          'blocked-shot', 'primary',   'Career shot blocks'),
        ('faceoffs',        'faceoff',      'primary',   'Career faceoff wins'),
        ('penalties_drawn', 'penalty',      'secondary', 'Career penalties drawn'),
        ('shots',           'shot-on-goal', 'primary',   'Career shots on goal')
),
counts AS (
    -- primary-role counts
    SELECT 'primary'::text AS role_kind, c.category, c.label,
           e.primary_player_id AS player_id, COUNT(*) AS n
    FROM cats c
    JOIN events_event e ON e.type_desc = c.type_desc AND e.primary_player_id IS NOT NULL
    WHERE c.role_kind = 'primary'
    GROUP BY c.category, c.label, e.primary_player_id
    UNION ALL
    -- secondary-role counts (assists + penalties_drawn)
    SELECT 'secondary'::text AS role_kind, c.category, c.label,
           e.secondary_player_id AS player_id, COUNT(*) AS n
    FROM cats c
    JOIN events_event e ON e.type_desc = c.type_desc AND e.secondary_player_id IS NOT NULL
    WHERE c.role_kind = 'secondary'
    GROUP BY c.category, c.label, e.secondary_player_id
),
spans AS (
    -- career start/end per player (computed once across all event roles)
    SELECT player_id,
           MIN(season) AS start_season,
           MAX(season) AS end_season
    FROM (
        SELECT e.primary_player_id   AS player_id, g.season FROM events_event e
            JOIN games_game g ON g.id = e.game_id WHERE e.primary_player_id IS NOT NULL
        UNION ALL
        SELECT e.secondary_player_id AS player_id, g.season FROM events_event e
            JOIN games_game g ON g.id = e.game_id WHERE e.secondary_player_id IS NOT NULL
    ) all_roles
    GROUP BY player_id
),
expanded AS (
    -- emit one row per (category, band) combination
    SELECT c.category, c.label, 'all'    AS band, c.player_id, c.n FROM counts c
    UNION ALL
    SELECT c.category, c.label, 'hof'    AS band, c.player_id, c.n FROM counts c
        JOIN players_player p ON p.nhl_api_id = c.player_id WHERE p.in_hhof
    UNION ALL
    SELECT c.category, c.label, 'active' AS band, c.player_id, c.n FROM counts c
        JOIN players_player p ON p.nhl_api_id = c.player_id WHERE p.is_active
),
ranked AS (
    SELECT category, label, band, player_id, n,
           ROW_NUMBER() OVER (PARTITION BY category, band ORDER BY n DESC) AS rank
    FROM expanded
)
SELECT
    r.category, r.label, r.band, r.rank, r.n AS value,
    r.player_id,
    p.first_name, p.last_name, p.position,
    p.is_active, p.in_hhof,
    s.start_season, s.end_season
FROM ranked r
JOIN players_player p ON p.nhl_api_id = r.player_id
LEFT JOIN spans s ON s.player_id = r.player_id
WHERE r.rank <= 30;

CREATE UNIQUE INDEX mv_records_pk ON mv_records (category, band, rank);


-- ── mv_goal_types ─────────────────────────────────────────────────────────
-- Career goal-type breakdown for records_overview sidebar.
CREATE MATERIALIZED VIEW mv_goal_types AS
SELECT shot_type, COUNT(*) AS n
FROM events_event
WHERE type_desc = 'goal' AND shot_type IS NOT NULL
GROUP BY shot_type
ORDER BY n DESC;

CREATE UNIQUE INDEX mv_goal_types_pk ON mv_goal_types (shot_type);
"""


DROP_SQL = """
DROP MATERIALIZED VIEW IF EXISTS mv_goal_types;
DROP MATERIALIZED VIEW IF EXISTS mv_records;
DROP MATERIALIZED VIEW IF EXISTS mv_rink_decade;
DROP MATERIALIZED VIEW IF EXISTS mv_rink_distance;
DROP MATERIALIZED VIEW IF EXISTS mv_rink_bins;
DROP MATERIALIZED VIEW IF EXISTS mv_eras_peaks;
DROP MATERIALIZED VIEW IF EXISTS mv_eras_drift;
DROP MATERIALIZED VIEW IF EXISTS mv_eras_cards;
DROP MATERIALIZED VIEW IF EXISTS mv_eras_curve;
"""


class Migration(migrations.Migration):
    dependencies = [("ingest", "0001_materialized_views")]
    operations = [migrations.RunSQL(sql=CREATE_SQL, reverse_sql=DROP_SQL)]
