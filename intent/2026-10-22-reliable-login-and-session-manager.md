---
status: shipped
---
# Giải pháp Đăng nhập & Quản lý Phiên (Session/Cookie) 100% Ổn định cho WSL2/Linux

**Problem**
Trong môi trường WSL2 (hoặc Linux container/headless server không có sẵn native $DISPLAY server):
1. Lệnh `auto_publisher.py --login` trước đây cố gắng mở Playwright với `headless=False` hoặc fallback qua `--remote-debugging-port=9222` kết hợp `chrome-devtools-frontend.appspot.com` / `coccoc://inspect`.
2. Do Playwright chạy `chromium_headless_shell` nên websocket bị ngắt kết nối (`WebSocket disconnected. Make sure --remote-allow-origins...`), đồng thời domain `appspot.com` hay bị chặn hoặc chậm, dẫn đến người dùng không thể đăng nhập trực quan được.
3. Người dùng trên Windows (sử dụng Cốc Cốc, Google Chrome, Microsoft Edge) cần một giải pháp đăng nhập 100% tin cậy, tiện lợi, không phụ thuộc vào devtools web socket hay X server, đồng thời hỗ trợ kiểm tra trạng thái đăng nhập của 3 nền tảng (YouTube Studio, TikTok Studio, Facebook Reels).

**Outcome**
1. **Module Quản lý Phiên & Cookie (`auth_state.json` & `cookies.json`)**:
   - Bộ phân tích và chuẩn hóa cookie đa định dạng (`parse_cookies_input`): hỗ trợ Cookie-Editor JSON, Playwright `storage_state`, Netscape cookies (hỗ trợ cả các dòng `#HttpOnly_`), dict phân nhóm platform, dict dạng key-value `{name: val}`, và raw headers.
   - Cơ chế tự động suy đoán domain theo tên cookie phiên (`infer_cookie_domain`): tự động gán `.tiktok.com`, `.youtube.com`, hoặc `.facebook.com` khi người dùng dán chuỗi header hoặc key-value mà không cần chỉ định domain.
   - Chuẩn hóa thuộc tính `sameSite` (Strict/Lax/None), bảo vệ thời hạn `expires` không bị hết hạn tức thì trong tương lai gần, tự động gán `secure=True` cho `sameSite=None`.
   - Hàm `check_auth_status()` kiểm tra trạng thái xác thực offline tức thì và chính xác cho cả 3 nền tảng (TikTok: `sessionid`, YouTube: `LOGIN_INFO`/`SID`, Facebook: `c_user`/`xs`), trích xuất UID Facebook từ cả memory và persistent profile.
   - Hàm `safe_add_cookies`: nạp an toàn vào BrowserContext, tự động fallback nạp từng cookie nếu có 1 cookie lỗi trong batch.
   - Đồng bộ và dọn sạch cả `auth_state.json` và `cookies.json` khi gọi `clear_cookies` để tránh cookie bị phục hồi ngoài ý muốn.
2. **Web Dashboard Đăng nhập & Quản lý Tài khoản (Port 8080)**:
   - Thêm tab "🔐 Đăng Nhập & Quản Lý Tài Khoản" song song với bảng tiến độ video.
   - Thẻ hiển thị trạng thái sống trực quan cho 3 nền tảng kèm số lượng cookie và UID, nút mở trực tiếp trang đăng nhập hoặc chuyển sang chế độ dán cookie nhanh.
   - Khung nạp cookie đa năng: hỗ trợ dán JSON từ Cookie-Editor, hỗ trợ chọn file trực tiếp từ máy tính (`.json` hoặc `.txt`).
   - Nút hành động nhanh: "🚀 Mở Cả 3 Trang Đăng Nhập Trên Trình Duyệt" mở đồng thời các tab trên trình duyệt của người dùng.
   - API RESTful: `GET /api/auth-status`, `POST /api/save-cookies`, `POST /api/clear-cookies`, `GET /api/export-cookies`, `POST /api/open-browser`, `GET /login-helper.bat`, `GET /login-helper.ps1` (kèm header CORS).
   - Cơ chế thông minh: dừng reload trang khi ở tab tài khoản để bảo vệ nội dung textarea, chỉ cập nhật trạng thái qua AJAX.
3. **Trợ lý Trình duyệt Windows & Cờ lệnh `--login` Mới**:
   - Tự động phát hiện màn hình Desktop Windows (`/mnt/c/Users/<User>/Desktop`) và tạo file `AutoPublisher_Login.bat` trực tiếp trên Desktop để người dùng click là mở ngay.
   - Cung cấp sẵn file tải về trực tiếp từ Dashboard: `/login-helper.bat` và `/login-helper.ps1`.
   - Nâng cấp `login_setup()` trong `auto_publisher.py`: xử lý bất đồng bộ chuẩn Python 3.12 (loại bỏ hoàn toàn lỗi TypeError giữa coroutine và Future), hỗ trợ cả môi trường TTY tương tác lẫn non-interactive, tự động mở các tab nền tảng chưa đăng nhập qua `wslview`, `cmd.exe /c start`, `powershell.exe Start-Process`, hoặc `explorer.exe`.
4. **Kiểm thử**:
   - Duy trì 100% 44 bài test ban đầu.
   - Bổ sung 16 bài test chuyên sâu (tổng cộng 60 tests), đạt tỉ lệ 60/60 PASS.

**Constraints**
- Giữ nguyên các định danh, giao diện và chức năng hiện hữu của Video Pipeline.
- Không thêm thư viện phụ thuộc bên ngoài mới ngoài những gì đã có trong repo (`playwright`, `http.server`, `json`, `asyncio`, v.v.).
- Đảm bảo an toàn bảo mật bí mật tài khoản (`auth_state.json`, `cookies.json` và các file test nằm trong `.gitignore`).

**Out of scope**
- Tự động vượt qua captcha hay câu hỏi bảo mật phức tạp mà không cần người dùng cấp cookie phiên đăng nhập.
