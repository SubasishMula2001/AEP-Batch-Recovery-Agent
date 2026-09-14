# Installation Guide

How to add the AEP Batch Recovery Agent to an existing Neuro SAN checkout.

This is the user-facing walkthrough. The
[README](../README.md#install-into-a-neuro-san-checkout) covers the same ground
with the implementation detail behind each step.

- [Prerequisites](#prerequisites)
- [Step 1 — Clone the agent](#step-1--clone-the-agent)
- [Step 2 — Run the installer](#step-2--run-the-installer)
- [Step 3 — Add your Adobe credentials](#step-3--add-your-adobe-credentials)
- [Step 4 — Restart Neuro SAN](#step-4--restart-neuro-san)
- [Step 5 — Use the agent](#step-5--use-the-agent)
- [Optional: the standalone app](#optional-the-standalone-app)
- [What the installer changes](#what-the-installer-changes)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)
- [Upgrading](#upgrading)

## Prerequisites

- A working Neuro SAN checkout. For Neuro SAN V3 that is the folder containing
  `start-neurosan.ps1`, `registries\`, and `agent_tools\`.
- Its Python environment already set up: `venv\Scripts\python.exe` (or
  `.venv\Scripts\python.exe`) must exist. If it does not, run the checkout's own
  Python setup first — on V3, `.\setup-python.ps1`.
- An LLM provider key already working in that checkout's `.env`
  (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`). The reasoning agents need one; the
  Adobe credentials below do not replace it.
- Adobe Experience Platform credentials: access token, client ID, organization
  ID, and sandbox name.
- Git, and PowerShell. The installer runs on the Windows PowerShell 5.1 that
  ships with Windows — nothing newer is required.

## Step 1 — Clone the agent

Clone it somewhere **outside** your Neuro SAN folder:

```powershell
cd C:\work
git clone https://github.com/SubasishMula2001/AEP-Batch-Recovery-Agent.git
cd AEP-Batch-Recovery-Agent
```

Cloning it *inside* the Neuro SAN checkout does work, but then the installer is
copying files into its own parent directory, which is confusing to reason about
if anything goes wrong. Keep them separate.

No `pip install` is needed for the agent network itself. Its only third-party
dependency is `requests`, which is normally already present in a Neuro SAN
environment. See [the standalone app](#optional-the-standalone-app) for the one
case that needs more.

## Step 2 — Run the installer

Run it from the root of this package, pointing at the **root** of your Neuro SAN
checkout:

```powershell
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\Neuro-San-V3-main"
```

A successful run prints:

```
AEP Batch Recovery Agent installed into C:\path\to\Neuro-San-V3-main
  network:    aep_batch_recovery
  registry:   registries\aep_batch_recovery.hocon
  coded tool: agent_tools\aep_batch_recovery
  manifest:   registries\manifest.hocon

Appended 4 empty placeholder(s) to .env: AEP_ACCESS_TOKEN, AEP_API_KEY, AEP_ORG_ID, AEP_SANDBOX_NAME

Checking the network parses the way Neuro SAN loads it...
  tools: aep_batch_recovery_manager, failed_batch_retriever, validation_error_analyzer, recovery_advisor, incident_reporter, aep_failed_batch_tool
  model: claude-sonnet
Checking the coded tool imports...
  AdobeFailedBatch -> CodedTool
Running the checkout's registry validator...
  all registries valid

Verification passed.
```

If your checkout has no `.env` yet, the first line reads `Created .env with
empty placeholders` instead. The reported `model` is whatever the network
resolves to in the shell you ran the installer from — usually your checkout's
shared default, since `AGENT_MODEL_NAME` normally lives in `.env` and is applied
by the launcher at runtime rather than being set in your shell.

Two things to take from that output:

**Note the `network:` line.** That is the name to select in the UI. On Neuro SAN
V3 and other flat checkouts it is `aep_batch_recovery`, with no prefix. The
`industry/aep_batch_recovery` form only applies to upstream
`neuro-san-studio`, which groups registries into subdirectories. The installer
detects which layout you have and prints the right name — use what it prints.

**Do not continue past a missing `Verification passed.`** The installer checks
its own work, so a failure here is a real problem that would otherwise surface
as a confusing error at launch. See [Troubleshooting](#troubleshooting).

Re-running the installer is safe at any time. Every step is idempotent: the
manifest is only edited when the entry is absent, and existing `.env` values are
never touched.

### Installer options

| Option | Effect |
|---|---|
| `-NeuroSanPath <path>` | Required. The Neuro SAN checkout root. |
| `-SkipChecks` | Install without the verification pass. |
| `-SkipEnvSeed` | Do not append `AEP_*` placeholders to the host `.env`. |

## Step 3 — Add your Adobe credentials

The installer appended empty placeholders to your Neuro SAN checkout's `.env`.
Open that file and fill them in:

```dotenv
AEP_ACCESS_TOKEN=your_access_token
AEP_API_KEY=your_client_id
AEP_ORG_ID=your_org_id
AEP_SANDBOX_NAME=your_sandbox
```

`AEP_API_KEY` is your Adobe **client ID**, not a separately issued API key.

Adobe access tokens expire. Refresh them according to your organization's OAuth
Server-to-Server process. Never commit real values — confirm `.env` is
git-ignored in your checkout; the installer warns you if it is not.

The credentials are read server-side, from the environment, at the moment the
tool runs. They are never sent to the model, never logged, and never placed in
the agent's response.

## Step 4 — Restart Neuro SAN

The manifest is read at startup, so a server that was already running will not
see the new network.

```powershell
cd "C:\path\to\Neuro-San-V3-main"
.\start-neurosan.ps1
```

On Neuro SAN V3, use `.\start-neurosan.ps1` rather than `ns run`. The script
sets `AGENT_MANIFEST_FILE` and `AGENT_TOOL_PATH` and works around spaces in the
repository path; `ns run` on its own will not find the registries. On upstream
`neuro-san-studio`, `ns run` is the correct command.

If startup reports `NeuroSan already appears to be running on port(s): 4173`,
that is either a live server or a stale listener left by a previous run.
Replace it:

```powershell
.\start-neurosan.ps1 -ForceRestart
```

## Step 5 — Use the agent

Open <http://localhost:4173> and select the network name the installer printed —
`aep_batch_recovery` on V3.

Submit a batch ID:

```
Analyze failed files for AEP batch 01ABCDEF1234567890 and prepare a recovery update.
```

The analysis appears in **Chat**. Open the **SlyData** tab to see
`aep_api_response`: the sanitized Adobe JSON from `get_batch_status`,
`list_failed_files`, and `inspect_failed_file` for the operations that ran.

The agent deliberately does not render failed source records. It reports only
allow-listed validation fields — keyword, message, violation pointer, schema
location. Credentials, authorization headers, and failed customer records are
never added to `aep_api_response`. When Adobe returns the rejected file as CSV
or another non-JSON format, the agent does not parse customer rows; it continues
using batch-level error codes from Adobe Catalog and reports only the file's
media type.

Schema changes, mapping changes, replay, deletion, and re-ingestion are treated
as approval-required actions. The agent recommends them; it does not perform
them.

To confirm the network registered without opening the UI:

```powershell
curl http://localhost:8080/api/v1/list
```

## Optional: the standalone app

The agent ships with its own web frontend, which runs independently of Neuro
SAN. In a second terminal:

```powershell
cd "C:\path\to\Neuro-San-V3-main"
.\venv\Scripts\Activate.ps1
python -m aep_batch_recovery.frontend_server
```

Open <http://127.0.0.1:5100>. This is a different port from the Neuro SAN UI on
4173 — both can run at once.

If it fails on a missing import, install its dependencies from this package:

```powershell
pip install -r requirements.txt
```

Override the bind address with `AEP_RECOVERY_HOST` and `AEP_RECOVERY_PORT`.

## What the installer changes

Inside your Neuro SAN checkout:

| Path | Change |
|---|---|
| `registries\aep_batch_recovery.hocon` | added — the agent network |
| `registries\manifest.hocon` | one entry added, if absent |
| `agent_tools\aep_batch_recovery\` | added — the Adobe coded tool |
| `aep_batch_recovery\` | added — the standalone app |
| `.env` | missing `AEP_*` keys appended, empty |

Nothing else is modified.

The coded tool goes in `agent_tools\` rather than `coded_tools\` when your
checkout has an `agent_tools\` directory. This is not cosmetic: `neuro-san`
ships a top-level `coded_tools` package in site-packages that shadows a local
one, so a tool installed there would not be found. If an earlier install left a
copy under `coded_tools\aep_batch_recovery\`, the installer removes it.

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `Target is not a Neuro SAN checkout` | `-NeuroSanPath` is not a checkout root. It needs either `registries\manifest.hocon` or `registries\industry\manifest.hocon` directly beneath it. Point at the folder containing `registries\`, not at `registries\` itself. |
| `Registry validation failed (see above)` at launch | Neuro SAN V3 gates startup on its own `validate_registries.py`. The server will not start until it passes. Re-run the installer and read the validator lines it prints — they name the offending file. |
| The network is missing from the UI list | The server was started before the install. Restart it; the manifest is only read at startup. |
| `missing_environment_variables` in the agent's reply | [Step 3](#step-3--add-your-adobe-credentials) was skipped, or the server was not restarted after editing `.env`. |
| `Cannot include file aaosa.hocon` at startup | Expected and harmless. The network lists each shared include under more than one path because the server and the registry validators resolve include paths differently; the path that does not apply is skipped with this warning. |
| `No venv found ... skipping verification` | The checkout's Python environment is not set up. Run its Python setup, then re-run the installer to get the verification pass. |
| `NeuroSan already appears to be running on port(s)` | A live server, or a stale listener whose process already exited. Relaunch with `-ForceRestart`. |
| `does not appear to be git-ignored` | Your checkout would commit `.env`. Add `.env` to its `.gitignore` before putting real credentials in the file. |
| `dubious ownership in repository` from git | The clone is owned by another account, commonly `BUILTIN\Administrators`. Run the `git config --global --add safe.directory ...` command git suggests. |

## Uninstalling

Delete what was added and remove the one manifest line:

```powershell
$ns = "C:\path\to\Neuro-San-V3-main"
Remove-Item "$ns\registries\aep_batch_recovery.hocon"
Remove-Item "$ns\agent_tools\aep_batch_recovery" -Recurse
Remove-Item "$ns\aep_batch_recovery" -Recurse
```

Then delete the `"aep_batch_recovery.hocon": true` line from
`registries\manifest.hocon` and restart the server. The `AEP_*` entries in
`.env` are inert once the network is gone; remove them at your discretion.

## Upgrading

```powershell
cd C:\work\AEP-Batch-Recovery-Agent
git pull
.\scripts\install_into_neuro_san.ps1 -NeuroSanPath "C:\path\to\Neuro-San-V3-main"
```

Then restart Neuro SAN. Your filled-in `.env` values survive: the installer only
appends keys that are absent and never edits an existing line.
