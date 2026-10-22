from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from coupons.models import Coupon

COUPONS = [
    dict(code="WELCOME10", description="10% off, up to 500", discount_type="PERCENT",
         value="10", min_order_value="500", max_discount="500", per_user_limit=1),
    dict(code="SALE20", description="20% off, up to 2000", discount_type="PERCENT",
         value="20", min_order_value="2000", max_discount="2000", per_user_limit=5),
    dict(code="FESTIVE500", description="Flat 500 off on orders above 5000",
         discount_type="FIXED", value="500", min_order_value="5000",
         usage_limit=100, per_user_limit=1),
    dict(code="NEWUSER", description="15% off for first-time customers, up to 1000",
         discount_type="PERCENT", value="15", min_order_value="0",
         max_discount="1000", per_user_limit=1),
]


class Command(BaseCommand):
    help = "Create the sample coupons (safe to run more than once)."

    def handle(self, *args, **options):
        created = 0
        for data in COUPONS:
            data = dict(data)
            code = data.pop("code")
            for key in ("value", "min_order_value", "max_discount"):
                if key in data:
                    data[key] = Decimal(data[key])
            data["valid_until"] = timezone.now() + timedelta(days=365)
            _, was_created = Coupon.objects.get_or_create(code=code, defaults=data)
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Done. {created} new coupon(s) created."))
