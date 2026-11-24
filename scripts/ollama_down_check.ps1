[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [ValidateRange(1, 3600)][int]$WaitSeconds = 300,
    [switch]$OllamaAlreadyStopped
)

$ErrorActionPreference = "Stop"
$script:BaseUri = [Uri]$BaseUrl
if ($script:BaseUri.Scheme -ne "http" -or $script:BaseUri.Host -notin @("127.0.0.1", "::1")) {
    throw "BaseUrl must use the numeric loopback host 127.0.0.1 or ::1 over HTTP."
}
$script:BaseUrl = $BaseUrl.TrimEnd("/")
$script:WaitSeconds = $WaitSeconds
$script:RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:OutputDirectory = Join-Path (Join-Path $script:RepoRoot "test_evidence") "ollama_outage"
New-Item -ItemType Directory -Path $script:OutputDirectory -Force | Out-Null
$script:LogPath = Join-Path $script:OutputDirectory "ollama-down-$($script:RunStamp).log"
$script:JsonPath = Join-Path $script:OutputDirectory "ollama-down-$($script:RunStamp).json"
[IO.File]::WriteAllText(
    $script:LogPath,
    "Harvey Ollama outage check started $((Get-Date).ToString('o'))$([Environment]::NewLine)",
    [Text.Encoding]::UTF8
)

$script:ApiHandler = [System.Net.Http.HttpClientHandler]::new()
$script:ApiHandler.UseProxy = $false
$script:ApiHandler.AllowAutoRedirect = $false
$script:ApiClient = [System.Net.Http.HttpClient]::new($script:ApiHandler)
$script:ApiClient.Timeout = [TimeSpan]::FromSeconds([Math]::Max(180, $WaitSeconds + 30))
$script:OllamaBaseUrl = "http://127.0.0.1:11434"
$script:Steps = [System.Collections.Generic.List[object]]::new()
$script:Evidence = [ordered]@{
    created_at = (Get-Date).ToString("o")
    log_file = $script:LogPath
    json_file = $script:JsonPath
    base_host = $script:BaseUri.Host
    commit_hash = $null
    ollama_url = $script:OllamaBaseUrl
    ollama_host = "127.0.0.1"
    ollama_version = $null
    model = $null
    seed = $null
    temperature = $null
    steps = @()
}

function Write-LogLine {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date).ToString("o"), $Message
    [IO.File]::AppendAllText(
        $script:LogPath,
        $line + [Environment]::NewLine,
        [Text.Encoding]::UTF8
    )
    Write-Host $Message
}

function Add-Step {
    param(
        [string]$Name,
        [bool]$Passed,
        [System.Collections.IDictionary]$Details
    )
    $result = if ($Passed) { "PASS" } else { "FAIL" }
    $entry = [ordered]@{ step = $Name; result = $result }
    foreach ($key in $Details.Keys) { $entry[$key] = $Details[$key] }
    [void]$script:Steps.Add([pscustomobject]$entry)
    $detailJson = ConvertTo-Json -InputObject $Details -Depth 10 -Compress
    Write-LogLine "[$result] $Name $detailJson"
}

function Get-PayloadStatus {
    param($Response)
    if ($null -eq $Response -or $null -eq $Response.Payload) { return "unavailable" }
    $property = $Response.Payload.PSObject.Properties["status"]
    if ($null -ne $property) { return [string]$property.Value }
    return "unavailable"
}

function Get-ErrorClass {
    param($Value)
    if ($Value -is [string] -and $Value -match '^\s*([A-Za-z][A-Za-z0-9_.]+):') {
        return $Matches[1]
    }
    if ($Value) { return "present" }
    return $null
}

function Get-QueueSummary {
    param($Payload)
    $queue = if ($Payload) { $Payload.queue } else { $null }
    return [ordered]@{
        queued = if ($queue) { [int]$queue.queued } else { $null }
        running = if ($queue) { [int]$queue.running } else { $null }
        done = if ($queue) { [int]$queue.done } else { $null }
        failed = if ($queue) { [int]$queue.failed } else { $null }
    }
}

function Invoke-LocalApi {
    param([string]$Method, [string]$Path)
    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method), "$($script:BaseUrl)$Path"
    )
    $response = $null
    try {
        $response = $script:ApiClient.SendAsync($request).GetAwaiter().GetResult()
        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $payload = $null
        if ($content) {
            try { $payload = ConvertFrom-Json -InputObject $content } catch { $payload = $null }
        }
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Payload = $payload
            ErrorType = $null
        }
    } catch {
        return [pscustomobject]@{
            StatusCode = 0
            Payload = $null
            ErrorType = $_.Exception.GetType().Name
        }
    } finally {
        $request.Dispose()
        if ($response) { $response.Dispose() }
    }
}

function Get-OllamaVersion {
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(5)
    $response = $null
    try {
        $response = $client.GetAsync("$($script:OllamaBaseUrl)/api/version").GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) { return $null }
        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $payload = ConvertFrom-Json -InputObject $content
        return [string]$payload.version
    } catch {
        return $null
    } finally {
        if ($response) { $response.Dispose() }
        $client.Dispose()
        $handler.Dispose()
    }
}

function Wait-ForSignalRun {
    param([int]$ProspectId, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        $last = Invoke-LocalApi -Method "GET" -Path "/api/prospects/$ProspectId/signals"
        $state = Get-PayloadStatus $last
        if ($state -notin @("queued", "running", "pending")) { return $last }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $last
}

function Update-Traceability {
    param($StatusResponse)
    $payload = if ($StatusResponse) { $StatusResponse.Payload } else { $null }
    $lastInference = if ($payload -and $payload.ollama) { $payload.ollama.last_inference } else { $null }
    if ($payload) { $script:Evidence["commit_hash"] = $payload.git_commit }
    $detectedVersion = Get-OllamaVersion
    if ($detectedVersion) { $script:Evidence["ollama_version"] = $detectedVersion }
    if ($payload -and $payload.ollama) {
        $script:Evidence["ollama_url"] = $payload.ollama.url
        try { $script:Evidence["ollama_host"] = ([Uri]$payload.ollama.url).Host } catch { }
        if ($payload.ollama.model) { $script:Evidence["model"] = $payload.ollama.model }
    }
    if ($lastInference) {
        $script:Evidence["model"] = $lastInference.model
        $script:Evidence["seed"] = $lastInference.seed
        $script:Evidence["temperature"] = $lastInference.temperature
    }
    return [pscustomobject]@{ Payload = $payload; LastInference = $lastInference }
}

try {
    # Capture the pre-outage version if possible, then guide the operator through
    # stopping and restarting Ollama. This does not run a model request.
    $script:Evidence["ollama_version"] = Get-OllamaVersion
    if (-not $OllamaAlreadyStopped) {
        Write-LogLine "Stop the local Ollama service/model now; leave the Harvey API running."
        [void](Read-Host "Press Enter when Ollama is stopped")
    }

    $downStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $ollamaDown = $downStatus.StatusCode -eq 200 -and $downStatus.Payload.ollama.available -eq $false
    $downTrace = Update-Traceability $downStatus
    Add-Step "Ollama unavailable is visible in API status" ([bool]$ollamaDown) ([ordered]@{
        http_status = $downStatus.StatusCode
        ollama_state = if ($downStatus.Payload) { $downStatus.Payload.ollama.state } else { "unavailable" }
        commit_hash = $script:Evidence.commit_hash
        model = $script:Evidence.model
        ollama_version = $script:Evidence.ollama_version
        queue_before = (Get-QueueSummary $downStatus.Payload)
    })

    $products = Invoke-LocalApi -Method "GET" -Path "/api/products"
    $relayCue = if ($products.Payload) { @($products.Payload | Where-Object { $_.name -eq "RelayCue" } | Select-Object -First 1) } else { @() }
    $productId = if ($products.StatusCode -eq 200 -and $relayCue.Count -gt 0) { [int]$relayCue[0].id } else { 0 }
    $prospectId = 0
    if ($productId -gt 0) {
        $prospects = Invoke-LocalApi -Method "GET" -Path "/api/products/$productId/prospects"
        $candidate = if ($prospects.Payload) { @($prospects.Payload | Where-Object { $_.page_text_path } | Select-Object -First 1) } else { @() }
        if ($candidate.Count -gt 0) { $prospectId = [int]$candidate[0].id }
    }

    $script:Evidence["product_id"] = if ($productId -gt 0) { $productId } else { $null }
    $script:Evidence["prospect_id"] = if ($prospectId -gt 0) { $prospectId } else { $null }
    $queuedPayload = $null
    if ($prospectId -gt 0 -and $ollamaDown) {
        $queuedResponse = Invoke-LocalApi -Method "POST" -Path "/api/prospects/$prospectId/signals"
        $queuedPayload = $queuedResponse.Payload
        $queuedState = Get-PayloadStatus $queuedResponse
        $queuedErrorClass = if ($queuedPayload) { Get-ErrorClass $queuedPayload.error } else { $null }
        $hasQueueTask = $queuedPayload -and $queuedPayload.queue_task_id
        $isQueued = $queuedResponse.StatusCode -eq 202 -and
            $queuedState -eq "queued" -and $hasQueueTask -and $queuedErrorClass
        if ($queuedPayload) {
            if ($queuedPayload.model_name) { $script:Evidence["model"] = $queuedPayload.model_name }
            if ($null -ne $queuedPayload.seed) { $script:Evidence["seed"] = $queuedPayload.seed }
            if ($null -ne $queuedPayload.temperature) { $script:Evidence["temperature"] = $queuedPayload.temperature }
        }
        Add-Step "AI workflow persists queued status and structured error" ([bool]$isQueued) ([ordered]@{
            product_id = $productId
            prospect_id = $prospectId
            http_status = $queuedResponse.StatusCode
            status = $queuedState
            queue_task_id = if ($queuedPayload) { $queuedPayload.queue_task_id } else { $null }
            run_id = if ($queuedPayload) { $queuedPayload.id } else { $null }
            model = if ($queuedPayload) { $queuedPayload.model_name } else { $null }
            seed = if ($queuedPayload) { $queuedPayload.seed } else { $null }
            temperature = if ($queuedPayload) { $queuedPayload.temperature } else { $null }
            error_class = $queuedErrorClass
        })
    } else {
        Add-Step "AI workflow persists queued status and structured error" $false ([ordered]@{
            status = if ($prospectId -le 0) { "no RelayCue prospect with stored page" } else { "Ollama was not confirmed unavailable" }
        })
    }

    if ($productId -gt 0) {
        $ranking = Invoke-LocalApi -Method "GET" -Path "/api/products/$productId/ranking"
        $rankedCount = if ($ranking.Payload) { @($ranking.Payload.prospects | Where-Object { $null -ne $_.rank }).Count } else { 0 }
        Add-Step "Deterministic ranking remains available during Ollama outage" `
            ($ranking.StatusCode -eq 200 -and $ranking.Payload.prospect_count -gt 0 -and $rankedCount -gt 0) `
            ([ordered]@{
                product_id = $productId
                http_status = $ranking.StatusCode
                prospect_count = if ($ranking.Payload) { $ranking.Payload.prospect_count } else { 0 }
                ranked_count = $rankedCount
                icp_status = if ($ranking.Payload) { $ranking.Payload.icp_status } else { "unavailable" }
            })
    } else {
        Add-Step "Deterministic ranking remains available during Ollama outage" $false ([ordered]@{ status = "RelayCue product unavailable" })
    }

    $queuedStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    Add-Step "Queue counts recorded while Ollama is down" `
        ($queuedStatus.StatusCode -eq 200) `
        ([ordered]@{
            http_status = $queuedStatus.StatusCode
            queue = (Get-QueueSummary $queuedStatus.Payload)
        })

    if ($ollamaDown -and $queuedPayload -and $queuedPayload.status -eq "queued") {
        Write-LogLine "Start the local Ollama service/model now; leave Harvey running."
        [void](Read-Host "Press Enter when Ollama is available again")
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        $upStatus = $null
        do {
            $upStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
            if ($upStatus.StatusCode -eq 200 -and $upStatus.Payload.ollama.available -eq $true) { break }
            Start-Sleep -Seconds 2
        } while ((Get-Date) -lt $deadline)
        $ollamaUp = $upStatus -and $upStatus.StatusCode -eq 200 -and $upStatus.Payload.ollama.available -eq $true
        $upTrace = Update-Traceability $upStatus
        Add-Step "Ollama recovery detected" ([bool]$ollamaUp) ([ordered]@{
            http_status = if ($upStatus) { $upStatus.StatusCode } else { 0 }
            ollama_state = if ($upStatus.Payload) { $upStatus.Payload.ollama.state } else { "unavailable" }
            queue_before_retry = (Get-QueueSummary $upStatus.Payload)
            ollama_version = $script:Evidence.ollama_version
            model = $script:Evidence.model
        })

        if ($ollamaUp) {
            $wake = Invoke-LocalApi -Method "POST" -Path "/api/queue/retry"
            Add-Step "Queue worker wake request" `
                ($wake.StatusCode -eq 200 -and $wake.Payload.status -eq "scheduled") `
                ([ordered]@{
                    http_status = $wake.StatusCode
                    status = if ($wake.Payload) { $wake.Payload.status } else { "unavailable" }
                    queue = (Get-QueueSummary $wake.Payload)
                })
            $retried = Wait-ForSignalRun -ProspectId $prospectId -TimeoutSeconds $WaitSeconds
            $retryState = Get-PayloadStatus $retried
            $queueAfter = Invoke-LocalApi -Method "GET" -Path "/api/status"
            $finalTrace = Update-Traceability $queueAfter
            Add-Step "Queued workflow retry result" ($retryState -eq "succeeded") ([ordered]@{
                prospect_id = $prospectId
                run_id = if ($retried.Payload) { $retried.Payload.id } else { $null }
                status = $retryState
                signal_count = if ($retried.Payload) { @($retried.Payload.signals).Count } else { 0 }
                error_class = if ($retried.Payload) { Get-ErrorClass $retried.Payload.error } else { $retried.ErrorType }
                queue_after = (Get-QueueSummary $queueAfter.Payload)
            })
        } else {
            Add-Step "Queue worker wake request" $false ([ordered]@{ status = "Ollama did not recover before timeout" })
            Add-Step "Queued workflow retry result" $false ([ordered]@{ status = "not reached" })
        }
    } else {
        Add-Step "Ollama recovery detected" $false ([ordered]@{ status = "outage workflow was not queued" })
        Add-Step "Queue worker wake request" $false ([ordered]@{ status = "not reached" })
        Add-Step "Queued workflow retry result" $false ([ordered]@{ status = "not reached" })
    }

    $finalStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $finalTrace = Update-Traceability $finalStatus
    $traceable = $finalStatus.StatusCode -eq 200 -and
        $script:Evidence.commit_hash -and $script:Evidence.commit_hash -ne "unknown" -and
        $script:Evidence.ollama_version -and $script:Evidence.model -and
        $null -ne $script:Evidence.seed -and $null -ne $script:Evidence.temperature
    Add-Step "Final runtime traceability" ([bool]$traceable) ([ordered]@{
        http_status = $finalStatus.StatusCode
        commit_hash = $script:Evidence.commit_hash
        ollama_host = $script:Evidence.ollama_host
        ollama_version = $script:Evidence.ollama_version
        model = $script:Evidence.model
        seed = $script:Evidence.seed
        temperature = $script:Evidence.temperature
    })
} catch {
    Add-Step "Outage check execution" $false ([ordered]@{ error_type = $_.Exception.GetType().Name })
} finally {
    $script:Evidence["completed_at"] = (Get-Date).ToString("o")
    $script:Evidence["steps"] = @($script:Steps.ToArray())
    $script:Evidence["overall_result"] = if (@($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count -eq 0) { "PASS" } else { "FAIL" }
    $script:Evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $script:JsonPath -Encoding UTF8
    $failures = @($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count
    $summary = if ($failures -eq 0) {
        "[PASS] Ollama-down check completed with no failed steps. Log and JSON saved."
    } else {
        "[FAIL] Ollama-down check recorded $failures failed step(s). Log and JSON saved."
    }
    Write-LogLine $summary
    $script:ApiClient.Dispose()
    $script:ApiHandler.Dispose()
    if ($failures -gt 0) { exit 1 }
}
