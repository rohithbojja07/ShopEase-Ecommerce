import json
import io
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

BASE = Path(__file__).resolve().parent
INPUT = BASE / "image_candidates_report.json"
OUTPUT = BASE / "validated_image_candidates.json"

SKIP_WORDS = (
    "facebook", "twitter", "instagram", "youtube", "logo",
    "icon", "favicon", "backpack", "mouse", "keyboard",
    "wallpaper", "banner", "social", "sprite", "placeholder"
)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
})

data = json.loads(INPUT.read_text(encoding="utf-8"))
report = {"products": []}

for product in data.get("products", []):
    candidates = product.get("candidates", [])
    valid = []
    skipped = 0

    # Check at most 40 candidates per product in this first pass.
    for candidate in candidates[:40]:
        url = candidate.get("url", "")
        low = url.lower()

        if any(word in low for word in SKIP_WORDS):
            skipped += 1
            continue

        try:
            response = session.get(
                url, timeout=15, stream=True
            )
            if response.status_code != 200:
                response.close()
                continue

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if not content_type.startswith("image/"):
                response.close()
                continue

            # Read a bounded amount for image validation.
            chunks = []
            total = 0
            for chunk in response.iter_content(65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= 8 * 1024 * 1024:
                    break
            response.close()

            raw = b"".join(chunks)
            image = Image.open(io.BytesIO(raw))
            image.verify()

            # Reopen to read dimensions after verify().
            image = Image.open(io.BytesIO(raw))
            width, height = image.size
            fmt = image.format

            if width < 300 or height < 300:
                continue

            valid.append({
                "url": url,
                "width": width,
                "height": height,
                "format": fmt,
                "content_type": content_type,
                "alt": candidate.get("alt", ""),
                "source_page": candidate.get("source_page", ""),
                "reviewed": False
            })

        except Exception:
            pass

        time.sleep(0.15)

    report["products"].append({
        "product_id": product["product_id"],
        "name": product["name"],
        "checked": min(len(candidates), 40),
        "valid_image_count": len(valid),
        "skipped_by_url_filter": skipped,
        "images": valid
    })

    print(
        f'[{product["product_id"]}] {product["name"]}: '
        f'{len(valid)} valid image files from '
        f'{min(len(candidates), 40)} checked'
    )

OUTPUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("\nValidation report:", OUTPUT)
print("No Django records or media files were changed.")
