---
status: shipped
---
# Tự động hóa đăng video đa nền tảng (4 tiếng / video) & Web Dashboard theo dõi (Port 8080)

**Problem**
Sau khi hoàn thiện pipeline dựng video Threads Shorts với AI Audio Director và kho Meme, người dùng cần:
1. Cơ chế tự động lập lịch xuất bản đều đặn 4 tiếng / 1 video (`INTERVAL_HOURS = 4`), tự động tạo caption kèm hashtag (`#shorts #threads #haihuoc #xuhuong`) từ câu hook mở đầu, và dùng Playwright Persistent Context tự động đăng lên 3 nền tảng: YouTube Shorts, TikTok Studio, Facebook Reels.
2. Cờ lệnh `--login` để đăng nhập 1 lần ban đầu và cờ `--dry-run` để giả lập quá trình đăng khi kiểm thử hệ thống mà không yêu cầu tài khoản thật.
3. Bảng điều khiển Web Dashboard trực tuyến ở cổng `8080` giao diện Dark Mode, tự làm mới mỗi 10 giây, hiển thị thống kê tổng số video đã xuất / đã đăng, đồng hồ đếm ngược đến lần đăng kế tiếp, bảng chi tiết từng video kèm nút bấm mở xem trực tiếp video ngay trên trình duyệt.

**Outcome**
1. Nâng cấp `auto_publisher.py`:
   - Bộ lập lịch 4 tiếng / video (`INTERVAL_HOURS = 4`) gọi pipeline xuất video vào `published_videos/`.
   - Caption tự động từ câu đầu kịch bản + hashtag chuẩn `#shorts #threads #haihuoc #xuhuong`.
   - Hỗ trợ tham số `--login` (`headless=False`), `--dry-run` (giả lập đăng tải), và `--once` (chạy 1 chu kỳ).
   - Playwright Persistent Context (`browser_profile/`) hỗ trợ `--no-sandbox` tương thích mọi môi trường Linux.
2. Web Dashboard trực tuyến tại `http://localhost:8080`:
   - Dark mode hiện đại, `<meta http-equiv="refresh" content="10">` (10 giây).
   - Thống kê: "Tổng video đã xuất" và "Tổng video đã đăng thành công".
   - Bộ đếm thời gian / mốc giờ chính xác sẽ đăng video tiếp theo (cộng 4 tiếng từ lần trước).
   - Bảng danh sách video: Mã ID, Thời gian, Tiêu đề kịch bản, Trạng thái YouTube Shorts, Trạng thái Facebook Reels, Trạng thái TikTok, Trạng thái tổng.
   - Nút bấm "🎬 Xem video" trực tiếp mở video phát trên trình duyệt qua endpoint `/videos/<filename>`.
3. Kiểm thử & Chạy thử nghiệm:
   - Chạy 1 chu kỳ tạo video và cập nhật lên Dashboard ở chế độ kiểm thử (`--dry-run --once`).
   - Kiểm tra giao diện bảng trạng thái và endpoint phát video hoạt động hoàn hảo.
   - Bộ unit test `test_auto_publisher.py` đạt 100% PASS.

**Constraints**
- Giữ nguyên toàn bộ logic đăng video và giao diện Dashboard mà người dùng đã thiết kế.
- Không sử dụng thư viện bên ngoài mới ngoài những gì đã có (`playwright`, `http.server`, `threading`, `json`, `asyncio`, `moviepy`, `edge-tts`).
- Đảm bảo an toàn bảo mật tuyệt đối cho thư mục cookie/session `browser_profile/`.

**Out of scope**
- Tự động giải CAPTCHA phức tạp (người dùng xác thực thủ công trong bước `--login` khi cần).
- Đăng tải lên các nền tảng khác ngoài TikTok, YouTube Shorts và Facebook Reels.

**Open questions**
- Không có (yêu cầu và mã nguồn đã được định nghĩa đầy đủ).
