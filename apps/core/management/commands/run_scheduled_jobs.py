from django.core.management.base import BaseCommand

from core.jobs import run_all_jobs


class Command(BaseCommand):
    help = "Run every idempotent INPROFIC scheduled maintenance job."

    def handle(self, *args, **options):
        completed = run_all_jobs(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(f"Completed {len(completed)} scheduled job(s)."))
