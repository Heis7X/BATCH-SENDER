from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from mailer.services import process_pending_jobs


class Command(BaseCommand):
    help = "Continuously process queued email recipient jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process one pass and exit.")
        parser.add_argument("--limit", type=int, default=20, help="Max queued recipients per pass.")
        parser.add_argument(
            "--sleep", type=float, default=5.0, help="Seconds to sleep between passes when idle."
        )
        parser.add_argument(
            "--pause-between-emails",
            type=float,
            default=0.0,
            help="Optional pause between sends, useful for gentle rate control.",
        )

    def handle(self, *args, **options):
        once = options["once"]
        limit = options["limit"]
        sleep_seconds = options["sleep"]
        pause_between_emails = options["pause_between_emails"]

        self.stdout.write(self.style.SUCCESS("Email worker started."))
        while True:
            processed = process_pending_jobs(limit=limit, pause_seconds=pause_between_emails)
            if processed:
                self.stdout.write(f"Processed {processed} recipient job(s).")
            elif once:
                self.stdout.write("No queued jobs found.")
            if once:
                break
            time.sleep(sleep_seconds)
