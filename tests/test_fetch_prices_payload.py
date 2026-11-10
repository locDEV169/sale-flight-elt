"""Unit checks for SerpAPI payload normalization."""

from unittest.mock import MagicMock, patch

from elt.extract.serpapi_flights import _as_payload_dict, _redact_secrets, fetch_prices


def test_redact_secrets_strips_api_key_from_url():
    raw = (
        "401 Client Error: Unauthorized for url: "
        "https://serpapi.com/search?engine=google_flights&api_key=super-secret&hl=vi"
    )
    out = _redact_secrets(raw)
    assert "super-secret" not in out
    assert "api_key=***" in out


def test_as_payload_dict_from_plain_dict():
    raw = {"best_flights": [{"price": 1}], "other_flights": [], "price_insights": {}}
    assert _as_payload_dict(raw) is raw


def test_as_payload_dict_from_serpapi_results_like():
    raw = {
        "best_flights": [{"price": 1165181}],
        "other_flights": [{"price": 1210781}],
        "price_insights": {"lowest_price": 1165181},
    }
    results = MagicMock()
    results.as_dict.return_value = raw
    assert _as_payload_dict(results) == raw


def test_fetch_prices_stores_full_payload_from_serpapi_results():
    raw = {
        "best_flights": [{"price": 1165181}],
        "other_flights": [{"price": 2000000}],
        "price_insights": {"lowest_price": 1165181, "price_level": "typical"},
    }
    results = MagicMock()
    results.as_dict.return_value = raw
    mock_client = MagicMock()
    mock_client.search.return_value = results

    with patch("elt.extract.serpapi_flights.serpapi.Client", return_value=mock_client):
        payload, status, error = fetch_prices(
            api_key="test-key",
            query={"engine": "google_flights"},
        )

    assert status == 200
    assert error is None
    assert "other_flights" in payload
    assert "price_insights" in payload
    assert payload["best_flights"][0]["price"] == 1165181


def test_fetch_prices_returns_body_error_from_google_flights():
    raw = {
        "error": "Google Flights hasn't returned any results for this query.",
        "search_metadata": {"status": "Success"},
    }
    results = MagicMock()
    results.as_dict.return_value = raw
    mock_client = MagicMock()
    mock_client.search.return_value = results

    with patch("elt.extract.serpapi_flights.serpapi.Client", return_value=mock_client):
        payload, status, error = fetch_prices(
            api_key="test-key",
            query={
                "engine": "google_flights",
                "departure_id": "DAD",
                "arrival_id": "SGN",
                "outbound_date": "2026-11-10",
                "api_key": "should-not-matter",
            },
        )

    assert status == 400
    assert error is not None
    assert "hasn't returned any results" in error
    assert payload.get("error")
