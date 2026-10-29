from products.models import Product

PRODUCT_DETAILS = {
    6: {
        "features": [
            "Samsung flagship smartphone",
            "Dynamic AMOLED display",
            "Multi-camera photography system",
            "Android smartphone experience",
            "USB-C connectivity"
        ],
        "specs": {
            "Brand": "Samsung",
            "Product Type": "Smartphone",
            "Series": "Galaxy S24"
        }
    },
    7: {
        "features": [
            "Apple iPhone smartphone",
            "Super Retina display",
            "Dual-camera system",
            "Face ID authentication",
            "USB-C connectivity"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Smartphone",
            "Model": "iPhone 15"
        }
    },
    10: {
        "features": [
            "Dell laptop for everyday computing",
            "Built-in keyboard and touchpad",
            "Integrated display",
            "Wireless connectivity"
        ],
        "specs": {
            "Brand": "Dell",
            "Product Type": "Laptop",
            "Series": "Inspiron 15"
        }
    },
    16: {
        "features": [
            "Sony over-ear headphones",
            "Wireless Bluetooth connectivity",
            "Noise-cancelling functionality",
            "Built-in microphone"
        ],
        "specs": {
            "Brand": "Sony",
            "Product Type": "Wireless Headphones",
            "Model": "WH-1000XM5"
        }
    },
    18: {
        "features": [
            "Apple iPhone Pro smartphone",
            "Advanced camera system",
            "Face ID authentication",
            "USB-C connectivity"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Smartphone",
            "Model": "iPhone 15 Pro"
        }
    },
    19: {
        "features": [
            "Samsung Galaxy A-series smartphone",
            "5G mobile connectivity",
            "Multi-camera system",
            "Android operating system"
        ],
        "specs": {
            "Brand": "Samsung",
            "Product Type": "Smartphone",
            "Model": "Galaxy A55 5G"
        }
    },
    20: {
        "features": [
            "OnePlus flagship smartphone",
            "High-refresh-rate display",
            "Multi-camera system",
            "5G connectivity"
        ],
        "specs": {
            "Brand": "OnePlus",
            "Product Type": "Smartphone",
            "Model": "OnePlus 12"
        }
    },
    21: {
        "features": [
            "OnePlus Nord-series smartphone",
            "5G connectivity",
            "Multi-camera system",
            "Android operating system"
        ],
        "specs": {
            "Brand": "OnePlus",
            "Product Type": "Smartphone",
            "Model": "Nord CE4"
        }
    },
    25: {
        "features": [
            "Apple MacBook Air laptop",
            "Apple M2 chip",
            "macOS operating system",
            "Portable laptop design"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Laptop",
            "Model": "MacBook Air M2",
            "Processor": "Apple M2"
        }
    },
    26: {
        "features": [
            "Apple MacBook Pro laptop",
            "Apple M3 chip family",
            "macOS operating system",
            "High-resolution display"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Laptop",
            "Model": "MacBook Pro 14 M3",
            "Processor": "Apple M3"
        }
    },
    32: {
        "features": [
            "Apple wireless earbuds",
            "Active noise cancellation",
            "Transparency mode",
            "Charging case"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Wireless Earbuds",
            "Model": "AirPods Pro (2nd generation)"
        }
    },
    33: {
        "features": [
            "Apple wireless earbuds",
            "Open-ear design",
            "Wireless connectivity",
            "Charging case"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Wireless Earbuds",
            "Model": "AirPods (3rd generation)"
        }
    },
    34: {
        "features": [
            "Apple over-ear headphones",
            "Active noise cancellation",
            "Spatial audio support",
            "Wireless connectivity"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Over-ear Headphones",
            "Model": "AirPods Max"
        }
    },
    35: {
        "features": [
            "JBL wireless headphones",
            "Bluetooth connectivity",
            "Foldable design",
            "Built-in microphone"
        ],
        "specs": {
            "Brand": "JBL",
            "Product Type": "Wireless Headphones",
            "Model": "Tune 770NC"
        }
    },
    36: {
        "features": [
            "Apple smartwatch",
            "Fitness and activity tracking",
            "Heart-rate monitoring",
            "Smartphone notifications"
        ],
        "specs": {
            "Brand": "Apple",
            "Product Type": "Smartwatch",
            "Model": "Watch Series 9"
        }
    },
    37: {
        "features": [
            "Samsung smartwatch",
            "Fitness tracking",
            "Sleep tracking",
            "Smartphone notifications"
        ],
        "specs": {
            "Brand": "Samsung",
            "Product Type": "Smartwatch",
            "Model": "Galaxy Watch6"
        }
    },
    38: {
        "features": [
            "Fire-Boltt smartwatch",
            "Bluetooth calling features",
            "Fitness tracking",
            "Smartphone notifications"
        ],
        "specs": {
            "Brand": "Fire-Boltt",
            "Product Type": "Smartwatch",
            "Model": "Ninja Call Pro Plus"
        }
    },
    39: {
        "features": [
            "Garmin GPS smartwatch",
            "Fitness activity tracking",
            "Health monitoring features",
            "Smartphone connectivity"
        ],
        "specs": {
            "Brand": "Garmin",
            "Product Type": "Smartwatch",
            "Model": "Venu Sq 2"
        }
    }
}

updated = 0

for product_id, details in PRODUCT_DETAILS.items():
    product = Product.objects.filter(pk=product_id).first()

    if product is None:
        print(f"SKIPPED: Product ID {product_id} not found")
        continue

    if not product.key_features:
        product.key_features = details["features"]

    if not product.specifications:
        product.specifications = details["specs"]

    product.save(update_fields=["key_features", "specifications"])
    updated += 1
    print(f"Updated: {product.name}")

print(f"\nFinished. Products processed: {updated}")
