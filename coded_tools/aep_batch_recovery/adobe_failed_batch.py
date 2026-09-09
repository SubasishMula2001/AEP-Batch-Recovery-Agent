# Copyright 2026 Cognizant Technology Solutions Corp.
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import requests

try:
    from neuro_san.interfaces.coded_tool import CodedTool
except ModuleNotFoundError:
    class CodedTool:  # type: ignore[no-redef]
        """Standalone fallback used when Neuro SAN is not installed."""


class AdobeFailedBatch(CodedTool):
    """Safely retrieves failed-batch metadata from Adobe Experience Platform."""

    BASE_URL = "https://platform.adobe.io/data/foundation/export/batches"
    CATALOG_BASE_URL = "https://platform.adobe.io/data/foundation/catalog/batches"
    BATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
    REQUIRED_ENV = (
        "AEP_ACCESS_TOKEN",
        "AEP_API_KEY",
        "AEP_ORG_ID",
        "AEP_SANDBOX_NAME",
    )

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        operation = str(args.get("operation", "list_failed_files")).strip()
        batch_id = str(args.get("batch_id", "")).strip()

        validation_error = self._validate_batch_id(batch_id)
        if validation_error:
            return {"ok": False, "error": validation_error}

        missing = [name for name in self.REQUIRED_ENV if not os.environ.get(name, "").strip()]
        if missing:
            return {
                "ok": False,
                "error": "Adobe API configuration is incomplete.",
                "missing_environment_variables": missing,
            }

        result: dict[str, Any]
        if operation == "get_batch_status":
            result = self._get_batch_status(batch_id)
        elif operation == "list_failed_files":
            result = self._list_failed_files(batch_id)
        elif operation == "inspect_failed_file":
            failed_file = str(args.get("failed_file", "")).strip()
            file_error = self._validate_failed_file(failed_file)
            if file_error:
                return {"ok": False, "error": file_error}
            result = self._inspect_failed_file(batch_id, failed_file)
        else:
            return {
                "ok": False,
                "error": "operation must be get_batch_status, list_failed_files, or inspect_failed_file",
            }

        self._publish_api_response(sly_data, operation, result)
        return result

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return await asyncio.to_thread(self.invoke, args, sly_data)

    @staticmethod
    def _publish_api_response(
        sly_data: dict[str, Any], operation: str, result: dict[str, Any]
    ) -> None:
        """Expose only the already-sanitized tool result to the Studio JSON tab."""
        api_response = sly_data.setdefault("aep_api_response", {})
        if not isinstance(api_response, dict):
            api_response = {}
            sly_data["aep_api_response"] = api_response
        api_response[operation] = result

    @classmethod
    def _validate_batch_id(cls, batch_id: str) -> str | None:
        if not batch_id:
            return "batch_id is required"
        if not cls.BATCH_ID_RE.fullmatch(batch_id):
            return "batch_id contains unsupported characters"
        return None

    @classmethod
    def _validate_failed_file(cls, failed_file: str) -> str | None:
        if not failed_file:
            return "failed_file is required for inspect_failed_file"
        if ".." in failed_file or not cls.FILE_RE.fullmatch(failed_file):
            return "failed_file must be a file name without a path"
        return None

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {os.environ['AEP_ACCESS_TOKEN'].strip()}",
            "x-api-key": os.environ["AEP_API_KEY"].strip(),
            "x-gw-ims-org-id": os.environ["AEP_ORG_ID"].strip(),
            "x-sandbox-name": os.environ["AEP_SANDBOX_NAME"].strip(),
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }

    def _list_failed_files(self, batch_id: str) -> dict[str, Any]:
        response = self._get(batch_id)
        if isinstance(response, dict):
            return response

        payload = self._json(response)
        if isinstance(payload, dict) and payload.get("ok") is False:
            return payload

        entries = payload.get("data", []) if isinstance(payload, dict) else []
        failed_files = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            if name and name != "_SUCCESS":
                failed_files.append({"name": name, "length": entry.get("length")})

        return {
            "ok": True,
            "operation": "list_failed_files",
            "batch_id": batch_id,
            "failed_file_count": len(failed_files),
            "failed_files": failed_files,
            "page_count": payload.get("_page", {}).get("count")
            if isinstance(payload.get("_page"), dict)
            else None,
        }

    def _inspect_failed_file(self, batch_id: str, failed_file: str) -> dict[str, Any]:
        response = self._get(batch_id, params={"path": failed_file})
        if isinstance(response, dict):
            return response

        try:
            payload = response.json()
        except ValueError:
            content_type = str(response.headers.get("content-type", "application/octet-stream"))
            errors = self._extract_json_lines_errors(response)
            return {
                "ok": True,
                "operation": "inspect_failed_file",
                "batch_id": batch_id,
                "failed_file": failed_file,
                "response_format": content_type.split(";", maxsplit=1)[0],
                "validation_error_count": len(errors),
                "validation_errors": errors,
                "note": (
                    "Adobe returned a file rather than a single JSON document. "
                    "Only allow-listed validation metadata was extracted; rejected "
                    "customer records were not retained or exposed."
                ),
            }

        if not isinstance(payload, (dict, list)):
            return {"ok": False, "error": "Adobe API returned an unsupported response."}
        if isinstance(payload, dict) and payload.get("ok") is False:
            return payload

        errors = self.extract_validation_errors(payload)
        return {
            "ok": True,
            "operation": "inspect_failed_file",
            "batch_id": batch_id,
            "failed_file": failed_file,
            "validation_error_count": len(errors),
            "validation_errors": errors,
        }

    def _extract_json_lines_errors(self, response: Any) -> list[dict[str, str]]:
        """Extract validation metadata from JSON Lines without retaining records."""
        errors: list[dict[str, str]] = []
        try:
            lines = response.iter_lines(decode_unicode=True)
            for index, line in enumerate(lines):
                if index >= 1000 or len(errors) >= 100:
                    break
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except (TypeError, ValueError):
                    continue
                errors.extend(self.extract_validation_errors(payload))
        except (AttributeError, TypeError):
            return []
        return errors[:100]

    def _get_batch_status(self, batch_id: str) -> dict[str, Any]:
        response = self._request(f"{self.CATALOG_BASE_URL}/{batch_id}")
        if isinstance(response, dict):
            return response

        payload = self._json(response)
        if isinstance(payload, dict) and payload.get("ok") is False:
            return payload
        batch = payload.get(batch_id, {}) if isinstance(payload, dict) else {}
        if not isinstance(batch, dict):
            return {"ok": False, "error": "Adobe returned an unsupported batch-status response."}

        errors = []
        for item in batch.get("errors", []):
            if isinstance(item, dict):
                errors.append(
                    {
                        "keyword": str(item.get("code", "batch_error"))[:100],
                        "message": str(item.get("description", "Batch processing error"))[:1000],
                    }
                )
        return {
            "ok": True,
            "operation": "get_batch_status",
            "batch_id": batch_id,
            "batch_status": str(batch.get("status", "unknown")),
            "batch_error_count": len(errors),
            "batch_errors": errors[:100],
        }

    def _get(self, batch_id: str, params: dict[str, str] | None = None) -> Any:
        return self._request(f"{self.BASE_URL}/{batch_id}/failed", params=params)

    def _request(self, url: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
        except requests.RequestException:
            return {
                "ok": False,
                "error": "Unable to connect to Adobe Experience Platform.",
                "error_type": "connection_error",
            }

        if response.ok:
            return response

        messages = {
            400: "Adobe rejected the batch or file request.",
            401: "Adobe authentication failed. Refresh the access token and verify the API key.",
            403: "Adobe denied access. Verify product-profile permissions, organization, and sandbox.",
            404: "The Adobe batch or failed file was not found.",
            429: "Adobe API rate limit reached. Wait before retrying.",
        }
        return {
            "ok": False,
            "error": messages.get(response.status_code, "Adobe API returned an unexpected error."),
            "status_code": response.status_code,
            "request_id": response.headers.get("x-request-id")
            or response.headers.get("x-correlation-id"),
        }

    @staticmethod
    def _json(response: Any) -> dict[str, Any] | list[Any]:
        try:
            payload = response.json()
        except ValueError:
            return {"ok": False, "error": "Adobe API returned a non-JSON response."}
        if isinstance(payload, (dict, list)):
            return payload
        return {"ok": False, "error": "Adobe API returned an unsupported response."}

    @classmethod
    def extract_validation_errors(cls, payload: Any) -> list[dict[str, str]]:
        """Return only validation metadata, never the failed customer record."""
        collected: list[dict[str, str]] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                direct = value.get("_validationErrors")
                if isinstance(direct, list):
                    for item in direct:
                        normalized = cls._normalize_error(item)
                        if normalized:
                            collected.append(normalized)
                for key, child in value.items():
                    if key not in {"_validationErrors", "xdmEntity", "data", "record"}:
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return collected[:100]

    @staticmethod
    def _normalize_error(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        allowed = ("keyword", "message", "pointerToViolation", "schemaLocation")
        return {
            key: str(value[key])[:1000]
            for key in allowed
            if value.get(key) is not None
        }
