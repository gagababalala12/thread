# Trợ lý Đăng nhập Trình duyệt Windows cho Auto-Publisher (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  🚀 TRỢ LÝ ĐĂNG NHẬP TRÌNH DUYỆT WINDOWS CHO AUTO-PUBLISHER" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Đang mở trình duyệt để bạn đăng nhập TikTok, YouTube, Facebook..." -ForegroundColor White

Start-Process "https://www.tiktok.com/login"
Start-Process "https://studio.youtube.com"
Start-Process "https://www.facebook.com"
Start-Process "http://localhost:8080#accounts"

Write-Host "`n[✓] Đã mở các trang đăng nhập và Web Dashboard tại http://localhost:8080#accounts" -ForegroundColor Green
Write-Host ""
Write-Host "👉 HƯỚNG DẪN TIẾP THEO:" -ForegroundColor Yellow
Write-Host "1. Đăng nhập tài khoản trên các tab vừa mở."
Write-Host "2. Dùng tiện ích 'Cookie-Editor' (trên Cốc Cốc / Chrome / Edge) -> Export as JSON."
Write-Host "3. Dán vào mục 'Đăng nhập & Quản lý Tài khoản' tại http://localhost:8080 rồi bấm 'Lưu Cookie'."
Write-Host ""
Write-Host "Nhấn phím bất kỳ để thoát..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
