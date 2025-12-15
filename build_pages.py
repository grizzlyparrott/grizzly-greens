#!/usr/bin/env python3
# build_pages.py
#
# base.html owns ALL chrome (nav/search/footer/scripts).
# This script ONLY injects page bodies into {{CONTENT}} and fills tokens:
# {{TITLE}}, {{DESCRIPTION}}, {{CANONICAL}}, {{GTAG}}, {{CONTENT}} (or {{CONTENT_HTML}})
#
# Generates:
# - /index.html
# - /<hub_slug>/index.html
# - /<hub_slug>/<filename>.html
# - /sitemap.xml
# - /search-index.json
#
# Hub card blurbs:
# - Prefer per-article card_blurb from pages_json for matching filename.
# - Fallback to per-article description.
# - Final fallback: a generic hub blurb (only if JSON missing).

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
SEARCH_INDEX_FILENAME = "search-index.json"

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "").strip())
VERBOSE = os.environ.get("VERBOSE", "0").strip() == "1"

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

def out_path(rel: str) -> Path:
    rel = (rel or "").lstrip("/")
    return (OUTPUT_DIR / rel) if str(OUTPUT_DIR) else Path(rel)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

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

def build_canonical(output_path_str: str) -> str:
    return f"{SITE_BASE}/{(output_path_str or '').lstrip('/')}"

def load_gtag_snippet() -> str:
    raw = os.environ.get("GTAG", "")
    if raw.strip():
        return raw.rstrip()
    gtag_file = os.environ.get("GTAG_FILE", "").strip()
    if gtag_file:
        p = Path(gtag_file)
        if p.exists():
            return read_text(p).rstrip()
    return ""

def template_render(base_html: str, title: str, description: str, canonical: str, content_html: str, gtag: str) -> str:
    html = base_html
    html = html.replace("{{TITLE}}", escape(title or ""))
    html = html.replace("{{DESCRIPTION}}", escape(description or ""))
    html = html.replace("{{CANONICAL}}", escape(canonical or ""))
    html = html.replace("{{GTAG}}", gtag or "")
    html = html.replace("{{CONTENT_HTML}}", content_html or "")
    html = html.replace("{{CONTENT}}", content_html or "")
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
    cards: List[str] = []
    for slug, hub_title, desc in HUBS:
        cards.append(card_html(hub_title, desc, f"/{slug}/", "Open hub"))
    return f"""
<header class="hero">
  <h1>{escape(SITE_NAME)}</h1>
  <p class="subtitle">Fast, practical lawn and yard knowledge. No fluff.</p>
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

    output_path_old = (obj.get("output_path") or obj.get("outputPath") or "").strip().lstrip("/")
    if not filename and output_path_old:
        filename = output_path_old.split("/")[-1]

    if not hub_slug:
        if output_path_old and "/" in output_path_old:
            hub_slug = normalize_slug(output_path_old.split("/")[0])
        else:
            return None

    if not filename:
        return None

    filename = ensure_html_filename(filename)
    output_path_new = build_output_path(hub_slug, filename)
    canonical = build_canonical(output_path_new)

    title = (obj.get("title") or "").strip()
    description = (obj.get("description") or "").strip()
    card_blurb = (obj.get("card_blurb") or obj.get("cardBlurb") or "").strip()
    content_html = obj.get("content_html") or obj.get("contentHtml") or ""

    if not title or not isinstance(content_html, str) or not content_html.strip():
        return None

    if not description:
        description = title
    if not card_blurb:
        card_blurb = description

    return {
        "hub_slug": hub_slug,
        "filename": filename,
        "output_path": output_path_new,
        "canonical": canonical,
        "title": title,
        "description": description,
        "card_blurb": card_blurb,
        "content_html": content_html.strip(),
        "_source_file": obj.get("_source_file", ""),
    }

def build_article_lookup(articles: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    # Key by (hub_slug, filename.html)
    m: Dict[Tuple[str, str], Dict] = {}
    for a in articles:
        key = (a["hub_slug"], ensure_html_filename(a["filename"]))
        m[key] = a
    return m

def hub_index_body(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]], lookup: Dict[Tuple[str, str], Dict]) -> str:
    cards: List[str] = []
    for t, fn in items:
        fn2 = ensure_html_filename(fn)
        href = f"/{hub_slug}/{fn2}"
        a = lookup.get((hub_slug, fn2))
        blurb = a["card_blurb"] if a else f"Practical guide in {hub_title.lower()}."
        cards.append(card_html(t, blurb, href, "Open"))

    return f"""
<header class="hub-hero">
  <h1>{escape(hub_title)}</h1>
  <p class="subtitle">{escape(hub_desc)}</p>
</header>

<section class="grid">
  {"".join(cards)}
</section>
""".strip()

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

def write_search_index(items: List[Dict[str, str]]) -> None:
    payload = {"items": items, "generated": str(date.today())}
    write_text(out_path(SEARCH_INDEX_FILENAME), json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

def main() -> int:
    if not BASE_HTML_PATH.exists():
        raise SystemExit("Missing base.html in repo root.")

    base_html = read_text(BASE_HTML_PATH)
    gtag = load_gtag_snippet()

    urls_for_sitemap: List[str] = []
    search_items: List[Dict[str, str]] = []

    # Load + normalize articles FIRST so hubs can pull real card blurbs
    raw_objs = load_article_json_files()
    articles: List[Dict] = []
    skipped = 0
    for o in raw_objs:
        a = normalize_article_obj(o)
        if a:
            articles.append(a)
        else:
            skipped += 1
    lookup = build_article_lookup(articles)

    # Homepage
    home_url = f"{SITE_BASE}/"
    home_html = template_render(
        base_html=base_html,
        title=SITE_NAME,
        description="Practical lawn, weed, irrigation, soil, and yard safety guides.",
        canonical=home_url,
        content_html=homepage_body(),
        gtag=gtag,
    )
    write_text(out_path("index.html"), home_html)
    urls_for_sitemap.append(home_url)
    search_items.append({"t": SITE_NAME, "u": "/", "d": "Homepage"})

    # Hub index pages
    for slug, hub_title, hub_desc in HUBS:
        items = read_hub_filenames_csv(slug)
        hub_url = f"{SITE_BASE}/{slug}/"
        hub_html = template_render(
            base_html=base_html,
            title=f"{hub_title} - {SITE_NAME}",
            description=hub_desc,
            canonical=hub_url,
            content_html=hub_index_body(slug, hub_title, hub_desc, items, lookup),
            gtag=gtag,
        )
        write_text(out_path(f"{slug}/index.html"), hub_html)
        urls_for_sitemap.append(hub_url)
        search_items.append({"t": hub_title, "u": f"/{slug}/", "d": hub_desc})
        log(f"Built hub: {slug}/index.html")

    # Article pages
    built = 0
    for a in articles:
        page_html = template_render(
            base_html=base_html,
            title=a["title"],
            description=a["description"],
            canonical=a["canonical"],
            content_html=a["content_html"],
            gtag=gtag,
        )
        write_text(out_path(a["output_path"]), page_html)
        urls_for_sitemap.append(a["canonical"])
        search_items.append({"t": a["title"], "u": f'/{a["output_path"]}', "d": a["description"]})
        built += 1

    write_sitemap(urls_for_sitemap)
    write_search_index(search_items)

    if VERBOSE:
        print(f"Built hubs={len(HUBS)} articles={built} skipped_json={skipped} output_dir='{OUTPUT_DIR or ''}'")
    else:
        if built == 0 and raw_objs:
            print("Built 0 articles. JSON missing required fields: hub_slug, filename, title, content_html.")
        elif not raw_objs:
            print("No pages_json/*.json found. Built homepage, hubs, sitemap, search index only.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
