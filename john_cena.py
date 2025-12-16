#!/usr/bin/env python3
# john_cena.py
#
# Uses YOUR layout:
# - base.html in repo root
# - pages_json/<hub_slug>/*.json (recursive)
# - <hub_slug>/filenames.csv (title,filename) as the master internal-link database
# - Writes:
#   - index.html
#   - <hub_slug>/index.html
#   - <hub_slug>/<filename>.html (article pages)
#   - sitemap.xml
#   - search-index.json (optional, but used by your on-site search)
#
# Key behaviors:
# - Converts ".json" -> ".html" (never ".json.html")
# - Internal links injected inside the article HTML (2–4 links each)
# - ~85% same-hub links, ~15% cross-hub links (best-effort, based on availability)
# - Skips rewriting files if output content is identical (fast incremental builds)
# - Hard-fails duplicate outputs (same hub + same filename)

from __future__ import annotations

import csv
import json
import os
import re
import hashlib
import random
from pathlib import Path
from datetime import date
from html import escape
from typing import Dict, List, Optional, Tuple, Any

SITE_NAME = "GrizzlyGreens"
SITE_DOMAIN = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_DOMAIN}"

BASE_HTML_PATH = Path("base.html")
PAGES_JSON_DIR = Path("pages_json")
SITEMAP_PATH = Path("sitemap.xml")
SEARCH_INDEX_PATH = Path("search-index.json")

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "").strip())  # optional override
VERBOSE = os.environ.get("VERBOSE", "0").strip() == "1"

HUBS: List[Tuple[str, str, str]] = [
    ("lawn-basics", "Lawn and Grass Basics", "Grass types, mowing basics, common problems, and practical fixes."),
    ("weeds-pests", "Weeds, Pests, & Lawn Diseases", "Identification first, then control: weeds, insects, and common lawn diseases."),
    ("watering-irrigation", "Watering, Irrigation & Drainage", "Watering schedules, sprinkler setups, drainage issues, and fixes that work."),
    ("soil-fertilizer", "Soil, Fertilizer & Amendments", "Soil basics, nutrients, pH, and amendments that actually move the needle."),
    ("tools-safety", "Tools, Equipment & Yard Safety", "Tools that matter, maintenance, and safety rules that prevent dumb injuries."),
]

TITLE_NUM_PREFIX_RE = re.compile(r"^\s*\d+\.\s*")

def log(msg: str) -> None:
    if VERBOSE:
        print(msg)

def out_path(rel: str) -> Path:
    rel = (rel or "").lstrip("/")
    if str(OUTPUT_DIR):
        return OUTPUT_DIR / rel
    return Path(rel)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_if_changed(path: Path, content: str, stats: Dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old == content:
            stats["skipped"] += 1
            return
    path.write_text(content, encoding="utf-8", newline="\n")
    stats["written"] += 1

def normalize_slug(s: str) -> str:
    return (s or "").strip().strip("/")

def clean_title(t: str) -> str:
    t = (t or "").strip()
    t = TITLE_NUM_PREFIX_RE.sub("", t)
    return t.strip()

def ensure_html_filename(name: str) -> str:
    name = (name or "").strip()
    lower = name.lower()
    if lower.endswith(".html"):
        return name
    if lower.endswith(".json"):
        return name[:-5] + ".html"
    return name + ".html"

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
    # If you want GTAG in base.html directly, leave this empty and keep {{GTAG}} in base.html.
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

def stable_rng(seed_text: str) -> random.Random:
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    seed_int = int(h[:16], 16)
    return random.Random(seed_int)

def read_hub_filenames_csv(hub_slug: str) -> List[Tuple[str, str]]:
    # Reads /<hub_slug>/filenames.csv with header: title,filename
    csv_path = Path(hub_slug) / "filenames.csv"
    if not csv_path.exists():
        return []
    rows: List[Tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = clean_title((r.get("title") or "").strip())
            fn = (r.get("filename") or "").strip()
            if not t or not fn:
                continue
            rows.append((t, ensure_html_filename(fn)))
    return rows

def load_internal_link_db_from_csv() -> Dict[str, List[Tuple[str, str]]]:
    # Master DB of linkable pages per hub, from filenames.csv (your real setup)
    db: Dict[str, List[Tuple[str, str]]] = {}
    for hub_slug, _hub_title, _hub_desc in HUBS:
        db[hub_slug] = read_hub_filenames_csv(hub_slug)
    return db

def choose_internal_links(
    hub_slug: str,
    out_filename_html: str,
    link_db: Dict[str, List[Tuple[str, str]]],
    total_min: int = 2,
    total_max: int = 4,
    same_hub_ratio: float = 0.85,
) -> List[Tuple[str, str]]:
    hub_slug = normalize_slug(hub_slug)
    out_filename_html = ensure_html_filename(out_filename_html)

    rng = stable_rng(f"{hub_slug}/{out_filename_html}")
    total = rng.choice([2, 3, 3, 4])
    total = max(total_min, min(total_max, total))

    same_target = max(0, min(total, int(round(total * same_hub_ratio))))
    cross_target = total - same_target

    self_href = f"/{hub_slug}/{out_filename_html}"
    chosen: List[Tuple[str, str]] = []
    used = {self_href}

    same_pool = [(t, f"/{hub_slug}/{ensure_html_filename(fn)}") for (t, fn) in link_db.get(hub_slug, [])]
    same_pool = [(t, href) for (t, href) in same_pool if href not in used]
    rng.shuffle(same_pool)
    for t, href in same_pool:
        if len(chosen) >= same_target:
            break
        if href in used:
            continue
        chosen.append((t, href))
        used.add(href)

    other_hubs = [h for (h, _t, _d) in HUBS if h != hub_slug]
    rng.shuffle(other_hubs)
    cross_pool: List[Tuple[str, str]] = []
    for h in other_hubs:
        for t, fn in link_db.get(h, []):
            href = f"/{h}/{ensure_html_filename(fn)}"
            if href not in used:
                cross_pool.append((t, href))
    rng.shuffle(cross_pool)
    for t, href in cross_pool:
        if len(chosen) >= (same_target + cross_target):
            break
        if href in used:
            continue
        chosen.append((t, href))
        used.add(href)

    if len(chosen) < total:
        # Fill whatever is left from anywhere
        remaining: List[Tuple[str, str]] = []
        for h in [hub_slug] + other_hubs:
            for t, fn in link_db.get(h, []):
                href = f"/{h}/{ensure_html_filename(fn)}"
                if href not in used:
                    remaining.append((t, href))
        rng.shuffle(remaining)
        for t, href in remaining:
            if len(chosen) >= total:
                break
            if href in used:
                continue
            chosen.append((t, href))
            used.add(href)

    return chosen[:total]

# ADDED: inline link slot support (keeps old behavior as fallback if slots are not present)
INLINE_LINK_SLOTS = [
    "{{INTERNAL_LINK_SLOT_1}}",
    "{{INTERNAL_LINK_SLOT_2}}",
    "{{INTERNAL_LINK_SLOT_3}}",
    "{{INTERNAL_LINK_SLOT_4}}",
]

def render_inline_link(title: str, href: str) -> str:
    return f'<a href="{href}">{escape(title)}</a>'

def inject_inline_links_via_slots(content_html: str, links: List[Tuple[str, str]]) -> Tuple[str, int]:
    html = (content_html or "")
    if not html or not links:
        return html, 0
    inserted = 0
    for slot, (title, href) in zip(INLINE_LINK_SLOTS, links):
        if slot in html:
            html = html.replace(slot, render_inline_link(title, href), 1)
            inserted += 1
    return html, inserted

def inject_links_inside_article(content_html: str, links: List[Tuple[str, str]]) -> str:
    if not links:
        return content_html

    html = (content_html or "").rstrip()
    if not html:
        return html

    # New preferred behavior: replace inline slots inside paragraphs
    html2, inserted = inject_inline_links_via_slots(html, links)
    if inserted > 0:
        # Remove any unused slots so they never ship
        for slot in INLINE_LINK_SLOTS:
            html2 = html2.replace(slot, "")
        return html2

    # Fallback: keep your existing "Related guides" block behavior unchanged
    li = "".join([f'<li><a href="{href}">{escape(title)}</a></li>' for (title, href) in links])
    block = (
        '<section class="related-guides">'
        '<h2>Related guides</h2>'
        '<ul class="related-list">' + li + '</ul>'
        '</section>'
    )

    # Insert after first paragraph if possible
    m = re.search(r"</p\s*>", html2, flags=re.IGNORECASE)
    if m:
        i = m.end()
        return html2[:i] + "\n" + block + "\n" + html2[i:]

    # Else insert after first h1 if present
    m = re.search(r"</h1\s*>", html2, flags=re.IGNORECASE)
    if m:
        i = m.end()
        return html2[:i] + "\n" + block + "\n" + html2[i:]

    # Else append
    return html2 + "\n" + block + "\n"

def card_html(title: str, blurb: str, href: str) -> str:
    return f"""
<article class="card card-link">
  <a class="card-hit" href="{href}" aria-label="{escape(title)}"></a>
  <h2><a class="card-title-link" href="{href}">{escape(title)}</a></h2>
  <p class="card-blurb">{escape(blurb)}</p>
  <a class="read-more" href="{href}">Read article</a>
</article>
""".strip()

def homepage_body() -> str:
    cards: List[str] = []
    for slug, hub_title, desc in HUBS:
        cards.append(card_html(hub_title, desc, f"/{slug}/"))
    return f"""
<section class="hero">
  <h1>{escape(SITE_NAME)}</h1>
  <p class="subtitle">Fast, practical lawn and yard knowledge. No fluff.</p>
</section>
<section class="cards">
  {"".join(cards)}
</section>
""".strip()

def hub_index_body(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]], article_lookup: Dict[Tuple[str, str], Dict[str, Any]]) -> str:
    cards: List[str] = []
    for t, fn_html in items:
        fn_html = ensure_html_filename(fn_html)
        href = f"/{hub_slug}/{fn_html}"
        a = article_lookup.get((hub_slug, fn_html))
        blurb = (a.get("card_blurb") or a.get("description") or hub_desc) if a else hub_desc
        cards.append(card_html(t, blurb, href))
    return f"""
<section class="hub-hero">
  <h1>{escape(hub_title)}</h1>
  <p class="subtitle">{escape(hub_desc)}</p>
</section>
<section class="cards">
  {"".join(cards)}
</section>
""".strip()

def load_article_json_files() -> List[Dict[str, Any]]:
    objs: List[Dict[str, Any]] = []
    if not PAGES_JSON_DIR.exists():
        return objs
    for path in sorted(PAGES_JSON_DIR.rglob("*.json")):
        try:
            obj = json.loads(read_text(path))
            if isinstance(obj, dict):
                obj["_source_file"] = str(path)
                objs.append(obj)
        except Exception:
            continue
    return objs

def normalize_article_obj(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    hub_slug = normalize_slug(obj.get("hub_slug") or "")
    filename = (obj.get("filename") or "").strip()

    output_path_old = (obj.get("output_path") or obj.get("outputPath") or "").strip().lstrip("/")
    if not filename and output_path_old:
        filename = output_path_old.split("/")[-1]

    # If filename still missing, derive from JSON file name (pages_json/<hub>/<slug>.json)
    if not filename:
        src = (obj.get("_source_file") or "")
        if src:
            stem = Path(src).name  # e.g. how-grass-actually-grows.json
            filename = stem

    if not hub_slug:
        if output_path_old and "/" in output_path_old:
            hub_slug = normalize_slug(output_path_old.split("/")[0])
        else:
            # Try derive from folder in pages_json: pages_json/<hub>/...
            src = (obj.get("_source_file") or "")
            if src:
                parts = Path(src).parts
                # find "pages_json" then next segment
                if "pages_json" in parts:
                    i = parts.index("pages_json")
                    if i + 1 < len(parts):
                        hub_slug = normalize_slug(parts[i + 1])
    if not hub_slug:
        return None

    if not filename:
        return None

    filename_html = ensure_html_filename(filename)
    output_path_new = build_output_path(hub_slug, filename_html)
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
        "filename": filename_html,
        "output_path": output_path_new,
        "canonical": canonical,
        "title": title,
        "description": description,
        "card_blurb": card_blurb,
        "content_html": content_html.strip(),
        "_source_file": obj.get("_source_file", ""),
    }

def enforce_no_duplicate_outputs(articles: List[Dict[str, Any]]) -> None:
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for a in articles:
        key = (a["hub_slug"], a["filename"])
        if key in seen:
            raise SystemExit(
                "Duplicate article JSON detected for the same output:\n"
                f"Output: {a['hub_slug']}/{a['filename']}\n"
                f"First JSON:  {seen[key].get('_source_file','(unknown)')}\n"
                f"Second JSON: {a.get('_source_file','(unknown)')}\n"
                "Fix: delete one JSON or change filename/hub_slug so outputs are unique."
            )
        seen[key] = a

def write_sitemap(urls: List[str], stats: Dict[str, int]) -> None:
    clean = sorted({u.strip() for u in urls if u and u.strip()})
    items = [f"  <url><loc>{escape(u)}</loc></url>" for u in clean]
    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        *items,
        "</urlset>",
        "",
    ])
    write_if_changed(out_path(str(SITEMAP_PATH)), xml, stats)

def write_search_index(items: List[Dict[str, str]], stats: Dict[str, int]) -> None:
    payload = {"items": items, "generated": str(date.today())}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    write_if_changed(out_path(str(SEARCH_INDEX_PATH)), text, stats)

def main() -> int:
    if not BASE_HTML_PATH.exists():
        raise SystemExit("Missing base.html in repo root.")

    base_html = read_text(BASE_HTML_PATH)
    gtag = load_gtag_snippet()

    stats = {"written": 0, "skipped": 0}

    # Link DB must match YOUR real files: <hub>/filenames.csv
    link_db = load_internal_link_db_from_csv()
    if VERBOSE:
        for h, rows in link_db.items():
            log(f"link_db[{h}] = {len(rows)} (from {h}/filenames.csv)")

    raw = load_article_json_files()
    articles: List[Dict[str, Any]] = []
    for o in raw:
        a = normalize_article_obj(o)
        if a:
            articles.append(a)

    enforce_no_duplicate_outputs(articles)

    # Build lookup for hub cards to use real card_blurb if JSON exists
    article_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for a in articles:
        article_lookup[(a["hub_slug"], a["filename"])] = a

    urls: List[str] = []
    search_items: List[Dict[str, str]] = []

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
    write_if_changed(out_path("index.html"), home_html, stats)
    urls.append(home_url)
    search_items.append({"t": SITE_NAME, "u": "/", "d": "Homepage"})

    # Hub pages
    for hub_slug, hub_title, hub_desc in HUBS:
        items = read_hub_filenames_csv(hub_slug)
        hub_url = f"{SITE_BASE}/{hub_slug}/"
        hub_html = template_render(
            base_html=base_html,
            title=f"{hub_title} - {SITE_NAME}",
            description=hub_desc,
            canonical=hub_url,
            content_html=hub_index_body(hub_slug, hub_title, hub_desc, items, article_lookup),
            gtag=gtag,
        )
        write_if_changed(out_path(f"{hub_slug}/index.html"), hub_html, stats)
        urls.append(hub_url)
        search_items.append({"t": hub_title, "u": f"/{hub_slug}/", "d": hub_desc})

    # Article pages + internal link injection
    injected_count = 0
    for a in articles:
        # IMPORTANT: link candidates come from filenames.csv across hubs
        links = choose_internal_links(a["hub_slug"], a["filename"], link_db)
        if links:
            injected_count += 1

        content_with_links = inject_links_inside_article(a["content_html"], links)

        page_html = template_render(
            base_html=base_html,
            title=a["title"],
            description=a["description"],
            canonical=a["canonical"],
            content_html=content_with_links,
            gtag=gtag,
        )
        write_if_changed(out_path(a["output_path"]), page_html, stats)
        urls.append(a["canonical"])
        search_items.append({"t": a["title"], "u": f'/{a["output_path"]}', "d": a["description"]})

    write_sitemap(urls, stats)
    write_search_index(search_items, stats)

    if VERBOSE:
        print(f"json_found={len(raw)} articles_built={len(articles)} injected={injected_count} written={stats['written']} skipped={stats['skipped']}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
