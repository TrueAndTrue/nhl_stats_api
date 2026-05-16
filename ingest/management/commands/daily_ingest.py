"""Fetch any games the DB is missing since its latest completed game.

    python manage.py daily_ingest                # default catch-up to yesterday
    python manage.py daily_ingest --through 2026-05-10
    python manage.py daily_ingest --max-days 7   # safety cap

Production cron (Heroku Scheduler add-on, daily at 10:00 UTC):
    python manage.py daily_ingest && python manage.py refresh_landing_mvs

Setup:
    heroku addons:create scheduler:standard -a nhl-api
    heroku addons:open scheduler -a nhl-api   # web UI to add the job
"""

from __future__ import annotations

import logging
import time
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ingest.daily import run_daily_ingest


class Command(BaseCommand):
    help = "Daily incremental ingest from the NHL API into Postgres."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--through",
            help="End date (YYYY-MM-DD). Defaults to yesterday.",
            default=None,
        )
        parser.add_argument(
            "--max-days",
            type=int,
            default=None,
            help="Refuse to run if the gap is wider than this many days.",
        )
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **opts) -> None:
        if opts["verbose"]:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

        through = None
        if opts["through"]:
            try:
                through = date.fromisoformat(opts["through"])
            except ValueError as e:
                raise CommandError(f"invalid --through date: {e}")

        t0 = time.perf_counter()
        try:
            report = run_daily_ingest(through=through, max_days=opts["max_days"])
        except RuntimeError as e:
            raise CommandError(str(e))

        elapsed = time.perf_counter() - t0
        self.stdout.write(self.style.SUCCESS(
            f"ingest complete in {elapsed:.1f}s: "
            f"days={report.days_fetched} games={report.games_fetched} "
            f"events={report.events_inserted} new_players={report.new_players} "
            f"incomplete_skipped={report.games_skipped_incomplete} "
            f"missing_player_skips={report.missing_player_skips} "
            f"failed={len(report.games_failed)}"
        ))
        if report.games_failed:
            self.stdout.write(self.style.WARNING(f"failed game ids: {report.games_failed}"))
