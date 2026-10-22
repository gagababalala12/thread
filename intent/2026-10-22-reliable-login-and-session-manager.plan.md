---
status: shipped
---
# Kế hoạch triển khai: Hệ thống Đăng nhập & Quản lý Cookie Đa Nền tảng

## Files to Modify & Create
1. `.gitignore`:
   - Bổ sung `auth_state.json`, `test_auth_state.json`, `cookies.json`, `test_cookies.json` để bảo vệ thông tin phiên người dùng theo chuẩn an toàn bảo mật `/bto-secrets`.
2. `auto_publisher.py`:
   - Thêm các hằng số: `AUTH_STATE_FILE = Path("auth_state.json")`, `COOKIES_FILE = Path("cookies.json")`.
   - Hàm `infer_cookie_domain(name)`: tự động suy đoán domain của TikTok, YouTube, Facebook khi người dùng nhập cookie không có domain.
   - Hàm `normalize_cookie(c, default_domain=None)`: chuẩn hóa `sameSite`, `expires`, `secure`, `httpOnly`, domain và path.
   - Hàm `parse_cookies_input(raw_input, default_domain=None)`: phân tích dữ liệu cookie từ Cookie-Editor JSON, Playwright storage_state, Dict platforms, Dict key-value `{name: val}`, Netscape (hỗ trợ `#HttpOnly_`) hoặc chuỗi header.
   - Hàm `load_saved_cookies(target_file=None)`: nạp cookie từ target_file (nếu có) hoặc hợp nhất từ `auth_state.json` và `cookies.json`.
   - Hàm `save_cookies(cookies, target_file, merge=True)`: lưu và hợp nhất cookie vào `auth_state.json` hoặc target_file chỉ định.
   - Hàm `clear_cookies(platform, target_file)`: xóa cookie của một hoặc tất cả nền tảng, tự động đồng bộ dọn sạch cả `cookies.json`.
   - Hàm `check_auth_status(cookies=None)`: kiểm tra tính hợp lệ của phiên đăng nhập (TikTok, YouTube, Facebook) kèm URL chuyển hướng tương ứng.
   - Hàm `launch_windows_browser(url)`: mở URL trên trình duyệt Windows từ WSL2 hỗ trợ `wslview`, `cmd.exe /c start`, `powershell.exe Start-Process`, và `explorer.exe`.
   - Hàm `deploy_windows_desktop_helper(port)`: tự động tạo file `AutoPublisher_Login.bat` trực tiếp trên Desktop Windows của người dùng.
   - Hàm `safe_add_cookies(context, cookies)`: nạp cookie an toàn vào Playwright context, có cơ chế fallback nạp từng cookie khi nạp dạng batch gặp lỗi.
   - Cập nhật `publish_all_platforms`: tự động nạp saved cookies an toàn vào Playwright persistent context và lưu lại cookies mới sau phiên đăng bài.
   - Cập nhật `DashboardHandler`:
     - Endpoint `GET /api/auth-status`: trả về JSON trạng thái đăng nhập 3 nền tảng.
     - Endpoint `GET /api/export-cookies`: tải về file `auth_state.json`.
     - Endpoint `GET /login-helper.bat`: tải về file script `.bat`.
     - Endpoint `GET /login-helper.ps1`: tải về file script `.ps1`.
     - Endpoint `POST /api/open-browser`: kích hoạt mở các trang đăng nhập trên trình duyệt Windows.
     - Endpoint `POST /api/save-cookies`: nhận JSON cookie từ người dùng, lưu và trả về trạng thái mới.
     - Endpoint `POST /api/clear-cookies`: xóa cookie theo yêu cầu.
     - Mở rộng giao diện HTML Dashboard với 2 tab: Video Pipeline và Quản lý Tài khoản (Status cards, Cookie Importer, Quick Guide, Nút mở cả 3 tab đăng nhập, và Input chọn file từ máy tính).
   - Cập nhật `login_setup()`: xử lý bất đồng bộ chuẩn coroutine trong Python 3.12 (loại bỏ TypeError giữa Future và coroutine), kích hoạt Windows Browser + Web Dashboard, tự động tạo desktop shortcut, và lắng nghe tự động hoàn tất khi cả 3 nền tảng đã sẵn sàng.
3. `login_helper_windows.bat` & `login_helper_windows.ps1`:
   - Script hỗ trợ người dùng trên Windows khởi chạy nhanh các tab đăng nhập và trang quản lý Dashboard với 1 click.
4. `test_auto_publisher.py`:
   - Bổ sung 16 bài test chuyên sâu cho cookie parsing (Netscape #HttpOnly_, key-value dict, domain inference), auth status checking, merging với custom target_file, dọn sạch cookies.json, safe_add_cookies batch fallback, login_setup coroutine execution, API endpoints và desktop helper deployment.
5. `README.md`:
   - Cập nhật hướng dẫn chi tiết cách đăng nhập tài khoản bằng Cookie-Editor trên Cốc Cốc / Chrome / Edge hoặc qua Desktop Helper.

## Risks & Mitigations
- **Risk 1: Chromium xóa cookie khi hết hạn hoặc khi cùng phiên đóng lại.**
  - *Mitigation*: Tự động cập nhật `expires` cho cookie hợp lệ nếu thời hạn trong quá khứ hoặc chưa thiết lập, và lưu trữ dự phòng ở định dạng Playwright `storage_state` (`auth_state.json`) để nạp lại mỗi khi khởi chạy context.
- **Risk 2: `<meta http-equiv="refresh" content="10">` làm mất nội dung người dùng đang nhập vào textarea.**
  - *Mitigation*: JavaScript quản lý tự động hủy/dừng refresh khi người dùng chuyển sang tab Tài khoản hoặc đang focus vào khung nhập liệu, chỉ reload khi đang ở tab pipeline. Giữ nguyên thẻ meta trong HTML để đảm bảo 100% tương thích ngược với các test case hiện có.
- **Risk 3: Thao tác gọi Windows binary từ WSL2 bị treo trong môi trường không có console tương tác.**
  - *Mitigation*: Sử dụng `subprocess.Popen` không đồng bộ và không chặn luồng (non-blocking) với `stdout/stderr=DEVNULL`, hỗ trợ đầy đủ các kênh `wslview`, `cmd.exe /c start`, `powershell.exe`, và `explorer.exe`.
- **Risk 4: Ghi đè cookie giữa các nền tảng khi nạp riêng lẻ hoặc cookie cũ phục hồi từ cookies.json.**
  - *Mitigation*: Hàm `save_cookies` luôn hợp nhất (merge) theo key `(domain, path, name)`. Hàm `clear_cookies` lọc và dọn sạch cả trong `cookies.json` để loại bỏ hoàn toàn rủi ro tái xuất hiện cookie cũ.
- **Risk 5: Một cookie dị biệt làm hỏng toàn bộ batch add_cookies trong Playwright.**
  - *Mitigation*: `safe_add_cookies` tự động thử nạp cả batch, nếu Chromium từ chối sẽ chuyển sang nạp từng cookie đơn lẻ để bảo toàn tối đa các cookie phiên hợp lệ.

## Proof of Completion
- Toàn bộ 44 unit test cũ và 16 unit test mới đều PASS (60/60 tests pass qua `.venv/bin/python -m unittest discover`).
- Chạy thử nghiệm CLI: `python auto_publisher.py --check-login` và `python auto_publisher.py --login` chạy trơn tru, hiển thị trạng thái và không bị lỗi TypeError hay bị treo.
- Kiểm thử các API `/api/auth-status`, `/api/save-cookies`, `/api/clear-cookies`, `/api/export-cookies`, `/api/open-browser`, `/login-helper.bat` hoạt động chuẩn xác.
