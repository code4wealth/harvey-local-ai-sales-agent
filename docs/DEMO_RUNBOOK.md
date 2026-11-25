# Windows demo and acceptance runbook

> **Owner-reported partial results; evidence review is pending.** This document
is an instruction set, not a test result. The owner reports a Windows live run
and an eight-workflow Wi-Fi-disconnected run; the run date, logs, screenshots,
network observations, and outage/recovery result are not fully evidenced in this
checkout. Section 6 separates those owner reports from checks still pending.

Use Windows PowerShell 5.1 or PowerShell 7 from the repository root. The demo
uses only fictional `SAMPLE` product/prospect/reply data. It does not discover
prospects. `/operations` is the UI for the product-level pipeline; the offline
acceptance script below separately executes the eight individual workflow
checks. Do not describe those two runs as the same pipeline execution.

The scripts write timestamped records automatically:

- `scripts/offline_acceptance.ps1` writes a `.log` and `.json` under
  `test_evidence/offline/`.
- `scripts/ollama_down_check.ps1` writes a `.log` and `.json` under
  `test_evidence/ollama_outage/`.

The first script makes one `https://example.com/` request as an offline
indicator. A failed request is **not proof** that all outbound routes are
blocked. The second script tests Ollama availability, a queued AI task,
deterministic ranking during the outage, restart, queue wake, and task recovery.
Neither script is a packet capture. Preserve failed as well as passed evidence.

## 1. Install dependencies and cache models while online

In a PowerShell window at the repository root, create evidence directories and
start a transcript for preparation output:

```powershell
$RepoRoot = (Resolve-Path .).Path
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OfflineDir = Join-Path $RepoRoot 'test_evidence\offline'
$OutageDir = Join-Path $RepoRoot 'test_evidence\ollama_outage'
New-Item -ItemType Directory -Force -Path $OfflineDir, $OutageDir | Out-Null
Start-Transcript -Path (Join-Path $OfflineDir "preparation-$RunStamp.txt")
```

Install the project into its local virtual environment. If script activation is
blocked, the process-scoped setting below does not change the machine policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python scripts/verify_no_cloud.py
python -m pytest -q
```

On the target laptop, `pytest` should find PowerShell and run the two script
parser checks rather than skip them. A skip or failure is not a PowerShell
acceptance pass. Keep the exact test output in the preparation transcript.

Pull the exact generation model that will be used for the demo. These commands
match the earlier user-reported target setup; if the target uses a different
`DEFAULT_MODEL`, pull and test that exact tag instead:

```powershell
ollama pull qwen3:4b
ollama list
```

Cache the embedding model **before setting the offline flags**. The application
embedding loader forces Hugging Face/Transformers offline mode; for the first
cache fill, use the library directly while connected:

```powershell
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:OFFLINE_STRICT -ErrorAction SilentlyContinue
python -c 'from sentence_transformers import SentenceTransformer; model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2"); print("embedding dimension:", model.get_sentence_embedding_dimension())'
python -c 'from huggingface_hub.constants import HF_HUB_CACHE; print("Hugging Face cache:", HF_HUB_CACHE)'
```

A successful cache fill must complete before Wi-Fi is disabled. Then set the
process-scoped local-only configuration and run both real local smoke checks:

```powershell
$env:DEFAULT_MODEL = 'qwen3:4b'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:OFFLINE_STRICT = '1'
$DemoDb = Join-Path $RepoRoot "data\harvey-offline-$RunStamp.db"
$env:DB_PATH = $DemoDb
Write-Host "Isolated demo DB: $DemoDb"
python scripts/import_replies.py --db-path $DemoDb
python scripts/smoke_embeddings.py
python scripts/smoke_ollama.py
```

`smoke_embeddings.py` verifies the already-cached embedding model while offline;
`smoke_ollama.py` makes a real local Ollama request using `qwen3:4b`. These are
live target checks, not unit tests, and their outcome is still **PENDING** until
performed. The new database is separate from `data\harvey.db` and is ignored by
Git.

Immediately after `smoke_ollama.py`, capture the loaded model's runtime placement
and Ollama's listener. `ollama ps` is the runtime view; the hardware-tier
recommendation alone does not establish the CPU/GPU split.

```powershell
$RuntimeEvidence = Join-Path $OfflineDir "runtime-$RunStamp.txt"
"Captured: $(Get-Date -Format o)" | Set-Content -Encoding UTF8 $RuntimeEvidence
"--- ollama list ---" | Add-Content -Encoding UTF8 $RuntimeEvidence
ollama list | Add-Content -Encoding UTF8 $RuntimeEvidence
"--- ollama ps ---" | Add-Content -Encoding UTF8 $RuntimeEvidence
ollama ps | Add-Content -Encoding UTF8 $RuntimeEvidence
"--- netstat port 11434 ---" | Add-Content -Encoding UTF8 $RuntimeEvidence
netstat -ano | findstr ":11434" | Add-Content -Encoding UTF8 $RuntimeEvidence
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    "--- nvidia-smi ---" | Add-Content -Encoding UTF8 $RuntimeEvidence
    nvidia-smi | Add-Content -Encoding UTF8 $RuntimeEvidence
} else {
    "nvidia-smi not available" | Add-Content -Encoding UTF8 $RuntimeEvidence
}
Stop-Transcript
```

The transcript and runtime file are supplementary local notes; the scripts'
JSON/log files remain the acceptance records. Confirm the listener is local and
record the exact `netstat` line. Do not claim a GPU split if `ollama ps` does not
show one.

## 2. Start the API and load only fictional sample records

Open a **new** PowerShell window at the repository root. Environment variables
are process-scoped, so set the same database/model/offline values in the API
window. Copy the exact database path printed above:

```powershell
$RepoRoot = (Resolve-Path .).Path
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$DemoDb = Join-Path $RepoRoot 'data\harvey-offline-REPLACE_WITH_RUNSTAMP.db'
$env:DB_PATH = $DemoDb
$env:DEFAULT_MODEL = 'qwen3:4b'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:OFFLINE_STRICT = '1'
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Replace the `REPLACE_WITH_RUNSTAMP` portion with the actual timestamp from the
first window. Keep this API window open. It must bind to `127.0.0.1`, not
`0.0.0.0`.

In a third PowerShell window, create a RelayCue product and import the bundled
fictional prospects. The CSV contains repository-local page paths; it does not
fetch the web. The text-only SAMPLE replies (`R001` included) were imported into
the isolated database in the preparation step:

```powershell
$RepoRoot = (Resolve-Path .).Path
$BaseUrl = 'http://127.0.0.1:8000'
$SetupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$SetupTranscript = Join-Path $RepoRoot "test_evidence\offline\sample-setup-$SetupStamp.txt"
Start-Transcript -Path $SetupTranscript
$Body = @{
    name = 'RelayCue'
    description = 'Fictional support handoff workspace'
    docs_path = 'data/company_info/relaycue.md'
} | ConvertTo-Json -Compress
$Product = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/products" `
    -ContentType 'application/json' -Body $Body
$ProductId = [int]$Product.id
$ProspectsCsv = Join-Path $RepoRoot 'data\prospects\SAMPLE_relaycue.csv'
$ImportResult = Invoke-RestMethod -Method Post `
    -Uri "$BaseUrl/api/products/$ProductId/prospects/import" `
    -ContentType 'text/csv; charset=utf-8' -InFile $ProspectsCsv
$ImportResult
Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/status" | ConvertTo-Json -Depth 8
Stop-Transcript
```

The expected import counts are not acceptance results until the commands run; use
the API's actual response. Keep the database, model cache, API, and Ollama on
the same Windows user account. Do not place real prospect data in the demo DB.

## 3. Disconnect Wi-Fi and run the eight offline workflow checks

First identify the Wi-Fi adapter. Run the adapter commands in an **elevated**
PowerShell window if Windows requests administrator permission. Substitute the
exact adapter name shown on this laptop (it may not be named `Wi-Fi`):

```powershell
Get-NetAdapter | Format-Table Name, InterfaceDescription, Status
$WifiName = 'Wi-Fi'
Disable-NetAdapter -Name $WifiName -Confirm:$false
Get-NetAdapter -Name $WifiName | Format-Table Name, Status
```

A Windows Settings Wi-Fi toggle is an alternative if the adapter cmdlet is
unavailable, but record which method was used. Do not proceed as an offline run
if the adapter did not actually disconnect. Leave Ollama and the local API
running. In a fresh PowerShell window at the repository root, save the observed
network state and run the acceptance script:

```powershell
$RepoRoot = (Resolve-Path .).Path
$OfflineDir = Join-Path $RepoRoot 'test_evidence\offline'
$WifiName = 'Wi-Fi' # use the actual adapter name from Get-NetAdapter
$DeviceEvidence = Join-Path $OfflineDir ("device-state-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.txt')
"Captured: $(Get-Date -Format o)" | Set-Content -Encoding UTF8 $DeviceEvidence
"--- Wi-Fi adapter ---" | Add-Content -Encoding UTF8 $DeviceEvidence
Get-NetAdapter -Name $WifiName | Format-List Name, InterfaceDescription, Status | Out-String | Add-Content -Encoding UTF8 $DeviceEvidence
"--- local Ollama process ---" | Add-Content -Encoding UTF8 $DeviceEvidence
ollama ps | Add-Content -Encoding UTF8 $DeviceEvidence
"--- local API and Ollama listeners ---" | Add-Content -Encoding UTF8 $DeviceEvidence
netstat -ano | findstr ":8000" | Add-Content -Encoding UTF8 $DeviceEvidence
netstat -ano | findstr ":11434" | Add-Content -Encoding UTF8 $DeviceEvidence
```

Resolve the RelayCue product ID and invoke the script with all eight workflow
steps in the documented order. Run this in its own PowerShell window; a failed
script exits non-zero after writing its timestamped evidence:

```powershell
$BaseUrl = 'http://127.0.0.1:8000'
$RelayCue = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/products" |
    Where-Object { $_.name -eq 'RelayCue' } | Select-Object -First 1
if (-not $RelayCue) { throw 'RelayCue sample product is missing.' }
$ProductId = [int]$RelayCue.id
.\scripts\offline_acceptance.ps1 `
    -ProfileProductId $ProductId `
    -IcpProductId $ProductId `
    -ReplyId 'R001' `
    -WaitSeconds 300
```

The eight checks are:

1. Business profile generation.
2. Product ICP generation.
3. Research from the already-saved prospect page (metadata/file check only; no model call or web fetch).
4. Signal extraction from that local page.
5. Evidence-grounded problem statement (a valid missing-evidence `skipped` result is recorded as such).
6. Product scoring/ranking (deterministic ranking).
7. Evidence-grounded unsent draft (`sent` must remain `false`; a no-evidence skip is recorded).
8. Reply classification of the SAMPLE reply `R001`.

The script resolves the first RelayCue prospect with a saved page. It records
statuses, IDs/counts, model/runtime traceability, a one-shot public-host probe,
and a process-connection snapshot; it does not save generated statement, draft,
reply, or page text. The probe must fail to be an offline indicator, but that
single failure is not comprehensive network isolation evidence. The TCP snapshot
is not a packet capture. If any workflow or runtime check fails, retain the
`.json` and `.log`, describe the actual outcome, and do not relabel it PASS.

After the script completes, reconnect Wi-Fi and confirm the adapter state:

```powershell
Enable-NetAdapter -Name $WifiName -Confirm:$false
Get-NetAdapter -Name $WifiName | Format-Table Name, Status
```

Do not stop the API or Ollama yet if you are continuing directly to the outage
check. The offline script writes `acceptance-<timestamp>.log` and
`acceptance-<timestamp>.json` under `test_evidence/offline/`; your network and
runtime notes are saved there too.

## 4. Stop and restart Ollama for the outage/recovery check

The API must remain running against the same isolated database, and RelayCue
must still have a saved prospect page. Reconnect Wi-Fi before this separate
check so the outage test is not confused with the Wi-Fi-off test. Use a
controllable Ollama server window: if Ollama is running in the system tray,
quit that instance first, then start `ollama serve` in a dedicated PowerShell
window and leave that window open. Confirm the server is listening:

```powershell
ollama ps
netstat -ano | findstr ":11434"
```

`ollama stop qwen3:4b` only unloads the model; it does **not** make the Ollama
server unavailable and is not sufficient for this test. In a separate
PowerShell window at the repository root, start a transcript and run the
interactive script:

```powershell
$RepoRoot = (Resolve-Path .).Path
$OutageDir = Join-Path $RepoRoot 'test_evidence\ollama_outage'
$OutageStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutageTranscript = Join-Path $OutageDir "operator-session-$OutageStamp.txt"
Start-Transcript -Path $OutageTranscript
.\scripts\ollama_down_check.ps1 -WaitSeconds 300
```

When the script says to stop Ollama, switch to its dedicated `ollama serve`
window and press **Ctrl+C**. Confirm the listener is gone, then press Enter in
the outage-script window:

```powershell
netstat -ano | findstr ":11434"
```

The script checks that the API reports Ollama unavailable, submits one signal
workflow and expects a persisted `queued` state, checks deterministic ranking,
and records queue counts while Ollama is down. When it asks to start Ollama,
return to the dedicated server window and run:

```powershell
ollama serve
```

Wait for the server to report ready. In another PowerShell window, confirm the
listener is back and append the result to the outage transcript if desired:

```powershell
netstat -ano | findstr ":11434"
ollama ps
```

Then press Enter in the script window. It waits for Ollama recovery, requests a
queue-worker wake, and polls for the queued signal run to finish. `ollama ps`
and `netstat` observations do not by themselves prove workflow success; inspect
the script's actual result and generated JSON/log files. End the transcript
when the script returns:

```powershell
Stop-Transcript
Get-ChildItem $OutageDir | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name, Length, LastWriteTime
```

The script writes `ollama-down-<timestamp>.log` and
`ollama-down-<timestamp>.json` under `test_evidence/ollama_outage/`. Preserve
failed files and record any permission errors or service restarts that prevented
a controlled outage.

## 5. Seven-to-nine-minute demo talk track

This is an **approximately eight-minute narration plan**, not a measured runtime
or performance claim. The target laptop's model execution time is unverified;
wait for actual workflow responses and record the real elapsed time rather than
rushing or claiming a fixed result.

| Time | Demo action and suggested narration |
|---|---|
| 0:00–0:45 | “This demo uses fictional SAMPLE data. There is no automatic prospect discovery; the app only processes the imported CSV and saved page text. AI inference is sent to local Ollama, not a hosted service.” |
| 0:45–1:30 | Open `http://127.0.0.1:8000/operations`. Show RelayCue and the product-level pipeline controls. Explain that `/operations` is the visual workflow console; the eight acceptance checks are a separate PowerShell run. |
| 1:30–2:00 | Show `HF_HUB_OFFLINE=1`, the `ollama ps` output, and the `netstat` listener record. State that these are observations from this run only; the hardware recommendation is not a CPU/GPU benchmark. |
| 2:00–6:20 | Start `offline_acceptance.ps1`. Narrate the ordered checks as they appear: **1** profile; **2** ICP; **3** local saved-page research; **4** signals; **5** problem statement; **6** ranking; **7** unsent draft; **8** reply classification. Explain that no-evidence skips are valid workflow outcomes, not fabricated successes. |
| 6:20–7:20 | Show the actual timestamped `test_evidence/offline/` log and JSON summary. Read only statuses and counts; do not invent or expose output text as an acceptance result. If the probe, API, model, or any step failed, describe that result honestly. |
| 7:20–8:00 | “The script's `example.com` probe is only one offline indicator, and its TCP snapshot is not a packet capture. Wi-Fi isolation, model offload, and the Ollama outage/recovery run remain PENDING until their separate evidence is reviewed.” |

If inference takes longer than the planned segment, keep the demo recording or
extend the session and report the actual duration. The 7–9-minute target is not
verified until it has been timed on the target laptop.

## 6. Current physical-device status

### Owner-reported Windows run

Windows runs: owner-reported, 2026-11-26 (local time, IST). The workspace snapshot carries earlier timestamps (2026-11-23 UTC); the runs were performed afterwards. The reported outcomes were not independently inspected from a laptop capture in this checkout.

- Live local inference used `qwen3:4b` via Ollama. The owner reports `ollama ps`
  showed about 66% GPU / 34% CPU on an RTX 3050, with 15.7 GB RAM and 12 CPUs.
  An exact model digest, Ollama version, and embedding-device placement were
  not supplied in this update.
- The online FieldNest run reportedly completed profile, ICP, signals, problem
  statement, draft, and ranking; 20 prospects and 60 sample replies were
  imported. The owner reports `R004` classified `not_interested`, matching the
  ambiguous development label (the label is present in the checked-in evaluator
  data; the runtime result itself has no capture file here).
- The owner reports all eight workflows worked with Wi-Fi disconnected and that
  this run was screen-recorded. This does not establish that the PowerShell
  acceptance script was used, that the screen recording is stored here, or
  that network traces/listener logs were captured.

Ping failure / `netstat` on port 11434, Ollama outage/recovery status, screenshot
file list, and demo footer commit hash remain unresolved. The owner supplied two
Drive links, but their roles and contents are unconfirmed; the demo-video URL
remains unresolved until the recording link is identified. Leave each item
pending until the owner supplies a value or an artifact is verified.

### Evidence present in this checkout

The actual files under `test_evidence/` are:

- `test_evidence/online/README.md` — template only; not screenshots or run logs.
- `test_evidence/real_run/smoke_embeddings.txt` — earlier operator-provided
  embedding smoke record.
- `test_evidence/real_run/smoke_ollama.txt` — earlier single-call Ollama smoke
  record.

There are no files under `test_evidence/offline/` or
`test_evidence/ollama_outage/`, and no screenshot image file is present under
`test_evidence/` in this checkout.

### Still pending

- The owner confirms the reported date as 2026-11-26 (local time, IST); review/attach the screen recording and verify which supplied Drive link contains it.
- Confirm whether the offline PowerShell script ran; save/review its actual log
  and JSON if available. Confirm the `example.com` probe result and any ping,
  listener (`netstat`), or network-capture evidence; do not infer these.
- Run and record the controlled Ollama stop, queued task, deterministic ranking,
  restart, worker wake, and replay if it was not completed.
- Identify which of the two owner-supplied Drive links is the demo video, then
  record its URL and the commit hash visible in its footer; check the video
  matches the final branch commit.
- Add actual target-run screenshots, if they exist, and record their real
  paths. No screenshot is present under `test_evidence/`; three static dashboard
  images under `docs/images/` are not evidence from the owner-reported run.
- Record target embedding-device placement and any performance only from an
  actual capture; none was reported here.

Do not replace these entries with mock/unit-test results, expected output, or
operator instructions. Preserve failures and skips; do not commit real prospect
data or private machine details.
