# V1100 Startup Script
$portCheck = Test-NetConnection -ComputerName localhost -Port 7687 -InformationLevel Quiet
if (-not $portCheck) {
    Write-Host "Neo4j Offline!" -ForegroundColor Red
} else {
    Write-Host "Neo4j Online!" -ForegroundColor Green
}
if (Test-Path ".\venv\Scripts\activate.ps1") {
    . .\venv\Scripts\activate.ps1
}
Set-Location -Path "backend"
Start-Process -FilePath "..\venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app", "--host", "0.0.0.0", "--port", "8000" -NoNewWindow
Start-Sleep -Seconds 3
Start-Process "http://localhost:8000"
Write-Host "V1100 Started."
