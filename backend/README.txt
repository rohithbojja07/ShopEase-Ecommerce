# ShopEase product image importer

## Files
- `product_image_manifest.json`: add verified direct image URLs for your 32 products.
- `import_product_images.py`: validates and imports images through the existing `ProductImage` model.

## Important
The manifest starts with empty image lists. No image URLs are invented or assumed. Add 5–6 distinct, exact-model image entries per product. Prefer official manufacturer sources and check permission/terms for reuse.

Each image entry should look like:
```json
{
  "url": "https://manufacturer.example/path/to/actual-image.jpg",
  "alt_text": "Samsung Galaxy S24 rear view",
  "source_page": "https://manufacturer.example/product-page"
}
```

## Run a dry run
Copy both files into `C:\Projects\ecommerce\backend`, then run:
```powershell
python manage.py shell -c "exec(open('import_product_images.py', encoding='utf-8').read())"
```
The script defaults to dry-run mode (`APPLY_IMPORT = False`) and writes `product_image_import_report.json`.

After reviewing the report, change `APPLY_IMPORT = False` to `APPLY_IMPORT = True` in `import_product_images.py` and rerun to import valid images as secondary images. Existing primary images are not replaced.
