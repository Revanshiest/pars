# Запуск пакетной обработки inbox/sources и мониторинг прогресса
$ErrorActionPreference = "Stop"
$ApiKey = "nickel-admin-key-change-me-min16"
$Base = "http://localhost:8000"
$Headers = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }

Write-Host "=== Nickel batch ingest ===" -ForegroundColor Cyan

$live = Invoke-RestMethod -Uri "$Base/live" -TimeoutSec 30
Write-Host "API: $($live.status)"

$glossary = Invoke-RestMethod -Uri "$Base/api/v1/glossary" -Headers @{ "X-API-Key" = $ApiKey } -TimeoutSec 120
Write-Host "Glossary terms: $($glossary.Count)"

$body = @{
    folder_path = "/app/data/inbox/sources"
    extractor   = "yandex"
    recursive   = $true
} | ConvertTo-Json

Write-Host "Starting batch ingest (1087+ PDFs, recursive, yandex)..."
$job = Invoke-RestMethod -Method POST -Uri "$Base/api/v1/documents/ingest-folder" -Headers $Headers -Body $body -TimeoutSec 120
Write-Host "Batch job id: $($job.id)" -ForegroundColor Green
Write-Host "Track at: http://localhost/ (Ingest page) or poll /api/v1/jobs/$($job.id)"

while ($true) {
    Start-Sleep -Seconds 30
    $j = Invoke-RestMethod -Uri "$Base/api/v1/jobs/$($job.id)" -Headers @{ "X-API-Key" = $ApiKey } -TimeoutSec 60
    $pct = if ($j.files_total -gt 0) { [math]::Round((($j.files_done + $j.files_failed) / $j.files_total) * 100) } else { 0 }
    Write-Host "$(Get-Date -Format 'HH:mm:ss') status=$($j.status) progress=$($j.files_done)/$($j.files_total) failed=$($j.files_failed) ($pct%) stage=$($j.stage)"
    if ($j.status -in @("completed", "failed")) {
        Write-Host "Done: $($j.status)" -ForegroundColor $(if ($j.status -eq 'completed') { 'Green' } else { 'Red' })
        if ($j.error) { Write-Host $j.error }
        break
    }
}
