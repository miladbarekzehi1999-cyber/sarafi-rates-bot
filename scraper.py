import os
import sys
import re
import html as html_escape
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime

SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"
DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"
KHORASAN_URL_CANDIDATES = [
    "https://sarafi.af/fa/exchange-rates/khorasan-market",
    "https://sarafi.af/fa/exchange-rates/khorasan",
    "https://sarafi.af/fa/exchange-rates/markit-khorasan",
    "https://sarafi.af/fa/exchange-rates/market-khorasan",
]

def get_env(name: str, required: bool = True) -> str:
    value = os.getenv(name)
    if required and not value:
        print(f"ERROR: Missing environment variable: {name}")
        sys.exit(1)
    return value or ""

def clean_text(text: str) -> str:
    return " ".join(str(text).split()).strip()

def safe(text) -> str:
    return html_escape.escape(str(text), quote=False)

def get_tehran_time() -> str:
    tehran = pytz.timezone("Asia/Tehran")
    return datetime.now(tehran).strftime("%Y-%m-%d %H:%M")

def is_number_like(value: str) -> bool:
    value = clean_text(value)
    return bool(re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", value))

def currency_flag(code: str) -> str:
    flags = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "IRR": "🇮🇷", "PKR": "🇵🇰", "SAR": "🇸🇦", "AED": "🇦🇪"}
    return flags.get(str(code).upper(), "💵")

def name_flag(name: str) -> str:
    if "دالر" in name or "دلار" in name: return "🇺🇸"
    if "یورو" in name: return "🇪🇺"
    if "پوند" in name: return "🇬🇧"
    if "ایران" in name or "تومان" in name: return "🇮🇷"
    if "پاکستان" in name: return "🇵🇰"
    if "سعودی" in name: return "🇸🇦"
    if "درهم" in name or "امارات" in name: return "🇦🇪"
    return "💵"

def fetch_url(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        return response.text if response.status_code == 200 else None
    except:
        return None

def fetch_first_working_url(urls):
    for url in urls:
        html = fetch_url(url)
        if html: return url, html
    return None, None

def market_is_open(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True).lower()
    for word in ["مارکیت بسته", "بازار بسته", "تعطیل", "closed"]:
        if word in text: return False
    return True

def split_currency_name(first_cell: str):
    first_cell = clean_text(first_cell)
    if " - " in first_cell:
        left, right = first_cell.split(" - ", 1)
        return clean_text(left), clean_text(right)
    match = re.match(r"^([A-Z]{3})\s+(.+)$", first_cell)
    if match: return clean_text(match.group(1)), clean_text(match.group(2))
    return "", first_cell

def extract_rates_from_main_table(html: str):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table: return []
    rates = []
    rows = table.find_all("tr")
    for row in rows:
        cols = [clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]
        if len(cols) < 3 or "خرید" in " ".join(cols): continue
        
        # Identify numeric indexes
        nums = [i for i, c in enumerate(cols) if is_number_like(c)]
        if len(nums) < 2: continue

        # On the website, Change % is usually at index 0 (the first column)
        change_text = cols[0].replace("%", "").strip()
        change_val = 0.0
        try: change_val = float(change_text)
        except: pass

        buy = cols[nums[0]]
        sell = cols[nums[1]]
        
        # Find currency name (usually near the end or start)
        first = cols[-1] if not is_number_like(cols[-1]) else cols[1]
        code, name = split_currency_name(first)
        if not name: continue

        rates.append({
            "code": code,
            "name": name,
            "buy": buy,
            "sell": sell,
            "change": f"{change_val}%",
            "trend": "🟢" if change_val > 0 else ("🔴" if change_val < 0 else "⚪")
        })
    return rates

def build_message(title, rates, source_name, source_url, channel_link, icon):
    if not rates: return None
    time = get_tehran_time()
    lines = [f"{icon} <b>{safe(title)}</b>", "", "━━━━━━━━━━━━━━"]
    for rate in rates:
        lines.append("")
        lines.append(format_currency_title(rate))
        lines.append(f"خرید: <b>{safe(rate['buy'])}</b>")
        lines.append(f"فروش: <b>{safe(rate['sell'])}</b>")
        lines.append(f"تغییرات: {rate['trend']} <b>{safe(rate['change'])}</b>")
    
    lines.extend(["", "━━━━━━━━━━━━━━", f"🕒 بروزرسانی: {safe(time)}", f"منبع: {safe(source_name)}"])
    if channel_link: lines.append(f"کانال: {safe(channel_link)}")
    return "\n".join(lines)

def format_currency_title(item):
    code, name = item.get("code", ""), item.get("name", "")
    flag = currency_flag(code) if code else name_flag(name)
    title = f"<b>{safe(code)}</b> — {safe(name)}" if code else f"<b>{safe(name)}</b>"
    return f"{flag} {title}"

def send_telegram_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    requests.post(url, data=payload, timeout=30)

def main():
    bot_token = get_env("BOT_TOKEN")
    chat_ids = os.getenv("CHAT_IDS", "").split(",")
    channel_link = os.getenv("CHANNEL_LINK", "")
    
    # Process Markets
    sources = [
        (SARAI_URL, "نرخ اسعار سرای شهزاده", "سرای شهزاده", "💱"),
        (DAB_URL, "نرخ‌های د افغانستان بانک", "د افغانستان بانک", "🏦")
    ]

    messages = []
    for url, title, name, icon in sources:
        html = fetch_url(url)
        if html and market_is_open(html):
            rates = extract_rates_from_main_table(html)
            msg = build_message(title, rates, name, url, channel_link, icon)
            if msg: messages.append(msg)

    # Send
    for chat_id in chat_ids:
        for m in messages:
            send_telegram_message(bot_token, chat_id.strip(), m)

if __name__ == "__main__":
    main()
