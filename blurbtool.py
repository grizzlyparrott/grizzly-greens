#!/usr/bin/env python3
"""
Update GrizzlyGreens hub-card blurbs from each linked article's
<meta name="description">.

Safe behavior:
- Dry-run by default.
- Only writes files when --apply is included.
- Creates a timestamped backup beside the repository before writing.
- Preserves the rest of each hub page exactly as-is.
- Uses only Python's standard library.

Examples, run from the grizzly-greens repository root:

    py update_hub_blurbs.py --only soil-fertilizer/index.html
    py update_hub_blurbs.py --only soil-fertilizer/index.html --apply

    py update_hub_blurbs.py
    py update_hub_blurbs.py --apply
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ARTICLE_BLOCK_RE = re.compile(
    r'<article\b[^>]*\bclass=(["\'])[^"\']*\bcard-link\b[^"\']*\1[^>]*>'
    r'.*?</article>',
    re.IGNORECASE | re.DOTALL,
)

BLURB_RE = re.compile(
    r'(<p\b[^>]*\bclass=(["\'])[^"\']*\bcard-blurb\b[^"\']*\2[^>]*>)'
    r'(.*?)'
    r'(</p>)',
    re.IGNORECASE | re.DOTALL,
)

HREF_RE = re.compile(
    r'\bhref=(["\'])([^"\']+?\.html(?:[?#][^"\']*)?)\1',
    re.IGNORECASE,
)

TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")


class MetaDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.description is not None or tag.lower() != "meta":
            return

        values = {
            key.lower(): value
            for key, value in attrs
            if key and value is not None
        }

        if values.get("name", "").strip().lower() == "description":
            content = values.get("content", "").strip()
            if content:
                self.description = content


def read_text(path: Path) -> tuple[str, str]:
    """Read UTF-8 HTML while preserving whether it used a BOM."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def write_text(path: Path, text: str, encoding: str) -> None:
    path.write_text(text, encoding=encoding, newline="")


def plain_text(fragment: str) -> str:
    value = TAG_RE.sub("", fragment)
    value = html.unescape(value)
    return WHITESPACE_RE.sub(" ", value).strip()


def article_meta_description(article_path: Path) -> str | None:
    try:
        source, _ = read_text(article_path)
    except (OSError, UnicodeDecodeError):
        return None

    parser = MetaDescriptionParser()
    try:
        parser.feed(source)
    except Exception:
        return None

    return parser.description


def resolve_article_path(root: Path, hub_path: Path, href: str) -> Path | None:
    parsed = urlparse(html.unescape(href))

    # Ignore non-web schemes such as mailto:, javascript:, etc.
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None

    url_path = unquote(parsed.path)
    if not url_path.lower().endswith(".html"):
        return None

    if url_path.startswith("/"):
        candidate = root / url_path.lstrip("/")
    else:
        candidate = hub_path.parent / url_path

    try:
        candidate = candidate.resolve()
        root_resolved = root.resolve()
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return None

    return candidate


def first_article_href(article_block: str) -> str | None:
    match = HREF_RE.search(article_block)
    return match.group(2) if match else None


def collect_existing_blurbs(source: str) -> Counter[str]:
    blurbs: list[str] = []
    for article_match in ARTICLE_BLOCK_RE.finditer(source):
        blurb_match = BLURB_RE.search(article_match.group(0))
        if blurb_match:
            blurbs.append(plain_text(blurb_match.group(3)).casefold())
    return Counter(blurbs)


def update_hub(
    root: Path,
    hub_path: Path,
    replace_all: bool,
) -> tuple[str, list[dict[str, str]], int]:
    source, encoding = read_text(hub_path)
    existing_counts = collect_existing_blurbs(source)

    rows: list[dict[str, str]] = []
    changed_cards = 0

    def replace_article(article_match: re.Match[str]) -> str:
        nonlocal changed_cards

        block = article_match.group(0)
        href = first_article_href(block)
        blurb_match = BLURB_RE.search(block)

        if not href or not blurb_match:
            return block

        old_html = blurb_match.group(3)
        old_text = plain_text(old_html)

        # By default, protect one-off custom blurbs. The bad hub blurbs repeat
        # dozens of times, so they are replaced automatically.
        if not replace_all and existing_counts[old_text.casefold()] < 2:
            rows.append(
                {
                    "hub": str(hub_path.relative_to(root)),
                    "article": href,
                    "status": "skipped_unique_blurb",
                    "old_blurb": old_text,
                    "new_blurb": "",
                }
            )
            return block

        article_path = resolve_article_path(root, hub_path, href)
        if article_path is None:
            rows.append(
                {
                    "hub": str(hub_path.relative_to(root)),
                    "article": href,
                    "status": "invalid_article_path",
                    "old_blurb": old_text,
                    "new_blurb": "",
                }
            )
            return block

        if not article_path.is_file():
            rows.append(
                {
                    "hub": str(hub_path.relative_to(root)),
                    "article": str(article_path.relative_to(root)),
                    "status": "article_missing",
                    "old_blurb": old_text,
                    "new_blurb": "",
                }
            )
            return block

        description = article_meta_description(article_path)
        if not description:
            rows.append(
                {
                    "hub": str(hub_path.relative_to(root)),
                    "article": str(article_path.relative_to(root)),
                    "status": "meta_description_missing",
                    "old_blurb": old_text,
                    "new_blurb": "",
                }
            )
            return block

        new_text = WHITESPACE_RE.sub(" ", description).strip()
        new_html = html.escape(new_text, quote=False)

        if old_text == new_text:
            rows.append(
                {
                    "hub": str(hub_path.relative_to(root)),
                    "article": str(article_path.relative_to(root)),
                    "status": "already_correct",
                    "old_blurb": old_text,
                    "new_blurb": new_text,
                }
            )
            return block

        changed_cards += 1
        rows.append(
            {
                "hub": str(hub_path.relative_to(root)),
                "article": str(article_path.relative_to(root)),
                "status": "changed",
                "old_blurb": old_text,
                "new_blurb": new_text,
            }
        )

        start, end = blurb_match.span(3)
        return block[:start] + new_html + block[end:]

    updated_source = ARTICLE_BLOCK_RE.sub(replace_article, source)
    return updated_source, rows, changed_cards


def find_hubs(root: Path, only: str | None) -> list[Path]:
    if only:
        target = (root / only).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise ValueError("--only must point to a file inside the repository.")
        return [target]

    return sorted(
        path
        for path in root.rglob("index.html")
        if path.is_file() and "card-blurb" in path.read_text(encoding="utf-8", errors="ignore")
    )


def write_report(root: Path, rows: list[dict[str, str]]) -> Path:
    report_path = root / "hub_blurb_report.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["hub", "article", "status", "old_blurb", "new_blurb"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace repeated hub-card blurbs with linked article meta descriptions."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current folder.",
    )
    parser.add_argument(
        "--only",
        help="Process one hub path relative to the repository root, such as soil-fertilizer/index.html.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag, the script performs a dry run.",
    )
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Also replace one-off custom card blurbs. Default: only repeated blurbs.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: Repository folder does not exist: {root}", file=sys.stderr)
        return 2

    try:
        hubs = find_hubs(root, args.only)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not hubs:
        print("No hub index.html files containing card-blurb were found.")
        return 1

    missing_hubs = [path for path in hubs if not path.is_file()]
    if missing_hubs:
        for path in missing_hubs:
            print(f"ERROR: Hub file does not exist: {path}", file=sys.stderr)
        return 2

    run_results: list[tuple[Path, str, str, int]] = []
    all_rows: list[dict[str, str]] = []
    total_changed_cards = 0

    for hub_path in hubs:
        original, encoding = read_text(hub_path)
        updated, rows, changed_cards = update_hub(
            root=root,
            hub_path=hub_path,
            replace_all=args.replace_all,
        )
        run_results.append((hub_path, updated, encoding, changed_cards))
        all_rows.extend(rows)
        total_changed_cards += changed_cards

    changed_hubs = [item for item in run_results if item[3] > 0]
    report_path = write_report(root, all_rows)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"\nMode: {mode}")
    print(f"Repository: {root}")
    print(f"Hub files scanned: {len(hubs)}")
    print(f"Hub files needing changes: {len(changed_hubs)}")
    print(f"Card blurbs needing changes: {total_changed_cards}")
    print(f"Report: {report_path}")

    status_counts = Counter(row["status"] for row in all_rows)
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    if not args.apply:
        print("\nNothing was written. Review hub_blurb_report.csv, then rerun with --apply.")
        return 0

    if not changed_hubs:
        print("\nNo HTML files needed changes.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = root.parent / f"{root.name}-hub-blurb-backup-{timestamp}"

    try:
        for hub_path, updated, encoding, changed_cards in changed_hubs:
            relative = hub_path.relative_to(root)
            backup_path = backup_root / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hub_path, backup_path)
            write_text(hub_path, updated, encoding)
    except OSError as exc:
        print(f"\nERROR while writing files: {exc}", file=sys.stderr)
        print(f"Backups created so far are in: {backup_root}", file=sys.stderr)
        return 3

    print(f"\nUpdated {len(changed_hubs)} hub file(s) and {total_changed_cards} card blurb(s).")
    print(f"Backup folder: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
