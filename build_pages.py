#!/usr/bin/env python3
# build_pages.py
# GrizzlyGreens static generator (GitHub Pages friendly)
# - Reads base.html template
# - Reads pages_json/*.json for article content
# - Reads each hub's filenames.csv for hub index cards
# - Writes:
#   - /index.html (homepage)
#   - /<hub_slug>/index.html (hub pages)
#   - /<hub_slug>/<filename>.html (article pages)
#   - /sitemap.xml

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
SITEMAP_PATH = Path("sitemap.xml")

# Hubs: folder slug -> display title + short description
HUBS = [
    ("lawn-basics", "Lawn and Grass Basics", "Grass types, mowing basics, common problems, and practical fixes."),
    ("weeds-pests", "Weeds, Pests, & Lawn Diseases", "Identification first, then control: weeds, insects, and common lawn diseases."),
    ("watering-irrigation", "Watering, Irrigation, & Drainage", "Watering schedules, sprinkler setups, drainage issues, and fixes that work."),
    ("soil-fertilizer", "Soil, Fertilizer, & Amendments", "Soil basics, nutrients, pH, and amendments that actually move the needle."),
    ("tools-safety", "Tools, Equipment, & Yard Safety", "Tools that matter, maintenance, and safety rules that prevent dumb injuries."),
]

# Footer links you already have in your template
FOOTER_LINKS = [
    ("/about.html", "About"),
    ("/disclaimer.html", "Disclaimer"),
    ("/privacy-policy.html", "Privacy Policy"),
    ("/sitemap.xml", "Sitemap"),
]

# ----------------------------
# Helpers
# ----------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

def ensure_html_filename(name: str) -> str:
    name = name.strip()
    if not name.lower().endswith(".html"):
        name += ".html"
    return name

def build_output_path(hub_slug: str, filename: str) -> str:
    hub_slug = hub_slug.strip().strip("/")

    # if someone accidentally passes "hub/file.html", keep it but normalize
    filename = filename.strip().lstrip("/")
    if "/" in filename:
        # already includes a folder
        parts = filename.split("/")
        filename = parts[-1]

    filename = ensure_html_filename(filename)
    return f"{hub_slug}/{filename}"

def build_canonical(output_path: str) -> str:
    output_path = output_path.lstrip("/")
    return f"{SITE_BASE}/{output_path}"

def template_render(base_html: str, title: str, description: str, canonical: str, content_html: str) -> str:
    # Support either {{CONTENT}} or {{CONTENT_HTML}} tokens in base.html
    html = base_html
    html = html.replace("{{TITLE}}", escape(title))
    html = html.replace("{{DESCRIPTION}}", escape(description))
    html = html.replace("{{CANONICAL}}", escape(canonical))
    html = html.replace("{{CONTENT_HTML}}", content_html)
    html = html.replace("{{CONTENT}}", content_html)
    return html

def nav_html(active_hub: Optional[str] = None) -> str:
    # Builds the top nav links; "Home" + hubs
    links = ['<nav class="topnav">']
    links.append('<a class="navlink" href="/">Home</a>')
    for slug, label, _desc in HUBS:
        cls = "navlink"
        if active_hub and slug == active_hub:
            cls += " active"
        links.append(f'<a class="{cls}" href="/{slug}/">{escape(label)}</a>')
    links.append("</nav>")
    return "\n".join(links)

def footer_html() -> str:
    parts = ['<footer class="site-footer">', '<div class="footer-links">']
    for href, text in FOOTER_LINKS:
        parts.append(f'<a href="{href}">{escape(text)}</a>')
    parts.append("</div>")
    parts.append(f'<div class="footer-copy">&copy; {date.today().year} {escape(SITE_DOMAIN)}</div>')
    parts.append("</footer>")
    return "\n".join(parts)

def search_bar_html(placeholder: str = "Search GrizzlyGreens...") -> str:
    # Stub UI only; you can wire JS later (like your other sites)
    return f"""
<div class="search-wrap">
  <input id="site-search" class="search" type="search" placeholder="{escape(placeholder)}" autocomplete="off">
</div>
""".strip()

def card_html(title: str, blurb: str, href: str, button_text: str = "Open") -> str:
    return f"""
<article class="card">
  <h2 class="card-title"><a href="{href}">{escape(title)}</a></h2>
  <p class="card-text">{escape(blurb)}</p>
  <a class="btn secondary" href="{href}">{escape(button_text)}</a>
</article>
""".strip()

def homepage_content() -> str:
    # Homepage: header + 5 hub cards
    hub_cards = []
    for slug, title, desc in HUBS:
        hub_cards.append(card_html(title, desc, f"/{slug}/", "Open hub"))
    return f"""
{nav_html(active_hub=None)}
{search_bar_html()}
<main class="container">
  <header class="hero">
    <h1>{escape(SITE_NAME)}</h1>
    <p class="subtitle">Fast, practical lawn and yard knowledge. No fluff. Built to scale cleanly.</p>
  </header>
  <section class="grid">
    {"".join(hub_cards)}
  </section>
</main>
{footer_html()}
""".strip()

def hub_index_content(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]]) -> str:
    # items = [(title, filename.html), ...] for that hub
    cards = []
    for title, filename in items:
        filename = ensure_html_filename(filename)
        href = f"/{hub_slug}/{filename}"
        # Use a generic blurb for now if you haven't authored yet; once JSON exists for that filename,
        # the hub page can be upgraded later to pull real blurbs.
        cards.append(card_html(title, "Practical guide in " + hub_title.lower() + ".", href, "Open"))
    return f"""
{nav_html(active_hub=hub_slug)}
{search_bar_html()}
<main class="container">
  <header class="hub-hero">
    <h1>{escape(hub_title)}</h1>
    <p class="subtitle">{escape(hub_desc)}</p>
  </header>
  <section class="grid">
    {"".join(cards)}
  </section>
</main>
{footer_html()}
""".strip()

def read_hub_filenames_csv(hub_slug: str) -> List[Tuple[str, str]]:
    # Reads /<hub_slug>/filenames.csv with header: title,filename
    csv_path = Path(hub_slug) / "filenames.csv"
    if not csv_path.exists():
        return []
    rows: List[Tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = (r.get("title") or "").strip()
            fn = (r.get("filename") or "").strip()
            if not t or not fn:
                continue
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
            # skip bad JSON; keep generator running
            continue
    return objs

def normalize_article_obj(obj: Dict) -> Optional[Dict]:
    # Minimal required for you: hub_slug + filename + content bits.
    # If old keys exist (output_path, canonical), accept them but normalize anyway.
    hub_slug = (obj.get("hub_slug") or "").strip().strip("/")
    filename = (obj.get("filename") or "").strip()

    # Back-compat: if filename missing but output_path present, derive filename from it
    output_path = (obj.get("output_path") or obj.get("outputPath") or "").strip().lstrip("/")
    if not filename and output_path:
        filename = output_path.split("/")[-1]

    if not hub_slug:
        # Back-compat: if output_path looks like hub/file.html, derive hub_slug
        if output_path and "/" in output_path:
            hub_slug = output_path.split("/")[0].strip()
        else:
            return None

    if not filename:
        return None

    filename = ensure_html_filename(filename)
    output_path2 = build_output_path(hub_slug, filename)
    canonical2 = build_canonical(output_path2)

    title = (obj.get("title") or "").strip()
    description = (obj.get("description") or "").strip()
    card_blurb = (obj.get("card_blurb") or obj.get("cardBlurb") or "").strip()
    content_html = obj.get("content_html") or obj.get("contentHtml") or ""

    # Hard requirement: title and content_html should exist for an article page.
    # If not, skip it rather than breaking the entire build.
    if not title or not isinstance(content_html, str) or not content_html.strip():
        return None

    # If bot didn't provide description/blurb yet, auto-fill minimally
    if not description:
        description = title
    if not card_blurb:
        card_blurb = description

    return {
        "hub_slug": hub_slug,
        "filename": filename,
        "output_path": output_path2,
        "canonical": canonical2,
        "title": title,
        "description": description,
        "card_blurb": card_blurb,
        "content_html": content_html,
        "_source_file": obj.get("_source_file", ""),
    }

def build_article_page(base_html: str, article: Dict) -> Tuple[str, str]:
    # returns (output_path, html)
    # Wrap content with shared nav/search/footer (so base.html stays generic)
    body = f"""
{nav_html(active_hub=article["hub_slug"])}
{search_bar_html()}
<main class="container article">
  {article["content_html"]}
</main>
{footer_html()}
""".strip()

    html = template_render(
        base_html=base_html,
        title=article["title"],
        description=article["description"],
        canonical=article["canonical"],
        content_html=body,
    )
    return article["output_path"], html

def build_simple_page(base_html: str, title: str, description: str, canonical: str, body_html: str) -> str:
    body = f"""
{nav_html(active_hub=None)}
{search_bar_html()}
<main class="container">
  {body_html}
</main>
{footer_html()}
""".strip()
    return template_render(base_html, title, description, canonical, body)

def write_sitemap(urls: List[str]) -> None:
    # De-dupe + stable order
    seen = set()
    clean = []
    for u in urls:
        u = u.strip()
        if not u or u in seen:
            continue
        seen.add(u)
        clean.append(u)

    items = []
    for u in clean:
        items.append(f"  <url><loc>{escape(u)}</loc></url>")

    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        *items,
        "</urlset>",
        "",
    ])
    write_text(SITEMAP_PATH, xml)

def main() -> int:
    if not BASE_HTML_PATH.exists():
        raise SystemExit("Missing base.html in repo root.")

    base_html = read_text(BASE_HTML_PATH)

    urls_for_sitemap: List[str] = []

    # 1) Homepage
    home_path = Path("index.html")
    home_html = template_render(
        base_html=base_html,
        title=SITE_NAME,
        description="Practical lawn, weed, irrigation, soil, and yard safety guides built to scale cleanly.",
        canonical=f"{SITE_BASE}/",
        content_html=homepage_content(),
    )
    write_text(home_path, home_html)
    urls_for_sitemap.append(f"{SITE_BASE}/")
    print("Built homepage index.html.")

    # 2) Hub index pages from filenames.csv (works even before articles exist)
    for slug, title, desc in HUBS:
        items = read_hub_filenames_csv(slug)
        hub_index_path = Path(slug) / "index.html"
        hub_html = template_render(
            base_html=base_html,
            title=f"{title} - {SITE_NAME}",
            description=desc,
            canonical=f"{SITE_BASE}/{slug}/",
            content_html=hub_index_content(slug, title, desc, items),
        )
        write_text(hub_index_path, hub_html)
        urls_for_sitemap.append(f"{SITE_BASE}/{slug}/")
    print(f"Built {len(HUBS)} hub index pages.")

    # 3) Article pages from pages_json/*.json
    raw_objs = load_article_json_files()
    article_objs: List[Dict] = []
    for o in raw_objs:
        a = normalize_article_obj(o)
        if a:
            article_objs.append(a)

    built_count = 0
    for a in article_objs:
        out_path, html = build_article_page(base_html, a)
        write_text(Path(out_path), html)
        urls_for_sitemap.append(build_canonical(out_path))
        built_count += 1

    print(f"Built {built_count} article pages from {len(raw_objs)} JSON files.")

    # 4) Sitemap
    write_sitemap(urls_for_sitemap)
    print(f"Wrote sitemap.xml with {len(set(urls_for_sitemap))} URLs.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
