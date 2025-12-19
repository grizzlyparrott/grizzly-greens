#!/usr/bin/env python3
import os
import re
import json
from pathlib import Path

# Folders to index (add/remove as needed)
HUB_DIRS = [
    "lawn-basics",
    "watering-irrigation",
    "weeds-pests",
    "soil-fertilizer",
    "tools-safety",
]

OUTFILE = "search-index.json"

TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
H1_RE = re.compile(r"<h1[^>]*>\s*(.*?)\s*</h1>", re.IGNORECASE | re.DOTALL)
META_DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")

def clean_text(s: str) -> str:
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def strip_tags(s: str) -> str:
    return clean_text(TAG_RE.sub("", s))

def read_file_text(p: Path) -> str:
    # Try UTF-8 first; fall back to latin-1 to avoid crashing on odd characters.
    try:
        return p.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1", errors="replace")

def extract_title(html: str, fallback_name: str) -> str:
    m = TITLE_RE.search(html)
    if m:
        t = strip_tags(m.group(1))
        if t:
            return t
    m = H1_RE.search(html)
    if m:
        t = strip_tags(m.group(1))
        if t:
            return t
    return fallback_name

def extract_description(html: str) -> str:
    m = META_DESC_RE.search(html)
    if m:
        d = strip_tags(m.group(1))
        return d[:200]
    return ""

def build_index(root: Path) -> list:
    items = []
    for hub in HUB_DIRS:
        hub_path = root / hub
        if not hub_path.is_dir():
            continue
        for p in sorted(hub_path.rglob("*.html")):
            # Skip index pages if you don't want them searchable
            if p.name.lower() in ("index.html",):
                continue

            html = read_file_text(p)
            fallback = p.stem.replace("-", " ").title()
            title = extract_title(html, fallback)
            desc = extract_description(html)

            # Build site-relative URL
            rel = p.as_posix().lstrip("./")
            if not rel.startswith("/"):
                rel = "/" + rel

            items.append({
                "title": title,
                "url": rel,
                "description": desc,
                "hub": hub,
            })

    # De-dupe by URL (last one wins)
    dedup = {}
    for it in items:
        dedup[it["url"]] = it
    out = list(dedup.values())

    # Sort for stable diffs
    out.sort(key=lambda x: (x.get("hub", ""), x.get("title", ""), x.get("url", "")))
    return out

def main():
    root = Path(__file__).resolve().parent
    data = build_index(root)

    out_path = root / OUTFILE
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {len(data)} items to {OUTFILE}")

if __name__ == "__main__":
    main()
