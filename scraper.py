import os
import sys
import html
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# URL Sources
SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"
DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"
KHORASAN_URLS = [
    "https://sarafi.af/fa/exchange-rates/khorasan-market",
    "https://sarafi.af/fa/exchange-rates/khorasan",
    "https://sarafi.af/fa/exchange-rates/markit-khorasan",
]

# ---------- HTTP SESSION WITH RETRIES ----------
def create_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Add a real browser User-Agent to avoid blocks
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session

session = create_session()

# ---------- UTILS ----------
def tehran_now():
    tz = pytz.timezone("Asia/Tehran")
    return datetime.now(tz)

def market_status():
    now = tehran_now()
    hour = now.hour
    if hour < 8 or hour > 17:
        return "closed"
    if hour == 17:
        return "closing"
    return "open"

# ---------- SCRAPING ----------
def fetch(url):
    try:
        r = session.get(url, timeout=30)
        return r.text if r.status_code == 200 else None
    except:
        return None

def parse_rates(html_content):
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, "lxml")
    table = soup.find("table")
    if not table:
        return []
    
    rates = []
    for row in table.find_all("tr"):
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue
        
        # Columns: [0]% | [1]Buy | [2]Sell | [3]Currency
        percent, buy, sell, currency = cols[0], cols[1], cols[2], cols[3]
        
        if "خرید" in percent or not buy:
            continue
            
        rates.append({
            "currency": currency,
            "buy": buy,
            "sell": sell,
            "percent": percent
        })
    return rates

# ---------- MESSAGING ----------
def build_message(title, rates, source, url, channel, icon):
    if not rates:
        return None
    
    lines = [f"{icon} <b>{html.escape(title)}</b>", "", "━━━━━━━━━━━━━━"]
    for r in rates:
        lines.append(f"\n<b>{html.escape(r['currency'])}</b>")
        lines.append(f"خرید: <b>{r['buy']}</b>")
        lines.append(f"فروش: <b>{r['sell']}</b>")
        lines.append(f"%: <b>{r['percent']}</b>")
    
    lines.append("\n━━━━━━━━━━━━━━")
    lines.append(f"🕒 {tehran_now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f'منبع: <a href="{url}">{source}</a>')
    if channel:
        lines.append(f'کانال: <a href="{channel}">{channel.split("/")[-1]}</a>')
    
    return "\n".join(lines)

def send_telegram(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        session.post(url, data=payload, timeout=20)
    except Exception as e:
        print(f"Error sending to {chat_id}: {e}")

# ---------- MAIN ----------
def main():
    status = market_status()
    if status == "closed":
        print("Market is closed. No broadcast.")
        return

    bot_token = os.getenv("BOT_TOKEN")
    # Supports single ID or comma-separated list
    raw_chats = os.getenv("CHAT_IDS") or os.getenv("CHAT_ID")
    if not bot_token or not raw_chats:
        print("Missing BOT_TOKEN or CHAT_IDS")
        return
    
    chats = [c.strip() for c in raw_chats.split(",") if c.strip()]
    channel = os.getenv("CHANNEL_LINK", "")

    # Define Titles
    if status == "closing":
        titles = ["قیمت بسته شدن شهزاده", "قیمت بسته شدن خراسان", "قیمت بسته شدن DAB"]
    else:
        titles = ["نرخ اسعار سرای شهزاده", "نرخ‌های مارکیت خراسان", "نرخ‌های د افغانستان بانک"]

    results = []
    
    # 1. Sarai Shahzada
    sarai_data = parse_rates(fetch(SARAI_URL))
    if sarai_data:
        results.append(build_message(titles[0], sarai_data, "سرای شهزاده", SARAI_URL, channel, "💱"))

    # 2. Khorasan
    kh_html = None
    curr_url = KHORASAN_URLS[0]
    for url in KHORASAN_URLS:
        html_text = fetch(url)
        if html_text:
            kh_html = html_text
            curr_url = url
            break
    kh_data = parse_rates(kh_html)
    if kh_data:
        results.append(build_message(titles[1], kh_data, "مارکیت خراسان", curr_url, channel, "🏪"))

    # 3. DAB
    dab_data = parse_rates(fetch(DAB_URL))
    if dab_data:
        results.append(build_message(titles[2], dab_data, "د افغانستان بانک", DAB_URL, channel, "🏦"))

    # Send all valid messages
    for chat in chats:
        for msg in results:
            if msg:
                send_telegram(bot_token, chat, msg)

if __name__ == "__main__":
    main()
