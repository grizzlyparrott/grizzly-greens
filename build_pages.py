#!/usr/bin/env python3
# build_pages.py
# Reads base.html + pages_json/*.json and writes final HTML files + hub index pages + sitemap.xml.
# Placeholders required in base.html:
# {{PAGE_TITLE}}, {{META_DESCRIPTION}}, {{CANONICAL_URL}}, {{CONTENT}}

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

SITE_HOST = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_HOST}"

PAGES_DIR = "pages_json"
BASE_FILE = "base.html"
SITEMAP_FILE = "sitemap.xml"

CANONICAL_BAD_SUFFIX = "/index.html"

# Locked hub contract (do not casually change)
HUBS = {
    "lawn-basics": {
        "title": "Lawn and Grass Basics",
        "intro": (
            "<p>Foundational lawn knowledge without the fluff. "
            "Grass types, mowing basics, common problems, and practical fixes.</p>"
        ),
    },
    "weeds-pests": {
        "title": "Weeds, Pests, & Lawn Diseases",
        "intro": (
            "<p>Identification first, then control. "
            "Weeds, insects, and common lawn diseases with realistic fixes.</p>"
        ),
    },
    "watering-irrigation": {
        "title": "Watering, Irrigation, & Drainage",
        "intro": (
            "<p>Water is the lever. "
            "Scheduling, irrigation basics, runoff, pooling, and drainage problems.</p>"
        ),
    },
    "soil-fertilizer": {
        "title": "Soil, Fertilizer, & Amendments",
        "intro": (
            "<p>Soil drives everything. "
            "Fertilizer basics, amendments, pH, and practical soil improvement.</p>"
        ),
    },
    "tools-safety": {
        "title": "Tools, Equipment, & Yard Safety",
        "intro": (
            "<p>Tools that actually matter, how to use them, and how to stay intact. "
            "Maintenance, safety, and choosing the right gear.</p>"
        ),
    },
}


def html_escape_attr(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def norm_url(url: str) -> str:
    url = url.strip()
    p = urlparse(url)

    if not p.scheme:
        path = url if url.startswith("/") else f"/{url}"
        base = urlparse(SITE_BASE)
        url = urlunparse((base.scheme, base.netloc, path, "", "", ""))
        p = urlparse(url)

    path = p.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    return urlunparse(("https", SITE_HOST, path, "", "", ""))


def iso_date_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def write_sitemap(repo_root: Path, urls: list[str]) -> None:
    uniq = sorted(set(urls))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    today = iso_date_utc()
    for u in uniq:
        lines.append("  <url>")
        lines.append(f"    <loc>{u}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    (repo_root / SITEMAP_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_html(base_html: str, page_title: str, meta_desc: str, canonical_url: str, content_html: str) -> str:
    html = base_html
    html = html.replace("{{PAGE_TITLE}}", html_escape_attr(page_title))
    html = html.replace("{{META_DESCRIPTION}}", html_escape_attr(meta_desc))
    html = html.replace("{{CANONICAL_URL}}", html_escape_attr(canonical_url))
    html = html.replace("{{CONTENT}}", content_html)
    return html


def validate_article(obj: dict, src_path: Path) -> dict:
    required = ["hub_slug", "slug", "title", "description", "card_blurb", "content_html"]
    for k in required:
        if k not in obj or not isinstance(obj[k], str) or not obj[k].strip():
            raise ValueError(f"{src_path}: missing/empty required field: {k}")

    hub_slug = obj["hub_slug"].strip()
    slug = obj["slug"].strip()
    title = obj["title"].strip()
    desc = obj["description"].strip()
    blurb = obj["card_blurb"].strip()
    content = obj["content_html"].strip()

    if hub_slug not in HUBS:
        raise ValueError(f"{src_path}: hub_slug must be one of {sorted(HUBS.keys())} (got: {hub_slug})")

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError(
            f"{src_path}: slug must be lowercase kebab-case letters/numbers only (got: {slug})"
        )

    if "<h1" not in content.lower():
        raise ValueError(f"{src_path}: content_html must include an <h1>")

    output_path = f"{hub_slug}/{slug}.html"
    canonical = f"{SITE_BASE}/{hub_slug}/{slug}.html"

    if canonical.endswith(CANONICAL_BAD_SUFFIX):
        raise ValueError(f"{src_path}: canonical must not end with {CANONICAL_BAD_SUFFIX} (got: {canonical})")

    return {
        "hub_slug": hub_slug,
        "slug": slug,
        "title": title,
        "description": desc,
        "card_blurb": blurb,
        "content_html": content,
        "output_path": output_path,
        "canonical": canonical,
    }


def hub_index_output_path(hub_slug: str) -> str:
    # We output /hub-slug/index.html but canonicalize to /hub-slug/
    return f"{hub_slug}/index.html"


def hub_index_canonical(hub_slug: str) -> str:
    return f"{SITE_BASE}/{hub_slug}/"


def build_hub_index_content(hub_slug: str, articles: list[dict]) -> str:
    hub_title = HUBS[hub_slug]["title"]
    hub_intro = HUBS[hub_slug]["intro"]

    items = []
    for a in articles:
        # a["canonical"] is the public URL; we link to path relative from root
        href = f"/{a['hub_slug']}/{a['slug']}.html"
        t = a["title"]
        b = a["card_blurb"]
        items.append(f'<article><h2><a href="{href}">{t}</a></h2><p>{b}</p></article>')

    listing = "\n".join(items) if items else "<p>No articles yet.</p>"
    return f"<h1>{hub_title}</h1>\n{hub_intro}\n<section>\n{listing}\n</section>"


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    base_path = repo_root / BASE_FILE
    pages_path = repo_root / PAGES_DIR

    if not base_path.exists():
        print(f"ERROR: missing {BASE_FILE} in repo root")
        return 2
    if not pages_path.exists() or not pages_path.is_dir():
        print(f"ERROR: missing folder {PAGES_DIR}/ in repo root")
        return 2

    base_html = base_path.read_text(encoding="utf-8", errors="strict")

    for ph in ["{{PAGE_TITLE}}", "{{META_DESCRIPTION}}", "{{CANONICAL_URL}}", "{{CONTENT}}"]:
        if ph not in base_html:
            print(f"ERROR: base.html missing placeholder {ph}")
            return 2

    json_files = sorted(pages_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: no JSON files found in {PAGES_DIR}/")
        return 2

    articles: list[dict] = []
    written_articles = 0

    for jf in json_files:
        raw = jf.read_text(encoding="utf-8", errors="strict")
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{jf}: invalid JSON: {e}")

        article = validate_article(obj, jf)
        out_file = repo_root / article["output_path"]
        out_file.parent.mkdir(parents=True, exist_ok=True)

        final_html = build_html(
            base_html=base_html,
            page_title=article["title"],
            meta_desc=article["description"],
            canonical_url=article["canonical"],
            content_html=article["content_html"],
        )
        out_file.write_text(final_html, encoding="utf-8")

        articles.append(article)
        written_articles += 1

    # Build hub index pages from articles
    written_hubs = 0
    hub_urls_for_sitemap: list[str] = []
    for hub_slug, hub in HUBS.items():
        hub_articles = [a for a in articles if a["hub_slug"] == hub_slug]
        hub_articles.sort(key=lambda x: x["title"].lower())

        hub_content = build_hub_index_content(hub_slug, hub_articles)
        hub_title = hub["title"]
        hub_desc = f"All GrizzlyGreens articles in {hub_title}."

        hub_out = repo_root / hub_index_output_path(hub_slug)
        hub_out.parent.mkdir(parents=True, exist_ok=True)

        final_hub_html = build_html(
            base_html=base_html,
            page_title=hub_title,
            meta_desc=hub_desc,
            canonical_url=hub_index_canonical(hub_slug),
            content_html=hub_content,
        )
        hub_out.write_text(final_hub_html, encoding="utf-8")

        written_hubs += 1
        hub_urls_for_sitemap.append(hub_index_canonical(hub_slug))

    # Sitemap URLs: homepage + hub canonicals + article canonicals
    urls = [SITE_BASE + "/"]
    urls.extend(hub_urls_for_sitemap)
    urls.extend([a["canonical"] for a in articles])
    write_sitemap(repo_root, urls)

    print(f"Built {written_articles} article pages from {len(json_files)} JSON files.")
    print(f"Built {written_hubs} hub index pages.")
    print(f"Wrote {SITEMAP_FILE} with {len(set(urls))} URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
