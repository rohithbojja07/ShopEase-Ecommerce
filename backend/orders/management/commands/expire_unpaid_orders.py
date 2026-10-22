from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order, OrderStatus
from orders.services import OrderError, cancel_order


class Command(BaseCommand):
    help = "Cancel unpaid orders whose payment window has passed and release their stock."

    def handle(self, *args, **options):
        overdue = Order.objects.filter(
            status=OrderStatus.PLACED, expires_at__lt=timezone.now()
        )
        cancelled = 0
        for order in overdue:
            try:
                cancel_order(order, note="Payment window expired.")
                cancelled += 1
            except OrderError:
                continue
        self.stdout.write(self.style.SUCCESS(f"Cancelled {cancelled} unpaid order(s)."))
