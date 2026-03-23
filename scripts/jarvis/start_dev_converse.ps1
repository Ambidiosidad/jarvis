param(
    [string]$SessionId = "jorge",
    [switch]$UseVision,
    [switch]$NoBuild,
    [switch]$SkipModelPull,
    [switch]$NoAutoUpdate,
    [string]$ComposeFile = "docker-compose.dev.yml"
)

$ErrorActionPreference = "Stop"

function Wait-Health {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$Retries = 60,
        [int]$SleepSeconds = 2
    )

    for ($i = 1; $i -le $Retries; $i++) {
        try {
            Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
            Write-Host "[OK] $Label" -ForegroundColor Green
            return
        }
        catch {
            Start-Sleep -Seconds $SleepSeconds
        }
    }

    throw "Timed out waiting for $Label at $Url"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$extensionsDir = Join-Path $repoRoot "extensions"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Install Docker Desktop first."
}

try {
    if (-not $NoAutoUpdate) {
        if (Get-Command git -ErrorAction SilentlyContinue) {
            Write-Host "[0/4] Syncing repository..." -ForegroundColor Cyan
            $dirty = (& git -C "$repoRoot" status --porcelain 2>$null)
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[WARN] Could not check git status. Continuing with local code." -ForegroundColor Yellow
            }
            elseif (-not [string]::IsNullOrWhiteSpace(($dirty -join ""))) {
                Write-Host "[WARN] Local changes detected. Auto-update skipped to avoid conflicts." -ForegroundColor Yellow
            }
            else {
                & git -C "$repoRoot" pull --rebase origin main | Out-Host
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "[OK] Repository updated from origin/main" -ForegroundColor Green
                }
                else {
                    Write-Host "[WARN] Auto-update failed. Continuing with local copy." -ForegroundColor Yellow
                }
            }
        }
        else {
            Write-Host "[WARN] git not found. Auto-update skipped." -ForegroundColor Yellow
        }
    }

    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not reachable. Start Docker Desktop and retry."
    }

    Push-Location $extensionsDir

    $upArgs = @("compose", "-f", $ComposeFile, "up", "-d")
    if (-not $NoBuild) {
        $upArgs += "--build"
    }

    Write-Host "[1/4] Starting JARVIS stack..." -ForegroundColor Cyan
    & docker @upArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed"
    }

    Write-Host "[2/4] Waiting for services..." -ForegroundColor Cyan
    Wait-Health -Url "http://localhost:8401/health" -Label "jarvis-memory"
    Wait-Health -Url "http://localhost:8402/health" -Label "jarvis-voice"
    Wait-Health -Url "http://localhost:8403/health" -Label "jarvis-brain"
    Wait-Health -Url "http://localhost:8405/health" -Label "jarvis-vision"

    if (-not $SkipModelPull) {
        Write-Host "[3/4] Ensuring base model is available..." -ForegroundColor Cyan
        & docker exec jarvis_ollama ollama pull gemma3:1b | Out-Host
    }

    $visionFlag = if ($UseVision) { "true" } else { "false" }

    Write-Host "[4/4] Entering continuous conversation mode..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "JARVIS conversation mode is live." -ForegroundColor Green
    Write-Host "Session: $SessionId"
    Write-Host "Vision flag: $visionFlag"
    Write-Host "Type 'salir', 'exit', or 'quit' to stop."
    Write-Host ""

    while ($true) {
        $u = Read-Host "Tu"
        if ([string]::IsNullOrWhiteSpace($u)) { continue }
        if ($u -in @("salir", "exit", "quit")) { break }

        $msg = [System.Uri]::EscapeDataString($u)
        $sid = [System.Uri]::EscapeDataString($SessionId)
        $uri = "http://localhost:8403/converse?message=$msg&session_id=$sid&use_vision=$visionFlag"

        try {
            $r = Invoke-RestMethod -Method Post -Uri $uri -TimeoutSec 120
            Write-Host "Jarvis: $($r.response)"

            if ($null -ne $r.controls_applied) {
                $controls = ($r.controls_applied | ConvertTo-Json -Compress)
                if ($controls -ne "{}") {
                    Write-Host "  [controls] $controls" -ForegroundColor DarkGray
                }
            }

            if ($null -ne $r.vision -and $null -ne $r.vision.summary) {
                Write-Host "  [vision] $($r.vision.summary)" -ForegroundColor DarkGray
            }
        }
        catch {
            Write-Host "Jarvis: I could not process that message right now." -ForegroundColor Yellow
        }

        Write-Host ""
    }
}
finally {
    if ((Get-Location).Path -eq (Resolve-Path $extensionsDir).Path) {
        Pop-Location
    }
}
