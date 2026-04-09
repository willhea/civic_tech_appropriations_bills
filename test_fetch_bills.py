"""Tests for fetch_bills.py."""

import time

import httpx
import pytest
import respx

from fetch_bills import (
    BILL_TYPES,
    api_get,
    fetch_committee_bills,
    format_bill,
)

TEST_API_KEY = "test-key"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Prevent real sleeps during tests."""
    monkeypatch.setattr(time, "sleep", lambda _: None)


# --- format_bill tests ---


class TestFormatBill:
    def test_formats_basic_bill(self):
        bill = {
            "type": "HR",
            "number": "1234",
            "congress": 119,
            "title": "Test Appropriations Act",
            "sponsors": [
                {"fullName": "Rep. Smith, Jane", "party": "D", "state": "CA"}
            ],
            "introducedDate": "2026-01-15",
            "latestAction": {
                "text": "Referred to Committee",
                "actionDate": "2026-01-15",
            },
            "policyArea": {"name": "Economics and Public Finance"},
        }
        result = format_bill(bill, 1)
        assert "H.R. 1234" in result
        assert "119th Congress" in result
        assert "Test Appropriations Act" in result
        assert "Rep. Smith, Jane (D-CA)" in result
        assert "2026-01-15" in result
        assert "Economics and Public Finance" in result

    def test_missing_sponsor(self):
        bill = {"type": "S", "number": "99", "congress": 119, "sponsors": []}
        result = format_bill(bill, 1)
        assert "No sponsor listed" in result

    def test_missing_policy_area(self):
        bill = {"type": "HR", "number": "1", "congress": 119}
        result = format_bill(bill, 1)
        assert "Not assigned" in result

    @pytest.mark.parametrize("bill_type,expected", [
        (code, slug) for code, (_, slug) in BILL_TYPES.items()
    ])
    def test_url_uses_correct_slug(self, bill_type, expected):
        bill = {"type": bill_type.upper(), "number": "100", "congress": 119}
        result = format_bill(bill, 1)
        assert expected in result


# --- api_get tests ---


class TestApiGet:
    @respx.mock
    def test_successful_request(self):
        respx.get("https://api.congress.gov/v3/bill/119/hr/1").respond(
            200, json={"bill": {"title": "Test"}}
        )
        with httpx.Client() as client:
            result = api_get(client, "/bill/119/hr/1", api_key=TEST_API_KEY)
        assert result == {"bill": {"title": "Test"}}

    @respx.mock
    def test_retries_on_server_error(self):
        route = respx.get("https://api.congress.gov/v3/test")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json={"ok": True}),
        ]
        with httpx.Client() as client:
            result = api_get(client, "/test", api_key=TEST_API_KEY)
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_raises_after_exhausting_retries(self):
        respx.get("https://api.congress.gov/v3/test").respond(500)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                api_get(client, "/test", api_key=TEST_API_KEY)


# --- fetch_committee_bills tests ---


class TestFetchCommitteeBills:
    @respx.mock
    def test_single_call_when_under_limit(self):
        """When total <= limit, one API call is enough."""
        respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills").respond(
            200,
            json={
                "pagination": {"count": 3},
                "committee-bills": {
                    "bills": [
                        {"congress": 119, "type": "HR", "number": "1"},
                        {"congress": 119, "type": "HR", "number": "2"},
                        {"congress": 119, "type": "HR", "number": "3"},
                    ]
                },
            },
        )
        with httpx.Client() as client:
            bills = fetch_committee_bills(client, "house", "hsap00", limit=10, api_key=TEST_API_KEY)
        assert len(bills) == 3

    @respx.mock
    def test_offsets_to_end_when_over_limit(self):
        """When total > limit, makes a second call with correct offset."""
        route = respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills")
        route.mock(side_effect=lambda request: httpx.Response(
            200, json=self._make_response(request),
        ))

        with httpx.Client() as client:
            bills = fetch_committee_bills(client, "house", "hsap00", limit=5, api_key=TEST_API_KEY)

        # Should make 2 calls: initial + offset
        assert route.call_count == 2
        # Second call should offset to the end (100 - 5 = 95)
        second_call = route.calls[1].request
        assert second_call.url.params["offset"] == "95"

    @respx.mock
    def test_returns_empty_for_zero_count(self):
        respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills").respond(
            200, json={"pagination": {"count": 0}, "committee-bills": {"bills": []}}
        )
        with httpx.Client() as client:
            bills = fetch_committee_bills(client, "house", "hsap00", api_key=TEST_API_KEY)
        assert bills == []

    def _make_response(self, request):
        """Build a mock response based on query params."""
        offset = int(request.url.params.get("offset", 0))

        if offset == 0:
            return {
                "pagination": {"count": 100},
                "committee-bills": {
                    "bills": [{"congress": 119, "type": "HR", "number": str(i)} for i in range(1, 6)]
                },
            }
        else:
            bills = [
                {"congress": 119, "type": "HR", "number": str(offset + i + 1)}
                for i in range(5)
            ]
            return {
                "pagination": {"count": 100},
                "committee-bills": {"bills": bills},
            }
