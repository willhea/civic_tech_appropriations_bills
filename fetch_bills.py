"""Download bill text versions from Congress.gov.

Uses the Congress.gov API v3 to fetch bill text in XML format
for downstream comparison between versions.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_URL = "https://api.congress.gov/v3"

# (human-readable label, congress.gov URL slug)
BILL_TYPES = {
    "hr": ("H.R.", "house-bill"),
    "s": ("S.", "senate-bill"),
    "hjres": ("H.J.Res.", "house-joint-resolution"),
    "sjres": ("S.J.Res.", "senate-joint-resolution"),
    "hres": ("H.Res.", "house-resolution"),
    "sres": ("S.Res.", "senate-resolution"),
    "hconres": ("H.Con.Res.", "house-concurrent-resolution"),
    "sconres": ("S.Con.Res.", "senate-concurrent-resolution"),
}

def sanitize_version_name(name: str) -> str:
    """Convert a version type like 'Reported in House' to 'reported-in-house'."""
    if not name:
        return "unknown"
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown"


def congress_for_year(year: int) -> int:
    """Map a calendar year to its Congress number.

    The 1st Congress began in 1789. Each Congress spans two years.
    """
    return (year - 1789) // 2 + 1


APPROPRIATIONS_COMMITTEES = [
    ("house", "hsap00"),
    ("senate", "ssap00"),
]


def get_api_key() -> str:
    """Load API key from environment, with DEMO_KEY fallback."""
    key = os.environ.get("CONGRESS_API_KEY", "DEMO_KEY")
    if key == "DEMO_KEY":
        print(
            "WARNING: Using DEMO_KEY (30 req/hr). "
            "Get a key at https://api.congress.gov/sign-up/",
            file=sys.stderr,
        )
    return key


def api_get(client: httpx.Client, path: str, params: dict | None = None, *, api_key: str) -> dict:
    """Make a GET request to the Congress.gov API with basic retry."""
    request_params = {**(params or {}), "api_key": api_key, "format": "json"}
    url = f"{BASE_URL}{path}" if path.startswith("/") else path

    last_resp = None
    for attempt in range(3):
        last_resp = client.get(url, params=request_params)
        if last_resp.status_code == 429:
            print("Rate limited, waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        if last_resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        last_resp.raise_for_status()
        return last_resp.json()

    # All retries exhausted
    last_resp.raise_for_status()
    return {}  # unreachable, raise_for_status throws on 429/5xx


def fetch_all_committee_bills(
    client: httpx.Client, chamber: str, committee_code: str, *, api_key: str, page_size: int = 250
) -> list[dict]:
    """Fetch all bills from a committee, paginating through the full list."""
    path = f"/committee/{chamber}/{committee_code}/bills"
    all_bills = []
    offset = 0

    while True:
        data = api_get(client, path, {"limit": page_size, "offset": offset}, api_key=api_key)
        bills = data.get("committee-bills", {}).get("bills", [])
        all_bills.extend(bills)
        total = data.get("pagination", {}).get("count", 0)
        offset += page_size
        if offset >= total:
            break

    return all_bills


def format_version_list(versions: list[dict]) -> str:
    """Format text versions as a numbered list for display."""
    if not versions:
        return "No text versions available."
    lines = []
    for i, v in enumerate(versions, 1):
        date_raw = v.get("date")
        date_str = date_raw[:10] if date_raw else "no date"
        lines.append(f"  {i}. {v.get('type', 'Unknown')} ({date_str})")
    return "\n".join(lines)


def fetch_text_versions(
    client: httpx.Client, congress: int, bill_type: str, number: int, *, api_key: str
) -> list[dict]:
    """Fetch all text versions for a bill, in chronological order (oldest first)."""
    path = f"/bill/{congress}/{bill_type}/{number}/text"
    data = api_get(client, path, api_key=api_key)
    versions = data.get("textVersions", [])
    # Sort chronologically (oldest first). Null-dated versions (e.g. Enrolled Bill)
    # get the max date so they sort alongside the latest entries, with type name
    # as tiebreaker (Enrolled Bill < Public Law alphabetically).
    max_date = max((v.get("date") for v in versions if v.get("date")), default="")
    versions.sort(key=lambda v: (v.get("date") or max_date, v.get("type", "")))
    return versions


def version_path(
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    index: int,
    version_type: str,
) -> Path:
    """Build the output path for a version file without writing anything."""
    bill_dir = output_dir / f"{congress}-{bill_type}-{number}"
    filename = f"{index}_{sanitize_version_name(version_type)}.xml"
    return bill_dir / filename


def save_version(
    content: bytes,
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    index: int,
    version_type: str,
) -> Path:
    """Write XML content to a structured output path. Returns the file path."""
    path = version_path(output_dir, congress, bill_type, number, index, version_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def download_version_xml(client: httpx.Client, url: str) -> bytes:
    """Download raw XML content from a congress.gov URL, with retry."""
    last_resp = None
    for attempt in range(3):
        last_resp = client.get(url)
        if last_resp.status_code == 429:
            print("Rate limited, waiting 60s...", file=sys.stderr)
            time.sleep(60)
            continue
        if last_resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        last_resp.raise_for_status()
        return last_resp.content

    last_resp.raise_for_status()
    return b""  # unreachable


def get_xml_url(version: dict) -> str | None:
    """Extract the XML format URL from a version's formats list."""
    for fmt in version.get("formats", []):
        if fmt.get("type") == "Formatted XML":
            return fmt.get("url")
    return None


def cmd_versions(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Show available text versions for a bill."""
    versions = fetch_text_versions(client, args.congress, args.bill_type, args.number, api_key=api_key)
    label, _ = BILL_TYPES.get(args.bill_type, (args.bill_type.upper(), ""))
    print(f"\nText versions for {label} {args.number} ({args.congress}th Congress):\n")
    print(format_version_list(versions))
    print()


def cmd_download(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Download text versions for a single bill."""
    versions = fetch_text_versions(client, args.congress, args.bill_type, args.number, api_key=api_key)

    if not versions:
        print("No text versions available.", file=sys.stderr)
        return

    if args.version is not None:
        if args.version < 1 or args.version > len(versions):
            print(f"Version {args.version} out of range (1-{len(versions)}).", file=sys.stderr)
            sys.exit(1)
        targets = [(args.version, versions[args.version - 1])]
    else:
        targets = list(enumerate(versions, 1))

    for index, version in targets:
        vtype = version.get("type", "unknown")
        xml_url = get_xml_url(version)
        if not xml_url:
            print(f"  Skipping version {index} ({vtype}): no XML available", file=sys.stderr)
            continue
        dest = version_path(args.output_dir, args.congress, args.bill_type, args.number, index, vtype)
        if dest.exists():
            print(f"  Already exists: {dest}", file=sys.stderr)
            continue
        print(f"  Downloading version {index}/{len(versions)}: {vtype}...", file=sys.stderr)
        content = download_version_xml(client, xml_url)
        save_version(content, args.output_dir, args.congress, args.bill_type, args.number, index, vtype)
        print(f"  Saved: {dest}", file=sys.stderr)


def cmd_download_all(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Download all appropriations bill versions for a year range."""
    if args.start_year > args.end_year:
        print(f"start_year ({args.start_year}) must be <= end_year ({args.end_year}).", file=sys.stderr)
        sys.exit(1)
    target_congresses = sorted({congress_for_year(y) for y in range(args.start_year, args.end_year + 1)})
    print(f"Target congresses: {target_congresses}", file=sys.stderr)

    # Fetch all bills from both committees
    all_bills = []
    for chamber, code in APPROPRIATIONS_COMMITTEES:
        print(f"Fetching bills from {chamber} appropriations...", file=sys.stderr)
        all_bills.extend(fetch_all_committee_bills(client, chamber, code, api_key=api_key))

    # Deduplicate and filter to target congresses
    seen = set()
    filtered = []
    for bill in all_bills:
        congress = bill.get("congress")
        if congress not in target_congresses:
            continue
        key = (congress, bill.get("type"), bill.get("number"))
        if key not in seen:
            seen.add(key)
            filtered.append(bill)

    print(f"Found {len(filtered)} bills for congresses {target_congresses}", file=sys.stderr)

    for bill in filtered:
        congress = bill.get("congress")
        bill_type = bill.get("type", "").lower()
        number = bill.get("number")
        label, _ = BILL_TYPES.get(bill_type, (bill_type.upper(), ""))
        print(f"\n{label} {number} ({congress}th Congress):", file=sys.stderr)

        versions = fetch_text_versions(client, congress, bill_type, number, api_key=api_key)
        if not versions:
            print("  No text versions available", file=sys.stderr)
            continue

        for index, version in enumerate(versions, 1):
            vtype = version.get("type", "unknown")
            xml_url = get_xml_url(version)
            if not xml_url:
                print(f"  Skipping version {index}: no XML available", file=sys.stderr)
                continue
            dest = version_path(args.output_dir, congress, bill_type, number, index, vtype)
            if dest.exists():
                print(f"  Already exists: {dest}", file=sys.stderr)
                continue
            print(f"  Downloading {index}/{len(versions)}: {vtype}...", file=sys.stderr)
            content = download_version_xml(client, xml_url)
            save_version(content, args.output_dir, congress, bill_type, number, index, vtype)
            print(f"  Saved: {dest}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Download appropriations bill text versions from Congress.gov",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # versions: list available text versions
    p_ver = subparsers.add_parser("versions", help="List available text versions for a bill")
    p_ver.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_ver.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_ver.add_argument("number", type=int, help="Bill number")

    # download: download versions for a single bill
    p_dl = subparsers.add_parser("download", help="Download bill text versions (XML)")
    p_dl.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_dl.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_dl.add_argument("number", type=int, help="Bill number")
    p_dl.add_argument("--version", type=int, default=None, help="Specific version number (1-indexed)")
    p_dl.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")

    # download-all: bulk download for a year range
    p_all = subparsers.add_parser("download-all", help="Download all appropriations bill versions for a year range")
    p_all.add_argument("start_year", type=int, help="Start year (e.g. 2024)")
    p_all.add_argument("end_year", type=int, help="End year (e.g. 2026)")
    p_all.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")

    return parser


def main():
    load_dotenv()
    api_key = get_api_key()
    parser = build_parser()
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        if args.command == "versions":
            cmd_versions(client, args, api_key)
        elif args.command == "download":
            cmd_download(client, args, api_key)
        elif args.command == "download-all":
            cmd_download_all(client, args, api_key)


if __name__ == "__main__":
    main()
