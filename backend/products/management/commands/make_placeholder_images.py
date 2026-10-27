import hashlib
import textwrap
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from products.models import Product, ProductImage

PALETTE = [
    (37, 99, 235), (8, 145, 178), (22, 163, 74), (217, 119, 6),
    (190, 24, 93), (109, 40, 217), (71, 85, 105),
]


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def make_image(product):
    seed = int(hashlib.md5(product.category.name.encode()).hexdigest(), 16)
    base = PALETTE[seed % len(PALETTE)]
    size = 800
    image = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(image)
    for y in range(size):  # lighter towards the bottom
        shade = int(60 * y / size)
        draw.line([(0, y), (size, y)], fill=tuple(min(255, c + shade) for c in base))
    draw.text((size / 2, 90), product.category.name.upper(), font=font(30), fill="white", anchor="mm")
    draw.multiline_text(
        (size / 2, size / 2), "\n".join(textwrap.wrap(product.name, 16)),
        font=font(54), fill="white", anchor="mm", align="center", spacing=12,
    )
    if product.brand:
        draw.text((size / 2, size - 90), product.brand.name, font=font(30), fill="white", anchor="mm")
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Give every product that has no picture a simple generated one."

    def handle(self, *args, **options):
        made = 0
        products = Product.objects.filter(images__isnull=True).select_related("category", "brand")
        for product in products:
            image = ProductImage(product=product, alt_text=product.name, is_primary=True)
            image.image.save(f"{product.slug}.jpg", ContentFile(make_image(product)), save=False)
            image.full_clean()
            image.save()
            made += 1
        self.stdout.write(self.style.SUCCESS(f"Pictures created for {made} product(s)."))
