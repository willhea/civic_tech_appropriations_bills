"""Download PDF counterparts for XML bill versions we already have locally.

For each ``bills/<congress>-<type>-<number>/<idx>_<slug>.xml`` file, look
up the version's PDF URL via the Congress.gov API (matching by version
type slug) and save the PDF next to the XML as
``<idx>_<slug>.pdf``. Skips when the PDF already exists.

Usage:
    uv run python scripts/fetch_pdfs_for_existing_xmls.py 118-hr-4366
    uv run python scripts/fetch_pdfs_for_existing_xmls.py --all
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_URL = "https://api.congress.gov/v3"


def sanitize(name: str) -> str:
    if not name:
        return "unknown"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unknown"


def fetch_versions(client: httpx.Client, congress: int, bill_type: str, number: int, *, api_key: str) -> list[dict]:
    url = f"{BASE_URL}/bill/{congress}/{bill_type}/{number}/text"
    for attempt in range(3):
        r = client.get(url, params={"api_key": api_key, "format": "json"})
        if r.status_code == 429:
            print("Rate limited, waiting 60s", file=sys.stderr)
            time.sleep(60)
            continue
        r.raise_for_status()
        return r.json().get("textVersions", [])
    return []


def pdf_url(version: dict) -> str | None:
    for fmt in version.get("formats", []):
        if fmt.get("type") == "PDF":
            return fmt.get("url")
    return None


def download(client: httpx.Client, url: str, dest: Path) -> None:
    for attempt in range(3):
        r = client.get(url)
        if r.status_code == 429:
            time.sleep(60)
            continue
        if r.status_code >= 500:
            time.sleep(2**attempt)
            continue
        r.raise_for_status()
        dest.write_bytes(r.content)
        return
    raise RuntimeError(f"Failed to download {url}")


def parse_bill_dir(name: str) -> tuple[int, str, int] | None:
    parts = name.split("-")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), "-".join(parts[1:-1]), int(parts[-1])
    except ValueError:
        return None


def fetch_for_bill(client: httpx.Client, bill_dir: Path, *, api_key: str) -> None:
    parsed = parse_bill_dir(bill_dir.name)
    if parsed is None:
        print(f"  skipping non-bill dir {bill_dir.name}", file=sys.stderr)
        return
    congress, bill_type, number = parsed

    xmls = sorted(bill_dir.glob("*.xml"))
    if not xmls:
        return

    versions = fetch_versions(client, congress, bill_type, number, api_key=api_key)
    by_slug = {sanitize(v.get("type", "")): v for v in versions}

    for xml_path in xmls:
        m = re.match(r"^(\d+)_(.+)$", xml_path.stem)
        if not m:
            continue
        idx, slug = m.group(1), m.group(2)
        pdf_path = xml_path.with_suffix(".pdf")
        if pdf_path.exists():
            print(f"  exists {pdf_path}", file=sys.stderr)
            continue
        version = by_slug.get(slug)
        if version is None:
            print(f"  no API version for slug {slug!r} in {bill_dir.name}", file=sys.stderr)
            continue
        url = pdf_url(version)
        if url is None:
            print(f"  no PDF URL for {slug} in {bill_dir.name}", file=sys.stderr)
            continue
        print(f"  downloading {pdf_path} <- {url}", file=sys.stderr)
        download(client, url, pdf_path)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("bills", nargs="*", help="Bill dir names (e.g. 118-hr-4366); empty + --all = all")
    p.add_argument("--all", action="store_true", help="Process every bill dir under bills/")
    p.add_argument("--bills-dir", type=Path, default=Path("bills"))
    args = p.parse_args()

    load_dotenv()
    api_key = os.environ.get("CONGRESS_API_KEY", "DEMO_KEY")
    if api_key == "DEMO_KEY":
        print("WARNING: using DEMO_KEY (30 req/hr)", file=sys.stderr)

    if args.all:
        targets = sorted(d for d in args.bills_dir.iterdir() if d.is_dir())
    else:
        targets = [args.bills_dir / b for b in args.bills]
        if not targets:
            p.error("Pass bill dir names or --all")

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for d in targets:
            print(f"\n{d.name}", file=sys.stderr)
            fetch_for_bill(client, d, api_key=api_key)


if __name__ == "__main__":
    main()
