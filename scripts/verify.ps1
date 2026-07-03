# Full verification without Docker (Windows)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host ""
Write-Host "=== Nickel verify ===" -ForegroundColor Cyan

Write-Host ""
Write-Host "[1/5] Python compile..." -ForegroundColor Yellow
Set-Location (Join-Path $Root "nickel")
python -m compileall -q api services cli.py
if ($LASTEXITCODE -ne 0) { throw "compile failed" }

Write-Host "[2/5] Pytest..." -ForegroundColor Yellow
$env:SKIP_OLLAMA_HEALTH = "true"
$env:JWT_SECRET = "test-secret-key-minimum-32-characters!!"
python -m pytest tests/ -q --tb=line
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "[3/5] Smoke test..." -ForegroundColor Yellow
Set-Location $Root
python scripts/smoke_test.py
if ($LASTEXITCODE -ne 0) { throw "smoke test failed" }

Write-Host "[4/5] Frontend build..." -ForegroundColor Yellow
Set-Location (Join-Path $Root "frontend")
npm run build --silent
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }

Write-Host "[5/5] Docker compose config..." -ForegroundColor Yellow
Set-Location $Root
docker compose config --quiet 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  docker compose config OK" -ForegroundColor Green
    Write-Host "  Run: docker compose up -d --build (when Docker Desktop is running)" -ForegroundColor DarkGray
} else {
    Write-Host "  Docker not available - skip (start Docker Desktop for full stack)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
Write-Host ""
