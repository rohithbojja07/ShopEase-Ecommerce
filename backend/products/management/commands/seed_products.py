from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from products.models import Brand, Category, Product, ProductVariant, SubCategory

# Old demo data removed before loading (fashion + retired electronics samples)
OLD_PRODUCT_SLUGS = [
    "classic-cotton-t-shirt", "slim-fit-jeans", "running-sneakers",
    "wireless-headphones", "casual-shirt", "casio-vintage-analog", "oneplus-12r",
]
OLD_SUBCATEGORY_SLUGS = ["t-shirts", "jeans", "sneakers", "headphones", "analog-watches"]
OLD_CATEGORY_SLUGS = ["clothing", "footwear", "electronics"]
OLD_BRAND_SLUGS = ["urbanwear", "stepup", "soundwave", "casio"]

# (name, category, subcategory, brand, discount %, featured, description,
#  [(sku, spec, color, price)])
PRODUCTS = [
    # ---------------- Mobiles ----------------
    ("Apple iPhone 15", "Mobiles", "Smartphones", "Apple", "5", True,
     "Dynamic Island, 48MP main camera and USB-C.",
     [("APL-IP15-128-BLK", "128GB", "Black", "79900"),
      ("APL-IP15-256-BLK", "256GB", "Black", "89900"),
      ("APL-IP15-128-BLU", "128GB", "Blue", "79900")]),
    ("Apple iPhone 15 Pro", "Mobiles", "Smartphones", "Apple", "4", True,
     "Titanium design with a pro camera system.",
     [("APL-IP15P-128-NAT", "128GB", "Natural Titanium", "134900"),
      ("APL-IP15P-256-BLU", "256GB", "Blue Titanium", "144900")]),
    ("Samsung Galaxy S24", "Mobiles", "Smartphones", "Samsung", "8", True,
     "Flagship smartphone with AMOLED display and triple camera.",
     [("SAM-S24-128-BLK", "8GB/128GB", "Onyx Black", "74999"),
      ("SAM-S24-256-BLK", "8GB/256GB", "Onyx Black", "79999"),
      ("SAM-S24-256-VIO", "8GB/256GB", "Cobalt Violet", "79999")]),
    ("Samsung Galaxy A55 5G", "Mobiles", "Smartphones", "Samsung", "10", False,
     "Mid-range 5G smartphone with a bright AMOLED screen.",
     [("SAM-A55-128-NVY", "8GB/128GB", "Awesome Navy", "39999"),
      ("SAM-A55-256-LIL", "8GB/256GB", "Awesome Lilac", "42999")]),
    ("OnePlus 12", "Mobiles", "Smartphones", "OnePlus", "8", True,
     "Flagship phone with fast charging and a 120Hz display.",
     [("OP-12-256-BLK", "12GB/256GB", "Silky Black", "64999"),
      ("OP-12-512-GRN", "16GB/512GB", "Flowy Emerald", "69999")]),
    ("OnePlus Nord CE4", "Mobiles", "Smartphones", "OnePlus", "10", False,
     "Value 5G phone with a smooth display and big battery.",
     [("OP-CE4-128-CHR", "8GB/128GB", "Dark Chrome", "24999"),
      ("OP-CE4-256-CEL", "8GB/256GB", "Celadon Marble", "26999")]),
    ("Redmi Note 13 Pro", "Mobiles", "Smartphones", "Xiaomi", "12", False,
     "200MP camera smartphone with a large AMOLED display.",
     [("RMI-N13P-128-BLK", "8GB/128GB", "Midnight Black", "25999"),
      ("RMI-N13P-256-PRP", "8GB/256GB", "Aurora Purple", "27999")]),
    ("Xiaomi 14", "Mobiles", "Smartphones", "Xiaomi", "7", False,
     "Compact flagship with a Leica-tuned camera system.",
     [("XMI-14-512-BLK", "12GB/512GB", "Black", "69999"),
      ("XMI-14-512-WHT", "12GB/512GB", "White", "69999")]),
    ("Google Pixel 8", "Mobiles", "Smartphones", "Google", "10", True,
     "Pixel camera with AI photo features and clean Android.",
     [("GOO-PX8-128-OBS", "8GB/128GB", "Obsidian", "75999"),
      ("GOO-PX8-256-HAZ", "8GB/256GB", "Hazel", "82999")]),
    ("Google Pixel 8a", "Mobiles", "Smartphones", "Google", "8", False,
     "Affordable Pixel with a great camera and long software support.",
     [("GOO-PX8A-128-BAY", "8GB/128GB", "Bay", "52999"),
      ("GOO-PX8A-256-POR", "8GB/256GB", "Porcelain", "59999")]),
    # ---------------- Laptops ----------------
    ("Apple MacBook Air M2", "Laptops", "Ultrabooks", "Apple", "6", True,
     "Thin and light laptop with the Apple M2 chip.",
     [("APL-MBA-8-256", "8GB/256GB", "Midnight", "99900"),
      ("APL-MBA-8-512", "8GB/512GB", "Starlight", "119900")]),
    ("Apple MacBook Pro 14 M3", "Laptops", "Ultrabooks", "Apple", "3", False,
     "Pro laptop with a Liquid Retina XDR display.",
     [("APL-MBP14-8-512", "8GB/512GB", "Space Grey", "169900"),
      ("APL-MBP14-16-1TB", "16GB/1TB", "Silver", "209900")]),
    ("Dell Inspiron 15", "Laptops", "Everyday Laptops", "Dell", "12", True,
     "15.6 inch laptop for study and office work.",
     [("DEL-INS15-8-512", "8GB/512GB", "Silver", "54990"),
      ("DEL-INS15-16-512", "16GB/512GB", "Silver", "62990")]),
    ("Dell XPS 13", "Laptops", "Ultrabooks", "Dell", "8", False,
     "Premium compact laptop with a near edge-to-edge display.",
     [("DEL-XPS13-16-512", "16GB/512GB", "Platinum", "129990"),
      ("DEL-XPS13-32-1TB", "32GB/1TB", "Graphite", "159990")]),
    ("HP Pavilion 14", "Laptops", "Ultrabooks", "HP", "10", False,
     "Slim and light 14 inch laptop with long battery life.",
     [("HP-PAV14-16-512", "16GB/512GB", "Natural Silver", "68990"),
      ("HP-PAV14-16-1TB", "16GB/1TB", "Warm Gold", "76990")]),
    ("HP Victus 15", "Laptops", "Gaming Laptops", "HP", "12", False,
     "Gaming laptop with dedicated graphics and a fast display.",
     [("HP-VIC15-16-512", "16GB/512GB", "Mica Silver", "74990"),
      ("HP-VIC15-16-1TB", "16GB/1TB", "Performance Blue", "84990")]),
    ("Lenovo IdeaPad Slim 3", "Laptops", "Everyday Laptops", "Lenovo", "15", False,
     "Lightweight everyday laptop for students.",
     [("LEN-IPS3-8-512", "8GB/512GB", "Arctic Grey", "42990"),
      ("LEN-IPS3-16-512", "16GB/512GB", "Abyss Blue", "49990")]),
    ("Lenovo IdeaPad Gaming 3", "Laptops", "Gaming Laptops", "Lenovo", "15", True,
     "Gaming laptop with dedicated graphics and a 144Hz display.",
     [("LEN-IPG3-16-512", "16GB/512GB", "Shadow Black", "72990"),
      ("LEN-IPG3-16-1TB", "16GB/1TB", "Onyx Grey", "81990")]),
    ("ASUS Vivobook 15", "Laptops", "Everyday Laptops", "ASUS", "14", False,
     "Everyday 15.6 inch laptop with a full HD display.",
     [("ASU-VB15-8-512", "8GB/512GB", "Quiet Blue", "44990"),
      ("ASU-VB15-16-512", "16GB/512GB", "Indie Black", "51990")]),
    ("ASUS ROG Strix G16", "Laptops", "Gaming Laptops", "ASUS", "9", True,
     "High performance gaming laptop with a 16 inch display.",
     [("ASU-ROG16-16-512", "16GB/512GB", "Eclipse Gray", "124990"),
      ("ASU-ROG16-16-1TB", "16GB/1TB", "Volt Green", "139990")]),
    # ---------------- Audio ----------------
    ("Apple AirPods Pro (2nd generation)", "Audio", "Earbuds", "Apple", "5", True,
     "Active noise cancelling earbuds with a MagSafe charging case.",
     [("APL-APP2-WHT", "", "White", "24900")]),
    ("Apple AirPods (3rd generation)", "Audio", "Earbuds", "Apple", "5", False,
     "Wireless earbuds with spatial audio.",
     [("APL-AP3-WHT", "", "White", "18900")]),
    ("Apple AirPods Max", "Audio", "Over-Ear Headphones", "Apple", "4", False,
     "Over-ear headphones with high fidelity sound.",
     [("APL-APM-GRY", "", "Space Grey", "59900"),
      ("APL-APM-SLV", "", "Silver", "59900")]),
    ("Sony WH-1000XM5", "Audio", "Over-Ear Headphones", "Sony", "10", True,
     "Wireless noise cancelling headphones with 30 hour battery.",
     [("SON-XM5-BLK", "", "Black", "29990"),
      ("SON-XM5-SLV", "", "Silver", "29990")]),
    ("JBL Tune 770NC", "Audio", "Over-Ear Headphones", "JBL", "20", False,
     "Wireless over-ear headphones with noise cancelling.",
     [("JBL-T770-BLK", "", "Black", "7999"),
      ("JBL-T770-BLU", "", "Blue", "7999")]),
    ("boAt Airdopes 141", "Audio", "Earbuds", "boAt", "40", False,
     "True wireless earbuds with long playback.",
     [("BOT-AD141-BLK", "", "Black", "1499"),
      ("BOT-AD141-WHT", "", "White", "1499")]),
    # ---------------- Watches ----------------
    ("Apple Watch SE", "Watches", "Smartwatches", "Apple", "5", True,
     "Smartwatch with fitness tracking and crash detection.",
     [("APL-WSE-40-MID", "40mm", "Midnight", "29900"),
      ("APL-WSE-44-STR", "44mm", "Starlight", "32900")]),
    ("Apple Watch Series 9", "Watches", "Smartwatches", "Apple", "5", True,
     "Bright always-on display with advanced health sensors.",
     [("APL-WS9-41-PNK", "41mm", "Pink", "41900"),
      ("APL-WS9-45-MID", "45mm", "Midnight", "44900")]),
    ("Samsung Galaxy Watch6", "Watches", "Smartwatches", "Samsung", "10", False,
     "Round AMOLED smartwatch with sleep and body tracking.",
     [("SAM-GW6-40-GRA", "40mm", "Graphite", "29999"),
      ("SAM-GW6-44-SLV", "44mm", "Silver", "32999")]),
    ("Noise ColorFit Pro 4", "Watches", "Smartwatches", "Noise", "30", False,
     "Bluetooth calling smartwatch with a bright AMOLED screen.",
     [("NOI-CFP4-BLK", "", "Jet Black", "4999"),
      ("NOI-CFP4-BLU", "", "Navy Blue", "4999")]),
    ("Fire-Boltt Ninja Call Pro Plus", "Watches", "Smartwatches", "Fire-Boltt", "50", False,
     "Budget smartwatch with Bluetooth calling.",
     [("FBT-NCPP-BLK", "", "Black", "1799"),
      ("FBT-NCPP-BLU", "", "Blue", "1799")]),
    ("Garmin Venu Sq 2", "Watches", "Smartwatches", "Garmin", "6", False,
     "GPS fitness smartwatch with a long battery life.",
     [("GAR-VSQ2-SLT", "", "Slate", "24990"),
      ("GAR-VSQ2-CRM", "", "Cream Gold", "24990")]),
]


class Command(BaseCommand):
    help = "Remove old demo products and load the electronics catalog."

    def remove_old_samples(self):
        new_slugs = {slugify(item[0]) for item in PRODUCTS}
        old_slugs = [s for s in OLD_PRODUCT_SLUGS if s not in new_slugs]
        Product.objects.filter(slug__in=old_slugs).delete()
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
