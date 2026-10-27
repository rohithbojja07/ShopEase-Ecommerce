"""
ShopEase ProductImage importer.

Run from the Django backend directory:
    python manage.py shell -c "exec(open('import_product_images.py', encoding='utf-8').read())"

Before running:
- Fill product_image_manifest.json with verified DIRECT image-file URLs.
- Keep APPLY_IMPORT = False for the first validation run.
- Change APPLY_IMPORT to True only after reviewing the dry-run report.

Expected manifest image fields:
    url, alt_text, source_page

This script does not discover URLs, bypass access controls, or assert that a source is official.
The source_page field is recorded in the report for manual provenance checking.
"""
import hashlib
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from products.models import Product, ProductImage

BASE_DIR = Path.cwd()
MANIFEST_PATH = BASE_DIR / "product_image_manifest.json"
REPORT_PATH = BASE_DIR / "product_image_import_report.json"
APPLY_IMPORT = False  # Review dry run first; change to True to create records.
TARGET_IMAGES_PER_PRODUCT = 6
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
TIMEOUT_SECONDS = 25
USER_AGENT = "ShopEaseProductImageImporter/1.0 (product image validation)"

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def safe_ext(image_format, content_type):
    fmt = (image_format or "").upper()
    mapping = {"JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}
    if fmt in mapping:
        return mapping[fmt]
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    return guessed if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"

if not MANIFEST_PATH.exists():
    raise SystemExit(f"Manifest not found: {MANIFEST_PATH}")

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# Hash existing image files so the same content is not imported twice.
existing_hashes = {}
for record in ProductImage.objects.select_related("product").all():
    try:
        if record.image and record.image.storage.exists(record.image.name):
            with record.image.open("rb") as f:
                digest = sha256(f.read())
            existing_hashes.setdefault((record.product_id, digest), record.id)
    except Exception as exc:
        print(f"WARNING: could not inspect existing image record {record.id}: {exc}")

report = {
    "apply_import": APPLY_IMPORT,
    "target_images_per_product": TARGET_IMAGES_PER_PRODUCT,
    "products": [],
    "created_records": 0,
    "skipped": 0,
    "errors": []
}

for entry in manifest.get("products", []):
    product_id = entry.get("product_id")
    product_name = entry.get("product_name", "")
    result = {
        "product_id": product_id,
        "product_name": product_name,
        "current_records": 0,
        "valid_manifest_images": 0,
        "would_add": 0,
        "added": 0,
        "skipped": [],
        "errors": [],
        "remaining_to_target": None
    }

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        result["errors"].append("Product ID not found in database")
        report["products"].append(result)
        continue

    result["current_records"] = ProductImage.objects.filter(product=product).count()
    images = entry.get("images", [])
    seen_manifest_hashes = set()

    for image_entry in images:
        url = (image_entry.get("url") or "").strip()
        alt_text = (image_entry.get("alt_text") or "").strip()
        source_page = (image_entry.get("source_page") or "").strip()

        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            result["errors"].append(f"Invalid URL: {url}")
            continue
        if not alt_text or not source_page:
            result["errors"].append(f"Missing alt_text/source_page for URL: {url}")
            continue

        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS, stream=True, allow_redirects=True)
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Image exceeds 20 MB limit")
                chunks.append(chunk)
            data = b"".join(chunks)
            response.close()

            content_type = response.headers.get("Content-Type", "")
            if not content_type.lower().startswith("image/"):
                raise ValueError(f"Response is not an image (Content-Type: {content_type})")

            try:
                with Image.open(BytesIO(data)) as im:
                    im.verify()
                with Image.open(BytesIO(data)) as im:
                    width, height = im.size
                    image_format = im.format
            except (UnidentifiedImageError, OSError) as exc:
                raise ValueError(f"Downloaded file is not a valid image: {exc}")

            if width < 200 or height < 200:
                raise ValueError(f"Image too small ({width}x{height}); skipped")

            digest = sha256(data)
            if digest in seen_manifest_hashes or (product.id, digest) in existing_hashes:
                result["skipped"].append({"url": url, "reason": "Duplicate image content"})
                report["skipped"] += 1
                continue
            seen_manifest_hashes.add(digest)
            result["valid_manifest_images"] += 1
            current_count = ProductImage.objects.filter(product=product).count()
            if current_count + result["would_add"] >= TARGET_IMAGES_PER_PRODUCT:
                result["skipped"].append({"url": url, "reason": "Target image count already reached"})
                report["skipped"] += 1
                continue

            result["would_add"] += 1
            if APPLY_IMPORT:
                extension = safe_ext(image_format, content_type)
                filename = f"product-{product.id}-{digest[:12]}{extension}"
                with transaction.atomic():
                    record = ProductImage(
                        product=product,
                        alt_text=alt_text[:255],
                        is_primary=False,
                        sort_order=(ProductImage.objects.filter(product=product).count() + 1),
                    )
                    record.image.save(filename, ContentFile(data), save=False)
                    record.save()
                existing_hashes[(product.id, digest)] = record.id
                result["added"] += 1
                report["created_records"] += 1

        except Exception as exc:
            result["errors"].append({"url": url, "error": str(exc)})

    actual_count = ProductImage.objects.filter(product=product).count()
    result["remaining_to_target"] = max(0, TARGET_IMAGES_PER_PRODUCT - actual_count - result["would_add"] if not APPLY_IMPORT else TARGET_IMAGES_PER_PRODUCT - actual_count)
    report["products"].append(result)

REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

print("\nSHOP EASE IMAGE IMPORT REPORT")
print("=" * 72)
print("Mode:", "IMPORT" if APPLY_IMPORT else "DRY RUN (no database changes)")
for result in report["products"]:
    print(
        f'{result["product_id"]} | {result["product_name"]} | '
        f'current={result["current_records"]} | validated={result["valid_manifest_images"]} | '
        f'added={result["added"]} | errors={len(result["errors"])}'
    )
    for error in result["errors"]:
        print("   ERROR:", error)
print("=" * 72)
print("Created records:", report["created_records"])
print("Skipped entries:", report["skipped"])
print("Detailed report:", REPORT_PATH)
if not APPLY_IMPORT:
    print("No database records or image files were changed. Review report, then set APPLY_IMPORT = True to import.")
