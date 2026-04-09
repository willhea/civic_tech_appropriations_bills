"""Fetch the 10 most recent appropriations bills from Congress.gov.

Uses the Congress.gov API v3 committee-bills endpoint to find bills
referred to the House and Senate Appropriations Committees.
"""

import os
import sys
import time

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


def fetch_committee_bills(
    client: httpx.Client, chamber: str, committee_code: str, limit: int = 10, *, api_key: str
) -> list[dict]:
    """Fetch the most recent bills from a committee's bill list.

    The API returns bills in ascending order with no reliable descending sort,
    so we check the total count and offset to the end if needed.
    """
    path = f"/committee/{chamber}/{committee_code}/bills"

    data = api_get(client, path, {"limit": limit}, api_key=api_key)
    total = data.get("pagination", {}).get("count", 0)
    bills = data.get("committee-bills", {}).get("bills", [])

    # If there are more bills than our limit, we got the oldest ones.
    # Re-fetch from the end.
    if total > limit:
        offset = total - limit
        data = api_get(client, path, {"limit": limit, "offset": offset}, api_key=api_key)
        bills = data.get("committee-bills", {}).get("bills", [])

    return bills


def fetch_bill_detail(client: httpx.Client, congress: int, bill_type: str, number: int, *, api_key: str) -> dict:
    """Fetch full detail for a single bill."""
    path = f"/bill/{congress}/{bill_type}/{number}"
    data = api_get(client, path, api_key=api_key)
    return data.get("bill", {})


def format_bill(bill: dict, index: int) -> str:
    """Format a bill's details for display."""
    bill_type = bill.get("type", "").lower()
    number = bill.get("number", "")
    congress = bill.get("congress", "")
    label, type_slug = BILL_TYPES.get(bill_type, (bill_type.upper(), "house-bill"))
    title = bill.get("title", "No title")

    sponsors = bill.get("sponsors", [])
    if sponsors:
        s = sponsors[0]
        sponsor_str = f"{s.get('fullName', 'Unknown')} ({s.get('party', '?')}-{s.get('state', '?')})"
    else:
        sponsor_str = "No sponsor listed"

    introduced = bill.get("introducedDate", "Unknown")
    latest = bill.get("latestAction", {})
    latest_action = f"{latest.get('text', 'None')} ({latest.get('actionDate', '')})"
    policy_area = bill.get("policyArea", {}).get("name", "Not assigned")
    url = f"https://www.congress.gov/bill/{congress}th-congress/{type_slug}/{number}"

    return (
        f"  {index}. {label} {number} ({congress}th Congress)\n"
        f"  Title:          {title}\n"
        f"  Sponsor:        {sponsor_str}\n"
        f"  Introduced:     {introduced}\n"
        f"  Policy Area:    {policy_area}\n"
        f"  Latest Action:  {latest_action}\n"
        f"  URL:            {url}"
    )


def main():
    load_dotenv()
    api_key = get_api_key()

    with httpx.Client(timeout=30) as client:
        all_bills = []
        for chamber, code in APPROPRIATIONS_COMMITTEES:
            print(f"Fetching bills from {chamber} appropriations ({code})...", file=sys.stderr)
            all_bills.extend(fetch_committee_bills(client, chamber, code, limit=10, api_key=api_key))

        # Deduplicate (a bill can appear in both committees)
        seen = set()
        combined = []
        for bill in all_bills:
            key = (bill.get("congress"), bill.get("type"), bill.get("number"))
            if key not in seen:
                seen.add(key)
                combined.append(bill)

        combined.sort(key=lambda b: b.get("updateDate", ""), reverse=True)
        combined = combined[:10]

        if not combined:
            print("No appropriations bills found.", file=sys.stderr)
            return

        print(f"\nFetching details for {len(combined)} bills...\n", file=sys.stderr)
        print("=" * 60)
        print("  10 Most Recent Appropriations Bills")
        print("=" * 60)

        for i, bill_summary in enumerate(combined, 1):
            congress = bill_summary.get("congress")
            bill_type = bill_summary.get("type", "").lower()
            number = bill_summary.get("number")

            detail = fetch_bill_detail(client, congress, bill_type, number, api_key=api_key)
            print(f"\n{'-' * 60}")
            print(format_bill(detail, i))

        print()


if __name__ == "__main__":
    main()
