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

To add the network and custom frontend to an existing Neuro SAN checkout:

```powershell
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\neuro-san"
```

The installer adapts to the checkout it is given and then verifies itself, so a
clean run ends with `Verification passed.`

**New here? Follow [docs/INSTALL.md](docs/INSTALL.md)** — the step-by-step
walkthrough, with prerequisites, expected output, troubleshooting, and
uninstall. The [Install into a Neuro SAN
checkout](#install-into-a-neuro-san-checkout) section below is the reference for
what the installer detects and why.

Configure the four Adobe values described below in the host `.env`, start the
host's server, and select the network in the UI. The analysis appears in
**Chat** and the sanitized API JSON appears in **SlyData** under
`aep_api_response`.

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

## Install into a Neuro SAN checkout

```powershell
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\neuro-san"
```

Run it from this package's root. It is safe to re-run: every step is idempotent,
and the manifest is only edited when the entry is missing.

### Supported host layouts

The installer detects the layout rather than assuming one, because the network
name and the destination directories differ between them.

| | Upstream `neuro-san-studio` | Neuro SAN V3 and other flat checkouts |
|---|---|---|
| Detected by | `registries/industry/manifest.hocon` | `registries/manifest.hocon` |
| Registry file | `registries/industry/aep_batch_recovery.hocon` | `registries/aep_batch_recovery.hocon` |
| Manifest entry | `"industry/aep_batch_recovery.hocon": true` | `"aep_batch_recovery.hocon": true` |
| **Network name in the UI** | `industry/aep_batch_recovery` | `aep_batch_recovery` |
| Coded tool package | `coded_tools/aep_batch_recovery/` | `agent_tools/aep_batch_recovery/` |

The coded tool location follows the host: checkouts that already have an
`agent_tools/` directory get the tool there, because `neuro-san` ships a
top-level `coded_tools` package in site-packages that would otherwise shadow a
local one. A stale copy left under `coded_tools/` by an earlier install is
removed.

The installer prints the network name it chose. Use that name in the UI — do not
assume the `industry/` prefix.

### What the installer verifies

After copying, it reports a pass or fail instead of leaving breakage to surface
at launch. It uses the host's `venv` or `.venv` and checks that:

1. the network parses the way the server parses it — as a string, with the repo
   root as the include basedir, which is what catches substitutions whose
   include did not resolve;
2. the coded tool imports from the tool path the server will use, and subclasses
   `CodedTool`;
3. the host's own `validate_registries.py` passes, if it has one. Some checkouts
   gate startup on it, so a failure here means the server will refuse to launch;
4. the four `AEP_*` values have real values, and lists any that are still empty.

Pass `-SkipChecks` to install without the verification pass.

### Adobe credential placeholders

The installer appends the `AEP_*` keys it does not find to the host checkout's
`.env`, creating the file if there is none, so there is nothing to copy by hand:

```dotenv
# Adobe Experience Platform credentials for the AEP Batch Recovery Agent.
# Added by install_into_neuro_san.ps1. Fill these in; never commit real values.
AEP_ACCESS_TOKEN=
AEP_API_KEY=
AEP_ORG_ID=
AEP_SANDBOX_NAME=
```

Only absent keys are appended, always with an empty value. An existing line is
never edited and a credential is never written, so re-running the installer
cannot clobber values you have already filled in. If the host is a git checkout
that does not ignore `.env`, the installer warns before you put real credentials
in it. Pass `-SkipEnvSeed` to leave the host `.env` untouched.

### Include paths and expected startup warnings

The network file lists each shared include under more than one path, for example
both `registries/aaosa.hocon` and `aaosa.hocon`. This is deliberate. The server
parses network files with `ConfigFactory.parse_string`, which resolves includes
against the process working directory, while registry validators parse them from
disk, which resolves against the file's own directory. No single spelling works
in both modes. A bare HOCON `include` is optional, so the path that does not
apply logs `Cannot include file ...` and is skipped. Those warnings at startup
are expected and harmless.

If the host has no `registries/expertise_scoping_instructions.hocon`, the
installer strips that include and its substitution from the installed copy and
warns. The agent then runs without that shared prompt fragment.

### Model selection

The network sets `"model_name": ${?AGENT_MODEL_NAME}`, so the host's configured
model wins and it falls back to the host's shared `config/llm_config.hocon`
default when that variable is unset. This matters on checkouts whose shared
default names a provider they have no key for. The host still needs a working
LLM provider for the reasoning agents; Adobe credentials stay server-side
environment variables.

### After installing

Start the host's server the way that checkout expects — Neuro SAN V3 uses
`.\start-neurosan.ps1`, which sets `AGENT_MANIFEST_FILE` and `AGENT_TOOL_PATH`
and works around spaces in the repo path; upstream Studio uses `ns run`. Then
select the printed network name and submit a batch ID.

To confirm the network registered without opening the UI:

```powershell
curl http://localhost:8080/api/v1/list
```

After the response completes, open the **SlyData** tab to view
`aep_api_response` as sanitized JSON. It contains the outputs from
`get_batch_status`, `list_failed_files`, and `inspect_failed_file` when those
operations run. Credentials, authorization headers, and failed customer records
are never added to this object.

The installer also copies the custom frontend into the host checkout. To run the
server and the custom frontend together, use separate terminals:

```powershell
# Terminal 1: Neuro SAN server and UI
.\start-neurosan.ps1        # or: ns run

# Terminal 2: AEP custom frontend
python -m aep_batch_recovery.frontend_server
```

### If something still fails

| Symptom | Cause |
|---|---|
| `Target is not a Neuro SAN checkout` | The path has neither manifest. Point `-NeuroSanPath` at the checkout root, not a subdirectory. |
| `Registry validation failed` at launch | The host gates startup on its validator. Re-run the installer and read the validator output it prints. |
| Network missing from the UI | The server was started before the install. Restart it; the manifest is read at startup. |
| `missing_environment_variables` in the tool result | The `AEP_*` values are not set in the host `.env`. |
| `NeuroSan already appears to be running on port(s)` | A previous run, or a stale listener whose process has already exited. Relaunch with `-ForceRestart`. |

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
