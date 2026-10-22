from django.core.management.base import BaseCommand

from inventory.models import Inventory
from products.models import ProductVariant

LAST_ITEM_SKU = "GOO-PX8A-256-POR"  # exactly 1 in stock, for the "last item" demo


class Command(BaseCommand):
    help = "Give sample stock to variants that have none yet."

    def handle(self, *args, **options):
        updated = 0
        for index, variant in enumerate(ProductVariant.objects.order_by("sku")):
            inv, _ = Inventory.objects.get_or_create(variant=variant)
            if inv.opening_stock or inv.available_stock or inv.reserved_stock or inv.sold_stock:
                continue  # already has stock, leave it alone
            if variant.sku == LAST_ITEM_SKU:
                stock = 1
            elif index % 7 == 0:
                stock = 4  # shows up as low stock
            else:
                stock = 30
            inv.opening_stock = stock
            inv.available_stock = stock
            inv.save(update_fields=["opening_stock", "available_stock", "updated_at"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Stock set for {updated} variant(s)."))
