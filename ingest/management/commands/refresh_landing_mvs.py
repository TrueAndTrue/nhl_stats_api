"""Refresh the materialized views that back /api/landing/.

Uses CONCURRENTLY so reads aren't blocked — that's why each MV has a UNIQUE
index (see ingest/migrations/0001_materialized_views.py).

Runs as the final step of the daily ingest cron:
    python manage.py daily_ingest && python manage.py refresh_landing_mvs
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import connection

MVS = ["mv_ledger", "mv_era_buckets", "mv_site_counts"]


class Command(BaseCommand):
    help = "Refresh landing-page materialized views (CONCURRENTLY)."

    def handle(self, *args, **opts) -> None:
        # CONCURRENTLY cannot run inside a transaction
        connection.set_autocommit(True)
        try:
            for name in MVS:
                t0 = time.perf_counter()
                with connection.cursor() as cur:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}")
                elapsed = (time.perf_counter() - t0) * 1000
                self.stdout.write(self.style.SUCCESS(f"{name}: {elapsed:.0f}ms"))
        finally:
            connection.set_autocommit(False)
