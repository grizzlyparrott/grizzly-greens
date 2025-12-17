#!/usr/bin/env python3
# make_link_plans.py
# Reads:  <hub>/filenames.csv  (columns: title,filename)
# Writes: link_plans/<hub>-link-plan.csv
# Each output row: article_title, filename, link1_title, link1_filename, ... link4_title, link4_filename
#
# CHANGE: link*_filename now always includes the correct ROOT-RELATIVE hub path:
#   /<hub>/<filename>
# This prevents broken cross-hub links when used directly as an href in HTML.

from __future__ import annotations
import csv
import hashlib
import random
from pathlib import Path
from typing import Dict, List, Tuple, Set

HUBS = [
    "lawn-basics",
    "weeds-pests",
    "watering-irrigation",
    "soil-fertilizer",
    "tools-safety",
]

MIN_LINKS = 2
MAX_LINKS = 4

# "one out of every five or ten" cross-hub swap -> pick a probability you like
CROSS_HUB_PROB = 0.15  # ~15% ~= 1 out of 6-7 articles swap 1 link cross-hub

OUT_DIR = Path("link_plans")


def stable_rng(seed_text: str) -> random.Random:
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    seed_int = int(h[:16], 16)
    return random.Random(seed_int)


def read_filenames_csv(hub: str) -> List[Tuple[str, str]]:
    p = Path(hub) / "filenames.csv"
    if not p.exists():
        raise FileNotFoundError(f"Missing: {p}")
    rows: List[Tuple[str, str]] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or "title" not in r.fieldnames or "filename" not in r.fieldnames:
            raise ValueError(f"{p} must have headers: title,filename")
        for row in r:
            title = (row.get("title") or "").strip()
            fn = (row.get("filename") or "").strip()
            if not title or not fn:
                continue
            rows.append((title, fn))
    return rows


def pick_k(rng: random.Random) -> int:
    # Weighted slightly toward 3 links to avoid monotony
    choices = [2, 3, 3, 4]
    k = rng.choice(choices)
    return max(MIN_LINKS, min(MAX_LINKS, k))


def href_path(hub: str, fn: str) -> str:
    # Always root-relative, so it works from any page location.
    return f"/{hub}/{fn.lstrip('/')}"


def choose_distinct_same_hub(
    rng: random.Random,
    hub: str,
    pool: List[Tuple[str, str]],
    n: int,
    banned_hrefs: Set[str],
) -> List[Tuple[str, str]]:
    # pool: [(title, filename)]
    cands = [(t, fn) for (t, fn) in pool if href_path(hub, fn) not in banned_hrefs]
    rng.shuffle(cands)
    out: List[Tuple[str, str]] = []
    for t, fn in cands:
        h = href_path(hub, fn)
        if h in banned_hrefs:
            continue
        out.append((t, h))
        banned_hrefs.add(h)
        if len(out) >= n:
            break
    return out


def main() -> int:
    hub_db: Dict[str, List[Tuple[str, str]]] = {}
    for h in HUBS:
        hub_db[h] = read_filenames_csv(h)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for hub in HUBS:
        articles = hub_db[hub]
        out_path = OUT_DIR / f"{hub}-link-plan.csv"

        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "article_title", "filename",
                "link1_title", "link1_filename",
                "link2_title", "link2_filename",
                "link3_title", "link3_filename",
                "link4_title", "link4_filename",
            ])

            for title, filename in articles:
                rng = stable_rng(f"{hub}::{filename}")
                k = pick_k(rng)

                # Ban the current article itself, using the same format we output for links
                banned_hrefs: Set[str] = {href_path(hub, filename)}

                # Pick k distinct links from the same hub (output as /hub/file.html)
                same = choose_distinct_same_hub(rng, hub, articles, k, banned_hrefs)

                # Optionally swap exactly one slot with a cross-hub link (also /hub/file.html)
                if same and rng.random() < CROSS_HUB_PROB:
                    other_hubs = [h for h in HUBS if h != hub]
                    rng.shuffle(other_hubs)

                    cross_pool: List[Tuple[str, str]] = []  # [(title, href)]
                    for oh in other_hubs:
                        for t2, fn2 in hub_db[oh]:
                            h = href_path(oh, fn2)
                            if h in banned_hrefs:
                                continue
                            cross_pool.append((t2, h))

                    rng.shuffle(cross_pool)
                    if cross_pool:
                        swap_i = rng.randrange(len(same))
                        t2, h = cross_pool[0]
                        same[swap_i] = (t2, h)
                        banned_hrefs.add(h)

                # Normalize to 4 slots
                links = same[:4]
                while len(links) < 4:
                    links.append(("", ""))

                w.writerow([
                    title, filename,
                    links[0][0], links[0][1],
                    links[1][0], links[1][1],
                    links[2][0], links[2][1],
                    links[3][0], links[3][1],
                ])

        print(f"Wrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
