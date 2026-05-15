"""
Management command para sembrar datos iniciales.

Crea:
  - 2 tenants: 'acme-corp' (Tenant A) y 'globex-inc' (Tenant B)
  - 3 reportes por cada tenant (para que el endpoint /api/reports/.../ devuelva data)

Uso:
    python manage.py seed_data
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from reportes.models import Tenant, Report


TENANTS = [
    {"name": "Acme Corporation", "slug": "acme-corp"},
    {"name": "Globex Inc", "slug": "globex-inc"},
]

SAMPLE_REPORTS = [
    {
        "title": "AWS cost breakdown — Q1 2026",
        "period": "2026-Q1",
        "total_cost_usd": "12450.75",
        "payload": {
            "by_service": {"EC2": 6200.00, "S3": 1200.50, "RDS": 4050.25, "Other": 1000.00},
            "currency": "USD",
        },
    },
    {
        "title": "GCP cost breakdown — Q1 2026",
        "period": "2026-Q1",
        "total_cost_usd": "8720.40",
        "payload": {
            "by_service": {"ComputeEngine": 5100.00, "CloudStorage": 920.00, "BigQuery": 2700.40},
            "currency": "USD",
        },
    },
    {
        "title": "Monthly snapshot — Apr 2026",
        "period": "2026-04",
        "total_cost_usd": "4150.20",
        "payload": {"by_provider": {"AWS": 2800.00, "GCP": 1350.20}},
    },
]


class Command(BaseCommand):
    help = "Crea tenants y reportes iniciales para el Sprint 3."

    def handle(self, *args, **kwargs):
        for t_data in TENANTS:
            tenant, created = Tenant.objects.get_or_create(
                slug=t_data["slug"],
                defaults={"name": t_data["name"]},
            )
            verb = "Created" if created else "Already existed"
            self.stdout.write(f"  {verb}: {tenant}")

            # Crear reportes solo si el tenant aún no tiene ninguno
            if not tenant.reports.exists():
                for r in SAMPLE_REPORTS:
                    Report.objects.create(
                        tenant=tenant,
                        title=r["title"],
                        period=r["period"],
                        total_cost_usd=Decimal(r["total_cost_usd"]),
                        payload=r["payload"],
                    )
                self.stdout.write(
                    f"    → {len(SAMPLE_REPORTS)} sample reports created"
                )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
