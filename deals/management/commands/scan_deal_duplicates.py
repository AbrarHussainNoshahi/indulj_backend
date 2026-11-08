from django.core.management.base import BaseCommand
from deals.models import Deal
from deals.duplicate_detector import detect_deal_duplicates


class Command(BaseCommand):
    help = "Scans all active and pending deals for duplicates against existing deals for the same restaurant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Clear all duplicate flags before re-scanning.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting existing deal duplicate flags...")
            Deal.objects.all().update(
                is_potential_duplicate=False,
                duplicate_of=None,
                duplicate_score=0.0,
                duplicate_reasons=[],
            )

        self.stdout.write("Scanning deals for potential duplicates...")
        deals = Deal.objects.filter(status__in=["active", "pending"]).order_by("id")
        flagged_count = 0

        for deal in deals:
            try:
                is_dup, match_deal, score, reasons = detect_deal_duplicates(deal)
                if is_dup and match_deal:
                    deal.is_potential_duplicate = True
                    deal.duplicate_of = match_deal
                    deal.duplicate_score = score
                    deal.duplicate_reasons = reasons
                    deal.save(update_fields=[
                        "is_potential_duplicate",
                        "duplicate_of",
                        "duplicate_score",
                        "duplicate_reasons",
                    ])
                    flagged_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Flagged Deal #{deal.id} ('{deal.title}') as duplicate of Deal #{match_deal.id} ('{match_deal.title}') with {score}% similarity"
                        )
                    )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error checking Deal #{deal.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Scan complete. Flagged {flagged_count} duplicate deal(s)."))

