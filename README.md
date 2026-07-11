# 📰 News Agent — Bản tin AI/Data Science hàng ngày

Agent tự động thu thập tin tức mới nhất về AI, Machine Learning, Data Science từ nhiều nguồn uy tín, dùng Gemini AI để lọc và tóm tắt bằng tiếng Việt, rồi gửi thẳng vào email mỗi ngày — không cần bật máy, không cần đụng tay.

## Cách hoạt động

```
RSS feeds (arXiv, TechCrunch, Wired, VentureBeat...) 
    → Gemini lọc tin đáng chú ý + tóm tắt tiếng Việt 
    → Gửi email 
    → (GitHub Actions chạy tự động mỗi ngày 9h sáng giờ VN)
```

## Nguồn tin đang dùng

- arXiv cs.AI / cs.LG (paper nghiên cứu mới)
- Google AI Blog
- MIT Technology Review - AI
- VentureBeat AI
- TechCrunch AI
- Wired AI
- Hacker News (tin AI được cộng đồng dev upvote ≥ 50 điểm)

Muốn thêm/bớt nguồn: sửa dictionary `FEEDS` trong `news_agent.py`.

## Cài đặt (chạy lần đầu trên máy)

### 1. Cài thư viện
```bash
pip3 install -r requirements.txt
```

### 2. Tạo file `.env` (không commit lên GitHub)
```
GEMINI_API_KEY=key-lấy-từ-aistudio.google.com
EMAIL_ADDRESS=email-gmail-dùng-để-gửi@gmail.com
EMAIL_APP_PASSWORD=16-ký-tự-app-password
EMAIL_TO=email-muốn-nhận-bản-tin
```

Lấy `EMAIL_APP_PASSWORD` tại **myaccount.google.com/apppasswords** (cần bật xác thực 2 bước trước).

### 3. Chạy thử
```bash
python3 news_agent.py
```

## Tự động hoá (chạy mỗi ngày, không cần bật máy)

1. Push code lên GitHub (repo này)
2. Vào **Settings → Secrets and variables → Actions**, thêm 4 secrets: `GEMINI_API_KEY`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `EMAIL_TO`
3. GitHub Actions (`.github/workflows/daily_digest.yml`) sẽ tự chạy **9h sáng giờ Việt Nam mỗi ngày**
4. Test chạy tay không cần đợi: vào tab **Actions** → **Daily AI/DS News Digest** → **Run workflow**

## Cấu trúc project

```
news-agent/
├── .github/workflows/daily_digest.yml   # lịch chạy tự động
├── news_agent.py                        # script chính
├── requirements.txt                     # thư viện cần cài
├── .env                                 # key bí mật (KHÔNG commit, đã có trong .gitignore)
└── digests/                             # nơi lưu lại bản tin từng ngày (tự tạo khi chạy)
```

## Ghi chú

- Cửa sổ thời gian lấy tin: 24 giờ gần nhất (đổi ở `fetch_recent_entries(hours=24)` trong `news_agent.py` nếu muốn).
- Toàn bộ nội dung (tóm tắt, tiêu đề dịch, lý do đáng chú ý) đều bằng tiếng Việt; tiêu đề gốc tiếng Anh vẫn giữ lại để dễ tra cứu.
- Nếu 1 nguồn nào đó lỗi khi chạy, log sẽ in `⚠ Lỗi đọc nguồn ...` — các nguồn khác vẫn chạy bình thường, không ảnh hưởng nhau.
