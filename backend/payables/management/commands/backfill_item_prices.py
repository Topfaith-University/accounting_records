from django.core.management.base import BaseCommand
from neomodel import db


class Command(BaseCommand):
    help = (
        "One-off backfill: for Item nodes still carrying the old single "
        "unit_price property, copy it into both cost_price and selling_price, "
        "then remove the stale unit_price property. Safe to run multiple times."
    )

    def handle(self, *args, **options):
        results, _ = db.cypher_query(
            """
            MATCH (i:Item)
            WHERE i.unit_price IS NOT NULL
            SET i.cost_price = coalesce(i.cost_price, i.unit_price),
                i.selling_price = coalesce(i.selling_price, i.unit_price)
            REMOVE i.unit_price
            RETURN count(i) AS updated
            """
        )
        updated = results[0][0] if results else 0
        self.stdout.write(self.style.SUCCESS(f"Backfilled cost_price/selling_price for {updated} item(s)."))
