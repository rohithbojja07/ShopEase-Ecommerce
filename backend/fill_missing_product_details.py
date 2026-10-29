from products.models import Product

details = {
    9: (
        ["Redmi smartphone", "High-resolution display", "Multi-camera system", "Android-based software"],
        {"Brand": "Xiaomi", "Model": "Redmi Note 13 Pro", "Type": "Smartphone"}
    ),
    11: (
        ["HP laptop", "Built-in keyboard and touchpad", "Integrated display", "Wireless connectivity"],
        {"Brand": "HP", "Model": "Pavilion 14", "Type": "Laptop"}
    ),
    12: (
        ["Lenovo gaming laptop", "Dedicated gaming-oriented design", "Built-in keyboard and touchpad", "Wireless connectivity"],
        {"Brand": "Lenovo", "Model": "IdeaPad Gaming 3", "Type": "Gaming Laptop"}
    ),
    13: (
        ["Apple smartwatch", "Fitness activity tracking", "Heart-rate monitoring", "Smartphone notifications"],
        {"Brand": "Apple", "Model": "Watch SE", "Type": "Smartwatch"}
    ),
    14: (
        ["Noise smartwatch", "Fitness tracking", "Smartphone notifications", "Watch-face customization"],
        {"Brand": "Noise", "Model": "ColorFit Pro 4", "Type": "Smartwatch"}
    ),
    17: (
        ["boAt wireless earbuds", "Bluetooth connectivity", "Portable charging case", "Built-in microphone"],
        {"Brand": "boAt", "Model": "Airdopes 141", "Type": "Wireless Earbuds"}
    ),
    22: (
        ["Xiaomi smartphone", "High-resolution display", "Multi-camera system", "Android-based software"],
        {"Brand": "Xiaomi", "Model": "Xiaomi 14", "Type": "Smartphone"}
    ),
    23: (
        ["Google Pixel smartphone", "Google Android experience", "Multi-camera photography", "Google AI features"],
        {"Brand": "Google", "Model": "Pixel 8", "Type": "Smartphone"}
    ),
    24: (
        ["Google Pixel smartphone", "Google Android experience", "AI-assisted photography", "Smartphone security features"],
        {"Brand": "Google", "Model": "Pixel 8a", "Type": "Smartphone"}
    ),
    27: (
        ["Dell laptop", "Portable laptop design", "Built-in keyboard and touchpad", "Wireless connectivity"],
        {"Brand": "Dell", "Model": "XPS 13", "Type": "Laptop"}
    ),
    28: (
        ["HP gaming laptop", "Gaming-oriented design", "Built-in keyboard and touchpad", "Wireless connectivity"],
        {"Brand": "HP", "Model": "Victus 15", "Type": "Gaming Laptop"}
    ),
    29: (
        ["Lenovo laptop", "Designed for everyday computing", "Built-in keyboard and touchpad", "Wireless connectivity"],
        {"Brand": "Lenovo", "Model": "IdeaPad Slim 3", "Type": "Laptop"}
    ),
    30: (
        ["ASUS laptop", "Portable laptop design", "Built-in keyboard and touchpad", "Wireless connectivity"],
        {"Brand": "ASUS", "Model": "Vivobook 15", "Type": "Laptop"}
    ),
    31: (
        ["ASUS ROG gaming laptop", "Gaming-oriented design", "High-performance product series", "Gaming-focused cooling design"],
        {"Brand": "ASUS", "Model": "ROG Strix G16", "Type": "Gaming Laptop"}
    ),
}

updated = 0

for product_id, (features, specs) in details.items():
    product = Product.objects.filter(pk=product_id).first()

    if product is None:
        print(f"SKIPPED: Product ID {product_id} not found")
        continue

    changed_fields = []

    if not product.key_features:
        product.key_features = features
        changed_fields.append("key_features")

    if not product.specifications:
        product.specifications = specs
        changed_fields.append("specifications")

    if changed_fields:
        product.save(update_fields=changed_fields)
        updated += 1
        print(f"UPDATED: {product.name}")
    else:
        print(f"ALREADY FILLED: {product.name}")

print(f"\nFinished. Products updated: {updated}")
