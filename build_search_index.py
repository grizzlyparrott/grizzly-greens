# build_search_index.py
# Builds search-index.json for GrizzlyGreens.net
# - Only indexes the 5 main hub folders
# - Uses root-relative URLs (never local filesystem paths)
# - Pulls title + meta description (fallback to first paragraph)
# - Output: search-index.json in repo root

import json
import os
import re
from pathlib import Path
from html import unescape

# ---- CONFIG ----
HUB_DIRS = [
    "lawn-basics",
    "weeds-pests",
    "watering-irrigation",
    "soil-fertilizer",
    "tools-safety",
]

OUTPUT_FILE = "search-index.json"

# If True, skip hub index pages (e.g. lawn-basics/index.html)
SKIP_HUB_INDEX_PAGES = True

# If True, skip root index.html (not in hubs anyway)
SKIP_ROOT_INDEX = True

# Limit description length in the dropdown
DESC_MAX_CHARS = 180

# ---- HTML PARSING HELPERS (simple + robust enough for your static pages) ----
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")

def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def strip_tags(html_fragment: str) -> str:
    # Remove tags and unescape entities
    text = TAG_RE.sub("", html_fragment)
    return collapse_ws(unescape(text))

def extract_title(html: str) -> str:
    m = TITLE_RE.search(html)
    if not m:
        return ""
    return strip_tags(m.group(1))

def extract_meta_description(html: str) -> str:
    m = META_DESC_RE.search(html)
    if not m:
        return ""
    return strip_tags(m.group(1))

def extract_first_paragraph(html: str) -> str:
    # Grab first non-empty <p> that isn't just nav/footer junk
    for m in P_RE.finditer(html):
        txt = strip_tags(m.group(1))
        if len(txt) >= 40:
            return txt
    return ""

def clamp_desc(desc: str, max_chars: int) -> str:
    desc = collapse_ws(desc)
    if len(desc) <= max_chars:
        return desc
    cut = desc[: max_chars - 1].rstrip()
    # avoid cutting mid-word if possible
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"

def is_html_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".html"

def should_skip(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root).as_posix()

    if SKIP_ROOT_INDEX and rel == "index.html":
        return True

    if SKIP_HUB_INDEX_PAGES:
        # skip */index.html inside hubs
        for hub in HUB_DIRS:
            if rel == f"{hub}/index.html":
                return True

    return False

def path_to_url(path: Path, repo_root: Path) -> str:
    # Convert repo file path to site-root-relative URL
    rel = path.relative_to(repo_root).as_posix()
    return "/" + rel

def build_index(repo_root: Path) -> list[dict]:
    items = []
    for hub in HUB_DIRS:
        hub_path = repo_root / hub
        if not hub_path.exists():
            print(f"[WARN] Missing hub folder: {hub_path}")
            continue

        for html_path in hub_path.rglob("*.html"):
            if not is_html_file(html_path):
                continue
            if should_skip(html_path, repo_root):
                continue

            try:
                html = html_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"[WARN] Failed to read {html_path}: {e}")
                continue

            title = extract_title(html)
            desc = extract_meta_description(html)

            if not desc:
                desc = extract_first_paragraph(html)

            # If still empty, leave it empty but do not break the index
            if desc:
                desc = clamp_desc(desc, DESC_MAX_CHARS)

            url = path_to_url(html_path, repo_root)

            # Defensive: never allow Windows paths in output
            if ":" in url or url.lower().startswith("/c/") or "\\" in url:
                print(f"[WARN] Bad URL computed for {html_path}: {url}")
                continue

            # Optional: ignore pages with no title (usually indicates a bad build)
            if not title:
                # fallback to filename
                title = html_path.stem.replace("-", " ").strip().title()

            items.append(
                {
                    "title": title,
                    "description": desc,
                    "url": url,
                    "hub": hub,
                }
            )

    # Sort for stable diffs
    items.sort(key=lambda x: (x["hub"], x["title"].lower()))
    return items

def main() -> None:
    repo_root = Path(__file__).resolve().parent
    index = build_index(repo_root)

    out_path = repo_root / OUTPUT_FILE
    out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(index)} items to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
