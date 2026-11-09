"""Unit check for BigQuery connectivity helper (mocked client)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from elt.load.bigquery import check_bigquery_connection


def test_check_bigquery_connection_ok():
    mock_client = MagicMock()
    mock_client.query.return_value.result.return_value = [{"ok": 1}]
    mock_client.get_dataset.return_value = SimpleNamespace(location="asia-southeast1")

    with patch("elt.load.bigquery.bigquery.Client", return_value=mock_client) as mock_ctor:
        info = check_bigquery_connection(project_id="demo-proj", dataset="flight_elt")

    assert info == {
        "project": "demo-proj",
        "dataset": "flight_elt",
        "location": "asia-southeast1",
    }
    mock_ctor.assert_called_once_with(
        project="demo-proj", location="asia-southeast1"
    )
    mock_client.query.assert_called_once_with("SELECT 1 AS ok")
    mock_client.get_dataset.assert_called_once_with("demo-proj.flight_elt")
