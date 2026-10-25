from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.db.models import (
    Count, DateField, F, IntegerField, OuterRef, Subquery, Sum, Value,
)
from django.db.models.functions import Coalesce, Trunc
from django.utils import timezone

from core.staffapi.queries import MONEY, ZERO, customers_queryset
from inventory.models import Inventory
from orders.models import Order, OrderItem, Refund
from payments.models import Payment
from products.models import Product
from reviews.queries import rating_annotations

User = get_user_model()

# "Sold" = paid and not returned or cancelled.
SOLD_STATUSES = ["CONFIRMED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]
PENDING_STATUSES = ["PLACED", "CONFIRMED", "PACKED"]
RETURNED_STATUSES = ["RETURN_REQUESTED", "RETURNED", "REFUNDED"]
PERIODS = {"daily": ("day", 30), "weekly": ("week", 12), "monthly": ("month", 12), "yearly": ("year", 5)}


def money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def local_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def next_month(day):
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def net_revenue(start=None, end=None):
    """Successful payments minus partial refunds. Cancelled and fully refunded orders count as 0."""
    payments = Payment.objects.filter(status="SUCCESS")
    refunds = Refund.objects.filter(payment__status="SUCCESS")
    if start is not None:
        payments = payments.filter(paid_at__gte=start)
        refunds = refunds.filter(processed_at__gte=start)
    if end is not None:
        payments = payments.filter(paid_at__lt=end)
        refunds = refunds.filter(processed_at__lt=end)
    gross = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    returned = refunds.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return gross - returned


def dashboard():
    today = timezone.localdate()
    day_start, day_end = local_start(today), local_start(today + timedelta(days=1))
    month_start, month_end = local_start(today.replace(day=1)), local_start(next_month(today))
    low = Inventory.objects.filter(
        available_stock__lte=F("low_stock_threshold"),
        variant__is_active=True, variant__product__is_active=True,
    )
    units = OrderItem.objects.filter(order__status__in=SOLD_STATUSES).aggregate(n=Sum("quantity"))["n"]
    low_items = [
        {
            "sku": item.variant.sku,
            "product": item.variant.product.name,
            "available": item.available_stock,
            "threshold": item.low_stock_threshold,
        }
        for item in low.select_related("variant__product").order_by("available_stock", "id")[:10]
    ]
    return {
        "total_sales": units or 0,
        "revenue": money(net_revenue()),
        "todays_revenue": money(net_revenue(day_start, day_end)),
        "monthly_revenue": money(net_revenue(month_start, month_end)),
        "total_orders": Order.objects.count(),
        "total_customers": User.objects.filter(is_staff=False).count(),
        "total_products": Product.objects.filter(is_active=True).count(),
        "low_stock_variants": low.count(),
        "low_stock_products": low.values("variant__product").distinct().count(),
        "low_stock_items": low_items,
        "pending_orders": Order.objects.filter(status__in=PENDING_STATUSES).count(),
        "cancelled_orders": Order.objects.filter(status="CANCELLED").count(),
        "returned_orders": Order.objects.filter(status__in=RETURNED_STATUSES).count(),
    }


def bucket_starts(period, count, today):
    if period == "daily":
        return [today - timedelta(days=i) for i in range(count - 1, -1, -1)]
    if period == "weekly":
        monday = today - timedelta(days=today.weekday())
        return [monday - timedelta(weeks=i) for i in range(count - 1, -1, -1)]
    if period == "monthly":
        year, month, starts = today.year, today.month, []
        for _ in range(count):
            starts.append(date(year, month, 1))
            month -= 1
            if month == 0:
                month, year = 12, year - 1
        return starts[::-1]
    return [date(today.year - i, 1, 1) for i in range(count - 1, -1, -1)]


def sales_series(period, buckets=None):
    """Revenue and order count per day, week, month or year. Empty periods show 0."""
    kind, default = PERIODS[period]
    starts = bucket_starts(period, buckets or default, timezone.localdate())
    begin = local_start(starts[0])
    paid = {
        row["b"]: row
        for row in (
            Payment.objects.filter(status="SUCCESS", paid_at__gte=begin)
            .annotate(b=Trunc("paid_at", kind, output_field=DateField()))
            .values("b")
            .annotate(revenue=Sum("amount"), orders=Count("order", distinct=True))
            .order_by()
        )
    }
    refunded = {
        row["b"]: row["total"]
        for row in (
            Refund.objects.filter(payment__status="SUCCESS", processed_at__gte=begin)
            .annotate(b=Trunc("processed_at", kind, output_field=DateField()))
            .values("b")
            .annotate(total=Sum("amount"))
            .order_by()
        )
    }
    series = []
    for start in starts:
        row = paid.get(start)
        revenue = (row["revenue"] if row else Decimal("0")) - refunded.get(start, Decimal("0"))
        series.append({
            "period": start.isoformat(),
            "orders": row["orders"] if row else 0,
            "revenue": money(revenue),
        })
    return series


def _product_row(product):
    return {
        "id": product.id,
        "name": product.name,
        "units_sold": product.units_sold,
        "revenue": money(product.sales_revenue),
        "views": product.view_count,
        "average_rating": round(product.average_rating, 2) if product.review_count else None,
        "review_count": product.review_count,
    }


def product_stats(limit=10, min_reviews=1):
    sold = OrderItem.objects.filter(
        variant__product=OuterRef("pk"), order__status__in=SOLD_STATUSES
    ).order_by().values("variant__product")
    products = Product.objects.filter(is_active=True).annotate(
        units_sold=Coalesce(
            Subquery(sold.annotate(u=Sum("quantity")).values("u"), output_field=IntegerField()),
            Value(0),
        ),
        sales_revenue=Coalesce(
            Subquery(sold.annotate(r=Sum("line_total")).values("r"), output_field=MONEY), ZERO
        ),
        **rating_annotations(),
    )
    rows = lambda queryset: [_product_row(p) for p in queryset[:limit]]
    return {
        "best_selling": rows(products.order_by("-units_sold", "-sales_revenue", "name")),
        "lowest_selling": rows(products.order_by("units_sold", "name")),
        "most_viewed": rows(products.order_by("-view_count", "name")),
        "highest_rated": rows(
            products.filter(review_count__gte=min_reviews)
            .order_by("-average_rating", "-review_count", "name")
        ),
    }


def customer_stats(days=30, limit=10):
    today = timezone.localdate()
    starts = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    joined = {
        row["b"]: row["n"]
        for row in (
            User.objects.filter(is_staff=False, date_joined__gte=local_start(starts[0]))
            .annotate(b=Trunc("date_joined", "day", output_field=DateField()))
            .values("b")
            .annotate(n=Count("id"))
            .order_by()
        )
    }
    customers = customers_queryset()
    total = customers.count()
    frequency = {str(n): customers.filter(order_count=n).count() for n in range(4)}
    frequency["4+"] = customers.filter(order_count__gte=4).count()
    returning = customers.filter(order_count__gte=2).count()
    active_orders = Order.objects.exclude(status="CANCELLED").filter(user__is_staff=False).count()
    top = customers.filter(net_spent__gt=0).order_by("-net_spent", "email")[:limit]
    return {
        "total_customers": total,
        "new_this_month": User.objects.filter(
            is_staff=False, date_joined__gte=local_start(today.replace(day=1))
        ).count(),
        "new_customers": [{"period": d.isoformat(), "count": joined.get(d, 0)} for d in starts],
        "returning_customers": returning,
        "repeat_rate_percent": round(returning / total * 100, 1) if total else 0.0,
        "order_frequency": frequency,
        "average_orders_per_customer": round(active_orders / total, 2) if total else 0.0,
        "top_customers": [
            {"id": c.id, "email": c.email, "orders": c.order_count, "net_spent": money(c.net_spent)}
            for c in top
        ],
    }
