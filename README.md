# AEP Batch Recovery Agent

A standalone operational application and Neuro SAN agent network for investigating failed Adobe Experience Platform batch ingestions. It retrieves failed-file metadata, inspects schema validation errors, recommends governed recovery checks, and prepares an update for delivery teams.

## What It Does

1. Accepts an AEP batch ID.
2. Calls Adobe Catalog Service to retrieve batch-level status and ingestion errors.
3. Calls Adobe's failed-batch endpoint to list failed paths and inspect record-level validation metadata when available.
4. Groups schema errors and recommends corrective checks.
5. Generates a concise incident update.

The application deliberately does **not** render the failed source record. It returns only allow-listed validation fields such as the keyword, message, violation pointer, and schema location.

Adobe can return the final rejected file as CSV or another non-JSON format. In
that case, the application does not parse or display customer rows. It continues
successfully using the batch-level error codes and descriptions from Adobe
Catalog and reports only the failed file's media type in the sanitized JSON.

The custom frontend includes an expandable **Adobe API Response** section. It
shows sanitized Catalog batch metadata and failed-export paths, but never shows
authorization headers, API keys, access tokens, or raw failed customer records.

## Download and Use

### Option 1: Clone with Git

```powershell
git clone https://github.com/SubasishMula2001/AEP-Batch-Recovery-Agent.git
cd AEP-Batch-Recovery-Agent
```

### Option 2: Download ZIP

1. Open the GitHub repository.
2. Select **Code**, then **Download ZIP**.
3. Extract the ZIP and open PowerShell in the extracted folder.

To add the network and custom frontend to an existing Neuro SAN Studio checkout:

```powershell
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\neuro-san-studio"
```

Configure the four Adobe values described below in the Neuro SAN Studio `.env`,
activate its virtual environment, and run `ns run`. Select
`industry/aep_batch_recovery` in Studio. The normal analysis appears in **Chat**
and the sanitized API JSON appears in **SlyData** under `aep_api_response`.

## Agent Network

```text
User / Batch ID
       |
       v
AEP Batch Recovery Manager
       |
       +--> Failed Batch Retriever --> Adobe API coded tool
       |
       +--> Validation Error Analyzer --> Adobe API coded tool
       |
       +--> Recovery Advisor
       |
       +--> Incident Reporter
```

The network definition is in `registries/industry/aep_batch_recovery.hocon`. The live API integration is in `coded_tools/aep_batch_recovery/adobe_failed_batch.py`.

## Adobe Configuration

Create `.env` from `.env.example` and set these values locally:

```dotenv
AEP_ACCESS_TOKEN=your_access_token
AEP_API_KEY=your_client_id
AEP_ORG_ID=your_org_id
AEP_SANDBOX_NAME=your_sandbox
```

Do not commit `.env`. Adobe access tokens expire and must be refreshed according to your organization's OAuth Server-to-Server process.

## Run the Custom App

From this project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m aep_batch_recovery.frontend_server
```

Open `http://127.0.0.1:5100`.

The custom application runs independently and does not require the Neuro SAN
Python package. When copied into Neuro SAN Studio, the Adobe client automatically
uses Neuro SAN's `CodedTool` base class.

## Install into Neuro SAN Studio

```powershell
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\neuro-san-studio"
```

Restart Neuro SAN, select `industry/aep_batch_recovery`, and submit a batch ID. Neuro SAN also needs a configured LLM provider for the reasoning agents. Adobe credentials remain server-side environment variables.

After the response completes, open the **SlyData** tab in Neuro SAN Studio to
view `aep_api_response` as sanitized JSON. It contains the outputs from
`get_batch_status`, `list_failed_files`, and `inspect_failed_file` when those
operations run. Credentials, authorization headers, and failed customer records
are never added to this object.

The installer also copies the custom frontend into the Neuro SAN checkout. From
that checkout, run `python -m aep_batch_recovery.frontend_server` to launch it.

To run Neuro SAN Studio and the custom frontend together, use separate terminals:

```powershell
# Terminal 1: Neuro SAN server and UI
ns run

# Terminal 2: AEP custom frontend
python -m aep_batch_recovery.frontend_server
```

## Test

```powershell
pytest -q
```

Tests mock all Adobe HTTP requests. They do not use your real credentials or make live API calls.

## Operational Notes

- Use a sandbox and product profile with only the permissions required for batch inspection.
- Keep corporate CA configuration in `REQUESTS_CA_BUNDLE` when required by your network.
- Schema changes, mapping changes, replay, deletion, and re-ingestion require approval.
- Preserve the original batch ID and selected failed-file name for traceability.
