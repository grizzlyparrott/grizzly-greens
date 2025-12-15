#!/usr/bin/env python3
# build_pages.py
# GrizzlyGreens static generator (GitHub Pages friendly)
# - base.html owns ALL chrome (nav/search/footer/scripts)
# - This script ONLY injects page bodies into {{CONTENT}}
# - Reads pages_json/*.json for article pages
# - Reads each hub's filenames.csv for hub index cards
# - Writes:
#   - /index.html
#   - /<hub_slug>/index.html
#   - /<hub_slug>/<filename>.html
#   - /sitemap.xml
#
# Optional env vars:
#   OUTPUT_DIR=dist        (write output under dist/)
#   VERBOSE=1              (print build logs)
#   GTAG='<script>...</script>'  (raw gtag snippet inserted into {{GTAG}})

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from datetime import date
from html import escape
from typing import Dict, List, Optional, Tuple

SITE_NAME = "GrizzlyGreens"
SITE_DOMAIN = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_DOMAIN}"

BASE_HTML_PATH = Path("base.html")
PAGES_JSON_DIR = Path("pages_json")
SITEMAP_FILENAME = "sitemap.xml"

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "").strip())
VERBOSE = os.environ.get("VERBOSE", "0").strip() == "1"

# Hubs: folder slug -> display title + short description
HUBS = [
    ("lawn-basics", "Lawn and Grass Basics", "Grass types, mowing basics, common problems, and practical fixes."),
    ("weeds-pests", "Weeds, Pests, & Lawn Diseases", "Identification first, then control: weeds, insects, and common lawn diseases."),
    ("watering-irrigation", "Watering, Irrigation, & Drainage", "Watering schedules, sprinkler setups, drainage issues, and fixes that work."),
    ("soil-fertilizer", "Soil, Fertilizer, & Amendments", "Soil basics, nutrients, pH, and amendments that actually move the needle."),
    ("tools-safety", "Tools, Equipment, & Yard Safety", "Tools that matter, maintenance, and safety rules that prevent dumb injuries."),
]

def log(msg: str) -> None:
    if VERBOSE:
        print(msg)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

def out_path(rel: str) -> Path:
    rel = rel.lstrip("/")
    return (OUTPUT_DIR / rel) if str(OUTPUT_DIR) else Path(rel)

def normalize_slug(s: str) -> str:
    return (s or "").strip().strip("/")

def ensure_html_filename(name: str) -> str:
    name = (name or "").strip()
    if not name.lower().endswith(".html"):
        name += ".html"
    return name

def build_output_path(hub_slug: str, filename: str) -> str:
    hub_slug = normalize_slug(hub_slug)
    filename = (filename or "").strip().lstrip("/")
    if "/" in filename:
        filename = filename.split("/")[-1]
    filename = ensure_html_filename(filename)
    return f"{hub_slug}/{filename}"

def build_canonical(output_path: str) -> str:
    return f"{SITE_BASE}/{(output_path or '').lstrip('/')}"

def template_render(base_html: str, title: str, description: str, canonical: str, content_html: str) -> str:
    # IMPORTANT: base.html already contains header/search/footer, so this only injects CONTENT.
    # Also replaces GTAG so {{GTAG}} never leaks to production.
    gtag = os.environ.get("GTAG", "").rstrip()

    html = base_html
    html = html.replace("{{TITLE}}", escape(title or ""))
    html = html.replace("{{DESCRIPTION}}", escape(description or ""))
    html = html.replace("{{CANONICAL}}", escape(canonical or ""))
    html = html.replace("{{GTAG}}", gtag)
    html = html.replace("{{CONTENT_HTML}}", content_html)
    html = html.replace("{{CONTENT}}", content_html)
    return html

def card_html(title: str, blurb: str, href: str, button_text: str = "Open") -> str:
    return f"""
<article class="card">
  <h2 class="card-title"><a href="{href}">{escape(title)}</a></h2>
  <p class="card-text">{escape(blurb)}</p>
  <a class="btn secondary" href="{href}">{escape(button_text)}</a>
</article>
""".strip()

def homepage_body() -> str:
    hub_cards = []
    for slug, title, desc in HUBS:
        hub_cards.append(card_html(title, desc, f"/{slug}/", "Open hub"))

    return f"""
<header class="hero">
  <h1>{escape(SITE_NAME)}</h1>
  <p class="subtitle">Fast, practical lawn and yard knowledge. No fluff. Built to scale cleanly.</p>
</header>

<section class="grid">
  {"".join(hub_cards)}
</section>
""".strip()

def hub_index_body(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]]) -> str:
    cards = []
    for title, filename in items:
        filename = ensure_html_filename(filename)
        href = f"/{hub_slug}/{filename}"
        cards.append(card_html(title, f"Practical guide in {hub_title.lower()}.", href, "Open"))

    return f"""
<header class="hub-hero">
  <h1>{escape(hub_title)}</h1>
  <p class="subtitle">{escape(hub_desc)}</p>
</header>

<section class="grid">
  {"".join(cards)}
</section>
""".strip()

def read_hub_filenames_csv(hub_slug: str) -> List[Tuple[str, str]]:
    csv_path = Path(hub_slug) / "filenames.csv"
    if not csv_path.exists():
        return []
    rows: List[Tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = (r.get("title") or "").strip()
            fn = (r.get("filename") or "").strip()
            if t and fn:
                rows.append((t, fn))
    return rows

def load_article_json_files() -> List[Dict]:
    objs: List[Dict] = []
    if not PAGES_JSON_DIR.exists():
        return objs
    for path in sorted(PAGES_JSON_DIR.glob("*.json")):
        try:
            obj = json.loads(read_text(path))
            if isinstance(obj, dict):
                obj["_source_file"] = str(path)
                objs.append(obj)
        except Exception:
            log(f"Skipping bad JSON: {path}")
    return objs

def normalize_article_obj(obj: Dict) -> Optional[Dict]:
    hub_slug = normalize_slug(obj.get("hub_slug") or "")
    filename = (obj.get("filename") or "").strip()

    output_path = (obj.get("output_path") or obj.get("outputPath") or "").strip().lstrip("/")
    if not filename and output_path:
        filename = output_path.split("/")[-1]

    if not hub_slug:
        if output_path and "/" in output_path:
            hub_slug = normalize_slug(output_path.split("/")[0])
        else:
            return None

    if not filename:
        return None

    filename = ensure_html_filename(filename)
    output_path2 = build_output_path(hub_slug, filename)
    canonical2 = build_canonical(output_path2)

    title = (obj.get("title") or "").strip()
    description = (obj.get("description") or "").strip()
    content_html = obj.get("content_html") or obj.get("contentHtml") or ""

    if not title or not isinstance(content_html, str) or not content_html.strip():
        return None

    if not description:
        description = title

    return {
        "hub_slug": hub_slug,
        "filename": filename,
        "output_path": output_path2,
        "canonical": canonical2,
        "title": title,
        "description": description,
        "content_html": content_html.strip(),
        "_source_file": obj.get("_source_file", ""),
    }

def write_sitemap(urls: List[str]) -> None:
    clean = sorted({u.strip() for u in urls if u and u.strip()})
    items = [f"  <url><loc>{escape(u)}</loc></url>" for u in clean]
    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        *items,
        "</urlset>",
        "",
    ])
    write_text(out_path(SITEMAP_FILENAME), xml)

def main() -> int:
    if not BASE_HTML_PATH.exists():
        raise SystemExit("Missing base.html in repo root.")

    base_html = read_text(BASE_HTML_PATH)
    urls_for_sitemap: List[str] = []

    # 1) Homepage
    home_html = template_render(
        base_html=base_html,
        title=SITE_NAME,
        description="Practical lawn, weed, irrigation, soil, and yard safety guides built to scale cleanly.",
        canonical=f"{SITE_BASE}/",
        content_html=homepage_body(),
    )
    write_text(out_path("index.html"), home_html)
    urls_for_sitemap.append(f"{SITE_BASE}/")
    log("Built homepage index.html")

    # 2) Hub index pages
    for slug, title, desc in HUBS:
        items = read_hub_filenames_csv(slug)
        hub_html = template_render(
            base_html=base_html,
            title=f"{title} - {SITE_NAME}",
            description=desc,
            canonical=f"{SITE_BASE}/{slug}/",
            content_html=hub_index_body(slug, title, desc, items),
        )
        write_text(out_path(f"{slug}/index.html"), hub_html)
        urls_for_sitemap.append(f"{SITE_BASE}/{slug}/")
        log(f"Built hub: {slug}/index.html")

    # 3) Article pages from pages_json/*.json
    raw_objs = load_article_json_files()
    built = 0
    skipped = 0

    for o in raw_objs:
        a = normalize_article_obj(o)
        if not a:
            skipped += 1
            continue

        page_html = template_render(
            base_html=base_html,
            title=a["title"],
            description=a["description"],
            canonical=a["canonical"],
            content_html=a["content_html"],
        )
        write_text(out_path(a["output_path"]), page_html)
        urls_for_sitemap.append(a["canonical"])
        built += 1

    # 4) Sitemap
    write_sitemap(urls_for_sitemap)

    if VERBOSE:
        print(f"Built hubs={len(HUBS)} articles={built} skipped={skipped} output_dir='{OUTPUT_DIR or ''}'")
    else:
        # Only talk when something is wrong
        if built == 0 and raw_objs:
            print("Built 0 articles. JSON objects are missing required fields: hub_slug, filename, title, content_html.")
        elif not raw_objs:
            print("No pages_json/*.json found. Built homepage, hubs, sitemap only.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
