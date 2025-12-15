#!/usr/bin/env python3
# build_pages.py
# Generates:
# - Article pages from pages_json/*.json (derived canonical + output path)
# - Hub index pages (/hub-slug/index.html) canonicalized to /hub-slug/
# - Homepage (/index.html) listing hubs as cards
# - sitemap.xml from canonicals only
#
# base.html must contain placeholders:
# {{PAGE_TITLE}}, {{META_DESCRIPTION}}, {{CANONICAL_URL}}, {{CONTENT}}

from __future__ import annotations

import json
import re
import time
from pathlib import Path

SITE_HOST = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_HOST}"

PAGES_DIR = "pages_json"
BASE_FILE = "base.html"
SITEMAP_FILE = "sitemap.xml"

CANONICAL_BAD_SUFFIX = "/index.html"
BLURB_CAP = 240

# Locked hub contract (do not casually change)
HUBS = {
    "lawn-basics": {
        "title": "Lawn and Grass Basics",
        "hub_card": "Grass types, mowing basics, common problems, and practical fixes.",
        "intro_html": (
            "<p>Foundational lawn knowledge without the fluff. Grass types, mowing basics, "
            "common problems, and practical fixes.</p>"
        ),
    },
    "weeds-pests": {
        "title": "Weeds, Pests, & Lawn Diseases",
        "hub_card": "Identification first, then control: weeds, insects, and common lawn diseases.",
        "intro_html": (
            "<p>Identification first, then control. Weeds, insects, and common lawn diseases "
            "with realistic fixes.</p>"
        ),
    },
    "watering-irrigation": {
        "title": "Watering, Irrigation, & Drainage",
        "hub_card": "Scheduling, irrigation basics, runoff, pooling, and drainage problems.",
        "intro_html": (
            "<p>Water is the lever. Scheduling, irrigation basics, runoff, pooling, and drainage problems.</p>"
        ),
    },
    "soil-fertilizer": {
        "title": "Soil, Fertilizer, & Amendments",
        "hub_card": "Soil fundamentals, fertilizer basics, amendments, pH, and improvement tactics.",
        "intro_html": (
            "<p>Soil drives everything. Fertilizer basics, amendments, pH, and practical soil improvement.</p>"
        ),
    },
    "tools-safety": {
        "title": "Tools, Equipment, & Yard Safety",
        "hub_card": "Tools that matter, how to use them, maintenance, and safety.",
        "intro_html": (
            "<p>Tools that actually matter, how to use them, and how to stay intact. "
            "Maintenance, safety, and choosing the right gear.</p>"
        ),
    },
}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def html_escape_attr(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def html_escape_text(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def cap_blurb(s: str, limit: int = BLURB_CAP) -> str:
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    cut = s[:limit].rstrip()
    # Avoid ugly mid-word cuts when possible
    sp = cut.rfind(" ")
    if sp >= max(0, limit - 40):
        cut = cut[:sp].rstrip()
    return cut + "…"


def iso_date_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def write_sitemap(repo_root: Path, urls: list[str]) -> None:
    uniq = sorted(set(urls))
    today = iso_date_utc()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
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


def hub_index_output_path(hub_slug: str) -> str:
    return f"{hub_slug}/index.html"


def hub_index_canonical(hub_slug: str) -> str:
    return f"{SITE_BASE}/{hub_slug}/"


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

    tags = obj.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list) or any((not isinstance(t, str) or not t.strip()) for t in tags):
        raise ValueError(f"{src_path}: tags must be an array of non-empty strings if provided")

    tags = [t.strip() for t in tags]

    if hub_slug not in HUBS:
        raise ValueError(f"{src_path}: hub_slug must be one of {sorted(HUBS.keys())} (got: {hub_slug})")

    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"{src_path}: slug must be lowercase kebab-case letters/numbers only (got: {slug})")

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
        "tags": tags,
        "output_path": output_path,
        "canonical": canonical,
    }


def build_article_cards(articles: list[dict]) -> str:
    cards = []
    for a in articles:
        href = f"/{a['hub_slug']}/{a['slug']}.html"
        title = html_escape_text(a["title"])
        blurb = html_escape_text(cap_blurb(a["card_blurb"]))
        tags = a.get("tags", [])

        tags_html = ""
        if tags:
            safe_tags = [html_escape_text(t) for t in tags]
            tags_html = f'<div class="card-tags">{" • ".join(safe_tags)}</div>'

        cards.append(
            f'<div class="card">'
            f'<h2 class="card-title"><a href="{href}">{title}</a></h2>'
            f'<p class="card-blurb">{blurb}</p>'
            f'{tags_html}'
            f'<a class="read-more" href="{href}">Read more</a>'
            f"</div>"
        )
    if not cards:
        return "<p>No articles yet.</p>"
    return '<div class="cards">\n' + "\n".join(cards) + "\n</div>"


def build_hub_index_content(hub_slug: str, articles: list[dict]) -> str:
    hub_title = HUBS[hub_slug]["title"]
    hub_intro = HUBS[hub_slug]["intro_html"]
    listing = build_article_cards(articles)
    return f"<h1>{html_escape_text(hub_title)}</h1>\n{hub_intro}\n{listing}"


def build_homepage_content() -> str:
    hub_cards = []
    for hub_slug in HUBS.keys():
        href = f"/{hub_slug}/"
        title = html_escape_text(HUBS[hub_slug]["title"])
        blurb = html_escape_text(HUBS[hub_slug]["hub_card"])
        hub_cards.append(
            f'<div class="card">'
            f'<h2 class="card-title"><a href="{href}">{title}</a></h2>'
            f'<p class="card-blurb">{blurb}</p>'
            f'<a class="read-more" href="{href}">Open hub</a>'
            f"</div>"
        )
    return (
        "<h1>GrizzlyGreens</h1>"
        "<p>Fast, practical lawn and yard knowledge. No fluff. Built to scale cleanly.</p>"
        '<div class="cards">\n' + "\n".join(hub_cards) + "\n</div>"
    )


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

    # Build hub index pages
    written_hubs = 0
    hub_urls_for_sitemap: list[str] = []
    for hub_slug in HUBS.keys():
        hub_articles = [a for a in articles if a["hub_slug"] == hub_slug]
        hub_articles.sort(key=lambda x: x["title"].lower())

        hub_content = build_hub_index_content(hub_slug, hub_articles)
        hub_title = HUBS[hub_slug]["title"]
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

    # Build homepage
    home_content = build_homepage_content()
    home_out = repo_root / "index.html"
    home_html = build_html(
        base_html=base_html,
        page_title="GrizzlyGreens",
        meta_desc="Practical lawn and yard knowledge across mowing, weeds, watering, soil, tools, and safety.",
        canonical_url=SITE_BASE + "/",
        content_html=home_content,
    )
    home_out.write_text(home_html, encoding="utf-8")

    # Sitemap: homepage + hub canonicals + article canonicals
    urls = [SITE_BASE + "/"]
    urls.extend(hub_urls_for_sitemap)
    urls.extend([a["canonical"] for a in articles])
    write_sitemap(repo_root, urls)

    print(f"Built {written_articles} article pages from {len(json_files)} JSON files.")
    print(f"Built {written_hubs} hub index pages.")
    print("Built homepage index.html.")
    print(f"Wrote {SITEMAP_FILE} with {len(set(urls))} URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
