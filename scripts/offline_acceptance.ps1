[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$ProfileProductId = 0,
    [int]$FirstIcpProductId = 0,
    [int]$SecondIcpProductId = 0,
    [int]$SignalLimit = 3,
    [string]$ReplyId = "R001",
    [int]$WaitSeconds = 300,
    [int]$PipelineWaitSeconds = 900
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
$script:SignalProspectId = $null
$script:SignalProspectIds = @()
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

function Invoke-And-Wait {
    param([string]$PostPath, [string]$GetPath)
    $posted = Invoke-LocalApi -Method "POST" -Path $PostPath
    $final = $posted
    $state = Get-PayloadStatus $final
    if ($state -in @("queued", "running", "pending")) {
        $deadline = (Get-Date).AddSeconds($WaitSeconds)
        do {
            Start-Sleep -Seconds 2
            $final = Invoke-LocalApi -Method "GET" -Path $GetPath
            $state = Get-PayloadStatus $final
        } while ($state -in @("queued", "running", "pending") -and (Get-Date) -lt $deadline)
    }
    return [pscustomobject]@{ Post = $posted; Final = $final }
}

function Invoke-Pipeline-And-Wait {
    param([int]$ProductId, [int]$TimeoutSeconds)
    $posted = Invoke-LocalApi -Method "POST" -Path "/api/products/$ProductId/pipeline"
    $final = $posted
    $runId = if ($posted.Payload) { [int]$posted.Payload.id } else { 0 }
    $state = Get-PayloadStatus $final
    if ($runId -gt 0 -and $state -in @("queued", "running", "pending")) {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        do {
            Start-Sleep -Seconds 2
            $final = Invoke-LocalApi -Method "GET" -Path "/api/pipeline-runs/$runId"
            $state = Get-PayloadStatus $final
        } while ($state -in @("queued", "running", "pending") -and (Get-Date) -lt $deadline)
    }
    return [pscustomobject]@{ Post = $posted; Final = $final }
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

try {
    $statusResponse = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $status = $statusResponse.Payload
    $hardwareResponse = Invoke-LocalApi -Method "GET" -Path "/api/hardware"
    $hw = $hardwareResponse.Payload
    $signalHashValid = [bool]($status.prompt_hashes.signals -match '^[0-9a-fA-F]{64}$')
    $replyHashValid = [bool]($status.prompt_hashes.replies -match '^[0-9a-fA-F]{64}$')
    $step1Pass = $statusResponse.StatusCode -eq 200 -and $hardwareResponse.StatusCode -eq 200 -and
        $status.git_commit -and $status.git_commit -ne "unknown" -and
        $signalHashValid -and $replyHashValid -and
        $status.ollama.available -eq $true -and $hw.recommended_model
    Add-Step "Status and hardware" ([bool]$step1Pass) ([ordered]@{
        status_http = $statusResponse.StatusCode
        hardware_http = $hardwareResponse.StatusCode
        commit = $status.git_commit
        model = $status.ollama.model
        ollama_state = $status.ollama.state
        ram_gb = $hw.ram_gb
        cpu_count = $hw.cpu_count
        gpu_status = $hw.gpu_status
        recommended_model = $hw.recommended_model
        prompt_hashes = $status.prompt_hashes
    })
    $dashboardResponse = Invoke-LocalApi -Method "GET" -Path "/"
    Add-Step "Dashboard route at slash" ($dashboardResponse.StatusCode -eq 200) ([ordered]@{
        http_status = $dashboardResponse.StatusCode
    })
    if ($statusResponse.StatusCode -ne 200 -or $status.ollama.available -ne $true) {
        Add-Step "Ollama available precondition" $false ([ordered]@{
            status_http = $statusResponse.StatusCode
            ollama_state = $status.ollama.state
        })
        throw [System.InvalidOperationException]::new("local Ollama must be available for offline acceptance")
    }

    $productsResponse = Invoke-LocalApi -Method "GET" -Path "/api/products"
    $productRows = @($productsResponse.Payload)
    $relayCue = @($productRows | Where-Object { $_.name -eq "RelayCue" } | Select-Object -First 1)
    $fieldNest = @($productRows | Where-Object { $_.name -eq "FieldNest" } | Select-Object -First 1)
    $orderedIds = @($productRows | ForEach-Object { [int]$_.id })
    if ($ProfileProductId -le 0) {
        $ProfileProductId = if ($relayCue.Count -gt 0) { [int]$relayCue[0].id } elseif ($orderedIds.Count -gt 0) { $orderedIds[0] } else { 0 }
    }
    if ($FirstIcpProductId -le 0) {
        $FirstIcpProductId = if ($relayCue.Count -gt 0) { [int]$relayCue[0].id } elseif ($orderedIds.Count -gt 0) { $orderedIds[0] } else { 0 }
    }
    if ($SecondIcpProductId -le 0) {
        $SecondIcpProductId = if ($fieldNest.Count -gt 0) { [int]$fieldNest[0].id } elseif ($orderedIds.Count -gt 1) { $orderedIds[1] } else { 0 }
    }
    $productsResolved = $productsResponse.StatusCode -eq 200 -and $ProfileProductId -gt 0 -and
        $FirstIcpProductId -gt 0 -and $SecondIcpProductId -gt 0 -and
        $FirstIcpProductId -ne $SecondIcpProductId
    Add-Step "Resolve demo product IDs" ([bool]$productsResolved) ([ordered]@{
        http_status = $productsResponse.StatusCode
        product_count = $productRows.Count
        profile_product_id = $ProfileProductId
        first_icp_product_id = $FirstIcpProductId
        second_icp_product_id = $SecondIcpProductId
        relaycue_id = if ($relayCue.Count -gt 0) { [int]$relayCue[0].id } else { $null }
        fieldnest_id = if ($fieldNest.Count -gt 0) { [int]$fieldNest[0].id } else { $null }
    })

    $profileResult = Invoke-And-Wait "/api/products/$ProfileProductId/profile" "/api/products/$ProfileProductId/profile"
    $profileState = Get-PayloadStatus $profileResult.Final
    Add-Step "Business profile product $ProfileProductId" (
        $profileResult.Post.StatusCode -in @(200, 202) -and $profileState -eq "succeeded"
    ) ([ordered]@{
        product_id = $ProfileProductId
        http_status = $profileResult.Post.StatusCode
        status = $profileState
        run_id = $profileResult.Final.Payload.id
        queue_task_id = $profileResult.Final.Payload.queue_task_id
        error_class = Get-ErrorClass $profileResult.Final.Payload.error
    })

    foreach ($productId in @($FirstIcpProductId, $SecondIcpProductId)) {
        $icpResult = Invoke-And-Wait "/api/products/$productId/icp" "/api/products/$productId/icp"
        $icpState = Get-PayloadStatus $icpResult.Final
        Add-Step "ICP product $productId" (
            $icpResult.Post.StatusCode -in @(200, 202) -and $icpState -eq "succeeded"
        ) ([ordered]@{
            product_id = $productId
            http_status = $icpResult.Post.StatusCode
            status = $icpState
            run_id = $icpResult.Final.Payload.id
            queue_task_id = $icpResult.Final.Payload.queue_task_id
            error_class = Get-ErrorClass $icpResult.Final.Payload.error
        })
    }

    if ($productsResponse.StatusCode -eq 200 -and $relayCue.Count -gt 0) {
        $relayId = [int]$relayCue[0].id
        $prospectsResponse = Invoke-LocalApi -Method "GET" -Path "/api/products/$relayId/prospects"
        $candidates = @($prospectsResponse.Payload | Where-Object { $_.page_text_path } | Select-Object -First $SignalLimit)
        if ($prospectsResponse.StatusCode -eq 200 -and $candidates.Count -gt 0) {
            foreach ($prospect in $candidates) {
                $prospectId = [int]$prospect.id
                $signalResult = Invoke-And-Wait "/api/prospects/$prospectId/signals" "/api/prospects/$prospectId/signals"
                $signalState = Get-PayloadStatus $signalResult.Final
                $signalCount = @($signalResult.Final.Payload.signals).Count
                Add-Step "Signals for stored-page prospect $prospectId" (
                    $signalResult.Post.StatusCode -in @(200, 202) -and $signalState -eq "succeeded"
                ) ([ordered]@{
                    product_id = $relayId
                    prospect_id = $prospectId
                    http_status = $signalResult.Post.StatusCode
                    status = $signalState
                    signal_count = $signalCount
                    quote_retries = $signalResult.Final.Payload.quote_retries
                    run_id = $signalResult.Final.Payload.id
                    queue_task_id = $signalResult.Final.Payload.queue_task_id
                    error_class = Get-ErrorClass $signalResult.Final.Payload.error
                })
            }
            $script:SignalProspectIds = @($candidates | ForEach-Object { [int]$_.id })
            $script:SignalProspectId = [int]$candidates[0].id
        } else {
            Add-Step "Signals for stored-page prospects" $false ([ordered]@{ product_id = $relayId; prospect_count = 0; status = "no stored-page candidates" })
        }
    } else {
        Add-Step "Signals for stored-page prospects" $false ([ordered]@{ status = "RelayCue product not available" })
    }

    foreach ($productId in @($FirstIcpProductId, $SecondIcpProductId)) {
        $rank = Invoke-LocalApi -Method "GET" -Path "/api/products/$productId/ranking"
        $ranked = @($rank.Payload.prospects | Where-Object { $null -ne $_.rank }).Count
        Add-Step "Deterministic ranking product $productId" (
            $rank.StatusCode -eq 200 -and $rank.Payload.prospect_count -gt 0 -and $ranked -gt 0
        ) ([ordered]@{
            product_id = $productId
            http_status = $rank.StatusCode
            prospect_count = $rank.Payload.prospect_count
            ranked_count = $ranked
            icp_status = $rank.Payload.icp_status
        })
    }
    if ($script:SignalProspectId) {
        $draftPath = "/api/products/$relayId/prospects/$($script:SignalProspectId)/draft"
        $draftResult = Invoke-And-Wait $draftPath $draftPath
        $draftState = Get-PayloadStatus $draftResult.Final
        Add-Step "Unsent draft" (
            $draftResult.Post.StatusCode -in @(200, 202) -and $draftState -in @("succeeded", "skipped")
        ) ([ordered]@{
            product_id = $relayId
            prospect_id = $script:SignalProspectId
            http_status = $draftResult.Post.StatusCode
            status = $draftState
            sent = $draftResult.Final.Payload.sent
            run_id = $draftResult.Final.Payload.id
            queue_task_id = $draftResult.Final.Payload.queue_task_id
            error_class = Get-ErrorClass $draftResult.Final.Payload.error
        })
    } else {
        Add-Step "Unsent draft" $false ([ordered]@{ status = "no RelayCue prospect selected" })
    }

    $problemRows = [System.Collections.Generic.List[object]]::new()
    $problemTargets = @($script:SignalProspectIds | Select-Object -First 3)
    if ($relayId -and $problemTargets.Count -gt 0) {
        foreach ($prospectId in $problemTargets) {
            $problemPath = "/api/products/$relayId/prospects/$prospectId/problem-statement"
            $problemResult = Invoke-And-Wait $problemPath $problemPath
            $problemRows.Add([pscustomobject]@{
                prospect_id = [int]$prospectId
                status = Get-PayloadStatus $problemResult.Final
                evidence_count = @($problemResult.Final.Payload.evidence).Count
                http_ok = $problemResult.Post.StatusCode -in @(200, 202)
            })
        }
        $problemIds = @($problemRows | ForEach-Object { $_.prospect_id })
        $problemStatuses = @($problemRows | ForEach-Object { $_.status })
        $problemEvidenceCount = [int](($problemRows | Measure-Object -Property evidence_count -Sum).Sum)
        $problemPassed = $problemRows.Count -gt 0 -and
            @($problemRows | Where-Object { -not $_.http_ok -or $_.status -notin @("succeeded", "skipped") }).Count -eq 0
        Add-Step "Problem statements (IDs, statuses, counts only)" ([bool]$problemPassed) ([ordered]@{
            prospect_ids = $problemIds
            statuses = $problemStatuses
            requested_count = $problemRows.Count
            succeeded_count = @($problemRows | Where-Object { $_.status -eq "succeeded" }).Count
            skipped_count = @($problemRows | Where-Object { $_.status -eq "skipped" }).Count
            evidence_span_count = $problemEvidenceCount
        })
    } else {
        Add-Step "Problem statements (IDs, statuses, counts only)" $false ([ordered]@{
            prospect_ids = @()
            statuses = @("not_run")
            requested_count = 0
            succeeded_count = 0
            skipped_count = 0
            evidence_span_count = 0
        })
    }

    $replyResult = Invoke-And-Wait "/api/replies/$ReplyId/classification" "/api/replies/$ReplyId/classification"
    $replyState = Get-PayloadStatus $replyResult.Final
    Add-Step "Reply classification $ReplyId" (
        $replyResult.Post.StatusCode -in @(200, 202) -and $replyState -eq "succeeded"
    ) ([ordered]@{
        reply_id = $ReplyId
        http_status = $replyResult.Post.StatusCode
        status = $replyState
        error_class = Get-ErrorClass $replyResult.Final.Payload.error
    })

    if ($ProfileProductId -gt 0) {
        $pipelineResult = Invoke-Pipeline-And-Wait `
            -ProductId $ProfileProductId -TimeoutSeconds $PipelineWaitSeconds
        $pipelineState = Get-PayloadStatus $pipelineResult.Final
        $pipelineStepCounts = $pipelineResult.Final.Payload.step_counts
        $pipelineStepCount = 0
        if ($pipelineStepCounts) {
            foreach ($countName in @("queued", "running", "done", "failed", "skipped")) {
                $pipelineStepCount += [int]$pipelineStepCounts.$countName
            }
        }
        $pipelinePass = $pipelineResult.Post.StatusCode -eq 202 -and
            $pipelineResult.Final.StatusCode -eq 200 -and
            $pipelineState -eq "done" -and $pipelineStepCount -gt 0
        Add-Step "Full product pipeline" ([bool]$pipelinePass) ([ordered]@{
            product_id = $ProfileProductId
            http_status = $pipelineResult.Post.StatusCode
            run_id = $pipelineResult.Final.Payload.id
            queue_task_id = $pipelineResult.Final.Payload.queue_task_id
            status = $pipelineState
            step_count = $pipelineStepCount
            step_counts = $pipelineStepCounts
            error_class = Get-ErrorClass $pipelineResult.Final.Payload.error
        })
    } else {
        Add-Step "Full product pipeline" $false ([ordered]@{ status = "no pipeline product resolved" })
    }

    $finalStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $lastInference = $finalStatus.Payload.ollama.last_inference
    $traceabilityReady = $finalStatus.StatusCode -eq 200 -and $lastInference -and
        $lastInference.model -and $null -ne $lastInference.seed -and
        $finalStatus.Payload.prompt_hashes.signals -match '^[0-9a-fA-F]{64}$' -and
        $finalStatus.Payload.prompt_hashes.replies -match '^[0-9a-fA-F]{64}$'
    Add-Step "Final model, seed, and prompt-hash traceability" ([bool]$traceabilityReady) ([ordered]@{
        http_status = $finalStatus.StatusCode
        commit = $finalStatus.Payload.git_commit
        model = $lastInference.model
        seed = $lastInference.seed
        temperature = $lastInference.temperature
        repeat_penalty = $lastInference.repeat_penalty
        prompt_hashes = $finalStatus.Payload.prompt_hashes
    })

    try {
        $listener = Get-NetTCPConnection -LocalPort $baseUri.Port -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) {
            $connections = @(Get-NetTCPConnection -OwningProcess $listener.OwningProcess -State Established -ErrorAction Stop)
            $nonLocal = @($connections | Where-Object { $_.RemoteAddress -notin @("127.0.0.1", "::1", "::ffff:127.0.0.1") })
            Add-Step "Established API-process peers are loopback-only" ($nonLocal.Count -eq 0) ([ordered]@{
                server_process_id = $listener.OwningProcess
                established_peer_count = $connections.Count
                nonlocal_peer_count = $nonLocal.Count
            })
        } else {
            Add-Step "Established API-process peers are loopback-only" $false ([ordered]@{ status = "API listener not found" })
        }
    } catch {
        Add-Step "Established API-process peers are loopback-only" $false ([ordered]@{ status = "Get-NetTCPConnection unavailable" })
    }

    $ollamaUrl = $null
    $ollamaHost = $null
    if ($status.ollama.url) {
        try { $ollamaUrl = [Uri]$status.ollama.url; $ollamaHost = $ollamaUrl.Host } catch { $ollamaHost = "invalid" }
    }
    $localOllama = $ollamaUrl -and $ollamaUrl.Scheme -eq "http" -and
        $ollamaHost -in @("127.0.0.1", "localhost", "::1")
    Add-Step "Model API endpoint is loopback-only" ([bool]$localOllama) ([ordered]@{
        ollama_host = $ollamaHost
        ollama_port = if ($ollamaUrl) { $ollamaUrl.Port } else { $null }
        ollama_state = $status.ollama.state
    })
} catch {
    Add-Step "Acceptance execution" $false ([ordered]@{ error_type = $_.Exception.GetType().Name })
} finally {
    $script:Evidence["steps"] = @($script:Steps.ToArray())
    $root = Split-Path -Parent $PSScriptRoot
    $outputDirectory = Join-Path $root "test_evidence\offline"
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $outputPath = Join-Path $outputDirectory ("acceptance-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $script:Evidence | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outputPath -Encoding UTF8
    $client.Dispose()
    $handler.Dispose()
    $failures = @($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count
    if ($failures -eq 0) {
        Write-Host "[PASS] Offline acceptance summary: all recorded steps passed. Evidence file written."
    } else {
        Write-Host "[FAIL] Offline acceptance summary: $failures step(s) failed. Evidence file written."
        exit 1
    }
}
