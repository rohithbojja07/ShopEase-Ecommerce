from django.db import transaction

from .models import Inventory


class InsufficientStock(Exception):
    """Raised when a variant does not have enough available stock."""

    def __init__(self, variant_id, requested, available):
        self.variant_id = variant_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Variant {variant_id}: requested {requested}, only {available} available."
        )


def _merge(items):
    """items = [(variant_id, quantity), ...]; duplicates are added together."""
    merged = {}
    for variant_id, quantity in items:
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        merged[variant_id] = merged.get(variant_id, 0) + quantity
    return merged


def _lock(merged):
    """Lock the inventory rows in a fixed order (prevents deadlocks)."""
    rows = (
        Inventory.objects.select_for_update()
        .filter(variant_id__in=list(merged))
        .order_by("variant_id")
    )
    inventories = {row.variant_id: row for row in rows}
    missing = set(merged) - set(inventories)
    if missing:
        raise ValueError(f"No inventory record for variant(s): {sorted(missing)}")
    return inventories


@transaction.atomic
def _transfer(items, source, target, also=None):
    """Move stock from one bucket to another. All items succeed or none do."""
    merged = _merge(items)
    inventories = _lock(merged)

    for variant_id, quantity in merged.items():
        have = getattr(inventories[variant_id], source)
        if have < quantity:
            if source == "available_stock":
                raise InsufficientStock(variant_id, quantity, have)
            raise ValueError(
                f"Variant {variant_id}: cannot move {quantity} out of {source} (only {have})."
            )

    for variant_id, quantity in merged.items():
        inv = inventories[variant_id]
        setattr(inv, source, getattr(inv, source) - quantity)
        setattr(inv, target, getattr(inv, target) + quantity)
        fields = [source, target, "updated_at"]
        if also:
            setattr(inv, also, getattr(inv, also) + quantity)
            fields.append(also)
        inv.save(update_fields=fields)
    return inventories


def reserve_many(items):
    """Checkout started: available -> reserved."""
    return _transfer(items, "available_stock", "reserved_stock")


def release_many(items):
    """Payment failed or checkout expired: reserved -> available."""
    return _transfer(items, "reserved_stock", "available_stock")


def confirm_sale_many(items):
    """Payment succeeded: reserved -> sold."""
    return _transfer(items, "reserved_stock", "sold_stock")


def restock_many(items, returned=False):
    """Order cancelled or item returned: sold -> available.

    Pass returned=True for customer returns so returned_stock is counted too.
    """
    return _transfer(
        items, "sold_stock", "available_stock",
        also="returned_stock" if returned else None,
    )
