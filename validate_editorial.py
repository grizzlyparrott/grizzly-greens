"""Validate every rebuilt article, discovered by its editorial-article class.

Run from any directory: python validate_editorial.py
Pillow is required for image decode/dimension checks.
"""

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
from xml.etree import ElementTree

from PIL import Image


ROOT = Path(__file__).resolve().parent
SITE = "https://grizzlygreens.net"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.editorial = False
        self.links = []
        self.images = []
        self.meta = {}
        self.canonical = None
        self.schema = []
        self._json = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "article" and "editorial-article" in attrs.get("class", "").split():
            self.editorial = True
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "img":
            self.images.append(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta[key] = attrs.get("content")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self._json = True

    def handle_data(self, data):
        if self._json:
            self.schema.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self._json = False


def local_target(href):
    if not href.startswith("/") or href.startswith("//"):
        return None
    path = unquote(urlparse(href).path).lstrip("/")
    target = ROOT / path
    return target / "index.html" if target.is_dir() else target


def main():
    errors = []
    pages = []
    search = json.loads((ROOT / "search-index.json").read_text(encoding="utf-8"))
    search_urls = {item["url"] for item in search}
    sitemap = ElementTree.parse(ROOT / "sitemap.xml")
    sitemap_dates = {
        entry.findtext("{*}loc"): entry.findtext("{*}lastmod")
        for entry in sitemap.findall(".//{*}url")
    }

    for path in sorted(ROOT.glob("*/*.html")):
        parsed = Page()
        parsed.feed(path.read_text(encoding="utf-8"))
        if not parsed.editorial:
            continue
        pages.append(path)
        url = SITE + "/" + path.relative_to(ROOT).as_posix()
        prefix = str(path.relative_to(ROOT))
        def fail(message):
            errors.append(f"{prefix}: {message}")

        if parsed.canonical != url:
            fail("canonical does not match preserved URL")
        if url not in sitemap_dates:
            fail("not in sitemap")
        if urlparse(url).path not in search_urls:
            fail("not in on-site search index")
        if parsed.meta.get("og:url") != url:
            fail("Open Graph URL differs from canonical")
        if not parsed.meta.get("article:modified_time"):
            fail("missing modified date")
        if len(parsed.schema) != 1:
            fail("expected one Article JSON-LD object")
            article = {}
        else:
            try:
                article = json.loads(parsed.schema[0])
            except json.JSONDecodeError:
                fail("invalid JSON-LD")
                article = {}
        if article.get("@type") != "Article":
            fail("schema type is not Article")
        if article.get("mainEntityOfPage", {}).get("@id") != url:
            fail("schema URL differs from canonical")
        if article.get("dateModified") != parsed.meta.get("article:modified_time"):
            fail("modified dates differ")
        if sitemap_dates.get(url) != parsed.meta.get("article:modified_time"):
            fail("sitemap date differs from article modified date")
        if article.get("datePublished") != parsed.meta.get("article:published_time"):
            fail("published dates differ")
        if not article.get("headline") or not article.get("description"):
            fail("missing schema headline or description")

        if len(parsed.images) != 1:
            fail("expected one informational article image")
        for img in parsed.images:
            source = img.get("src", "")
            target = local_target(source)
            if not target or not target.is_file():
                fail(f"missing image {source}")
                continue
            if not img.get("alt") or img.get("loading") != "lazy" or img.get("decoding") != "async":
                fail("image accessibility/loading attributes incomplete")
            if img.get("width") != "1600" or img.get("height") != "900":
                fail("image HTML dimensions differ from standard")
            try:
                with Image.open(target) as decoded:
                    if decoded.format != "WEBP" or decoded.size != (1600, 900):
                        fail("image format or dimensions differ from standard")
                    decoded.verify()
            except Exception as exc:
                fail(f"image decode failed: {exc}")
            if target.stat().st_size > 600_000:
                fail("image exceeds 600 KB")
            image_url = SITE + source
            for field in ("og:image", "twitter:image"):
                if parsed.meta.get(field) != image_url:
                    fail(f"{field} differs from article image")
            if article.get("image") != image_url:
                fail("schema image differs from article image")

        for href in parsed.links:
            target = local_target(href)
            if target and not target.is_file():
                fail(f"broken internal link {href}")
        if sum(href.startswith("https://extension.") for href in parsed.links) < 2:
            fail("fewer than two Extension source links")

    print(f"Checked {len(pages)} rebuilt articles")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print("Canonical, sitemap, search, schema, images, sources, and internal links: PASS")


if __name__ == "__main__":
    main()
