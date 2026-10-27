import re
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from products.models import Product, ProductImage

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = (
        "Attach pictures from a folder. Name each file after the product, e.g. "
        "samsung-galaxy-s24.jpg. Extra pictures: samsung-galaxy-s24_2.jpg"
    )

    def add_arguments(self, parser):
        parser.add_argument("folder", nargs="?")
        parser.add_argument("--list", action="store_true", help="Show the file name for each product")
        parser.add_argument("--add", action="store_true", help="Also add to products that already have pictures")

    def handle(self, *args, **options):
        if options["list"]:
            for product in Product.objects.filter(is_active=True).order_by("slug"):
                self.stdout.write(f"{product.slug}.jpg    ({product.name})")
            return
        if not options["folder"]:
            raise CommandError("Give the folder, or use --list to see the file names.")
        folder = Path(options["folder"])
        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        products = {p.slug: p for p in Product.objects.all()}
        loaded, added, skipped = set(), 0, 0
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in EXTENSIONS:
                continue
            slug = re.sub(r"_\d+$", "", path.stem.lower())
            product = products.get(slug)
            if product is None:
                self.stdout.write(self.style.WARNING(f"No product called {slug}: skipped {path.name}"))
                skipped += 1
                continue
            if product.images.exists() and product.id not in loaded and not options["add"]:
                self.stdout.write(f"{product.name} already has pictures: skipped {path.name}")
                skipped += 1
                continue
            image = ProductImage(
                product=product, alt_text=product.name,
                is_primary=not product.images.exists(), sort_order=product.images.count(),
            )
            with path.open("rb") as handle:
                image.image.save(path.name, File(handle), save=False)
            try:
                image.full_clean()  # checks type and the 10 MB limit
            except ValidationError as exc:
                self.stdout.write(self.style.WARNING(f"{path.name}: {' '.join(exc.messages)}"))
                skipped += 1
                continue
            image.save()
            loaded.add(product.id)
            added += 1
        self.stdout.write(self.style.SUCCESS(f"Added {added} picture(s), skipped {skipped}."))
