param(
    [switch]$InstallDeps
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $root "backend"
$frontendPath = Join-Path $root "frontend"

if (-not (Test-Path $backendPath)) {
    throw "Pasta backend não encontrada em: $backendPath"
}

if (-not (Test-Path $frontendPath)) {
    throw "Pasta frontend não encontrada em: $frontendPath"
}

$backendCommand = @(
    "Set-Location `"$backendPath`""
    "Write-Host 'Iniciando backend em http://0.0.0.0:8091 ...' -ForegroundColor Green"
)

if ($InstallDeps) {
    $backendCommand += "py -3.12 -m pip install -r requirements.txt"
}

$backendCommand += "py -3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8091"

$frontendCommand = @(
    "Set-Location `"$frontendPath`""
    "Write-Host 'Iniciando frontend em http://0.0.0.0:8090 ...' -ForegroundColor Cyan"
)

if ($InstallDeps) {
    $frontendCommand += "npm install"
}

$frontendCommand += "npm run dev"

Start-Process pwsh -ArgumentList @(
    "-NoExit",
    "-Command",
    ($backendCommand -join "; ")
)

Start-Process pwsh -ArgumentList @(
    "-NoExit",
    "-Command",
    ($frontendCommand -join "; ")
)

Write-Host "Serviços iniciados em novas janelas." -ForegroundColor Yellow
try {
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } |
        Select-Object -First 1 -ExpandProperty IPAddress)
} catch {
    $lanIp = $null
}
if ($lanIp) {
    Write-Host "Acesso local:" -ForegroundColor Yellow
    Write-Host "Backend:  http://127.0.0.1:8091" -ForegroundColor Yellow
    Write-Host "Frontend: http://127.0.0.1:8090" -ForegroundColor Yellow
    Write-Host "Acesso na rede (outros PCs):" -ForegroundColor Green
    Write-Host "Frontend: http://$lanIp:8090" -ForegroundColor Green
    Write-Host "API:      http://$lanIp:8091/api/v1" -ForegroundColor Green
} else {
    Write-Host "Backend:  http://127.0.0.1:8091" -ForegroundColor Yellow
    Write-Host "Frontend: http://127.0.0.1:8090" -ForegroundColor Yellow
}
