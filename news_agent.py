"""
News Agent - thu thập tin tức AI/Data Science mỗi ngày, tóm tắt bằng Gemini,
lưu vào digest_latest.json và gửi email.
Chạy: python3 news_agent.py
"""

import os
import json
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import feedparser
import ssl
import certifi
import urllib.request
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from dotenv import load_dotenv

# Một số trang chặn request có "danh tính" mặc định của feedparser -> giả làm trình duyệt thật
feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dùng bộ chứng chỉ SSL của certifi thay vì chứng chỉ hệ thống (hay bị thiếu trên Mac)
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") )

# Các nguồn tin miễn phí, không cần API key, uy tín cho AI/Data Science
FEEDS = {
    "arXiv cs.AI": "http://export.arxiv.org/rss/cs.AI",
    "arXiv cs.LG (Machine Learning)": "http://export.arxiv.org/rss/cs.LG",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    "MIT Technology Review - AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "Hacker News (Top AI mentions)": "https://hnrss.org/newest?q=AI+OR+%22machine+learning%22&points=50",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
}

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string"},
        "headline_summary": {"type": "string", "description": "2-3 câu tóm tắt xu hướng nổi bật nhất hôm nay"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Tiêu đề GỐC bằng tiếng Anh, giữ nguyên"},
                    "title_vi": {"type": "string", "description": "Tiêu đề dịch sang tiếng Việt, tự nhiên"},
                    "source": {"type": "string"},
                    "url": {"type": "string"},
                    "summary_vi": {"type": "string", "description": "Tóm tắt bằng tiếng Việt, 2-3 câu"},
                    "why_it_matters": {"type": "string", "description": "1 câu: vì sao đáng chú ý với sinh viên ngành AI/Data Science"},
                },
                "required": ["title", "title_vi", "source", "url", "summary_vi", "why_it_matters"],
            },
        },
    },
    "required": ["date", "headline_summary", "articles"],
}


def fetch_recent_entries(hours: int = 24) -> list:
    """Lấy các bài viết mới trong X giờ gần đây từ tất cả các nguồn."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    entries = []

    for source_name, url in FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": feedparser.USER_AGENT})
            raw = urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT).read()
            feed = feedparser.parse(raw)

            found_in_source = 0
            for entry in feed.entries[:15]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                entries.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "raw_summary": entry.get("summary", "")[:500],
                })
                found_in_source += 1
            print(f"  [{source_name}] tổng {len(feed.entries)} mục, lấy {found_in_source} mục mới")
        except Exception as e:
            print(f"  ⚠ Lỗi đọc nguồn {source_name}: {e}")

    return entries


# Mã lỗi HTTP tạm thời, đáng để thử lại (server quá tải, rate limit, timeout)
RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _call_gemini_with_retry(prompt: str, max_retries: int = 5, base_delay: float = 5.0):
    """Gọi Gemini với retry + exponential backoff cho lỗi tạm thời (vd. 503 UNAVAILABLE)."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DIGEST_SCHEMA,
                ),
            )
        except genai_errors.APIError as e:
            last_error = e
            if e.code not in RETRIABLE_STATUS_CODES or attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"  ⚠ Gemini lỗi {e.code} {e.status} (lần {attempt}/{max_retries}), thử lại sau {delay:.0f}s...")
            time.sleep(delay)
    raise last_error


def curate_digest(entries: list) -> dict:
    """Dùng Gemini lọc ra các tin đáng chú ý nhất và tóm tắt tiếng Việt."""
    entries_text = "\n\n".join(
        f"[{e['source']}] {e['title']}\nURL: {e['url']}\n{e['raw_summary']}"
        for e in entries
    )

    prompt = (
        f"Hôm nay là {datetime.now().strftime('%Y-%m-%d')}. Dưới đây là danh sách các bài viết/paper "
        f"mới nhất về AI, Machine Learning, Data Science từ nhiều nguồn (bằng tiếng Anh):\n\n{entries_text}\n\n"
        "Hãy chọn ra 6-10 tin ĐÁNG CHÚ Ý NHẤT (ưu tiên: breakthrough nghiên cứu mới, sản phẩm/model AI "
        "mới ra mắt, xu hướng ngành quan trọng — bỏ qua tin trùng lặp, tin quá nhỏ lẻ, tin quảng cáo).\n\n"
        "QUAN TRỌNG VỀ NGÔN NGỮ: TOÀN BỘ nội dung bạn viết ra (summary_vi, why_it_matters, "
        "headline_summary) PHẢI bằng tiếng Việt hoàn toàn, tự nhiên, dễ đọc — không lẫn tiếng Anh "
        "trừ tên riêng (tên công ty, tên model, tên người). Chỉ riêng trường 'title' thì GIỮ NGUYÊN "
        "tiếng Anh gốc (để khớp với link gốc).\n\n"
        "Với mỗi tin: tóm tắt bằng tiếng Việt (2-3 câu, dễ hiểu, không dịch máy móc), và giải thích "
        "1 câu tiếng Việt vì sao sinh viên ngành AI/Data Science nên quan tâm. Viết thêm 2-3 câu tiếng "
        "Việt tóm tắt xu hướng nổi bật nhất trong toàn bộ tin hôm nay (headline_summary)."
    )

    response = _call_gemini_with_retry(prompt)
    return json.loads(response.text)


def send_email(digest: dict):
    sender = os.environ.get("EMAIL_ADDRESS")
    app_password = os.environ.get("EMAIL_APP_PASSWORD")
    recipient = os.environ.get("EMAIL_TO", sender)

    if not sender or not app_password:
        print("  (Chưa cấu hình email, bỏ qua bước gửi mail)")
        return

    html_articles = ""
    for a in digest["articles"]:
        html_articles += f"""
        <div style="margin-bottom:20px;padding:16px;border-left:3px solid #2563EB;background:#F8FAFC;">
          <div style="font-size:11px;color:#64748B;text-transform:uppercase;">{a['source']}</div>
          <a href="{a['url']}" style="font-size:16px;font-weight:bold;color:#1E3A8A;text-decoration:none;">{a['title_vi']}</a>
          <div style="font-size:12px;color:#94A3B8;font-style:italic;margin-top:2px;">{a['title']}</div>
          <p style="margin:8px 0 4px 0;color:#334155;">{a['summary_vi']}</p>
          <p style="margin:0;font-size:13px;color:#0D9488;font-style:italic;">💡 {a['why_it_matters']}</p>
        </div>
        """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#1E3A8A;">📰 Bản tin AI/Data Science - {digest['date']}</h2>
      <p style="color:#475569;font-style:italic;">{digest['headline_summary']}</p>
      <hr style="border:none;border-top:1px solid #E2E8F0;margin:20px 0;">
      {html_articles}
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 AI/Data Science Digest - {digest['date']}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"  ✓ Đã gửi email tới {recipient}")


if __name__ == "__main__":
    print("Đang thu thập tin tức...")
    entries = fetch_recent_entries(hours=30)
    print(f"  Tìm thấy {len(entries)} bài viết mới.")

    if not entries:
        print("Không có tin mới, dừng.")
    else:
        # Lưu tạm các bài đã fetch trước khi gọi Gemini, để không mất dữ liệu
        # nếu Gemini lỗi (vd. 503 UNAVAILABLE) sau khi đã hết lượt retry.
        os.makedirs("digests", exist_ok=True)
        raw_entries_path = "digests/raw_entries_latest.json"
        with open(raw_entries_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        print("Đang lọc và tóm tắt bằng Gemini...")
        try:
            digest = curate_digest(entries)
        except genai_errors.APIError as e:
            print(f"  ✗ Gemini lỗi {e.code} {e.status} sau khi đã thử lại nhiều lần.")
            print(f"  Danh sách {len(entries)} bài viết đã fetch được lưu tại {raw_entries_path}, không bị mất.")
            raise
        digest["date"] = datetime.now().strftime("%Y-%m-%d")

        os.makedirs("digests", exist_ok=True)
        with open(f"digests/digest_{digest['date']}.json", "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
        with open("digests/digest_latest.json", "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Đã lưu {len(digest['articles'])} tin vào digests/digest_{digest['date']}.json")

        print("Đang gửi email...")
        send_email(digest)

        print("🎉 Xong.")