from django.db import models

from core.models import TimeStampedModel


class Inventory(TimeStampedModel):
    variant = models.OneToOneField(
        "products.ProductVariant", on_delete=models.CASCADE, related_name="inventory"
    )
    opening_stock = models.PositiveIntegerField(default=0)
    available_stock = models.PositiveIntegerField(default=0)
    reserved_stock = models.PositiveIntegerField(default=0)
    sold_stock = models.PositiveIntegerField(default=0)
    returned_stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    class Meta:
        verbose_name_plural = "inventory"
        ordering = ["variant__sku"]
        indexes = [models.Index(fields=["available_stock"])]

    def __str__(self):
        return f"{self.variant.sku}: {self.available_stock} available"

    @property
    def is_low_stock(self):
        return self.available_stock <= self.low_stock_threshold
