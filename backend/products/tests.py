from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APITestCase

from inventory.models import Inventory

from .models import Brand, Category, Product, ProductVariant


def make_product(name, category, brand, discount, variants):
    product = Product.objects.create(
        name=name,
        slug=name.lower().replace(" ", "-"),
        category=category,
        brand=brand,
        discount_percent=Decimal(discount),
    )
    for sku, size, color, price, stock in variants:
        variant = ProductVariant.objects.create(
            product=product, sku=sku, size=size, color=color, price=Decimal(price)
        )
        Inventory.objects.filter(variant=variant).update(
            opening_stock=stock, available_stock=stock
        )
    return product


class CatalogAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # reset the rate limiter between tests
        phones = Category.objects.create(name="Phones", slug="phones")
        laptops = Category.objects.create(name="Laptops", slug="laptops")
        acme = Brand.objects.create(name="Acme", slug="acme")
        zeta = Brand.objects.create(name="Zeta", slug="zeta")
        self.phone = make_product(
            "Acme Phone", phones, acme, "10",
            [("AP-1", "128GB", "Black", "1000.00", 5), ("AP-2", "256GB", "Blue", "1200.00", 5)],
        )
        self.laptop = make_product(
            "Zeta Laptop", laptops, zeta, "0", [("ZL-1", "8GB/512GB", "Silver", "50000.00", 3)]
        )
        self.tablet = make_product(
            "Acme Tablet", phones, acme, "5", [("AT-1", "64GB", "Grey", "20000.00", 0)]
        )

    def names(self, response):
        return [item["name"] for item in response.data["results"]]

    def test_list_is_public_and_paginated(self):
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_inactive_product_is_hidden(self):
        self.phone.is_active = False
        self.phone.save()
        self.assertNotIn("Acme Phone", self.names(self.client.get("/api/products/")))
        self.assertEqual(self.client.get(f"/api/products/{self.phone.id}/").status_code, 404)

    def test_filter_by_category(self):
        response = self.client.get("/api/products/?category=laptops")
        self.assertEqual(self.names(response), ["Zeta Laptop"])

    def test_filter_by_brand(self):
        response = self.client.get("/api/products/?brand=acme")
        self.assertEqual(sorted(self.names(response)), ["Acme Phone", "Acme Tablet"])

    def test_price_range_uses_the_discounted_price(self):
        # Acme Phone: 1000 with 10% off = 900
        response = self.client.get("/api/products/?min_price=850&max_price=950")
        self.assertEqual(self.names(response), ["Acme Phone"])

    def test_search_by_name(self):
        response = self.client.get("/api/products/?search=laptop")
        self.assertEqual(self.names(response), ["Zeta Laptop"])

    def test_filter_in_stock(self):
        response = self.client.get("/api/products/?in_stock=true")
        self.assertEqual(sorted(self.names(response)), ["Acme Phone", "Zeta Laptop"])

    def test_filter_by_color(self):
        response = self.client.get("/api/products/?color=blue")
        self.assertEqual(self.names(response), ["Acme Phone"])

    def test_ordering_by_final_price(self):
        response = self.client.get("/api/products/?ordering=final_min_price")
        self.assertEqual(self.names(response)[0], "Acme Phone")
        response = self.client.get("/api/products/?ordering=-final_min_price")
        self.assertEqual(self.names(response)[0], "Zeta Laptop")

    def test_detail_shows_variants_and_counts_views(self):
        response = self.client.get(f"/api/products/{self.phone.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["variants"]), 2)
        self.phone.refresh_from_db()
        self.assertEqual(self.phone.view_count, 1)

    def test_detail_does_not_expose_exact_stock(self):
        response = self.client.get(f"/api/products/{self.phone.id}/")
        variant = response.data["variants"][0]
        self.assertNotIn("available_stock", variant)
        self.assertIn("in_stock", variant)

    def test_inactive_variant_is_not_shown(self):
        ProductVariant.objects.filter(sku="AP-2").update(is_active=False)
        response = self.client.get(f"/api/products/{self.phone.id}/")
        self.assertEqual([v["sku"] for v in response.data["variants"]], ["AP-1"])
