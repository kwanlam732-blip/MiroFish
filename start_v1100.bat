@echo off
REM V1100 一鍵點火腳本 (Batch 版本)
REM ============================================

REM 雷達掃描：檢查 Neo4j 埠 7687
powershell -Command "if (!(Test-NetConnection -ComputerName localhost -Port 7687 -InformationLevel Quiet)) { Write-Host '⚠️ 警告：記憶圖譜離線！請先打開 Neo4j Desktop 點擊 Start！' -ForegroundColor Red; Read-Host '按 Enter 繼續' } else { Write-Host '✅ 圖譜記憶已連線！準備點火引擎...' -ForegroundColor Green }"

REM 啟動護盾：激活虛擬環境
call .\venv\Scripts\activate.bat

REM 引擎點火：切換至 backend 目錄並啟動 Uvicorn
cd backend
start ..\venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000

REM 全息展開：等待 3 秒後打開瀏覽器
timeout /t 3 /nobreak > nul
start http://localhost:8000

REM 首戰實測：印出歡迎詞
echo V1100 本地預言機已上線，首長，請開始您的任務。
pause