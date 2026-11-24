[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$WaitSeconds = 300,
    [switch]$OllamaAlreadyStopped
)

$ErrorActionPreference = "Stop"
$baseUri = [Uri]$BaseUrl
if ($baseUri.Scheme -ne "http" -or $baseUri.Host -notin @("127.0.0.1", "::1")) {
    throw "BaseUrl must use the numeric loopback host 127.0.0.1 or ::1 over HTTP."
}
$BaseUrl = $BaseUrl.TrimEnd("/")

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.UseProxy = $false
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds([Math]::Max(180, $WaitSeconds + 30))
$script:Steps = [System.Collections.Generic.List[object]]::new()
$script:Evidence = [ordered]@{
    created_at = (Get-Date).ToString("o")
    base_host = $baseUri.Host
    steps = @()
}

function Invoke-LocalApi {
    param([string]$Method, [string]$Path)
    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path"
    )
    $response = $null
    try {
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $payload = $null
        if ($content) {
            try { $payload = ConvertFrom-Json -InputObject $content } catch { $payload = $null }
        }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Payload = $payload; ErrorType = $null }
    } catch {
        return [pscustomobject]@{ StatusCode = 0; Payload = $null; ErrorType = $_.Exception.GetType().Name }
    } finally {
        $request.Dispose()
        if ($response) { $response.Dispose() }
    }
}

function Get-PayloadStatus {
    param($Response)
    if ($null -ne $Response.Payload -and $Response.Payload.PSObject.Properties.Name -contains "status") {
        return [string]$Response.Payload.status
    }
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

function Add-Step {
    param([string]$Name, [bool]$Passed, [System.Collections.IDictionary]$Details)
    $result = if ($Passed) { "PASS" } else { "FAIL" }
    $entry = [ordered]@{ step = $Name; result = $result }
    foreach ($key in $Details.Keys) { $entry[$key] = $Details[$key] }
    [void]$script:Steps.Add([pscustomobject]$entry)
    Write-Host "[$result] $Name"
}

function Get-QueueSummary {
    param($Payload)
    $queue = $Payload.queue
    return [ordered]@{
        queued = [int]($queue.queued)
        running = [int]($queue.running)
        done = [int]($queue.done)
        failed = [int]($queue.failed)
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

try {
    if (-not $OllamaAlreadyStopped) {
        Write-Host "Stop the local Ollama service/model now; leave the Harvey API running."
        [void](Read-Host "Press Enter when Ollama is stopped")
    }

    $downStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $ollamaDown = $downStatus.StatusCode -eq 200 -and $downStatus.Payload.ollama.available -eq $false
    Add-Step "Ollama unavailable is visible in API status" ([bool]$ollamaDown) ([ordered]@{
        http_status = $downStatus.StatusCode
        ollama_state = $downStatus.Payload.ollama.state
        commit = $downStatus.Payload.git_commit
        model = $downStatus.Payload.ollama.model
        prompt_hashes = $downStatus.Payload.prompt_hashes
        queue_before = if ($downStatus.Payload) { Get-QueueSummary $downStatus.Payload } else { $null }
    })

    $products = Invoke-LocalApi -Method "GET" -Path "/api/products"
    $relayCue = @($products.Payload | Where-Object { $_.name -eq "RelayCue" } | Select-Object -First 1)
    $prospectId = $null
    $productId = $null
    if ($products.StatusCode -eq 200 -and $relayCue.Count -gt 0) {
        $productId = [int]$relayCue[0].id
        $prospects = Invoke-LocalApi -Method "GET" -Path "/api/products/$productId/prospects"
        $candidate = @($prospects.Payload | Where-Object { $_.page_text_path } | Select-Object -First 1)
        if ($candidate.Count -gt 0) { $prospectId = [int]$candidate[0].id }
    }

    $queuedPayload = $null
    if ($null -ne $prospectId -and $ollamaDown) {
        $queuedResponse = Invoke-LocalApi -Method "POST" -Path "/api/prospects/$prospectId/signals"
        $queuedPayload = $queuedResponse.Payload
        $queuedState = Get-PayloadStatus $queuedResponse
        $isQueued = $queuedResponse.StatusCode -eq 202 -and $queuedState -eq "queued"
        Add-Step "AI workflow persists queued status and structured error" ([bool]$isQueued) ([ordered]@{
            product_id = $productId
            prospect_id = $prospectId
            http_status = $queuedResponse.StatusCode
            status = $queuedState
            queue_task_id = $queuedPayload.queue_task_id
            run_id = $queuedPayload.id
            model = $queuedPayload.model_name
            seed = $queuedPayload.seed
            temperature = $queuedPayload.temperature
            error_class = Get-ErrorClass $queuedPayload.error
        })
    } else {
        Add-Step "AI workflow persists queued status and structured error" $false ([ordered]@{
            status = if ($null -eq $prospectId) { "no RelayCue prospect with stored page" } else { "Ollama was not confirmed unavailable" }
        })
    }

    if ($null -ne $productId) {
        $ranking = Invoke-LocalApi -Method "GET" -Path "/api/products/$productId/ranking"
        $rankedCount = @($ranking.Payload.prospects | Where-Object { $null -ne $_.rank }).Count
        Add-Step "Deterministic ranking remains available during Ollama outage" (
            $ranking.StatusCode -eq 200 -and $ranking.Payload.prospect_count -gt 0 -and $rankedCount -gt 0
        ) ([ordered]@{
            product_id = $productId
            http_status = $ranking.StatusCode
            prospect_count = $ranking.Payload.prospect_count
            ranked_count = $rankedCount
            icp_status = $ranking.Payload.icp_status
        })
    } else {
        Add-Step "Deterministic ranking remains available during Ollama outage" $false ([ordered]@{ status = "RelayCue product unavailable" })
    }

    $queuedStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    Add-Step "Queue counts recorded while Ollama is down" ($queuedStatus.StatusCode -eq 200) ([ordered]@{
        http_status = $queuedStatus.StatusCode
        queue = if ($queuedStatus.Payload) { Get-QueueSummary $queuedStatus.Payload } else { $null }
    })

    if ($ollamaDown -and $queuedPayload -and $queuedPayload.status -eq "queued") {
        Write-Host "Start the local Ollama service/model now; leave Harvey running."
        [void](Read-Host "Press Enter when Ollama is available again")
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        $upStatus = $null
        do {
            $upStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
            if ($upStatus.StatusCode -eq 200 -and $upStatus.Payload.ollama.available -eq $true) { break }
            Start-Sleep -Seconds 2
        } while ((Get-Date) -lt $deadline)
        $ollamaUp = $upStatus -and $upStatus.StatusCode -eq 200 -and $upStatus.Payload.ollama.available -eq $true
        Add-Step "Ollama recovery detected" ([bool]$ollamaUp) ([ordered]@{
            http_status = $upStatus.StatusCode
            ollama_state = $upStatus.Payload.ollama.state
            queue_before_retry = if ($upStatus.Payload) { Get-QueueSummary $upStatus.Payload } else { $null }
        })

        if ($ollamaUp) {
            $wake = Invoke-LocalApi -Method "POST" -Path "/api/queue/retry"
            Add-Step "Queue worker wake request" (
                $wake.StatusCode -eq 200 -and $wake.Payload.status -eq "scheduled"
            ) ([ordered]@{
                http_status = $wake.StatusCode
                status = $wake.Payload.status
                queue = if ($wake.Payload) { Get-QueueSummary $wake.Payload } else { $null }
            })
            $retried = Wait-ForSignalRun -ProspectId $prospectId -TimeoutSeconds $WaitSeconds
            $retryState = Get-PayloadStatus $retried
            $queueAfter = Invoke-LocalApi -Method "GET" -Path "/api/status"
            Add-Step "Queued workflow retry result" ($retryState -eq "succeeded") ([ordered]@{
                prospect_id = $prospectId
                run_id = $retried.Payload.id
                status = $retryState
                signal_count = @($retried.Payload.signals).Count
                error_class = Get-ErrorClass $retried.Payload.error
                queue_after = if ($queueAfter.Payload) { Get-QueueSummary $queueAfter.Payload } else { $null }
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
} catch {
    Add-Step "Outage check execution" $false ([ordered]@{ error_type = $_.Exception.GetType().Name })
} finally {
    $script:Evidence["steps"] = @($script:Steps.ToArray())
    $root = Split-Path -Parent $PSScriptRoot
    $outputDirectory = Join-Path $root "test_evidence\ollama_outage"
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $outputPath = Join-Path $outputDirectory ("ollama-down-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $script:Evidence | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outputPath -Encoding UTF8
    $client.Dispose()
    $handler.Dispose()
    $failures = @($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count
    if ($failures -eq 0) {
        Write-Host "[PASS] Ollama-down summary: all recorded steps passed. Evidence file written."
    } else {
        Write-Host "[FAIL] Ollama-down summary: $failures step(s) failed. Evidence file written."
        exit 1
    }
}
