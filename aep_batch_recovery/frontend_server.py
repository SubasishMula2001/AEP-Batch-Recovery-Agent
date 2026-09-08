from __future__ import annotations

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
CODED_TOOLS = ROOT / "coded_tools"
load_dotenv(ROOT / ".env")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coded_tools.aep_batch_recovery.adobe_failed_batch import AdobeFailedBatch  # noqa: E402


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
    return {"status": "ok", "live_ready": not missing, "missing": missing}


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
        return _build_result(batch_id, [], None, batch_errors, batch_status)
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

    return _build_result(batch_id, failed_files, selected, errors, batch_status)


def _build_result(
    batch_id: str,
    failed_files: list[dict[str, Any]],
    selected: str | None,
    errors: list[dict[str, Any]],
    batch_status: str,
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
