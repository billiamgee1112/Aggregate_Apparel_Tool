# generate_site_images.py
"""
One-off (or rerun-when-branding-changes) build script that renders the
HTML/CSS templates in _asset_templates/ into real PNG images using Playwright
(already a project dependency), since no dedicated image-generation tool is
available. Regenerate by running this script again after editing a template.

Usage:
    python generate_site_images.py
"""
from playwright.sync_api import sync_playwright
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "_asset_templates")
STATIC_IMAGES_DIR = os.path.join(BASE_DIR, "static", "images")

os.makedirs(STATIC_IMAGES_DIR, exist_ok=True)

JOBS = [
    ("og_image.html", "og-featured.png", 1200, 630),
    ("placeholder_image.html", "placeholder.png", 800, 800),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    for template_name, output_name, width, height in JOBS:
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        output_path = os.path.join(STATIC_IMAGES_DIR, output_name)

        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file:///{template_path}")
        page.screenshot(path=output_path)
        page.close()
        print(f"Generated {output_path} ({width}x{height})")
    browser.close()

print("Done.")
