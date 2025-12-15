#!/usr/bin/env python3
# build_pages.py — FINAL
#
# RULES (non-negotiable):
# - base.html owns ALL layout (nav, search, footer, scripts)
# - This script injects ONLY page body into {{CONTENT}}
# - Cards show REAL article previews (card_blurb → description → fallback)
# - Entire card is clickable with a real CTA
# - Generates sitemap.xml + search-index.json
#
# Inputs:
# - base.html (repo root)
# - pages_json/*.json
# - <hub_slug>/filenames.csv  (title,filename)

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from datetime import date
from html import escape
from typing import Dict, List, Tuple, Optional

SITE_NAME = "GrizzlyGreens"
SITE_DOMAIN = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_DOMAIN}"

BASE_HTML = Path("base.html")
PAGES_JSON_DIR = Path("pages_json")

SITEMAP_FILE = "sitemap.xml"
SEARCH_INDEX_FILE = "search-index.json"

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "").strip())
VERBOSE = os.environ.get("VERBOSE", "0") == "1"

HUBS = [
    ("lawn-basics", "Lawn and Grass Basics", "Grass types, mowing basics, common problems, and practical fixes."),
    ("weeds-pests", "Weeds, Pests, & Lawn Diseases", "Identification first, then control: weeds, insects, and common lawn diseases."),
    ("watering-irrigation", "Watering, Irrigation, & Drainage", "Watering schedules, sprinkler setups, drainage issues, and fixes that work."),
    ("soil-fertilizer", "Soil, Fertilizer, & Amendments", "Soil basics, nutrients, pH, and amendments that actually move the needle."),
    ("tools-safety", "Tools, Equipment, & Yard Safety", "Tools that matter, maintenance, and safety rules that prevent dumb injuries."),
]

# ------------------ helpers ------------------

def log(msg: str) -> None:
    if VERBOSE:
        print(msg)

def out_path(rel: str) -> Path:
    rel = rel.lstrip("/")
    return OUTPUT_DIR / rel if str(OUTPUT_DIR) else Path(rel)

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write_text(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")

def ensure_html(fn: str) -> str:
    return fn if fn.endswith(".html") else fn + ".html"

def canonical(path: str) -> str:
    return f"{SITE_BASE}/{path.lstrip('/')}"

def load_gtag() -> str:
    return os.environ.get("GTAG", "").strip()

# ------------------ rendering ------------------

def render(base: str, title: str, desc: str, canon: str, body: str, gtag: str) -> str:
    html = base
    html = html.replace("{{TITLE}}", escape(title))
    html = html.replace("{{DESCRIPTION}}", escape(desc))
    html = html.replace("{{CANONICAL}}", escape(canon))
    html = html.replace("{{GTAG}}", gtag)
    html = html.replace("{{CONTENT}}", body)
    html = html.replace("{{CONTENT_HTML}}", body)
    return html

def card_html(title: str, blurb: str, href: str) -> str:
    return f"""
<article class="card card-link">
  <a class="card-hit" href="{href}" aria-label="{escape(title)}"></a>
  <h2 class="card-title">{escape(title)}</h2>
  <p class="card-text">{escape(blurb)}</p>
  <div class="card-actions">
    <span class="card-cta">Read article →</span>
  </div>
</article>
""".strip()

# ------------------ content builders ------------------

def homepage_body() -> str:
    cards = []
    for slug, title, desc in HUBS:
        cards.append(card_html(title, desc, f"/{slug}/"))
    return f"""
<header class="hero">
  <h1>{SITE_NAME}</h1>
  <p class="subtitle">Fast, practical lawn and yard knowledge. No fluff.</p>
</header>
<section class="grid">
  {"".join(cards)}
</section>
""".strip()

def hub_body(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]], lookup: Dict) -> str:
    cards = []
    for title, fn in items:
        fn = ensure_html(fn)
        art = lookup.get((hub_slug, fn))
        blurb = art["card_blurb"] if art else hub_desc
        cards.append(card_html(title, blurb, f"/{hub_slug}/{fn}"))
    return f"""
<header class="hub-hero">
  <h1>{escape(hub_title)}</h1>
  <p class="subtitle">{escape(hub_desc)}</p>
</header>
<section class="grid">
  {"".join(cards)}
</section>
""".strip()

# ------------------ data loading ------------------

def load_articles() -> List[Dict]:
    articles = []
    for p in sorted(PAGES_JSON_DIR.glob("*.json")):
        obj = json.loads(read_text(p))
        hub = obj.get("hub_slug")
        fn = ensure_html(obj.get("filename", ""))
        if not hub or not fn:
            continue
        articles.append({
            "hub": hub,
            "fn": fn,
            "title": obj["title"],
            "desc": obj.get("description", obj["title"]),
            "card_blurb": obj.get("card_blurb", obj.get("description", "")),
            "html": obj["content_html"],
        })
    return articles

def read_filenames_csv(hub: str) -> List[Tuple[str, str]]:
    p = Path(hub) / "filenames.csv"
    if not p.exists():
        return []
    rows = []
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["title"], r["filename"]))
    return rows

# ------------------ outputs ------------------

def write_sitemap(urls: List[str]) -> None:
    xml = "\n".join(
        ['<?xml version="1.0" encoding="UTF-8"?>',
         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'] +
        [f"<url><loc>{escape(u)}</loc></url>" for u in sorted(set(urls))] +
        ["</urlset>"]
    )
    write_text(out_path(SITEMAP_FILE), xml)

def write_search_index(items: List[Dict]) -> None:
    payload = {"items": items, "generated": str(date.today())}
    write_text(out_path(SEARCH_INDEX_FILE), json.dumps(payload, separators=(",", ":")))

# ------------------ main ------------------

def main() -> int:
    base = read_text(BASE_HTML)
    gtag = load_gtag()

    urls = []
    search_items = []

    articles = load_articles()
    lookup = {(a["hub"], a["fn"]): a for a in articles}

    # homepage
    home_html = render(
        base,
        SITE_NAME,
        "Practical lawn, weed, irrigation, soil, and yard safety guides.",
        f"{SITE_BASE}/",
        homepage_body(),
        gtag,
    )
    write_text(out_path("index.html"), home_html)
    urls.append(f"{SITE_BASE}/")
    search_items.append({"t": SITE_NAME, "u": "/", "d": "Homepage"})

    # hubs
    for slug, title, desc in HUBS:
        items = read_filenames_csv(slug)
        body = hub_body(slug, title, desc, items, lookup)
        page = render(base, f"{title} – {SITE_NAME}", desc, canonical(f"{slug}/"), body, gtag)
        write_text(out_path(f"{slug}/index.html"), page)
        urls.append(canonical(f"{slug}/"))
        search_items.append({"t": title, "u": f"/{slug}/", "d": desc})

    # articles
    for a in articles:
        page = render(
            base,
            a["title"],
            a["desc"],
            canonical(f'{a["hub"]}/{a["fn"]}'),
            a["html"],
            gtag,
        )
        write_text(out_path(f'{a["hub"]}/{a["fn"]}'), page)
        urls.append(canonical(f'{a["hub"]}/{a["fn"]}'))
        search_items.append({"t": a["title"], "u": f'/{a["hub"]}/{a["fn"]}', "d": a["desc"]})

    write_sitemap(urls)
    write_search_index(search_items)

    log(f"Built {len(articles)} articles")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
