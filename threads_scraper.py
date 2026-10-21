import asyncio
import json
import os
import re
from typing import List, Optional, Literal, Union
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HISTORY_FILE = Path(__file__).resolve().parent / "story_history.json"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

VIETNAMESE_ABBREVIATIONS = {
    r"\b(ko|k|khg)\b": "không",
    r"\b(dc|đc)\b": "được",
    r"\bhlv\b": "huấn luyện viên",
    r"\bvs\b": "với",
    r"\bj\b": "gì",
    r"\b(bt|bthg)\b": "bình thường",
    r"\bmn\b": "mọi người",
    r"\bntn\b": "như thế nào",
    r"\btks\b": "cảm ơn",
    r"\bthx\b": "cảm ơn",
    r"\bhnay\b": "hôm nay",
    r"\bnhiu\b": "nhiều",
    r"\bah\b": "ạ",
    r"\boh\b": "ồ",
}


def normalize_vietnamese_text(text: str) -> str:
    """Chuẩn hóa văn bản tiếng Việt UTF-8: thay thế toàn bộ từ viết tắt bằng từ tiếng Việt đầy đủ có dấu."""
    if not text:
        return text
    result = text
    for pattern, replacement in VIETNAMESE_ABBREVIATIONS.items():
        def replace_match(m):
            w = m.group(0)
            if w.isupper():
                return replacement.upper()
            if w[0].isupper():
                return replacement.capitalize()
            return replacement
        result = re.sub(pattern, replace_match, result, flags=re.IGNORECASE)
    return result


class StoryLine(BaseModel):
    text: str = Field(description="Nội dung câu thoại (tiếng Việt có dấu đầy đủ, không viết tắt).")
    voice: Literal["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"] = Field(
        default="vi-VN-HoaiMyNeural",
        description="Giọng đọc: 'vi-VN-HoaiMyNeural' (nữ) hoặc 'vi-VN-NamMinhNeural' (nam) tùy theo nhân vật đang nói."
    )
    sfx_after: Literal["none", "huh", "cai_gi_do", "laugh", "vine_boom", "wow"] = Field(
        default="none",
        description="Hiệu ứng âm thanh phát ngay sau khi đọc xong câu đó từ danh sách ['none', 'huh', 'cai_gi_do', 'laugh', 'vine_boom', 'wow']."
    )

    @field_validator("voice", mode="before")
    @classmethod
    def normalize_voice(cls, v):
        if not v or not isinstance(v, str):
            return "vi-VN-HoaiMyNeural"
        vl = v.lower().strip()
        if "female" in vl or "hoai" in vl or "nu" in vl or "nữ" in vl:
            return "vi-VN-HoaiMyNeural"
        if "nam" in vl or "male" in vl:
            return "vi-VN-NamMinhNeural"
        if v in ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"):
            return v
        return "vi-VN-HoaiMyNeural"

    @field_validator("sfx_after", mode="before")
    @classmethod
    def normalize_sfx_after(cls, v):
        if not v or not isinstance(v, str):
            return "none"
        vl = v.lower().strip()
        for ext in (".mp3", ".wav", ".aac", ".ogg"):
            if vl.endswith(ext):
                vl = vl[:-len(ext)].strip()
        if vl in ("huh", "cai_gi_do", "laugh", "vine_boom", "wow"):
            return vl
        if vl in ("caigido", "cai gi do"):
            return "cai_gi_do"
        if vl in ("vineboom", "vine boom"):
            return "vine_boom"
        return "none"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.text == other
        if isinstance(other, StoryLine):
            return (self.text, self.voice, self.sfx_after) == (other.text, other.voice, other.sfx_after)
        return False

    def __str__(self):
        return self.text

    def lower(self):
        return self.text.lower()

    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def keys(self):
        return ["text", "voice", "sfx_after"]

    def items(self):
        return [("text", self.text), ("voice", self.voice), ("sfx_after", self.sfx_after)]


class ThreadCard(BaseModel):
    card_id: int = Field(description="Số thứ tự khung bài đăng (1 hoặc 2)")
    time_ago: str = Field(description="Thời gian đăng giả lập, ví dụ: '2 giờ', '1 giờ'")
    likes: str = Field(description="Lượt tim giả lập hấp dẫn, ví dụ: '14,2K', '29,8K'")
    replies: str = Field(description="Lượt bình luận giả lập, ví dụ: '382', '1.104'")
    lines: List[StoryLine] = Field(
        description="Danh sách đúng 3 câu StoryLine trong khung này. Câu cuối của card 2 phải là câu chốt hạ gây cười."
    )
    use_video_meme_outro: bool = Field(
        default=True,
        description="Chèn clip video meme reaction vào cuối video sau câu chốt hạ của Card 2."
    )

    @field_validator("lines", mode="before")
    @classmethod
    def convert_lines(cls, v):
        if not isinstance(v, list):
            return v
        converted = []
        for item in v:
            if isinstance(item, str):
                converted.append(StoryLine(text=item, voice="vi-VN-HoaiMyNeural", sfx_after="none"))
            elif isinstance(item, dict):
                converted.append(StoryLine(**item))
            else:
                converted.append(item)
        return converted


class StorySelection(BaseModel):
    selected_post_index: int = Field(description="Vị trí bài đăng được chọn trong danh sách")
    humor_score: int = Field(description="Điểm độ hài hước và bất ngờ từ 1 đến 10")
    title: Optional[str] = Field(default="Kịch bản viral", description="Tiêu đề câu chuyện")
    cards: List[ThreadCard] = Field(description="Danh sách gồm đúng 2 card (Card 1 dẫn dắt, Card 2 chốt hạ)")
    use_video_meme_outro: bool = Field(
        default=True,
        description="Chèn clip video meme reaction vào cuối video sau câu chốt hạ của Card 2."
    )


def load_history() -> list:
    history_path = Path(HISTORY_FILE)
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except Exception as e:
            print(f"[!] Không thể đọc file lịch sử ({e}), khởi tạo danh sách trống.")
            return []
    return []


def save_history(new_title: str):
    history = load_history()
    history.append(new_title)
    if len(history) > 50:
        history = history[-50:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi khi ghi lịch sử: {e}")


async def scrape_threads_posts(urls: List[str], max_scrolls: int = 4) -> List[str]:
    raw_posts = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for url in urls:
            print(f"[+] Đang quét dữ liệu từ: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Cố gắng đóng popup / modal đăng nhập nếu có
                try:
                    close_buttons = page.locator('div[role="dialog"] [aria-label="Close"], div[role="dialog"] button:has-text("Đóng")')
                    if await close_buttons.count() > 0:
                        await close_buttons.first.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                for scroll_idx in range(max_scrolls):
                    elements = await page.locator('div[dir="auto"]').all_inner_texts()
                    for text in elements:
                        cleaned = text.strip()
                        if 80 <= len(cleaned) <= 650 and not cleaned.startswith("http"):
                            raw_posts.add(cleaned)

                    await page.mouse.wheel(0, 1800)
                    await asyncio.sleep(2)

                    # Bấm phím Escape để tắt các backdrop/overlay xuất hiện giữa chừng
                    try:
                        await page.keyboard.press("Escape")
                    except Exception:
                        pass

            except Exception as e:
                print(f"[!] Bỏ qua {url} do lỗi kết nối: {e}")

        await browser.close()

    return list(raw_posts)


def select_and_format_story(
    raw_posts: List[str],
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key:
        raise ValueError(
            "Chưa cấu hình GEMINI_API_KEY. Vui lòng truyền qua tham số api_key hoặc thiết lập biến môi trường GEMINI_API_KEY."
        )

    client = genai.Client(api_key=resolved_api_key)

    history = load_history()
    history_note = ""
    if history:
        history_note = (
            "\nCÁC CÂU CHUYỆN ĐÃ LÀM TRƯỚC ĐÓ (TUYỆT ĐỐI KHÔNG LẶP LẠI NỘI DUNG HOẶC CHỦ ĐỀ NÀY):\n"
            + "\n".join([f"- {h}" for h in history])
        )

    if not raw_posts:
        posts_payload = (
            "Hãy tự sáng tác 1 mẩu chuyện cười ngắn độc lạ khác hoàn toàn các chủ đề thông thường."
        )
    else:
        formatted_list = "\n---\n".join([f"[Bài {i}]: {post}" for i, post in enumerate(raw_posts[:25])])
        posts_payload = f"Danh sách các bài đăng vừa quét từ Threads:\n{formatted_list}"

    prompt = f"""
    Bạn là đạo diễn kịch bản kiêm đạo diễn âm thanh cho kênh YouTube Shorts triệu view (phong cách Động Threads).
    Nhiệm vụ:
    1. Chọn hoặc sáng tác 1 câu chuyện hài hước có cú twist mạnh và bất ngờ ở câu cuối cùng.
    {history_note}
    2. Toàn bộ chuỗi văn bản tiếng Việt bắt buộc phải có đầy đủ dấu tiếng Việt chuẩn UTF-8. Tuyệt đối KHÔNG viết tiếng Việt không dấu và KHÔNG dùng từ viết tắt (như "hlv", "ko", "dc", "vs", "j").
    3. Biên tập lại sang văn nói tiếng Việt tự nhiên, gãy gọn, không có emoji.
    4. Chia thành đúng 2 khung (Card 1 mở bài/gây tò mò gồm 3 câu, Card 2 giải quyết và chốt hạ gồm 3 câu; câu thứ 3 của Card 2 bắt buộc là cú twist đắt giá gây cười).
    5. Đạo diễn đa giọng đọc và âm thanh SFX cho từng câu (StoryLine):
       - text: Nội dung câu thoại tiếng Việt đầy đủ dấu.
       - voice: Chọn "vi-VN-HoaiMyNeural" (nữ) hoặc "vi-VN-NamMinhNeural" (nam) tùy nhân vật đang nói để tạo hội thoại sinh động giữa các nhân vật (ví dụ: mẹ/cô giáo/bạn gái chọn giọng nữ; bố/thầy giáo/bạn trai chọn giọng nam; người dẫn chuyện có thể chọn 1 trong 2).
       - sfx_after: Tự chọn hiệu ứng âm thanh phát ngay sau khi đọc xong câu đó từ danh sách ["none", "huh", "cai_gi_do", "laugh", "vine_boom", "wow"] sao cho khớp cảm xúc câu chuyện:
         * "huh": Sau câu hỏi ngơ ngác, thắc mắc, bối rối.
         * "cai_gi_do": Sau câu trả lời bất ngờ, lạ lùng hoặc ngớ ngẩn.
         * "laugh": Sau câu đùa dí dỏm hoặc chi tiết buồn cười.
         * "vine_boom": Sau câu twist cú chót hoặc tình huống sốc, vỡ mộng.
         * "wow": Sau lời khen hoặc chi tiết gây trầm trồ.
         * "none": Các câu bình thường không cần SFX.
    6. Thiết lập use_video_meme_outro: true để chèn clip meme reaction vào cuối video.
    
    {posts_payload}
    """

    candidate_models = [model]
    for fallback_m in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]:
        if fallback_m not in candidate_models:
            candidate_models.append(fallback_m)

    response = None
    last_error = None
    for current_model in candidate_models:
        print(f"[+] Đang gửi dữ liệu qua Gemini AI ({current_model}) để chấm điểm và tách câu...")
        try:
            resp = client.models.generate_content(
                model=current_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=StorySelection,
                    temperature=0.85,
                ),
            )
            if resp and (getattr(resp, "parsed", None) is not None or (getattr(resp, "text", None) and resp.text.strip())):
                response = resp
                break
        except Exception as e:
            print(f"[!] Gặp lỗi với model {current_model}: {e}. Đang thử model kế tiếp...")
            last_error = e

    if not response:
        raise last_error

    # Trích xuất dữ liệu trả về từ Gemini
    if hasattr(response, "parsed") and response.parsed is not None:
        if isinstance(response.parsed, StorySelection):
            result_data = response.parsed.model_dump()
        else:
            result_data = response.parsed
    else:
        result_data = json.loads(response.text)

    # Chuẩn hóa toàn bộ câu chữ trong cards: xóa bỏ từ viết tắt, đảm bảo dấu tiếng Việt
    cards = result_data.get("cards", [])
    for card in cards:
        if isinstance(card, dict):
            raw_lines = card.get("lines", [])
            for l in raw_lines:
                if isinstance(l, dict):
                    l["text"] = normalize_vietnamese_text(l.get("text", ""))
                elif hasattr(l, "text"):
                    l.text = normalize_vietnamese_text(l.text)
        elif hasattr(card, "lines"):
            for l in card.lines:
                if hasattr(l, "text"):
                    l.text = normalize_vietnamese_text(l.text)
                elif isinstance(l, dict):
                    l["text"] = normalize_vietnamese_text(l.get("text", ""))

    # Lưu lại lịch sử câu mở đầu
    if cards and len(cards) > 0:
        first_card = cards[0]
        raw_lines = first_card.get("lines", []) if isinstance(first_card, dict) else getattr(first_card, "lines", [])
        if raw_lines:
            first_l = raw_lines[0]
            first_text = first_l.get("text") if isinstance(first_l, dict) else getattr(first_l, "text", str(first_l))
            if first_text:
                save_history(first_text)

    print(f"[✓] Gemini đã chọn kịch bản (Điểm hài hước: {result_data.get('humor_score', 'N/A')}/10)")
    return {
        "title": result_data.get("title", "Kịch bản viral"),
        "cards": cards,
        "humor_score": result_data.get("humor_score"),
        "use_video_meme_outro": result_data.get("use_video_meme_outro", True),
    }


async def get_automated_story(
    target_urls: List[str],
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    raw_posts = await scrape_threads_posts(target_urls)
    if not raw_posts:
        raise RuntimeError("Chưa quét được bài từ Threads (danh sách bài đăng trống).")
    story_data = select_and_format_story(raw_posts, api_key=api_key, model=model)
    return story_data


__all__ = [
    "StoryLine",
    "ThreadCard",
    "StorySelection",
    "normalize_vietnamese_text",
    "load_history",
    "save_history",
    "scrape_threads_posts",
    "select_and_format_story",
    "get_automated_story",
    "HISTORY_FILE",
    "DEFAULT_MODEL",
    "VIETNAMESE_ABBREVIATIONS",
]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Threads Story Scraper & Gemini AI Story Formatter for YouTube Shorts"
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=[],
        help="Danh sách URL bài đăng hoặc trang Threads cần quét",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model Gemini sử dụng (mặc định: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Không quét Threads, yêu cầu Gemini tự sáng tác trực tiếp",
    )
    args = parser.parse_args()

    async def main():
        urls = args.urls
        if args.no_scrape or not urls:
            if not urls and not args.no_scrape:
                print("[!] Chưa chỉ định URLs. Chạy chế độ sáng tác tự động (hoặc truyền --urls).")
            result = select_and_format_story([], model=args.model)
        else:
            result = await get_automated_story(urls, model=args.model)

        print("\n" + "=" * 50)
        print("🎉 KẾT QUẢ KỊCH BẢN 2 CARD:")
        print("=" * 50)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())
