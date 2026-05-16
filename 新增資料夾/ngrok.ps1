# 設定變數
$port = 8000
$target = "127.0.0.1:$port"

Write-Host "--- LINE Bot 測試環境啟動器 ---" -ForegroundColor Cyan

# 1. 檢查本地 Port 是否有在執行
$check = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue

if ($check) {
    Write-Host "✅ 偵測到後端伺服器已在 $port 運作中。" -ForegroundColor Green
} else {
    Write-Host "⚠️  警告：Port $port 尚未啟動！請記得執行伺服器程式。" -ForegroundColor Yellow
}

# 2. 啟動 ngrok (使用最簡單的指令避免語法錯誤)
Write-Host "🚀 正在啟動 ngrok 隧道指向 $target ..." -ForegroundColor Cyan
ngrok http $target