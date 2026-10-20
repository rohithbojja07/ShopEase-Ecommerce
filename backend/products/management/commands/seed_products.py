from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from products.models import Brand, Category, Product, ProductVariant, SubCategory

# Old fashion/demo sample data, removed before the electronics catalog is loaded
OLD_PRODUCT_SLUGS = [
    "classic-cotton-t-shirt",
    "slim-fit-jeans",
    "running-sneakers",
    "wireless-headphones",
    "casual-shirt",
]
OLD_SUBCATEGORY_SLUGS = ["t-shirts", "jeans", "sneakers", "headphones"]
OLD_CATEGORY_SLUGS = ["clothing", "footwear", "electronics"]
OLD_BRAND_SLUGS = ["urbanwear", "stepup", "soundwave"]

# (name, category, subcategory, brand, discount %, featured, description,
#  [(sku, spec, color, price)])
PRODUCTS = [
    # ---- Mobiles ----
    ("Samsung Galaxy S24", "Mobiles", "Smartphones", "Samsung", "8", True,
     "Flagship smartphone with AMOLED display and triple camera.",
     [("SAM-S24-128-BLK", "8GB/128GB", "Onyx Black", "74999"),
      ("SAM-S24-256-BLK", "8GB/256GB", "Onyx Black", "79999"),
      ("SAM-S24-256-VIO", "8GB/256GB", "Cobalt Violet", "79999")]),
    ("Apple iPhone 15", "Mobiles", "Smartphones", "Apple", "5", True,
     "Dynamic Island, 48MP main camera and USB-C.",
     [("APL-IP15-128-BLK", "128GB", "Black", "79900"),
      ("APL-IP15-256-BLK", "256GB", "Black", "89900"),
      ("APL-IP15-128-BLU", "128GB", "Blue", "79900")]),
    ("OnePlus 12R", "Mobiles", "Smartphones", "OnePlus", "10", False,
     "Fast charging smartphone with a smooth 120Hz display.",
     [("OP-12R-128-GRY", "8GB/128GB", "Iron Gray", "39999"),
      ("OP-12R-256-BLU", "16GB/256GB", "Cool Blue", "45999")]),
    ("Redmi Note 13 Pro", "Mobiles", "Smartphones", "Xiaomi", "12", False,
     "200MP camera smartphone with a large AMOLED display.",
     [("RMI-N13P-128-BLK", "8GB/128GB", "Midnight Black", "25999"),
      ("RMI-N13P-256-PRP", "8GB/256GB", "Aurora Purple", "27999")]),
    # ---- Laptops ----
    ("Dell Inspiron 15", "Laptops", "Everyday Laptops", "Dell", "12", True,
     "15.6 inch laptop for study and office work.",
     [("DEL-INS15-8-512", "8GB/512GB", "Silver", "54990"),
      ("DEL-INS15-16-512", "16GB/512GB", "Silver", "62990")]),
    ("HP Pavilion 14", "Laptops", "Ultrabooks", "HP", "10", False,
     "Slim and light 14 inch laptop with long battery life.",
     [("HP-PAV14-16-512", "16GB/512GB", "Natural Silver", "68990"),
      ("HP-PAV14-16-1TB", "16GB/1TB", "Warm Gold", "76990")]),
    ("Lenovo IdeaPad Gaming 3", "Laptops", "Gaming Laptops", "Lenovo", "15", True,
     "Gaming laptop with dedicated graphics and a 144Hz display.",
     [("LEN-IPG3-16-512", "16GB/512GB", "Shadow Black", "72990"),
      ("LEN-IPG3-16-1TB", "16GB/1TB", "Onyx Grey", "81990")]),
    # ---- Watches ----
    ("Apple Watch SE", "Watches", "Smartwatches", "Apple", "5", True,
     "Smartwatch with fitness tracking and crash detection.",
     [("APL-WSE-40-MID", "40mm", "Midnight", "29900"),
      ("APL-WSE-44-STR", "44mm", "Starlight", "32900")]),
    ("Noise ColorFit Pro 4", "Watches", "Smartwatches", "Noise", "30", False,
     "Bluetooth calling smartwatch with a bright AMOLED screen.",
     [("NOI-CFP4-BLK", "", "Jet Black", "4999"),
      ("NOI-CFP4-BLU", "", "Navy Blue", "4999")]),
    ("Casio Vintage Analog", "Watches", "Analog Watches", "Casio", "0", False,
     "Classic stainless steel analog watch.",
     [("CAS-VIN-SLV", "", "Silver", "3495"),
      ("CAS-VIN-GLD", "", "Gold", "3995")]),
    # ---- Audio ----
    ("Sony WH-1000XM5", "Audio", "Over-Ear Headphones", "Sony", "10", True,
     "Wireless noise cancelling headphones with 30 hour battery.",
     [("SON-XM5-BLK", "", "Black", "29990"),
      ("SON-XM5-SLV", "", "Silver", "29990")]),
    ("boAt Airdopes 141", "Audio", "Earbuds", "boAt", "40", False,
     "True wireless earbuds with 42 hour playback.",
     [("BOT-AD141-BLK", "", "Black", "1499"),
      ("BOT-AD141-WHT", "", "White", "1499")]),
]


class Command(BaseCommand):
    help = "Remove the old fashion samples and load an electronics catalog."

    def remove_old_samples(self):
        Product.objects.filter(slug__in=OLD_PRODUCT_SLUGS).delete()
        SubCategory.objects.filter(
            slug__in=OLD_SUBCATEGORY_SLUGS, products__isnull=True
        ).delete()
        Category.objects.filter(
            slug__in=OLD_CATEGORY_SLUGS,
            products__isnull=True,
            subcategories__isnull=True,
        ).delete()
        Brand.objects.filter(slug__in=OLD_BRAND_SLUGS, products__isnull=True).delete()

    def handle(self, *args, **options):
        self.remove_old_samples()
        created = 0
        for name, cat, sub, brand_name, discount, featured, desc, variants in PRODUCTS:
            category, _ = Category.objects.get_or_create(
                slug=slugify(cat), defaults={"name": cat}
            )
            subcategory, _ = SubCategory.objects.get_or_create(
                category=category, slug=slugify(sub), defaults={"name": sub}
            )
            brand, _ = Brand.objects.get_or_create(
                slug=slugify(brand_name), defaults={"name": brand_name}
            )
            product, was_created = Product.objects.get_or_create(
                slug=slugify(name),
                defaults={
                    "name": name,
                    "description": desc,
                    "category": category,
                    "subcategory": subcategory,
                    "brand": brand,
                    "discount_percent": Decimal(discount),
                    "is_featured": featured,
                },
            )
            created += int(was_created)
            for sku, spec, color, price in variants:
                ProductVariant.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "product": product,
                        "size": spec,
                        "color": color,
                        "price": Decimal(price),
                    },
                )
        self.stdout.write(
            self.style.SUCCESS(f"Done. {created} new product(s) created.")
        )
