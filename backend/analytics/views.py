from django.db.models import Count
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import StaffPermission
from orders.models import Order, OrderStatus
from . import services


class DashboardView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {"get": "analytics.view_sales_analytics"}

    def get(self, request):
        return Response(services.dashboard())


class SalesAnalyticsView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {"get": "analytics.view_sales_analytics"}

    def get(self, request):
        period = request.query_params.get("period", "daily")
        if period not in services.PERIODS:
            raise ValidationError({
                "period": "Choose daily, weekly, monthly, or yearly."
            })

        buckets = None
        raw_buckets = request.query_params.get("buckets")
        if raw_buckets is not None:
            try:
                buckets = int(raw_buckets)
            except (TypeError, ValueError):
                raise ValidationError({
                    "buckets": "Provide a whole number between 1 and 365."
                })

            if not 1 <= buckets <= 365:
                raise ValidationError({
                    "buckets": "Provide a number between 1 and 365."
                })

        return Response({
            "series": services.sales_series(period, buckets)
        })


class ProductsAnalyticsView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {"get": "analytics.view_product_analytics"}

    def get(self, request):
        limit = self._integer_param(request, "limit", 10, 1, 100)
        min_reviews = self._integer_param(
            request, "min_reviews", 1, 1, 10000
        )
        return Response(
            services.product_stats(
                limit=limit,
                min_reviews=min_reviews,
            )
        )

    @staticmethod
    def _integer_param(request, name, default, minimum, maximum):
        raw = request.query_params.get(name)
        if raw is None:
            return default

        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({
                name: f"Provide a whole number between {minimum} and {maximum}."
            })

        if not minimum <= value <= maximum:
            raise ValidationError({
                name: f"Provide a number between {minimum} and {maximum}."
            })
        return value


class CustomersAnalyticsView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {"get": "analytics.view_customer_analytics"}

    def get(self, request):
        days = self._integer_param(request, "days", 30, 1, 365)
        limit = self._integer_param(request, "limit", 10, 1, 100)
        return Response(
            services.customer_stats(days=days, limit=limit)
        )

    @staticmethod
    def _integer_param(request, name, default, minimum, maximum):
        raw = request.query_params.get(name)
        if raw is None:
            return default

        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({
                name: f"Provide a whole number between {minimum} and {maximum}."
            })

        if not minimum <= value <= maximum:
            raise ValidationError({
                name: f"Provide a number between {minimum} and {maximum}."
            })
        return value


class TopProductsView(ProductsAnalyticsView):
    pass


class OrderStatusAnalyticsView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {"get": "analytics.view_sales_analytics"}

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
            ]
        })

