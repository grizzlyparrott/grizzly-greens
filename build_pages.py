#!/usr/bin/env python3
# build_pages.py
# Reads base.html + pages_json/*.json and writes final HTML files + sitemap.xml.
# Placeholders required in base.html:
# {{PAGE_TITLE}}, {{META_DESCRIPTION}}, {{CANONICAL_URL}}, {{CONTENT}}

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

SITE_HOST = "grizzlygreens.net"
SITE_BASE = f"https://{SITE_HOST}"
PAGES_DIR = "pages_json"
BASE_FILE = "base.html"
SITEMAP_FILE = "sitemap.xml"

CANONICAL_BAD_SUFFIX = "/index.html"

def html_escape_attr(s: str) -> str:
    # Safe for title/description/canonical attribute contexts
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )

def norm_url(url: str) -> str:
    url = url.strip()
    p = urlparse(url)

    # Resolve relative canonical against site base
    if not p.scheme:
        path = url if url.startswith("/") else f"/{url}"
        p = urlparse(SITE_BASE)
        url = urlunparse((p.scheme, p.netloc, path, "", "", ""))
        p = urlparse(url)

    # Force https + correct host, drop query/fragment
    path = p.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    return urlunparse(("https", SITE_HOST, path, "", "", ""))

def validate_page(obj: dict, src_path: Path) -> dict:
    required = ["title", "description", "canonical", "output_path", "content_html"]
    for k in required:
        if k not in obj or not isinstance(obj[k], str) or not obj[k].strip():
            raise ValueError(f"{src_path}: missing/empty required field: {k}")

    title = obj["title"].strip()
    desc = obj["description"].strip()
    canonical = norm_url(obj["canonical"])
    out_path = obj["output_path"].strip().lstrip("/")  # keep repo-relative
    content = obj["content_html"].strip()

    if not canonical.startswith(SITE_BASE + "/") and canonical != SITE_BASE + "/":
        raise ValueError(f"{src_path}: canonical must be on {SITE_BASE}/ (got: {canonical})")

    if canonical.endswith(CANONICAL_BAD_SUFFIX):
        raise ValueError(f"{src_path}: canonical must not end with {CANONICAL_BAD_SUFFIX} (got: {canonical})")

    if out_path.endswith("/"):
        raise ValueError(f"{src_path}: output_path must be a file path ending in .html (got: {out_path})")

    if not out_path.lower().endswith(".html"):
        raise ValueError(f"{src_path}: output_path must end in .html (got: {out_path})")

    # Basic sanity: require an H1 near the start of content
    if "<h1" not in content.lower():
        raise ValueError(f"{src_path}: content_html must include an <h1>")

    return {
        "title": title,
        "description": desc,
        "canonical": canonical,
        "output_path": out_path,
        "content_html": content,
    }

def build_html(base_html: str, page: dict) -> str:
    html = base_html
    html = html.replace("{{PAGE_TITLE}}", html_escape_attr(page["title"]))
    html = html.replace("{{META_DESCRIPTION}}", html_escape_attr(page["description"]))
    html = html.replace("{{CANONICAL_URL}}", html_escape_attr(page["canonical"]))
    html = html.replace("{{CONTENT}}", page["content_html"])
    return html

def iso_date_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())

def write_sitemap(repo_root: Path, urls: list[str]) -> None:
    # Dedupe + stable sort
    uniq = sorted(set(urls))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    today = iso_date_utc()
    for u in uniq:
        lines.append("  <url>")
        lines.append(f"    <loc>{u}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    (repo_root / SITEMAP_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

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

    # Hard fail if placeholders are missing (prevents silent drift)
    for ph in ["{{PAGE_TITLE}}", "{{META_DESCRIPTION}}", "{{CANONICAL_URL}}", "{{CONTENT}}"]:
        if ph not in base_html:
            print(f"ERROR: base.html missing placeholder {ph}")
            return 2

    json_files = sorted(pages_path.glob("*.json"))
    if not json_files:
        print(f"ERROR: no JSON files found in {PAGES_DIR}/")
        return 2

    written = 0
    canonicals: list[str] = []

    for jf in json_files:
        raw = jf.read_text(encoding="utf-8", errors="strict")
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{jf}: invalid JSON: {e}")

        page = validate_page(obj, jf)
        out_file = repo_root / page["output_path"]
        out_file.parent.mkdir(parents=True, exist_ok=True)

        final_html = build_html(base_html, page)
        out_file.write_text(final_html, encoding="utf-8")

        written += 1
        canonicals.append(page["canonical"])

    # Always ensure homepage is in sitemap (if you generate it later, it will dedupe)
    canonicals.append(SITE_BASE + "/")

    write_sitemap(repo_root, canonicals)

    print(f"Built {written} pages from {len(json_files)} JSON files.")
    print(f"Wrote {SITEMAP_FILE} with {len(set(canonicals))} URLs.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
