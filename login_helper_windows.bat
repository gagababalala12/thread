@echo off
chcp 65001 >nul
title Auto-Publisher - Trợ lý Đăng nhập Trình duyệt Windows

echo ======================================================================
echo   🚀 TRỢ LÝ ĐĂNG NHẬP TRÌNH DUYỆT WINDOWS CHO AUTO-PUBLISHER
echo ======================================================================
echo.
echo Đang mở trình duyệt trên Windows để bạn đăng nhập TikTok, YouTube, Facebook...
echo.

start "" "https://www.tiktok.com/login"
start "" "https://studio.youtube.com"
start "" "https://www.facebook.com"
start "" "http://localhost:8080#accounts"

echo [✓] Đã mở các tab đăng nhập và trang Web Dashboard!
echo.
echo ======================================================================
echo 👉 HƯỚNG DẪN 4 BƯỚC ĐỂ LƯU PHIÊN:
echo 1. Đăng nhập tài khoản trên các tab trình duyệt vừa mở.
echo 2. Cài tiện ích 'Cookie-Editor' trên Cốc Cốc, Chrome, hoặc Edge:
echo    https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
echo 3. Trên mỗi trang đã đăng nhập, bấm biểu tượng Cookie-Editor -> Export -> Export as JSON.
echo 4. Chuyển sang tab Web Dashboard (http://localhost:8080#accounts):
echo    Dán mã JSON vừa copy vào khung và bấm nút 'Lưu Cookie'.
echo ======================================================================
echo.
pause
