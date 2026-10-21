# Kế hoạch Kỹ thuật: Threads Story Scraper & Gemini AI Curation

Hợp đồng kỹ thuật triển khai cho intent: [2026-10-21-threads-story-scraper.md](file:///root/.gemini/antigravity/worktrees/jolly-bardeen/threads_story_scraper_gemini/intent/2026-10-21-threads-story-scraper.md)

---

## 1. Files sẽ chạm (theo thứ tự)

1. `requirements.txt`: Khai báo các thư viện chuẩn gồm `google-genai>=2.30.1`, `pydantic>=2.0.0`, `playwright>=1.40.0`, `python-dotenv>=1.0.0`.
2. `.env.example`: Biến môi trường mẫu cấu hình `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.8-flash`.
3. `.gitignore`: Bỏ qua các file sinh tự động (`story_history.json`, `.env`, `__pycache__`, `.playwright/`).
4. `threads_scraper.py`: Triển khai đầy đủ module:
   - Data models: `ThreadCard`, `StorySelection`
   - History management: `load_history()`, `save_history()`
   - Scraper: `scrape_threads_posts(urls, max_scrolls)` chống chặn và tự tắt modal
   - Curator: `select_and_format_story(raw_posts, api_key, model)` với fallback và validation
   - Orchestrator: `get_automated_story(target_urls, api_key, model)`
   - CLI: Block `if __name__ == "__main__":` hỗ trợ `--urls`, `--model`, `--no-scrape`
5. `test_threads_scraper.py`: Bộ kiểm thử tự động (Unit tests & Mock tests) kiểm tra schema, history và fallback.
6. `README.md`: Tài liệu hướng dẫn sử dụng, giải thích luồng hoạt động và ví dụ tích hợp.

---

## 2. Risks — Có thể gãy gì & Cách kiểm bắt được

| Risk | Nguy cơ gãy | Cách xử lý & Kiểm soát |
|---|---|---|
| **R1: Threads chặn bot / DOM thay đổi** | Playwright không tìm thấy `div[dir="auto"]` hoặc vướng popup | Xử lý ngoại lệ theo từng URL; bấm `Escape` và nút đóng popup; nếu `raw_posts` rỗng thì Gemini tự động chuyển sang kịch bản sáng tác gốc. |
| **R2: Phản hồi AI sai cấu trúc** | Kết quả không khớp 2 card hoặc câu chốt hạ | Sử dụng `response_schema=StorySelection` từ `types.GenerateContentConfig`, ưu tiên trích xuất `response.parsed`. |
| **R3: File lịch sử bị hỏng** | `story_history.json` bị lỗi cú pháp json | Bọc `try/except (json.JSONDecodeError, OSError)` để tự động phục hồi về mảng rỗng `[]`. |
| **R4: Thiếu hoặc sai GEMINI_API_KEY** | Crash ứng dụng không rõ nguyên nhân | Kiểm tra rõ ràng và ném `ValueError` kèm hướng dẫn thiết lập biến môi trường. |

---

## 3. Proof — Định nghĩa xong (Definition of Done)

Hệ thống được coi là hoàn thành khi thỏa mãn các bằng chứng sau:

1. **Syntax Check**:
   ```bash
   python3 -m py_compile threads_scraper.py test_threads_scraper.py
   ```
   *Kỳ vọng*: Exit code 0, không có lỗi cú pháp.

2. **Automated Unit & Mock Tests**:
   ```bash
   python3 -m unittest test_threads_scraper.py
   ```
   *Kỳ vọng*: Tất cả test case về Pydantic schema validation, history cap (50 entries), và prompt payload formatting đều PASSED.

3. **CLI Interface**:
   ```bash
   python3 threads_scraper.py --help
   ```
   *Kỳ vọng*: Hiển thị đầy đủ hướng dẫn các tham số `--urls`, `--model`, `--no-scrape`.
