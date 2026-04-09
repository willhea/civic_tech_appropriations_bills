# Appropriations Bills Fetcher

Fetches the 10 most recent appropriations bills from Congress.gov. "Appropriations bill" = any bill referred to the House Appropriations Committee (hsap00) or Senate Appropriations Committee (ssap00).

## Setup

```bash
uv sync
```

Copy your API key into `.env`:

```
CONGRESS_API_KEY=your_key_here
```

Get a free key at https://api.congress.gov/sign-up/. The script falls back to the demo key (30 req/hr) if no key is set.

## Run

```bash
uv run python fetch_bills.py
```

## How it works

1. Queries the Congress.gov API v3 `/committee/{chamber}/{code}/bills` endpoint for both House and Senate Appropriations
2. Combines and deduplicates bills from both committees
3. Fetches full details (title, sponsor, status) for the 10 most recent
4. Prints formatted output with links to congress.gov
