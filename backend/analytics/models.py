from django.db import models


class AnalyticsAccess(models.Model):
    """No table. It only exists to hold the dashboard permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_sales_analytics", "Can view sales analytics"),
            ("view_product_analytics", "Can view product analytics"),
            ("view_customer_analytics", "Can view customer analytics"),
        ]
