from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem, OrderStatus
from payments.models import Payment, PaymentStatus
from products.models import Product


class StaffAnalyticsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class DashboardView(APIView):
    permission_classes = [StaffAnalyticsPermission]

    def get(self, request):
        User = get_user_model()

        successful_payments = Payment.objects.filter(
            status=PaymentStatus.SUCCESS
        )

        return Response({
            "total_customers": User.objects.filter(
                is_staff=False
            ).count(),
            "total_products": Product.objects.filter(
                is_active=True
            ).count(),
            "total_orders": Order.objects.count(),
            "total_revenue": successful_payments.aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00"),
            "successful_payments": successful_payments.count(),
            "pending_orders": Order.objects.filter(
                status__in=[
                    OrderStatus.PLACED,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PACKED,
                ]
            ).count(),
            "delivered_orders": Order.objects.filter(
                status=OrderStatus.DELIVERED
            ).count(),
            "cancelled_orders": Order.objects.filter(
                status=OrderStatus.CANCELLED
            ).count(),
        })


class SalesAnalyticsView(APIView):
    permission_classes = [StaffAnalyticsPermission]

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            raise ValidationError({
                "days": "Provide a whole number between 1 and 365."
            })

        if not 1 <= days <= 365:
            raise ValidationError({
                "days": "Provide a number between 1 and 365."
            })

        start_date = timezone.now() - timedelta(days=days)

        sales = (
            Payment.objects.filter(
                status=PaymentStatus.SUCCESS,
                paid_at__gte=start_date,
                paid_at__isnull=False,
            )
            .annotate(date=TruncDate("paid_at"))
            .values("date")
            .annotate(
                revenue=Sum("amount"),
                payment_count=Count("id"),
            )
            .order_by("date")
        )

        return Response({
            "period_days": days,
            "results": [
                {
                    "date": item["date"],
                    "revenue": item["revenue"],
                    "successful_payments": item["payment_count"],
                }
                for item in sales
            ],
        })


class TopProductsView(APIView):
    permission_classes = [StaffAnalyticsPermission]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
        except (TypeError, ValueError):
            raise ValidationError({
                "limit": "Provide a whole number between 1 and 100."
            })

        if not 1 <= limit <= 100:
            raise ValidationError({
                "limit": "Provide a number between 1 and 100."
            })

        products = (
            OrderItem.objects.filter(
                order__status=OrderStatus.DELIVERED
            )
            .values("variant__product_id", "product_name")
            .annotate(
                units_sold=Sum("quantity"),
                order_count=Count("order_id", distinct=True),
                sales_amount=Sum("line_total"),
            )
            .order_by("-units_sold", "-sales_amount")[:limit]
        )

        return Response({
            "results": list(products),
        })


class OrderStatusAnalyticsView(APIView):
    permission_classes = [StaffAnalyticsPermission]

    def get(self, request):
        counts = dict(
            Order.objects.values("status")
            .annotate(total=Count("id"))
            .values_list("status", "total")
        )

        return Response({
            "results": [
                {
                    "status": status.value,
                    "label": status.label,
                    "count": counts.get(status.value, 0),
                }
                for status in OrderStatus
            ],
        })
