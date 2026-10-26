#!/usr/bin/env bash
# ==============================================================================
# Script cài đặt tự động 1-Click cho VPS Linux / Google Cloud Compute Engine
# Dự án: Auto Threads Shorts Scraper & Publisher
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 BẮT ĐẦU CÀI ĐẶT DỰ ÁN AUTO THREADS SHORTS TRÊN LINUX / VPS / GCP"
echo "=================================================================="

# 1. Cài đặt các gói hệ thống cần thiết (FFmpeg, Python3, Git, Curl)
echo "[1/5] Đang cập nhật gói và cài đặt FFmpeg, Python3-venv..."
sudo apt update
sudo apt install -y python3-pip python3-venv ffmpeg git curl

# 2. Tạo môi trường ảo Python
echo "[2/5] Đang khởi tạo môi trường ảo Python (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. Nâng cấp pip và cài đặt dependencies
echo "[3/5] Đang cài đặt các thư viện Python từ requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Cài đặt Chromium cho Playwright kèm thư viện phụ thuộc
echo "[4/5] Đang tải Chromium cho Playwright..."
playwright install --with-deps chromium

# 5. Kiểm tra file cấu hình .env
echo "[5/5] Kiểm tra file cấu hình môi trường..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[i] Đã tạo file .env mẫu từ .env.example. Vui lòng cập nhật GEMINI_API_KEY nếu cần."
    fi
fi

echo "=================================================================="
echo "🎉 CÀI ĐẶT HOÀN TẤT!"
echo "👉 Để chạy thử 1 video:             .venv/bin/python auto_publisher.py --once"
echo "👉 Để mở Dashboard theo dõi (8080): .venv/bin/python auto_publisher.py --server-only"
echo "👉 Để chạy tự động chu kỳ 4 tiếng:  .venv/bin/python auto_publisher.py"
echo "=================================================================="
