"""Tests for fetch_bills.py."""

import time

import httpx
import pytest
import respx

from fetch_bills import (
    BILL_TYPES,
    api_get,
    congress_for_year,
    download_version_xml,
    fetch_all_committee_bills,
    fetch_text_versions,
    format_version_list,
    sanitize_version_name,
    save_version,
    version_path,
)

TEST_API_KEY = "test-key"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Prevent real sleeps during tests."""
    monkeypatch.setattr(time, "sleep", lambda _: None)


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


# --- fetch_all_committee_bills tests ---


class TestFetchAllCommitteeBills:
    @respx.mock
    def test_single_page(self):
        """When all bills fit in one page, only one API call."""
        respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills").respond(
            200,
            json={
                "pagination": {"count": 3},
                "committee-bills": {
                    "bills": [
                        {"congress": 118, "type": "HR", "number": "1"},
                        {"congress": 118, "type": "HR", "number": "2"},
                        {"congress": 118, "type": "HR", "number": "3"},
                    ]
                },
            },
        )
        with httpx.Client() as client:
            bills = fetch_all_committee_bills(client, "house", "hsap00", api_key=TEST_API_KEY)
        assert len(bills) == 3

    @respx.mock
    def test_paginates_multiple_pages(self):
        """Fetches all pages when total exceeds page size."""
        route = respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills")
        route.mock(side_effect=lambda request: httpx.Response(
            200, json=self._paginated_response(request),
        ))
        with httpx.Client() as client:
            bills = fetch_all_committee_bills(client, "house", "hsap00", api_key=TEST_API_KEY, page_size=3)
        assert len(bills) == 5
        assert route.call_count == 2

    def _paginated_response(self, request):
        offset = int(request.url.params.get("offset", 0))
        if offset == 0:
            return {
                "pagination": {"count": 5},
                "committee-bills": {
                    "bills": [
                        {"congress": 118, "type": "HR", "number": str(i)}
                        for i in range(1, 4)
                    ]
                },
            }
        else:
            return {
                "pagination": {"count": 5},
                "committee-bills": {
                    "bills": [
                        {"congress": 118, "type": "HR", "number": str(i)}
                        for i in range(4, 6)
                    ]
                },
            }


# --- congress_for_year tests ---


class TestCongressForYear:
    def test_known_values(self):
        assert congress_for_year(2024) == 118
        assert congress_for_year(2025) == 119
        assert congress_for_year(2026) == 119
        assert congress_for_year(1789) == 1
        assert congress_for_year(1790) == 1

    def test_year_range_produces_correct_set(self):
        congresses = sorted({congress_for_year(y) for y in range(2024, 2027)})
        assert congresses == [118, 119]

    def test_even_odd_year_same_congress(self):
        # Both years of a congress map to the same number
        assert congress_for_year(2023) == 118
        assert congress_for_year(2024) == 118


# --- sanitize_version_name tests ---


class TestSanitizeVersionName:
    def test_standard_name(self):
        assert sanitize_version_name("Reported in House") == "reported-in-house"

    def test_enrolled_bill(self):
        assert sanitize_version_name("Enrolled Bill") == "enrolled-bill"

    def test_strips_special_characters(self):
        assert sanitize_version_name("Public Law (No.)") == "public-law-no"

    def test_collapses_multiple_hyphens(self):
        assert sanitize_version_name("Some -- Name") == "some-name"

    def test_empty_string(self):
        assert sanitize_version_name("") == "unknown"


# --- format_version_list tests ---


class TestFormatVersionList:
    def test_numbered_output(self):
        versions = [
            {"date": "2023-06-27T04:00:00Z", "type": "Reported in House", "formats": []},
            {"date": "2023-07-27T04:00:00Z", "type": "Engrossed in House", "formats": []},
        ]
        result = format_version_list(versions)
        assert "1." in result
        assert "2." in result
        assert "Reported in House" in result
        assert "2023-06-27" in result

    def test_null_date(self):
        versions = [{"date": None, "type": "Enrolled Bill", "formats": []}]
        result = format_version_list(versions)
        assert "Enrolled Bill" in result
        assert "no date" in result

    def test_empty_list(self):
        result = format_version_list([])
        assert "No text versions" in result


# --- fetch_text_versions tests ---


class TestFetchTextVersions:
    @respx.mock
    def test_returns_versions_in_chronological_order(self):
        # API returns newest-first; fetch_text_versions sorts by date (oldest first)
        api_response = [
            {
                "date": "2023-07-27T04:00:00Z",
                "type": "Engrossed in House",
                "formats": [
                    {"type": "Formatted XML", "url": "https://congress.gov/eh.xml"},
                ],
            },
            {
                "date": "2023-06-27T04:00:00Z",
                "type": "Reported in House",
                "formats": [
                    {"type": "Formatted XML", "url": "https://congress.gov/rh.xml"},
                ],
            },
        ]
        respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(
            200, json={"textVersions": api_response, "pagination": {"count": 2}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 4366, api_key=TEST_API_KEY)
        assert len(result) == 2
        assert result[0]["type"] == "Reported in House"
        assert result[1]["type"] == "Engrossed in House"

    @respx.mock
    def test_enrolled_bill_sorts_before_public_law(self):
        api_response = [
            {"date": "2024-03-10T04:00:00Z", "type": "Public Law", "formats": []},
            {"date": None, "type": "Enrolled Bill", "formats": []},
            {"date": "2023-06-27T04:00:00Z", "type": "Reported in House", "formats": []},
        ]
        respx.get("https://api.congress.gov/v3/bill/118/hr/1/text").respond(
            200, json={"textVersions": api_response, "pagination": {"count": 3}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 1, api_key=TEST_API_KEY)
        assert result[0]["type"] == "Reported in House"
        assert result[1]["type"] == "Enrolled Bill"
        assert result[2]["type"] == "Public Law"

    @respx.mock
    def test_returns_empty_list_when_no_versions(self):
        respx.get("https://api.congress.gov/v3/bill/118/hr/9999/text").respond(
            200, json={"textVersions": [], "pagination": {"count": 0}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 9999, api_key=TEST_API_KEY)
        assert result == []


# --- save_version tests ---


class TestSaveVersion:
    def test_creates_dir_and_file(self, tmp_path):
        content = b"<bill>test</bill>"
        path = save_version(content, tmp_path, 118, "hr", 4366, 1, "Reported in House")
        assert path.exists()
        assert path.read_bytes() == content

    def test_correct_filename(self, tmp_path):
        path = save_version(b"<xml/>", tmp_path, 119, "s", 100, 3, "Engrossed in Senate")
        assert path.name == "3_engrossed-in-senate.xml"
        assert path.parent.name == "119-s-100"

    def test_existing_dir_no_error(self, tmp_path):
        save_version(b"<a/>", tmp_path, 118, "hr", 1, 1, "Introduced in House")
        path = save_version(b"<b/>", tmp_path, 118, "hr", 1, 2, "Reported in House")
        assert path.exists()


class TestVersionPath:
    def test_returns_expected_path(self, tmp_path):
        path = version_path(tmp_path, 118, "hr", 4366, 1, "Reported in House")
        assert path == tmp_path / "118-hr-4366" / "1_reported-in-house.xml"

    def test_already_downloaded_detected(self, tmp_path):
        path = version_path(tmp_path, 118, "hr", 4366, 1, "Reported in House")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"<existing/>")
        assert path.exists()


# --- download_version_xml tests ---


class TestDownloadVersionXml:
    @respx.mock
    def test_returns_xml_bytes(self):
        xml_content = b"<bill><title>Test</title></bill>"
        respx.get("https://www.congress.gov/118/bills/hr4366/rh.xml").respond(
            200, content=xml_content, headers={"content-type": "application/xml"},
        )
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/118/bills/hr4366/rh.xml")
        assert result == xml_content

    @respx.mock
    def test_retries_on_server_error(self):
        route = respx.get("https://www.congress.gov/test.xml")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, content=b"<ok/>"),
        ]
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/test.xml")
        assert result == b"<ok/>"
        assert route.call_count == 2

    @respx.mock
    def test_retries_on_429(self):
        route = respx.get("https://www.congress.gov/test.xml")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200, content=b"<ok/>"),
        ]
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/test.xml")
        assert result == b"<ok/>"

    @respx.mock
    def test_raises_after_exhausting_retries(self):
        respx.get("https://www.congress.gov/fail.xml").respond(500)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                download_version_xml(client, "https://www.congress.gov/fail.xml")

    @respx.mock
    def test_raises_on_4xx(self):
        respx.get("https://www.congress.gov/missing.xml").respond(404)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                download_version_xml(client, "https://www.congress.gov/missing.xml")


