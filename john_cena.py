#!/usr/bin/env python3
# jon_cena.py — build + incremental + internal link injection
#
# What it does:
# - base.html owns chrome; this injects ONLY {{CONTENT}} / {{CONTENT_HTML}}
# - reads pages_json/**.json (recursive)
# - reads internal link DB from /<hub_slug>/filenames.json (supports REAL JSON or "title,filename" lines)
# - injects 2–4 internal links per article (~85% same hub, ~15% cross hub) deterministically
# - hub index uses /<hub_slug>/filenames.csv for titles, and uses JSON card_blurb if available
# - incremental writes (writes only if file content changed)
# - hard-fails duplicates (same hub_slug + filename)

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

TITLE_NUM_PREFIX_RE = re.compile(r"^\s*\d+\.\s*")
CSV_HEADER_RE = re.compile(r"^\s*title\s*,\s*filename\s*$", re.I)

def log(msg: str) -> None:
    if VERBOSE:
        print(msg)

def out_path(rel: str) -> Path:
    rel = (rel or "").lstrip("/")
    return (OUTPUT_DIR / rel) if str(OUTPUT_DIR) else Path(rel)

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

def clean_title(t: str) -> str:
    t = (t or "").strip()
    t = TITLE_NUM_PREFIX_RE.sub("", t)
    return t.strip()

def parse_title_filename_line(line: str) -> Optional[Tuple[str, str]]:
    s = (line or "").strip()
    if not s:
        return None
    if s.startswith("#"):
        return None
    if CSV_HEADER_RE.match(s):
        return None
    if "," not in s:
        return None
    title, fn = s.split(",", 1)
    title = clean_title(title.strip().strip('"').strip("'"))
    fn = fn.strip().strip('"').strip("'")
    if not title or not fn:
        return None
    fn = ensure_html_filename(fn)
    return (title, fn)

def coerce_link_rows(data: Any) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                t = clean_title(str(item.get("title", "")).strip())
                fn = str(item.get("filename", "")).strip()
                if t and fn:
                    rows.append((t, ensure_html_filename(fn)))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                t = clean_title(str(item[0]).strip())
                fn = str(item[1]).strip()
                if t and fn:
                    rows.append((t, ensure_html_filename(fn)))
    elif isinstance(data, dict):
        # accept {"items":[...]} or {"links":[...]}
        for k in ("items", "links"):
            if k in data and isinstance(data[k], list):
                rows.extend(coerce_link_rows(data[k]))
    return rows

def load_internal_link_db() -> Dict[str, List[Tuple[str, str]]]:
    db: Dict[str, List[Tuple[str, str]]] = {}
    for hub_slug, _hub_title, _hub_desc in HUBS:
        p = Path(hub_slug) / "filenames.json"
        rows: List[Tuple[str, str]] = []
        if p.exists():
            raw = read_text(p)
            parsed_as_json = False
            try:
                j = json.loads(raw)
                rows = coerce_link_rows(j)
                parsed_as_json = True
            except Exception:
                parsed_as_json = False
            if not parsed_as_json:
                for line in raw.splitlines():
                    got = parse_title_filename_line(line)
                    if got:
                        rows.append(got)
        db[hub_slug] = rows
    return db

def stable_rng(seed_text: str) -> random.Random:
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    seed_int = int(h[:16], 16)
    return random.Random(seed_int)

def choose_internal_links(
    hub_slug: str,
    filename: str,
    link_db: Dict[str, List[Tuple[str, str]]],
    total_min: int = 2,
    total_max: int = 4,
    same_hub_ratio: float = 0.85,
) -> List[Tuple[str, str]]:
    hub_slug = normalize_slug(hub_slug)
    filename = ensure_html_filename(filename)

    rng = stable_rng(f"{hub_slug}/{filename}")
    total = rng.choice([2, 3, 3, 4])
    total = max(total_min, min(total_max, total))

    same_target = max(0, min(total, int(round(total * same_hub_ratio))))
    cross_target = total - same_target

    self_href = f"/{hub_slug}/{filename}"
    chosen: List[Tuple[str, str]] = []
    chosen_hrefs = set([self_href])

    same_pool = link_db.get(hub_slug, [])
    same_pool = [(t, f"/{hub_slug}/{ensure_html_filename(fn)}") for (t, fn) in same_pool if f"/{hub_slug}/{ensure_html_filename(fn)}" != self_href]
    rng.shuffle(same_pool)
    for t, href in same_pool:
        if len(chosen) >= same_target:
            break
        if href in chosen_hrefs:
            continue
        chosen.append((t, href))
        chosen_hrefs.add(href)

    other_hubs = [h for (h, _t, _d) in HUBS if h != hub_slug]
    rng.shuffle(other_hubs)
    cross_pool: List[Tuple[str, str]] = []
    for h in other_hubs:
        for t, fn in link_db.get(h, []):
            href = f"/{h}/{ensure_html_filename(fn)}"
            if href not in chosen_hrefs:
                cross_pool.append((t, href))
    rng.shuffle(cross_pool)
    for t, href in cross_pool:
        if len(chosen) >= (same_target + cross_target):
            break
        if href in chosen_hrefs:
            continue
        chosen.append((t, href))
        chosen_hrefs.add(href)

    if len(chosen) < total:
        remaining: List[Tuple[str, str]] = []
        for h in [hub_slug] + other_hubs:
            for t, fn in link_db.get(h, []):
                href = f"/{h}/{ensure_html_filename(fn)}"
                if href not in chosen_hrefs:
                    remaining.append((t, href))
        rng.shuffle(remaining)
        for t, href in remaining:
            if len(chosen) >= total:
                break
            if href in chosen_hrefs:
                continue
            chosen.append((t, href))
            chosen_hrefs.add(href)

    return chosen[:total]

def inject_links_inside_article(content_html: str, links: List[Tuple[str, str]]) -> str:
    if not links:
        return content_html

    li = "".join([f'<li><a href="{href}">{escape(title)}</a></li>' for (title, href) in links])
    block = (
        '<section class="related-guides">'
        '<h2>Related guides</h2>'
        '<ul class="related-list">' + li + '</ul>'
        '</section>'
    )

    html = content_html.rstrip()

    # Prefer inserting after the first paragraph so it is "inside" the article, not a footer.
    idx = html.lower().find("</p>")
    if idx != -1:
        insert_at = idx + 4
        return html[:insert_at] + "\n" + block + "\n" + html[insert_at:]

    # Otherwise insert after first h2 if no paragraph exists.
    idx2 = html.lower().find("</h2>")
    if idx2 != -1:
        insert_at2 = idx2 + 5
        return html[:insert_at2] + "\n" + block + "\n" + html[insert_at2:]

    # Worst case: append.
    return html + "\n" + block + "\n"

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

def hub_index_body(hub_slug: str, hub_title: str, hub_desc: str, items: List[Tuple[str, str]], lookup: Dict[Tuple[str, str], Dict]) -> str:
    cards: List[str] = []
    for t, fn in items:
        fn2 = ensure_html_filename(fn)
        href = f"/{hub_slug}/{fn2}"
        a = lookup.get((hub_slug, fn2))
        blurb = a["card_blurb"] if a else hub_desc
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

def load_article_json_files() -> List[Dict]:
    objs: List[Dict] = []
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
    m: Dict[Tuple[str, str], Dict] = {}
    for a in articles:
        m[(a["hub_slug"], ensure_html_filename(a["filename"]))] = a
    return m

def enforce_no_duplicate_outputs(articles: List[Dict]) -> None:
    seen: Dict[Tuple[str, str], Dict] = {}
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
    write_if_changed(out_path(SITEMAP_FILENAME), xml, stats)

def write_search_index(items: List[Dict[str, str]], stats: Dict[str, int]) -> None:
    payload = {"items": items, "generated": str(date.today())}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    write_if_changed(out_path(SEARCH_INDEX_FILENAME), text, stats)

def main() -> int:
    if not BASE_HTML_PATH.exists():
        raise SystemExit("Missing base.html in repo root.")

    base_html = read_text(BASE_HTML_PATH)
    gtag = load_gtag_snippet()

    stats = {"written": 0, "skipped": 0}

    link_db = load_internal_link_db()
    if VERBOSE:
        for h, rows in link_db.items():
            log(f"links_db[{h}]={len(rows)}")

    raw_objs = load_article_json_files()
    articles: List[Dict] = []
    for o in raw_objs:
        a = normalize_article_obj(o)
        if a:
            articles.append(a)

    enforce_no_duplicate_outputs(articles)
    lookup = build_article_lookup(articles)

    urls_for_sitemap: List[str] = []
    search_items: List[Dict[str, str]] = []

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
    urls_for_sitemap.append(home_url)
    search_items.append({"t": SITE_NAME, "u": "/", "d": "Homepage"})

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
        write_if_changed(out_path(f"{slug}/index.html"), hub_html, stats)
        urls_for_sitemap.append(hub_url)
        search_items.append({"t": hub_title, "u": f"/{slug}/", "d": hub_desc})

    for a in articles:
        picked = choose_internal_links(a["hub_slug"], a["filename"], link_db)
        body = inject_links_inside_article(a["content_html"], picked)

        page_html = template_render(
            base_html=base_html,
            title=a["title"],
            description=a["description"],
            canonical=a["canonical"],
            content_html=body,
            gtag=gtag,
        )
        write_if_changed(out_path(a["output_path"]), page_html, stats)
        urls_for_sitemap.append(a["canonical"])
        search_items.append({"t": a["title"], "u": f'/{a["output_path"]}', "d": a["description"]})

    write_sitemap(urls_for_sitemap, stats)
    write_search_index(search_items, stats)

    if VERBOSE:
        print(f"json_found={len(raw_objs)} articles_built={len(articles)} written={stats['written']} skipped={stats['skipped']}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
