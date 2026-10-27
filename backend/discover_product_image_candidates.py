import json
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent
SOURCE_FILE = BASE_DIR / "source_pages.json"
REPORT_FILE = BASE_DIR / "image_candidates_report.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
}

class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag.lower() == "img":
            for key in ("src", "data-src", "data-original",
                        "data-lazy-src", "data-image"):
                if attrs.get(key):
                    self.images.append(
                        (attrs[key], attrs.get("alt", ""), key)
                    )

            for key in ("srcset", "data-srcset"):
                if attrs.get(key):
                    for part in attrs[key].split(","):
                        url = part.strip().split()[0]
                        self.images.append(
                            (url, attrs.get("alt", ""), key)
                        )

        if tag.lower() == "meta":
            prop = (
                attrs.get("property") or attrs.get("name") or ""
            ).lower()

            if prop in (
                "og:image", "og:image:secure_url",
                "twitter:image", "twitter:image:src"
            ) and attrs.get("content"):
                self.images.append(
                    (attrs["content"], "", prop)
                )

        if tag.lower() == "source":
            for key in ("src", "srcset"):
                if attrs.get(key):
                    for part in attrs[key].split(","):
                        self.images.append(
                            (part.strip().split()[0], "", key)
                        )


def main():
    if not SOURCE_FILE.exists():
        print("ERROR: source_pages.json was not found.")
        return

    data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))

    report = {
        "note": (
            "Candidate URLs require manual review. "
            "No database records or image files are changed."
        ),
        "products": []
    }

    session = requests.Session()
    session.headers.update(HEADERS)

    for product in data.get("products", []):
        result = {
            "product_id": product["product_id"],
            "name": product["name"],
            "pages_checked": [],
            "candidates": [],
            "errors": []
        }

        seen = set()

        for page_url in product.get("source_pages", []):
            page_result = {"url": page_url, "status": None}

            try:
                response = session.get(page_url, timeout=25)
                page_result["status"] = response.status_code
                response.raise_for_status()

                parser = ImageParser()
                parser.feed(response.text)

                for raw_url, alt, found_by in parser.images:
                    image_url = urljoin(
                        response.url,
                        raw_url.strip().replace("&amp;", "&")
                    )

                    parsed = urlparse(image_url)

                    if parsed.scheme not in ("http", "https"):
                        continue
                    if not parsed.netloc or image_url in seen:
                        continue
                    if image_url.startswith("data:"):
                        continue

                    low_url = image_url.lower().split("?")[0]
                    if any(word in low_url for word in (
                        "logo", "favicon", "sprite",
                        "placeholder", "avatar"
                    )):
                        continue

                    seen.add(image_url)
                    result["candidates"].append({
                        "url": image_url,
                        "alt": alt[:250],
                        "found_by": found_by,
                        "source_page": response.url,
                        "reviewed": False
                    })

            except Exception as exc:
                result["errors"].append({
                    "url": page_url,
                    "error": str(exc)
                })

            result["pages_checked"].append(page_result)
            time.sleep(0.4)

        result["candidate_count"] = len(result["candidates"])
        report["products"].append(result)

        print(
            f'[{product["product_id"]}] {product["name"]}: '
            f'{result["candidate_count"]} candidate images'
        )

    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nProducts processed:", len(report["products"]))
    print("Report saved to:", REPORT_FILE)
    print("No Django database changes were made.")


if __name__ == "__main__":
    main()
