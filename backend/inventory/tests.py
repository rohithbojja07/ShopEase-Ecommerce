import threading
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase

from products.models import Category, Product, ProductVariant

from .models import Inventory
from .services import (
    InsufficientStock,
    confirm_sale_many,
    release_many,
    reserve_many,
    restock_many,
)


def make_variant(sku="T-1", stock=10):
    category, _ = Category.objects.get_or_create(slug="test-cat", defaults={"name": "Test Cat"})
    product, _ = Product.objects.get_or_create(
        slug="test-product", defaults={"name": "Test Product", "category": category}
    )
    variant = ProductVariant.objects.create(
        product=product, sku=sku, size=sku, price=Decimal("100.00")
    )
    Inventory.objects.filter(variant=variant).update(opening_stock=stock, available_stock=stock)
    return variant


def stock_of(variant):
    return Inventory.objects.get(variant=variant)


class StockServiceTests(TestCase):
    def test_inventory_is_created_automatically_for_new_variant(self):
        variant = make_variant()
        self.assertTrue(Inventory.objects.filter(variant=variant).exists())

    def test_reserve_moves_available_to_reserved(self):
        variant = make_variant(stock=10)
        reserve_many([(variant.id, 3)])
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (7, 3))

    def test_cannot_reserve_more_than_available(self):
        variant = make_variant(stock=2)
        with self.assertRaises(InsufficientStock):
            reserve_many([(variant.id, 3)])
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (2, 0))

    def test_multi_item_reservation_is_all_or_nothing(self):
        ok = make_variant("A-1", stock=5)
        short = make_variant("A-2", stock=1)
        with self.assertRaises(InsufficientStock):
            reserve_many([(ok.id, 2), (short.id, 5)])
        self.assertEqual(stock_of(ok).available_stock, 5)  # untouched
        self.assertEqual(stock_of(short).available_stock, 1)

    def test_confirm_sale_moves_reserved_to_sold(self):
        variant = make_variant(stock=10)
        reserve_many([(variant.id, 4)])
        confirm_sale_many([(variant.id, 4)])
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock, inv.sold_stock), (6, 0, 4))

    def test_release_puts_reserved_stock_back(self):
        variant = make_variant(stock=10)
        reserve_many([(variant.id, 4)])
        release_many([(variant.id, 4)])
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (10, 0))

    def test_customer_return_counts_returned_stock(self):
        variant = make_variant(stock=10)
        reserve_many([(variant.id, 2)])
        confirm_sale_many([(variant.id, 2)])
        restock_many([(variant.id, 1)], returned=True)
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.sold_stock, inv.returned_stock), (9, 1, 1))

    def test_cancellation_restocks_without_counting_a_return(self):
        variant = make_variant(stock=10)
        reserve_many([(variant.id, 2)])
        confirm_sale_many([(variant.id, 2)])
        restock_many([(variant.id, 2)])
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.sold_stock, inv.returned_stock), (10, 0, 0))

    def test_cannot_restock_more_than_was_sold(self):
        variant = make_variant(stock=10)
        with self.assertRaises(ValueError):
            restock_many([(variant.id, 1)])

    def test_stock_stays_consistent_after_a_full_order_lifecycle(self):
        variant = make_variant(stock=20)
        reserve_many([(variant.id, 5)])
        confirm_sale_many([(variant.id, 5)])
        restock_many([(variant.id, 2)], returned=True)
        reserve_many([(variant.id, 3)])
        release_many([(variant.id, 3)])
        inv = stock_of(variant)
        total = inv.available_stock + inv.reserved_stock + inv.sold_stock
        self.assertEqual(total, inv.opening_stock)


class ConcurrencyTests(TransactionTestCase):
    """Real database transactions in parallel threads."""

    def test_last_item_can_only_be_reserved_once(self):
        variant = make_variant("LAST-1", stock=1)
        outcomes = []

        def attempt():
            try:
                reserve_many([(variant.id, 1)])
                outcomes.append("ok")
            except InsufficientStock:
                outcomes.append("sold_out")
            except Exception as exc:  # anything else is a real problem
                outcomes.append(f"error: {exc}")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("sold_out"), 9)
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (0, 1))
