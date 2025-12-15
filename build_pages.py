# build_pages.py
# Generates:
# - Article pages from pages_json/*.json
# - Hub index pages (cards) from hub filenames.csv + whatever articles exist
# - Root homepage index.html (hub cards)
# - sitemap.xml (only canonical URLs)
#
# JSON expected per article (in pages_json/*.json):
# {
#   "hub_slug": "lawn-basics",
#   "filename": "what-type-of-grass-do-i-have.html",
#   "title": "What Type of Grass Do I Have",
#   "description": "One-sentence meta description.",
#   "card_blurb": "Short blurb for hub cards.",
#   "tags": ["optional", "array"],
#   "content_html": "<h1>...</h1><p>...</p>..."
# }

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional


SITE_NAME = "GrizzlyGreens"
SITE_DOMAIN = "https://grizzlygreens.net"

# Folder slugs you told me you use in the repo
HUBS: List[Tuple[str, str]] = [
    ("lawn-basics", "Lawn and Grass Basics"),
    ("weeds-pests", "Weeds, Pests, & Lawn Diseases"),
    ("watering-irrigation", "Watering, Irrigation, & Drainage"),
    ("soil-fertilizer", "Soil, Fertilizer, & Amendments"),
    ("tools-safety", "Tools, Equipment, & Yard Safety"),
]

REPO_ROOT = Path(__file__).resolve().parent
PAGES_JSON_DIR = REPO_ROOT / "pages_json"
BASE_HTML_PATH = REPO_ROOT / "base.html"
STYLES_CSS_PATH = REPO_ROOT / "styles.css"


def now_yyyy_mm_dd() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def normalize_filename(fn: str) -> str:
    fn = fn.strip()
    if not fn:
        return fn
    if not fn.lower().endswith(".html"):
        fn = fn + ".html"
    return fn


def hub_folder(hub_slug: str) -> Path:
    return REPO_ROOT / hub_slug


def url_for(hub_slug: str, filename: str) -> str:
    filename = normalize_filename(filename)
    return f"/{hub_slug}/{filename}"


def canonical_for(hub_slug: str, filename: str) -> str:
    return f"{SITE_DOMAIN}{url_for(hub_slug, filename)}"


def safe_md5_int(s: str) -> int:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def load_hub_filenames_csv(hub_slug: str) -> List[Tuple[str, str]]:
    """
    Returns list of (title, filename) from /{hub_slug}/filenames.csv
    """
    path = hub_folder(hub_slug) / "filenames.csv"
    if not path.exists():
        return []
    out: List[Tuple[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        # expects headers: title,filename
        for row in reader:
            title = (row.get("title") or "").strip()
            filename = normalize_filename((row.get("filename") or "").strip())
            if title and filename:
                out.append((title, filename))
    return out


def build_master_link_pool() -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Returns:
      pool_by_hub[hub_slug] = list of (title, filename, url_path)
    """
    pool_by_hub: Dict[str, List[Tuple[str, str, str]]] = {}
    for hub_slug, _hub_title in HUBS:
        items = []
        for title, filename in load_hub_filenames_csv(hub_slug):
            items.append((title, filename, url_for(hub_slug, filename)))
        pool_by_hub[hub_slug] = items
    return pool_by_hub


def pick_internal_links(
    pool_by_hub: Dict[str, List[Tuple[str, str, str]]],
    hub_slug: str,
    this_filename: str,
    k_same: int = 2,
    k_cross: int = 2,
) -> List[Tuple[str, str]]:
    """
    Picks (anchor_text, href) pairs deterministically based on hub+filename.
    Prefers same hub first, then cross hubs.
    """
    this_filename = normalize_filename(this_filename)
    seed = safe_md5_int(f"{hub_slug}|{this_filename}")

    chosen: List[Tuple[str, str]] = []

    same_pool = [x for x in pool_by_hub.get(hub_slug, []) if x[1] != this_filename]
    if same_pool:
        start = seed % len(same_pool)
        for i in range(min(k_same, len(same_pool))):
            t, _fn, href = same_pool[(start + i) % len(same_pool)]
            chosen.append((t, href))

    cross_items: List[Tuple[str, str, str]] = []
    for other_hub, _ in HUBS:
        if other_hub == hub_slug:
            continue
        cross_items.extend(pool_by_hub.get(other_hub, []))

    if cross_items:
        start = (seed * 7 + 13) % len(cross_items)
        for i in range(min(k_cross, len(cross_items))):
            t, _fn, href = cross_items[(start + i) % len(cross_items)]
            chosen.append((t, href))

    # Ensure uniqueness by href, preserve order
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for t, href in chosen:
        if href in seen:
            continue
        seen.add(href)
        uniq.append((t, href))
    return uniq


def inject_links_into_content_html(content_html: str, links: List[Tuple[str, str]]) -> str:
    """
    Inserts 2 links after the first </p> and 2 links near the end (before last </p> if found),
    without needing the bot to generate links.
    """
    if not links:
        return content_html

    first_two = links[:2]
    last_two = links[2:4]

    def make_links_block(pairs: List[Tuple[str, str]]) -> str:
        # Plain, SEO-safe: one sentence, two links
        if not pairs:
            return ""
        parts = [f'<a href="{href}">{text}</a>' for text, href in pairs]
        if len(parts) == 1:
            return f"<p>Related: {parts[0]}.</p>"
        return f"<p>Related: {parts[0]} and {parts[1]}.</p>"

    block_a = make_links_block(first_two)
    block_b = make_links_block(last_two)

    html = content_html

    # Insert block_a after first </p>
    idx = html.find("</p>")
    if idx != -1 and block_a:
        insert_at = idx + len("</p>")
        html = html[:insert_at] + "\n" + block_a + html[insert_at:]
    elif block_a:
        # fallback: prepend
        html = block_a + "\n" + html

    # Insert block_b near end: before last </p> (or append)
    if block_b:
        last_idx = html.rfind("</p>")
        if last_idx != -1:
            insert_at = last_idx + len("</p>")
            html = html[:insert_at] + "\n" + block_b + html[insert_at:]
        else:
            html = html + "\n" + block_b

    return html


def render_base(
    title: str,
    description: str,
    canonical: str,
    nav_html: str,
    body_html: str,
    gtag_id: Optional[str] = None,
) -> str:
    base = read_text(BASE_HTML_PATH)

    # Simple placeholder replacement (base.html must contain these tokens)
    out = base
    out = out.replace("{{PAGE_TITLE}}", title)
    out = out.replace("{{META_DESCRIPTION}}", description)
    out = out.replace("{{CANONICAL_URL}}", canonical)
    out = out.replace("{{NAV_HTML}}", nav_html)
    out = out.replace("{{BODY_HTML}}", body_html)

    if "{{GTAG_SNIPPET}}" in out:
        if gtag_id:
            snippet = (
                '<!-- Google tag (gtag.js) -->\n'
                f'<script async src="https://www.googletagmanager.com/gtag/js?id={gtag_id}"></script>\n'
                "<script>\n"
                "  window.dataLayer = window.dataLayer || [];\n"
                "  function gtag(){dataLayer.push(arguments);}\n"
                "  gtag('js', new Date());\n\n"
                f"  gtag('config', '{gtag_id}');\n"
                "</script>\n"
            )
            out = out.replace("{{GTAG_SNIPPET}}", snippet)
        else:
            out = out.replace("{{GTAG_SNIPPET}}", "")
    return out


def nav_html() -> str:
    # Hardcoded nav to hub indexes + home
    links = ['<a href="/">Home</a>']
    for hub_slug, hub_title in HUBS:
        links.append(f'<a href="/{hub_slug}/">{hub_title}</a>')
    return '<nav class="top-nav">' + "\n".join(links) + "</nav>"


def hub_index_card(title: str, blurb: str, href: str) -> str:
    return (
        '<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-desc">{blurb}</div>'
        f'<a class="btn" href="{href}">Open hub</a>'
        "</div>"
    )


def article_card(title: str, blurb: str, href: str) -> str:
    return (
        '<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-desc">{blurb}</div>'
        f'<a class="btn" href="{href}">Read</a>'
        "</div>"
    )


def build_homepage(gtag_id: Optional[str] = None) -> None:
    hub_blurbs = {
        "lawn-basics": "Grass types, mowing basics, common problems, and practical fixes.",
        "weeds-pests": "Identification first, then control: weeds, insects, and common lawn diseases.",
        "watering-irrigation": "Watering frequency, drainage, irrigation basics, and drought-proofing.",
        "soil-fertilizer": "Soil, fertilizer, compost, amendments, and what actually moves the needle.",
        "tools-safety": "Tools that matter, how to use them, and how to avoid dumb injuries.",
    }

    cards = []
    for hub_slug, hub_title in HUBS:
        cards.append(hub_index_card(hub_title, hub_blurbs.get(hub_slug, ""), f"/{hub_slug}/"))

    body = (
        f"<h1>{SITE_NAME}</h1>\n"
        "<p>Fast, practical lawn and yard knowledge. No fluff. Built to scale cleanly.</p>\n"
        '<div class="cards">' + "\n".join(cards) + "</div>\n"
    )

    html = render_base(
        title=f"{SITE_NAME}",
        description="Practical lawn, yard, and DIY outdoor knowledge: grass, weeds, watering, soil, and tools.",
        canonical=f"{SITE_DOMAIN}/",
        nav_html=nav_html(),
        body_html=body,
        gtag_id=gtag_id,
    )
    write_text(REPO_ROOT / "index.html", html)


def build_hub_indexes(gtag_id: Optional[str] = None) -> None:
    """
    Builds /{hub}/index.html using filenames.csv titles and whatever article JSONs exist for blurbs.
    """
    # Build blurb lookup from existing JSONs (hub_slug+filename -> (title, blurb))
    blurb_lookup: Dict[Tuple[str, str], Tuple[str, str]] = {}
    if PAGES_JSON_DIR.exists():
        for p in sorted(PAGES_JSON_DIR.glob("*.json")):
            try:
                data = json.loads(read_text(p))
            except Exception:
                continue
            hub = (data.get("hub_slug") or "").strip()
            fn = normalize_filename((data.get("filename") or "").strip())
            title = (data.get("title") or "").strip()
            blurb = (data.get("card_blurb") or "").strip()
            if hub and fn and title:
                blurb_lookup[(hub, fn)] = (title, blurb)

    for hub_slug, hub_title in HUBS:
        items = load_hub_filenames_csv(hub_slug)
        cards = []
        for title, filename in items:
            href = url_for(hub_slug, filename)
            t2, b2 = blurb_lookup.get((hub_slug, filename), (title, ""))
            cards.append(article_card(t2, b2, href))

        body = (
            f"<h1>{hub_title}</h1>\n"
            '<div class="cards">' + "\n".join(cards) + "</div>\n"
        )

        html = render_base(
            title=f"{hub_title} | {SITE_NAME}",
            description=f"{hub_title} guides and articles.",
            canonical=f"{SITE_DOMAIN}/{hub_slug}/",
            nav_html=nav_html(),
            body_html=body,
            gtag_id=gtag_id,
        )
        write_text(hub_folder(hub_slug) / "index.html", html)


def build_articles(gtag_id: Optional[str] = None) -> int:
    pool_by_hub = build_master_link_pool()
    count = 0

    if not PAGES_JSON_DIR.exists():
        return 0

    for p in sorted(PAGES_JSON_DIR.glob("*.json")):
        data = json.loads(read_text(p))

        hub_slug = (data.get("hub_slug") or "").strip()
        filename = normalize_filename((data.get("filename") or "").strip())
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        content_html = (data.get("content_html") or "").strip()

        if not hub_slug or not filename or not title or not content_html:
            continue

        links = pick_internal_links(pool_by_hub, hub_slug, filename, k_same=2, k_cross=2)
        content_html = inject_links_into_content_html(content_html, links)

        canonical = canonical_for(hub_slug, filename)

        body = content_html

        html = render_base(
            title=f"{title} | {SITE_NAME}",
            description=description,
            canonical=canonical,
            nav_html=nav_html(),
            body_html=body,
            gtag_id=gtag_id,
        )

        out_path = hub_folder(hub_slug) / filename
        write_text(out_path, html)
        count += 1

    return count


def build_sitemap() -> int:
    """
    Only canonical URLs: homepage, hub indexes, and any article pages listed in pages_json.
    """
    urls: List[Tuple[str, str]] = []

    today = now_yyyy_mm_dd()

    urls.append((f"{SITE_DOMAIN}/", today))
    for hub_slug, _ in HUBS:
        urls.append((f"{SITE_DOMAIN}/{hub_slug}/", today))

    if PAGES_JSON_DIR.exists():
        for p in sorted(PAGES_JSON_DIR.glob("*.json")):
            try:
                data = json.loads(read_text(p))
            except Exception:
                continue
            hub_slug = (data.get("hub_slug") or "").strip()
            filename = normalize_filename((data.get("filename") or "").strip())
            if hub_slug and filename:
                urls.append((canonical_for(hub_slug, filename), today))

    # Deduplicate
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for u, lm in urls:
        if u in seen:
            continue
        seen.add(u)
        uniq.append((u, lm))

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u, lm in uniq:
        lines.append("  <url>")
        lines.append(f"    <loc>{u}</loc>")
        lines.append(f"    <lastmod>{lm}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")

    write_text(REPO_ROOT / "sitemap.xml", "\n".join(lines) + "\n")
    return len(uniq)


def main() -> int:
    # If you have a GA4 Measurement ID already, put it here. Example: "G-XXXXXXXXXX"
    GTAG_ID: Optional[str] = None

    if not BASE_HTML_PATH.exists():
        raise FileNotFoundError(f"Missing base.html at {BASE_HTML_PATH}")

    if not STYLES_CSS_PATH.exists():
        raise FileNotFoundError(f"Missing styles.css at {STYLES_CSS_PATH}")

    articles_built = build_articles(gtag_id=GTAG_ID)
    build_hub_indexes(gtag_id=GTAG_ID)
    build_homepage(gtag_id=GTAG_ID)
    sitemap_count = build_sitemap()

    print(f"Built {articles_built} article pages from JSON files.")
    print(f"Built {len(HUBS)} hub index pages.")
    print("Built homepage index.html.")
    print(f"Wrote sitemap.xml with {sitemap_count} URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
