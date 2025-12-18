# build_sitemap.py
# Builds sitemap.xml containing ONLY published article pages:
# any .html file inside a hub folder, excluding index.html (and excluding root-level html).

from __future__ import annotations

import os
from pathlib import Path
import xml.etree.ElementTree as ET

BASE_URL = "https://grizzlygreens.net"  # no trailing slash
OUTPUT_FILENAME = "sitemap.xml"

EXCLUDE_FILENAMES = {
    "index.html",
    "404.html",
}

EXCLUDE_DIR_NAMES = {
    ".git",
    ".github",
    ".vscode",
    "__pycache__",
    "node_modules",
    ".idea",
}

def is_hub_dir(p: Path) -> bool:
    return p.is_dir() and p.name not in EXCLUDE_DIR_NAMES and not p.name.startswith(".")

def collect_article_urls(site_root: Path) -> list[str]:
    urls: list[str] = []

    # Hub folders are immediate children of the site root (e.g. lawn-basics/, tools-safety/, etc.)
    for hub in sorted(site_root.iterdir()):
        if not is_hub_dir(hub):
            continue

        # Only include .html files that actually exist inside the hub directory tree
        for html_path in sorted(hub.rglob("*.html")):
            if not html_path.is_file():
                continue
            if html_path.name in EXCLUDE_FILENAMES:
                continue

            # Convert to URL path
            rel = html_path.relative_to(site_root).as_posix()
            urls.append(f"{BASE_URL}/{rel}")

    # De-dupe while keeping sort stable
    return sorted(set(urls))

def write_sitemap(urls: list[str], out_path: Path) -> None:
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset = ET.Element("{http://www.sitemaps.org/schemas/sitemap/0.9}urlset")

    for u in urls:
        url_el = ET.SubElement(urlset, "{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        loc_el = ET.SubElement(url_el, "{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        loc_el.text = u

    tree = ET.ElementTree(urlset)

    # Pretty print (Python 3.9+)
    try:
        ET.indent(tree, space="  ", level=0)  # type: ignore[attr-defined]
    except Exception:
        pass

    tree.write(out_path, encoding="UTF-8", xml_declaration=True)

def main() -> int:
    site_root = Path(__file__).resolve().parent
    urls = collect_article_urls(site_root)

    out_path = site_root / OUTPUT_FILENAME
    write_sitemap(urls, out_path)

    print(f"Wrote {out_path} with {len(urls)} article URLs.")
    if len(urls) == 0:
        print("WARNING: 0 URLs found. Are your hub folders under this script’s folder?")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
