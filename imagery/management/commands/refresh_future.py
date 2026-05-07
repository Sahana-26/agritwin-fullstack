from datetime import date

from django.core.management.base import BaseCommand

from imagery.services import seed_future_runs


class Command(BaseCommand):
    help = "Process newly completed future 10-day windows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--until",
            type=str,
            help="End date in YYYY-MM-DD. Defaults to today.",
        )
        parser.add_argument(
            "--include-partial",
            action="store_true",
            help="Also process the currently incomplete trailing window.",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Reprocess windows even if they are already ready.",
        )

    def handle(self, *args, **options):
        until = options.get("until")
        include_partial = options.get("include_partial", False)
        rebuild = options.get("rebuild", False)

        if until:
            year, month, day = [int(v) for v in until.split("-")]
            until_date = date(year, month, day)
        else:
            until_date = date.today()

        runs = seed_future_runs(
            until_date,
            completed_only=not include_partial,
            skip_ready=not rebuild,
        )

        mode_label = "all windows" if include_partial else "completed 10-day windows"
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(runs)} future runs through {until_date.isoformat()} ({mode_label})."
            )
        )