from django.core.management.base import BaseCommand
from django.db import close_old_connections

from imagery.models import AnalysisRecord
from imagery.services import (
    RUN_SUMMARY_TYPE,
    get_or_create_run,
    historical_run_specs,
    process_run,
)


class Command(BaseCommand):
    help = "Process and store historical seasonal runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip runs whose summary record is already ready.",
        )
        parser.add_argument(
            "--from-record-key",
            type=str,
            default=None,
            help="Start from this record_key, e.g. historical_2019_pre_monsoon",
        )

    def handle(self, *args, **options):
        resume = options["resume"]
        from_record_key = options["from_record_key"]

        specs = historical_run_specs()

        started = from_record_key is None
        processed = 0
        skipped = 0

        for spec in specs:
            if not started:
                if spec["record_key"] != from_record_key:
                    continue
                started = True

            close_old_connections()

            existing = AnalysisRecord.objects.filter(
                analysis_type=RUN_SUMMARY_TYPE,
                record_key=spec["record_key"],
            ).first()

            if resume and existing and existing.status == "ready":
                skipped += 1
                self.stdout.write(f"Skipping ready: {spec['record_key']}")
                continue

            run = get_or_create_run(spec)
            self.stdout.write(f"Processing: {run.record_key} (current status: {run.status})")
            process_run(run)
            processed += 1

            close_old_connections()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Processed={processed}, Skipped ready={skipped}"
            )
        )