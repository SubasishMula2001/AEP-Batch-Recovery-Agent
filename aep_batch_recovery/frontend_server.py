from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = Path(__file__).resolve().parent / "frontend"
load_dotenv(ROOT / ".env")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The Adobe client lives in this package's coded_tools/ when the app runs from
# its own checkout, and in the host's tool package once installed into a Neuro
# SAN checkout. Some hosts name that agent_tools/ because site-packages ships a
# top-level coded_tools that would shadow a local one, so the name is not fixed.
TOOL_PACKAGES = ("coded_tools", "agent_tools")
TOOL_PACKAGE: str | None = None
AdobeFailedBatch = None

for _candidate in TOOL_PACKAGES:
    try:
        _module = importlib.import_module(f"{_candidate}.aep_batch_recovery.adobe_failed_batch")
    except ModuleNotFoundError as exc:
        # Only move on when it is this candidate that is absent. A genuinely
        # missing dependency of the tool must not be reported as a layout
        # problem, which would send you looking in the wrong place.
        if exc.name == _candidate or (exc.name or "").startswith(f"{_candidate}."):
            continue
        raise
    AdobeFailedBatch = _module.AdobeFailedBatch
    TOOL_PACKAGE = _candidate
    break

if AdobeFailedBatch is None:
    raise ModuleNotFoundError(
        "Could not import the Adobe coded tool. Looked for "
        + " and ".join(f"{name}.aep_batch_recovery.adobe_failed_batch" for name in TOOL_PACKAGES)
        + f" under {ROOT}. Install the agent into this checkout with "
        "scripts/install_into_neuro_san.ps1, or run this app from the "
        "AEP-Batch-Recovery-Agent checkout."
    )


class AnalyzeRequest(BaseModel):
    batch_id: str
    failed_file: str | None = None


app = FastAPI(title="AEP Batch Recovery Agent")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    missing = [name for name in AdobeFailedBatch.REQUIRED_ENV if not os.environ.get(name, "").strip()]
    return {"status": "ok", "live_ready": not missing, "missing": missing, "tool_package": TOOL_PACKAGE}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    tool = AdobeFailedBatch()
    batch_id = request.batch_id.strip()
    error = tool._validate_batch_id(batch_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    batch_result = tool.invoke({"operation": "get_batch_status", "batch_id": batch_id}, {})
    if not isinstance(batch_result, dict) or not batch_result.get("ok"):
        return {"ok": False, "stage": "Batch Intake", **dict(batch_result)}

    listed = tool.invoke({"operation": "list_failed_files", "batch_id": batch_id}, {})
    if not isinstance(listed, dict) or not listed.get("ok"):
        return {"ok": False, "stage": "Failed File Retriever", **dict(listed)}
    failed_files = listed.get("failed_files", [])
    batch_errors = batch_result.get("batch_errors", [])
    batch_status = str(batch_result.get("batch_status", "unknown"))
    if not failed_files:
        return _build_result(
            batch_id,
            [],
            None,
            batch_errors,
            batch_status,
            None,
            "Adobe Catalog batch errors" if batch_errors else "No structured errors returned",
        )
    names = {str(entry.get("name")) for entry in failed_files if isinstance(entry, dict)}
    selected = request.failed_file or str(failed_files[0].get("name"))
    if selected not in names:
        raise HTTPException(status_code=400, detail="Select a failed file returned for this batch.")
    inspected = tool.invoke(
        {"operation": "inspect_failed_file", "batch_id": batch_id, "failed_file": selected},
        {},
    )
    if not isinstance(inspected, dict) or not inspected.get("ok"):
        return {"ok": False, "stage": "Validation Analyzer", **dict(inspected)}
    errors = batch_errors or inspected.get("validation_errors", [])
    error_source = (
        "Adobe Catalog batch errors"
        if batch_errors
        else "Adobe failed-file validation metadata"
        if errors
        else "No structured errors returned"
    )

    return _build_result(
        batch_id, failed_files, selected, errors, batch_status, inspected, error_source
    )


def _build_result(
    batch_id: str,
    failed_files: list[dict[str, Any]],
    selected: str | None,
    errors: list[dict[str, Any]],
    batch_status: str,
    inspection: dict[str, Any] | None,
    error_source: str,
) -> dict[str, Any]:
    categories = sorted({str(item.get("keyword", "validation")) for item in errors})
    actions = _recommend(errors)
    if not failed_files:
        summary = f"Batch status is {batch_status}. No failed ingestion paths were returned."
    else:
        summary = (
            f"Batch status is {batch_status}. Found {len(failed_files)} failed path(s) "
            f"and {len(errors)} batch or validation error(s)."
        )

    report = (
        f"AEP ingestion batch {batch_id}: {summary} "
        f"Error categories: {', '.join(categories) if categories else 'none detected'}. "
        f"Next action: {actions[0]}"
    )
    return {
        "ok": True,
        "mode": "live-adobe-api",
        "batch_id": batch_id,
        "batch_status": batch_status,
        "summary": summary,
        "failed_files": failed_files,
        "selected_file": selected,
        "file_inspection": inspection,
        "error_source": error_source,
        "validation_errors": errors,
        "categories": categories,
        "recommended_actions": actions,
        "incident_update": report,
        "api_response": {
            "catalog_batch_response": {
                "batch_id": batch_id,
                "status": batch_status,
                "errors": errors,
            },
            "failed_export_response": {
                "batch_id": batch_id,
                "failed_paths": failed_files,
                "selected_file_inspection": inspection,
            },
        },
    }


def _recommend(errors: list[dict[str, Any]]) -> list[str]:
    keywords = {str(error.get("keyword", "")).lower() for error in errors}
    messages = " ".join(str(error.get("message", "")).lower() for error in errors)
    actions = []
    if "does not exist in the target schema" in messages:
        actions.append("Remove or remap fields that are not defined in the target XDM schema.")
    if "required" in keywords:
        actions.append("Map or populate required fields before re-ingestion.")
    if "format" in keywords:
        actions.append("Normalize source values to the formats defined by the target XDM schema.")
    if "type" in keywords:
        actions.append("Convert source values to the target XDM data types.")
    actions.extend(
        [
            "Validate a corrected sample against the target schema.",
            "Re-ingest only after approval and retain the original batch ID for traceability.",
        ]
    )
    return list(dict.fromkeys(actions))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "aep_batch_recovery.frontend_server:app",
        host=os.environ.get("AEP_RECOVERY_HOST", "127.0.0.1"),
        port=int(os.environ.get("AEP_RECOVERY_PORT", "5100")),
        reload=False,
    )
