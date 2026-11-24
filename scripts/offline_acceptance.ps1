[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$ProfileProductId = 0,
    [int]$IcpProductId = 0,
    [string]$ReplyId = "R001",
    [ValidateRange(1, 3600)][int]$WaitSeconds = 300,
    [ValidateRange(1, 7200)][int]$PipelineWaitSeconds = 900
)

$ErrorActionPreference = "Stop"
$script:BaseUri = [Uri]$BaseUrl
if ($script:BaseUri.Scheme -ne "http" -or $script:BaseUri.Host -notin @("127.0.0.1", "::1")) {
    throw "BaseUrl must use the numeric loopback host 127.0.0.1 or ::1 over HTTP."
}
$script:BaseUrl = $BaseUrl.TrimEnd("/")
$script:WaitSeconds = $WaitSeconds
$script:ReplyId = $ReplyId
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:ProspectPageRoot = [IO.Path]::GetFullPath((Join-Path (Join-Path $script:RepoRoot "data") "prospect_pages"))
$script:RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:OutputDirectory = Join-Path (Join-Path $script:RepoRoot "test_evidence") "offline"
New-Item -ItemType Directory -Path $script:OutputDirectory -Force | Out-Null
$script:LogPath = Join-Path $script:OutputDirectory "acceptance-$($script:RunStamp).log"
$script:JsonPath = Join-Path $script:OutputDirectory "acceptance-$($script:RunStamp).json"
[IO.File]::WriteAllText(
    $script:LogPath,
    "Harvey offline acceptance started $((Get-Date).ToString('o'))$([Environment]::NewLine)",
    [Text.Encoding]::UTF8
)

$script:ApiHandler = [System.Net.Http.HttpClientHandler]::new()
$script:ApiHandler.UseProxy = $false
$script:ApiHandler.AllowAutoRedirect = $false
$script:ApiClient = [System.Net.Http.HttpClient]::new($script:ApiHandler)
$script:ApiClient.Timeout = [TimeSpan]::FromSeconds([Math]::Max(180, $WaitSeconds + 30))
$script:Steps = [System.Collections.Generic.List[object]]::new()
$script:OllamaBaseUrl = "http://127.0.0.1:11434"
$script:Evidence = [ordered]@{
    created_at = (Get-Date).ToString("o")
    log_file = $script:LogPath
    json_file = $script:JsonPath
    commit_hash = $null
    ollama_url = $null
    ollama_host = $null
    ollama_version = $null
    model = $null
    seed = $null
    temperature = $null
    public_host_probe = $null
    api_process_nonloopback_connection_attempted = $null
    workflow_order = @(
        "1. Business profile",
        "2. Product ICP",
        "3. Research from saved prospect data",
        "4. Signals",
        "5. Problem statement",
        "6. Scoring/ranking",
        "7. Unsent email draft",
        "8. Reply classification",
        "9. Full product pipeline (extra)"
    )
    steps = @()
}
$script:ProfileProductId = 0
$script:IcpProductId = 0
$script:ProspectId = 0
$script:SavedProspect = $null

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

function Test-PublicInternet {
    # This is one short connectivity probe, not a model request or a complete
    # network-isolation proof. Any HTTP response means the public host was reached.
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(3)
    $response = $null
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $response = $client.GetAsync("https://example.com/").GetAwaiter().GetResult()
        return [pscustomobject]@{
            request_failed = $false
            http_status = [int]$response.StatusCode
            error_type = $null
            model_request = $false
        }
    } catch {
        return [pscustomobject]@{
            request_failed = $true
            http_status = $null
            error_type = $_.Exception.GetType().Name
            model_request = $false
        }
    } finally {
        if ($response) { $response.Dispose() }
        $client.Dispose()
        $handler.Dispose()
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

function Invoke-And-Wait {
    param(
        [string]$PostPath,
        [string]$GetPath,
        [int]$TimeoutSeconds = 300
    )
    $posted = Invoke-LocalApi -Method "POST" -Path $PostPath
    $final = $posted
    $state = Get-PayloadStatus $final
    if ($state -in @("queued", "running", "pending")) {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
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

function Get-SavedPageMetadata {
    param([string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw "The prospect has no saved page path."
    }
    $normalized = $RelativePath.Replace("\", "/")
    if (
        [IO.Path]::IsPathRooted($RelativePath) -or
        $normalized -match '^[A-Za-z]:' -or
        ($normalized.Split("/") -contains "..")
    ) {
        throw "Saved page path is not a safe repository-relative path."
    }
    $repositoryPrefix = "data/prospect_pages/"
    $pageRelativePath = $normalized
    if ($normalized.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $pageRelativePath = $normalized.Substring($repositoryPrefix.Length)
    }
    if ([string]::IsNullOrWhiteSpace($pageRelativePath)) {
        throw "The prospect saved-page path does not name a file."
    }
    $fullPath = [IO.Path]::GetFullPath((Join-Path $script:ProspectPageRoot $pageRelativePath))
    $rootPrefix = $script:ProspectPageRoot.TrimEnd(
        [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Saved page path resolves outside data/prospect_pages."
    }
    $text = [IO.File]::ReadAllText($fullPath, [Text.Encoding]::UTF8)
    return [pscustomobject]@{ FilePath = $fullPath; CharacterCount = $text.Length }
}

function Run-WorkflowStep {
    param([string]$Name, [scriptblock]$Action)
    try {
        $result = & $Action
        Add-Step -Name $Name -Passed ([bool]$result.Passed) -Details $result.Details
    } catch {
        Add-Step -Name $Name -Passed $false -Details ([ordered]@{
            error_type = $_.Exception.GetType().Name
        })
    }
}

function New-WorkflowResult {
    param([bool]$Passed, [System.Collections.IDictionary]$Details)
    return [pscustomobject]@{ Passed = $Passed; Details = $Details }
}

function Get-NonLoopbackConnectionSnapshot {
    try {
        $listener = Get-NetTCPConnection -LocalPort $script:BaseUri.Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if (-not $listener) {
            return [pscustomobject]@{ available = $true; listener_found = $false; nonloopback_count = $null }
        }
        $connections = @(
            Get-NetTCPConnection -OwningProcess $listener.OwningProcess -ErrorAction Stop |
                Where-Object { $_.State -in @("Established", "SynSent", "SynReceived") }
        )
        $nonLoopback = @(
            $connections | Where-Object {
                $_.RemoteAddress -notin @("127.0.0.1", "::1", "::ffff:127.0.0.1")
            }
        )
        return [pscustomobject]@{
            available = $true
            listener_found = $true
            server_process_id = $listener.OwningProcess
            observed_peer_count = $connections.Count
            nonloopback_count = $nonLoopback.Count
            nonloopback_connection_attempted = ($nonLoopback.Count -gt 0)
            snapshot_only = $true
        }
    } catch {
        return [pscustomobject]@{
            available = $false
            listener_found = $false
            nonloopback_count = $null
            error_type = $_.Exception.GetType().Name
            snapshot_only = $true
        }
    }
}

$script:InternetProbe = $null
try {
    # The required first acceptance step is deliberately a non-model public-host probe.
    $script:InternetProbe = Test-PublicInternet
    $script:Evidence["public_host_probe"] = $script:InternetProbe
    Add-Step -Name "Public internet probe (offline indicator)" `
        -Passed ([bool]$script:InternetProbe.request_failed) `
        -Details ([ordered]@{
            host = "example.com"
            request_failed = $script:InternetProbe.request_failed
            http_status = $script:InternetProbe.http_status
            error_type = $script:InternetProbe.error_type
            model_request = $false
        })
    if (-not $script:InternetProbe.request_failed) {
        Write-LogLine "[WARNING] The public host responded. This run is NOT an offline proof."
    } else {
        Write-LogLine "[INFO] The public-host probe failed; this single probe is not proof that every outbound route is blocked."
    }

    $statusResponse = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $status = $statusResponse.Payload
    $hardwareResponse = Invoke-LocalApi -Method "GET" -Path "/api/hardware"
    $hardware = $hardwareResponse.Payload
    $ollamaUrl = if ($status -and $status.ollama) { [string]$status.ollama.url } else { $null }
    $ollamaUri = $null
    if ($ollamaUrl) { try { $ollamaUri = [Uri]$ollamaUrl } catch { $ollamaUri = $null } }
    $script:Evidence["commit_hash"] = if ($status) { $status.git_commit } else { $null }
    $script:Evidence["ollama_url"] = $ollamaUrl
    $script:Evidence["ollama_host"] = if ($ollamaUri) { $ollamaUri.Host } else { $null }
    $script:Evidence["ollama_version"] = Get-OllamaVersion
    $script:Evidence["model"] = if ($status -and $status.ollama) { $status.ollama.model } else { $null }

    $statusPass = $statusResponse.StatusCode -eq 200 -and
        $hardwareResponse.StatusCode -eq 200 -and
        $status -and $status.ollama.available -eq $true
    Add-Step -Name "API, Ollama, and hardware preflight" -Passed ([bool]$statusPass) -Details ([ordered]@{
        status_http = $statusResponse.StatusCode
        hardware_http = $hardwareResponse.StatusCode
        ollama_state = if ($status -and $status.ollama) { $status.ollama.state } else { "unavailable" }
        ollama_host = $script:Evidence.ollama_host
        ollama_version = $script:Evidence.ollama_version
        model = $script:Evidence.model
        commit_hash = $script:Evidence.commit_hash
        ram_gb = if ($hardware) { $hardware.ram_gb } else { $null }
        cpu_count = if ($hardware) { $hardware.cpu_count } else { $null }
        gpu_status = if ($hardware) { $hardware.gpu_status } else { $null }
        recommended_model = if ($hardware) { $hardware.recommended_model } else { $null }
    })

    $productsResponse = Invoke-LocalApi -Method "GET" -Path "/api/products"
    $productRows = if ($productsResponse.Payload) { @($productsResponse.Payload) } else { @() }
    $relayCue = @($productRows | Where-Object { $_.name -eq "RelayCue" } | Select-Object -First 1)
    if ($ProfileProductId -le 0) {
        $ProfileProductId = if ($relayCue.Count -gt 0) { [int]$relayCue[0].id } elseif ($productRows.Count -gt 0) { [int]$productRows[0].id } else { 0 }
    }
    if ($IcpProductId -le 0) { $IcpProductId = $ProfileProductId }
    $script:ProfileProductId = $ProfileProductId
    $script:IcpProductId = $IcpProductId

    if ($ProfileProductId -gt 0) {
        $prospectsResponse = Invoke-LocalApi -Method "GET" -Path "/api/products/$ProfileProductId/prospects"
        $prospectRows = if ($prospectsResponse.Payload) { @($prospectsResponse.Payload) } else { @() }
        $candidate = @($prospectRows | Where-Object { $_.page_text_path } | Select-Object -First 1)
        if ($candidate.Count -gt 0) {
            $script:ProspectId = [int]$candidate[0].id
            $script:SavedProspect = $candidate[0]
        }
    }
    Add-Step -Name "Resolve acceptance records" `
        -Passed ($productsResponse.StatusCode -eq 200 -and $ProfileProductId -gt 0 -and $IcpProductId -gt 0) `
        -Details ([ordered]@{
            products_http = $productsResponse.StatusCode
            profile_product_id = $ProfileProductId
            icp_product_id = $IcpProductId
            saved_page_prospect_id = if ($script:ProspectId -gt 0) { $script:ProspectId } else { $null }
            reply_id = $ReplyId
        })

    Run-WorkflowStep "1. Business profile" {
        if ($script:ProfileProductId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no product resolved" }))
        }
        $result = Invoke-And-Wait `
            -PostPath "/api/products/$($script:ProfileProductId)/profile" `
            -GetPath "/api/products/$($script:ProfileProductId)/profile" `
            -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $state -eq "succeeded") `
            ([ordered]@{
                product_id = $script:ProfileProductId
                http_status = $result.Post.StatusCode
                status = $state
                run_id = if ($result.Final.Payload) { $result.Final.Payload.id } else { $null }
                queue_task_id = if ($result.Final.Payload) { $result.Final.Payload.queue_task_id } else { $null }
                error_class = if ($result.Final.Payload) { Get-ErrorClass $result.Final.Payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "2. Product ICP" {
        if ($script:IcpProductId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no product resolved" }))
        }
        $result = Invoke-And-Wait `
            -PostPath "/api/products/$($script:IcpProductId)/icp" `
            -GetPath "/api/products/$($script:IcpProductId)/icp" `
            -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $state -eq "succeeded") `
            ([ordered]@{
                product_id = $script:IcpProductId
                http_status = $result.Post.StatusCode
                status = $state
                run_id = if ($result.Final.Payload) { $result.Final.Payload.id } else { $null }
                queue_task_id = if ($result.Final.Payload) { $result.Final.Payload.queue_task_id } else { $null }
                error_class = if ($result.Final.Payload) { Get-ErrorClass $result.Final.Payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "3. Research from saved prospect data" {
        if ($script:ProspectId -le 0 -or $null -eq $script:SavedProspect) {
            return (New-WorkflowResult $false ([ordered]@{
                status = "no prospect with stored page resolved"
                model_call = $false
            }))
        }
        $prospectResponse = Invoke-LocalApi -Method "GET" -Path "/api/prospects/$($script:ProspectId)"
        $relativePagePath = if ($prospectResponse.Payload) { [string]$prospectResponse.Payload.page_text_path } else { "" }
        $page = Get-SavedPageMetadata -RelativePath $relativePagePath
        New-WorkflowResult `
            ($prospectResponse.StatusCode -eq 200 -and $page.CharacterCount -gt 0) `
            ([ordered]@{
                prospect_id = $script:ProspectId
                file_path = $page.FilePath
                character_count = $page.CharacterCount
                model_call = $false
            })
    }

    Run-WorkflowStep "4. Signals" {
        if ($script:ProspectId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no prospect with stored page resolved" }))
        }
        $path = "/api/prospects/$($script:ProspectId)/signals"
        $result = Invoke-And-Wait -PostPath $path -GetPath $path -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        $payload = $result.Final.Payload
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $state -eq "succeeded") `
            ([ordered]@{
                prospect_id = $script:ProspectId
                http_status = $result.Post.StatusCode
                status = $state
                run_id = if ($payload) { $payload.id } else { $null }
                signal_count = if ($payload) { @($payload.signals).Count } else { 0 }
                error_class = if ($payload) { Get-ErrorClass $payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "5. Problem statement" {
        if ($script:ProspectId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no prospect with stored page resolved" }))
        }
        $path = "/api/products/$($script:ProfileProductId)/prospects/$($script:ProspectId)/problem-statement"
        $result = Invoke-And-Wait -PostPath $path -GetPath $path -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        $payload = $result.Final.Payload
        $acceptedState = $state -in @("succeeded", "skipped")
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $acceptedState) `
            ([ordered]@{
                product_id = $script:ProfileProductId
                prospect_id = $script:ProspectId
                http_status = $result.Post.StatusCode
                status = $state
                evidence_count = if ($payload) { @($payload.evidence).Count } else { 0 }
                skipped_for_missing_evidence = ($state -eq "skipped")
                error_class = if ($payload) { Get-ErrorClass $payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "6. Scoring/ranking" {
        if ($script:ProfileProductId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no product resolved" }))
        }
        $result = Invoke-LocalApi -Method "GET" -Path "/api/products/$($script:ProfileProductId)/ranking"
        $payload = $result.Payload
        $ranked = if ($payload) { @($payload.prospects | Where-Object { $null -ne $_.rank }).Count } else { 0 }
        New-WorkflowResult `
            ($result.StatusCode -eq 200 -and $payload.prospect_count -gt 0 -and $ranked -gt 0) `
            ([ordered]@{
                product_id = $script:ProfileProductId
                http_status = $result.StatusCode
                prospect_count = if ($payload) { $payload.prospect_count } else { 0 }
                ranked_count = $ranked
                icp_status = if ($payload) { $payload.icp_status } else { "unavailable" }
            })
    }

    Run-WorkflowStep "7. Unsent email draft" {
        if ($script:ProspectId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no prospect with stored page resolved" }))
        }
        $path = "/api/products/$($script:ProfileProductId)/prospects/$($script:ProspectId)/draft"
        $result = Invoke-And-Wait -PostPath $path -GetPath $path -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        $payload = $result.Final.Payload
        $sent = if ($payload -and $null -ne $payload.sent) { [bool]$payload.sent } else { $null }
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $state -in @("succeeded", "skipped") -and $sent -eq $false) `
            ([ordered]@{
                product_id = $script:ProfileProductId
                prospect_id = $script:ProspectId
                http_status = $result.Post.StatusCode
                status = $state
                sent = $sent
                run_id = if ($payload) { $payload.id } else { $null }
                error_class = if ($payload) { Get-ErrorClass $payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "8. Reply classification" {
        $path = "/api/replies/$($script:ReplyId)/classification"
        $result = Invoke-And-Wait -PostPath $path -GetPath $path -TimeoutSeconds $script:WaitSeconds
        $state = Get-PayloadStatus $result.Final
        $payload = $result.Final.Payload
        New-WorkflowResult `
            ($result.Post.StatusCode -in @(200, 202) -and $state -eq "succeeded") `
            ([ordered]@{
                reply_id = $script:ReplyId
                http_status = $result.Post.StatusCode
                status = $state
                error_class = if ($payload) { Get-ErrorClass $payload.error } else { $result.Final.ErrorType }
            })
    }

    Run-WorkflowStep "9. Full product pipeline (extra)" {
        if ($script:ProfileProductId -le 0) {
            return (New-WorkflowResult $false ([ordered]@{ status = "no product resolved" }))
        }
        $result = Invoke-Pipeline-And-Wait -ProductId $script:ProfileProductId -TimeoutSeconds $PipelineWaitSeconds
        $state = Get-PayloadStatus $result.Final
        $payload = $result.Final.Payload
        $counts = if ($payload) { $payload.step_counts } else { $null }
        $total = 0
        if ($counts) {
            foreach ($name in @("queued", "running", "done", "failed", "skipped")) {
                $total += [int]$counts.$name
            }
        }
        New-WorkflowResult `
            ($result.Post.StatusCode -eq 202 -and $result.Final.StatusCode -eq 200 -and $state -eq "done" -and $total -gt 0) `
            ([ordered]@{
                product_id = $script:ProfileProductId
                http_status = $result.Post.StatusCode
                run_id = if ($payload) { $payload.id } else { $null }
                status = $state
                step_count = $total
                step_counts = $counts
                error_class = if ($payload) { Get-ErrorClass $payload.error } else { $result.Final.ErrorType }
            })
    }

    $finalStatus = Invoke-LocalApi -Method "GET" -Path "/api/status"
    $lastInference = if ($finalStatus.Payload) { $finalStatus.Payload.ollama.last_inference } else { $null }
    $version = Get-OllamaVersion
    $script:Evidence["commit_hash"] = if ($finalStatus.Payload) { $finalStatus.Payload.git_commit } else { $script:Evidence.commit_hash }
    $script:Evidence["ollama_version"] = $version
    if ($lastInference) {
        $script:Evidence["model"] = $lastInference.model
        $script:Evidence["seed"] = $lastInference.seed
        $script:Evidence["temperature"] = $lastInference.temperature
    }
    $runtimeReady = $finalStatus.StatusCode -eq 200 -and
        $script:Evidence.commit_hash -and $script:Evidence.commit_hash -ne "unknown" -and
        $script:Evidence.ollama_host -and $script:Evidence.ollama_version -and
        $script:Evidence.model -and $null -ne $script:Evidence.seed -and $null -ne $script:Evidence.temperature
    Add-Step -Name "Runtime traceability" -Passed ([bool]$runtimeReady) -Details ([ordered]@{
        http_status = $finalStatus.StatusCode
        commit_hash = $script:Evidence.commit_hash
        ollama_host = $script:Evidence.ollama_host
        ollama_version = $script:Evidence.ollama_version
        model = $script:Evidence.model
        seed = $script:Evidence.seed
        temperature = $script:Evidence.temperature
    })

    $connectionSnapshot = Get-NonLoopbackConnectionSnapshot
    $script:Evidence["api_process_nonloopback_connection_attempted"] = $connectionSnapshot.nonloopback_connection_attempted
    Add-Step -Name "API process non-loopback connection snapshot" `
        -Passed ([bool]($connectionSnapshot.available -and $connectionSnapshot.listener_found -and $connectionSnapshot.nonloopback_count -eq 0)) `
        -Details ([ordered]@{
            snapshot_only = $connectionSnapshot.snapshot_only
            listener_found = $connectionSnapshot.listener_found
            observed_peer_count = $connectionSnapshot.observed_peer_count
            nonloopback_count = $connectionSnapshot.nonloopback_count
            nonloopback_connection_attempted = $connectionSnapshot.nonloopback_connection_attempted
            error_type = $connectionSnapshot.error_type
        })
} catch {
    Add-Step -Name "Acceptance execution" -Passed $false -Details ([ordered]@{
        error_type = $_.Exception.GetType().Name
    })
} finally {
    $recordedWorkflowNames = @($script:Steps | ForEach-Object { $_.step })
    $expectedSteps = @(
        "1. Business profile",
        "2. Product ICP",
        "3. Research from saved prospect data",
        "4. Signals",
        "5. Problem statement",
        "6. Scoring/ranking",
        "7. Unsent email draft",
        "8. Reply classification",
        "9. Full product pipeline (extra)"
    )
    foreach ($name in $expectedSteps) {
        if ($recordedWorkflowNames -notcontains $name) {
            Add-Step -Name $name -Passed $false -Details ([ordered]@{ status = "not reached" })
            $recordedWorkflowNames += $name
        }
    }
    $script:Evidence["completed_at"] = (Get-Date).ToString("o")
    $script:Evidence["steps"] = @($script:Steps.ToArray())
    $script:Evidence["overall_result"] = if (@($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count -eq 0) { "PASS" } else { "FAIL" }
    $script:Evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $script:JsonPath -Encoding UTF8
    $failures = @($script:Steps | Where-Object { $_.result -eq "FAIL" }).Count
    $summary = if ($failures -eq 0) {
        "[PASS] Offline acceptance completed with no failed steps. Log and JSON saved."
    } else {
        "[FAIL] Offline acceptance recorded $failures failed step(s). Log and JSON saved."
    }
    Write-LogLine $summary
    $script:ApiClient.Dispose()
    $script:ApiHandler.Dispose()
    if ($failures -gt 0) { exit 1 }
}
