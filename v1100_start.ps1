# MiroFish V1100 自動重啟與防呆啟動腳本
# ==========================================

Write-Host "🚀 [V1100] 正在啟動全息指揮台..." -ForegroundColor Cyan

# 1. 檢查並清理 8000 端口
$port = 8000
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess
    Write-Host "⚠️ [防呆] 發現端口 $port 已被 PID $pid 佔用，正在強制釋放..." -ForegroundColor Yellow
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# 2. 啟動 Uvicorn 服務
Write-Host "✅ [V1100] 端口已就緒，正在掛載後端總線 (Port: $port)..." -ForegroundColor Green
Write-Host "💡 提示：若遇到代碼更新後自動重啟失敗，請重新執行此腳本。" -ForegroundColor Gray

try {
    cd backend
    # 排除 noisy 目錄（如上傳資料或靜態資源），防止因檔案頻繁變動導致重啟崩潰
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "data/*" --reload-exclude "static/*"
} catch {
    Write-Host "❌ [錯誤] 啟動失敗：$($_.Exception.Message)" -ForegroundColor Red
}
