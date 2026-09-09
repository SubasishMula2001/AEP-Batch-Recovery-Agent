from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from coded_tools.aep_batch_recovery.adobe_failed_batch import AdobeFailedBatch


@pytest.fixture(autouse=True)
def adobe_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEP_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("AEP_API_KEY", "client-id")
    monkeypatch.setenv("AEP_ORG_ID", "org@AdobeOrg")
    monkeypatch.setenv("AEP_SANDBOX_NAME", "dev")


def response(payload: object, status: int = 200) -> Mock:
    item = Mock()
    item.ok = 200 <= status < 300
    item.status_code = status
    item.headers = {"x-request-id": "request-123"}
    item.json.return_value = payload
    return item


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_returns_catalog_batch_errors(get: Mock) -> None:
    get.return_value = response(
        {
            "batch-123": {
                "status": "failed",
                "errors": [
                    {
                        "code": "INGEST-1205-400",
                        "description": "A source field does not exist in the target schema.",
                        "rows": [],
                    }
                ],
            }
        }
    )

    sly_data = {}
    result = AdobeFailedBatch().invoke(
        {"operation": "get_batch_status", "batch_id": "batch-123"}, sly_data
    )

    assert result["ok"] is True
    assert result["batch_status"] == "failed"
    assert result["batch_errors"] == [
        {
            "keyword": "INGEST-1205-400",
            "message": "A source field does not exist in the target schema.",
        }
    ]
    assert sly_data["aep_api_response"]["get_batch_status"] == result


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_lists_failed_files_without_success_marker(get: Mock) -> None:
    get.return_value = response(
        {"data": [{"name": "failed.json", "length": 20}, {"name": "_SUCCESS", "length": 0}]}
    )

    result = AdobeFailedBatch().invoke(
        {"operation": "list_failed_files", "batch_id": "batch-123"}, {}
    )

    assert result["ok"] is True
    assert result["failed_files"] == [{"name": "failed.json", "length": 20}]
    call = get.call_args
    assert call.kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert call.kwargs["headers"]["x-sandbox-name"] == "dev"
    assert call.kwargs["timeout"] == 30


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_inspection_excludes_customer_record(get: Mock) -> None:
    get.return_value = response(
        {
            "xdmEntity": {"email": "private@example.invalid"},
            "_validationErrors": [
                {
                    "keyword": "required",
                    "message": "Field is required",
                    "pointerToViolation": "#/identityMap/ECID",
                    "unexpected": "not returned",
                }
            ],
        }
    )

    result = AdobeFailedBatch().invoke(
        {
            "operation": "inspect_failed_file",
            "batch_id": "batch-123",
            "failed_file": "failed.json",
        },
        {},
    )

    serialized = str(result)
    assert result["validation_error_count"] == 1
    assert "private@example.invalid" not in serialized
    assert "unexpected" not in serialized


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_non_json_failed_file_is_safely_described(get: Mock) -> None:
    item = response({})
    item.headers = {"content-type": "text/csv; charset=utf-8"}
    item.json.side_effect = ValueError("not JSON")
    item.content = b"email,firstName\nprivate@example.invalid,Private"
    item.iter_lines.return_value = [
        "email,firstName",
        "private@example.invalid,Private",
    ]
    get.return_value = item

    sly_data = {}
    result = AdobeFailedBatch().invoke(
        {
            "operation": "inspect_failed_file",
            "batch_id": "batch-123",
            "failed_file": "failed.csv",
        },
        sly_data,
    )

    assert result["ok"] is True
    assert result["response_format"] == "text/csv"
    assert result["validation_errors"] == []
    assert "private@example.invalid" not in str(result)
    assert sly_data["aep_api_response"]["inspect_failed_file"] == result


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_extracts_errors_from_json_lines_without_exposing_record(get: Mock) -> None:
    item = response({})
    item.headers = {"content-type": "application/x-ndjson"}
    item.json.side_effect = ValueError("multiple JSON documents")
    item.iter_lines.return_value = [
        '{"xdmEntity":{"email":"private@example.invalid"},'
        '"_validationErrors":[{"keyword":"format","message":"Invalid timestamp",'
        '"pointerToViolation":"#/timestamp"}]}'
    ]
    get.return_value = item

    result = AdobeFailedBatch().invoke(
        {
            "operation": "inspect_failed_file",
            "batch_id": "batch-123",
            "failed_file": "failed.jsonl",
        },
        {},
    )

    assert result["validation_error_count"] == 1
    assert result["validation_errors"][0]["message"] == "Invalid timestamp"
    assert "private@example.invalid" not in str(result)


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_rejects_path_traversal_without_request(get: Mock) -> None:
    result = AdobeFailedBatch().invoke(
        {
            "operation": "inspect_failed_file",
            "batch_id": "batch-123",
            "failed_file": "../secret.json",
        },
        {},
    )
    assert result["ok"] is False
    get.assert_not_called()


@patch("coded_tools.aep_batch_recovery.adobe_failed_batch.requests.get")
def test_returns_safe_authentication_error(get: Mock) -> None:
    get.return_value = response({"detail": "sensitive provider text"}, status=401)
    result = AdobeFailedBatch().invoke(
        {"operation": "list_failed_files", "batch_id": "batch-123"}, {}
    )
    assert result["status_code"] == 401
    assert "sensitive provider text" not in str(result)
