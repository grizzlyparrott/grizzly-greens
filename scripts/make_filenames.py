#!/usr/bin/env python3
# make_filenames.py
# Usage: python make_filenames.py path/to/hub/titles.txt
# Output: path/to/hub/filenames.csv

import csv
import re
import sys
import unicodedata
from pathlib import Path

MAX_TOTAL_LEN = 50  # total filename length INCLUDING ".html"
EXT = ".html"

def slugify(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"^\d+[\.\)\-]*\s*", "", s)  # remove leading "1. " / "1) " / "1 - "
    s = s.replace("&", " and ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s if s else "untitled"

def enforce_len(base: str) -> str:
    max_base_len = MAX_TOTAL_LEN - len(EXT)
    trimmed = base[:max_base_len].rstrip("-")
    return trimmed if trimmed else "untitled"

def unique_name(base: str, used: set) -> str:
    base = enforce_len(base)
    candidate = base
    n = 2
    while candidate + EXT in used:
        suffix = f"-{n}"
        allowed = MAX_TOTAL_LEN - len(EXT) - len(suffix)
        candidate = enforce_len(base[:allowed] + suffix)
        n += 1
    used.add(candidate + EXT)
    return candidate + EXT

def main():
    if len(sys.argv) != 2:
        print("Usage: python make_filenames.py path/to/titles.txt")
        sys.exit(1)

    titles_path = Path(sys.argv[1])
    if not titles_path.exists():
        print("titles.txt not found")
        sys.exit(1)

    hub_dir = titles_path.parent
    out_path = hub_dir / "filenames.csv"

    titles = [
        line.strip()
        for line in titles_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    used = set()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "filename"])
        for title in titles:
            base = slugify(title)
            filename = unique_name(base, used)
            writer.writerow([title, filename])

    print(f"Wrote {len(titles)} filenames to {out_path.resolve()}")

if __name__ == "__main__":
    main()
