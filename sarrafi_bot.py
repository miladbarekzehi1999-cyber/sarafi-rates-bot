import os
import html
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Sources
SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"
DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"
KHORASAN_URLS = [
    "https://sarafi.af/fa/exchange-rates/khorasan-market",
    "https://sarafi.af/fa/exchange-rates/khorasan",
]

def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"})
    return session

session = create_session()

def get_tehran_time():
    return datetime.now(pytz.timezone("Asia/Tehran"))

def parse_rates(url):
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.find("table")
        if not table: return []
        
        data = []
        rows = table.find_all("tr")
        
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            
            # Skip header rows
            if not cols or "خرید" in cols[0] or "خرید" in "".join(cols):
                continue
            
            if len(cols) >= 4:
                # The logic to fix the column shift:
                # Standard: [%] [Buy] [Sell] [Currency]
                # If first column is empty or looks like a currency name, we adjust.
                
                percent = cols[0]
                buy = cols[1]
                sell = cols[2]
                currency = cols[3]

                # Validation: if percent has letters, it's probably the currency (Shifted table)
                if any(c.isalpha() for c in percent):
                    currency = percent
                    percent = "---" # No percentage available for this source

                data.append({
                    "pc": percent,
                    "buy": buy,
                    "sell": sell,
                    "cur": currency
                })
        return data
    except Exception as e:
        print(f"Error parsing {url}: {e}")
        return []

def build_msg(title, rates, source_name, source_url, channel):
    if not rates: return None
    t_now = get_tehran_time().strftime("%Y-%m-%d %H:%M")
    
    # Use emoji based on source
    icon = "🏦" if "بانک" in source_name else "💱"
    if "خراسان" in source_name: icon = "🏪"

    lines = [f"{icon} <b>{title}</b>", "━━━━━━━━━━━━━━"]
    
    for r in rates:
        lines.append(f"\n<b>{r['cur']}</b>")
        lines.append(f"خرید: <b>{r['buy']}</b>")
        lines.append(f"فروش: <b>{r['sell']}</b>")
        # Only show percentage if it's a real value
        if r['pc'] != "---":
            lines.append(f"%: <b>{r['pc']}</b>")
            
    lines.extend(["\n━━━━━━━━━━━━━━", f"🕒 {t_now}", f'منبع: <a href="{source_url}">{source_name}</a>'])
    if channel:
        # Clean channel link for display
        display_channel = channel.split("/")[-1] if "/" in channel else channel
        lines.append(f'کانال: <a href="{channel}">@{display_channel}</a>')
        
    return "\n".join(lines)

def main():
    now = get_tehran_time()
    # Market Hours: 08:00 AM to 05:00 PM (17:00)
    if now.hour < 8 or now.hour > 17:
        print("Market is closed.")
        return 

    bot_token = os.getenv("BOT_TOKEN")
    chats = [c.strip() for c in (os.getenv("CHAT_IDS") or "").split(",") if c.strip()]
    channel = os.getenv("CHANNEL_LINK")

    if not bot_token or not chats:
        print("Missing Credentials")
        return

    is_closing = (now.hour == 17)
    
    # List of tasks: (URL, Source Name, Display Name)
    tasks = [
        (SARAI_URL, "سرای شهزاده", "سرای شهزاده"),
        (DAB_URL, "د افغانستان بانک", "د افغانستان بانک"),
    ]
    
    # Try to find working Khorasan URL
    for k_url in KHORASAN_URLS:
        k_data = parse_rates(k_url)
        if k_data:
            tasks.append((k_url, "مارکیت خراسان", "مارکیت خراسان"))
            break

    messages = []
    for url, full_name, display_name in tasks:
        title = f"قیمت بسته شدن {display_name}" if is_closing else f"نرخ‌های {display_name}"
        data = parse_rates(url)
        msg = build_msg(title, data, full_name, url, channel)
        if msg:
            messages.append(msg)

    for chat in chats:
        for m in messages:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage", 
                    data={"chat_id": chat, "text": m, "parse_mode": "HTML", "disable_web_page_preview": True},
                    timeout=20
                )
            except:
                continue

if __name__ == "__main__":
    main()
