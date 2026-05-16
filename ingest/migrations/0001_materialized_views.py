"""Materialized views that back /api/landing/.

Three MVs, each refreshable independently via REFRESH MATERIALIZED VIEW
CONCURRENTLY (which requires a UNIQUE index on each MV).

Refreshed by `python manage.py refresh_landing_mvs` as the final step of the
daily ingest cron.
"""

from django.db import migrations


CREATE_SQL = """
-- ── mv_ledger ────────────────────────────────────────────────────────────────
-- Career top-1 by 4 metrics: goals, faceoffs won, hits delivered, blocks.
CREATE MATERIALIZED VIEW mv_ledger AS
WITH ranked AS (
    SELECT
        e.type_desc,
        e.primary_player_id,
        COUNT(*) AS n,
        ROW_NUMBER() OVER (PARTITION BY e.type_desc ORDER BY COUNT(*) DESC) AS rn
    FROM events_event e
    WHERE e.type_desc IN ('goal', 'faceoff', 'hit', 'blocked-shot')
      AND e.primary_player_id IS NOT NULL
    GROUP BY e.type_desc, e.primary_player_id
)
SELECT
    r.type_desc,
    CASE r.type_desc
        WHEN 'goal' THEN 'Career goals'
        WHEN 'faceoff' THEN 'Career faceoffs won'
        WHEN 'hit' THEN 'Career hits delivered'
        WHEN 'blocked-shot' THEN 'Career shot blocks'
    END AS metric,
    r.primary_player_id AS player_id,
    p.first_name,
    p.last_name,
    r.n AS value,
    p.is_active
FROM ranked r
JOIN players_player p ON p.nhl_api_id = r.primary_player_id
WHERE r.rn = 1;

CREATE UNIQUE INDEX mv_ledger_pk ON mv_ledger (type_desc);


-- ── mv_era_buckets ───────────────────────────────────────────────────────────
-- 8 era buckets: events + games count per era label.
CREATE MATERIALIZED VIEW mv_era_buckets AS
WITH eras(label, lo, hi, ord) AS (
    VALUES
        ('1917-29', 19171918, 19291930, 1),
        ('1930-49', 19301931, 19491950, 2),
        ('1950-69', 19501951, 19691970, 3),
        ('1970-89', 19701971, 19891990, 4),
        ('1990-99', 19901991, 19991999, 5),
        ('2000-09', 20001999, 20091999, 6),
        ('2010-19', 20101999, 20191999, 7),
        ('2020-26', 20201999, 20991999, 8)
),
event_counts AS (
    SELECT
        CASE
            WHEN g.season BETWEEN 19171918 AND 19291930 THEN '1917-29'
            WHEN g.season BETWEEN 19301931 AND 19491950 THEN '1930-49'
            WHEN g.season BETWEEN 19501951 AND 19691970 THEN '1950-69'
            WHEN g.season BETWEEN 19701971 AND 19891990 THEN '1970-89'
            WHEN g.season BETWEEN 19901991 AND 19991999 THEN '1990-99'
            WHEN g.season BETWEEN 20001999 AND 20091999 THEN '2000-09'
            WHEN g.season BETWEEN 20101999 AND 20191999 THEN '2010-19'
            WHEN g.season BETWEEN 20201999 AND 20991999 THEN '2020-26'
        END AS era,
        COUNT(*) AS events
    FROM events_event e
    JOIN games_game g ON g.id = e.game_id
    GROUP BY 1
),
game_counts AS (
    SELECT
        CASE
            WHEN season BETWEEN 19171918 AND 19291930 THEN '1917-29'
            WHEN season BETWEEN 19301931 AND 19491950 THEN '1930-49'
            WHEN season BETWEEN 19501951 AND 19691970 THEN '1950-69'
            WHEN season BETWEEN 19701971 AND 19891990 THEN '1970-89'
            WHEN season BETWEEN 19901991 AND 19991999 THEN '1990-99'
            WHEN season BETWEEN 20001999 AND 20091999 THEN '2000-09'
            WHEN season BETWEEN 20101999 AND 20191999 THEN '2010-19'
            WHEN season BETWEEN 20201999 AND 20991999 THEN '2020-26'
        END AS era,
        COUNT(*) AS games
    FROM games_game
    GROUP BY 1
)
SELECT
    eras.label AS era,
    eras.ord,
    COALESCE(ec.events, 0) AS events,
    COALESCE(gc.games, 0) AS games
FROM eras
LEFT JOIN event_counts ec ON ec.era = eras.label
LEFT JOIN game_counts gc ON gc.era = eras.label;

CREATE UNIQUE INDEX mv_era_buckets_pk ON mv_era_buckets (era);


-- ── mv_site_counts ───────────────────────────────────────────────────────────
-- Single-row roll-up of the 7 scalar counts on the landing page.
CREATE MATERIALIZED VIEW mv_site_counts AS
SELECT
    1 AS pk,  -- so we can have a unique index on a single-row MV
    (SELECT COUNT(*) FROM events_event) AS total_events,
    (SELECT COUNT(*) FROM games_game) AS total_games,
    (SELECT COUNT(*) FROM players_player) AS total_players,
    (SELECT COUNT(*) FROM events_event
        WHERE type_desc IN ('shot-on-goal', 'goal', 'missed-shot', 'blocked-shot')
        AND coord_x IS NOT NULL) AS shots_with_coords,
    (SELECT COUNT(DISTINCT season) FROM games_game) AS total_seasons,
    (SELECT COUNT(*) FROM players_player WHERE in_hhof) AS hhof,
    (SELECT COUNT(*) FROM players_player WHERE is_active) AS active;

CREATE UNIQUE INDEX mv_site_counts_pk ON mv_site_counts (pk);
"""


DROP_SQL = """
DROP MATERIALIZED VIEW IF EXISTS mv_site_counts;
DROP MATERIALIZED VIEW IF EXISTS mv_era_buckets;
DROP MATERIALIZED VIEW IF EXISTS mv_ledger;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("events", "0009_initial"),
        ("games", "0003_initial"),
        ("players", "0004_initial"),
    ]
    operations = [
        migrations.RunSQL(sql=CREATE_SQL, reverse_sql=DROP_SQL),
    ]
