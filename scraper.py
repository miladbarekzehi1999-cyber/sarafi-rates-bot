import os
import sys
import re
import html as html_escape
import requests
import pytz
from bs4 import BeautifulSoup
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"

DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"

KHORASAN_URL_CANDIDATES = [
    "https://sarafi.af/fa/exchange-rates/khorasan-market",
    "https://sarafi.af/fa/exchange-rates/khorasan",
    "https://sarafi.af/fa/exchange-rates/markit-khorasan",
    "https://sarafi.af/fa/exchange-rates/market-khorasan",
]


# =========================
# HTTP SESSION WITH RETRIES
# =========================
def create_session():
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


session = create_session()


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
    return bool(re.fullmatch(r"-?[0-9]+(?:[.,][0-9]+)?%?", value))


def currency_flag(code: str) -> str:
    flags = {
        "USD": "🇺🇸",
        "EUR": "🇪🇺",
        "GBP": "🇬🇧",
        "IRR": "🇮🇷",
        "PKR": "🇵🇰",
        "SAR": "🇸🇦",
        "AED": "🇦🇪",
    }

    return flags.get(str(code).upper(), "💵")


def name_flag(name: str) -> str:
    name = str(name)

    if "دالر" in name or "دلار" in name:
        return "🇺🇸"
    if "یورو" in name:
        return "🇪🇺"
    if "پوند" in name:
        return "🇬🇧"
    if "ایران" in name or "تومان" in name:
        return "🇮🇷"
    if "پاکستان" in name:
        return "🇵🇰"
    if "سعودی" in name:
        return "🇸🇦"
    if "درهم" in name or "امارات" in name:
        return "🇦🇪"

    return "💵"


def fetch_url(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = session.get(url, headers=headers, timeout=30)

        print(f"Fetch {url} => {response.status_code}")

        if response.status_code != 200:
            return None

        return response.text

    except Exception as e:
        print(f"WARNING: Failed to fetch {url}: {e}")
        return None


def fetch_first_working_url(urls):
    for url in urls:
        html = fetch_url(url)
        if html:
            return url, html

    return None, None


def market_is_open(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")

    text = soup.get_text(" ", strip=True).lower()

    closed_words = ["مارکیت بسته", "بازار بسته", "تعطیل", "closed"]

    for word in closed_words:
        if word in text:
            return False

    return True


def split_currency_name(first_cell: str):
    first_cell = clean_text(first_cell)

    if " - " in first_cell:
        left, right = first_cell.split(" - ", 1)
        return clean_text(left), clean_text(right)

    match = re.match(r"^([A-Z]{3})\s+(.+)$", first_cell)

    if match:
        return clean_text(match.group(1)), clean_text(match.group(2))

    return "", first_cell


def extract_rates_from_main_table(html: str):
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")

    if not table:
        return []

    rates = []

    rows = table.find_all("tr")

    for row in rows:
        cols = [
            clean_text(c.get_text(" ", strip=True))
            for c in row.find_all(["td", "th"])
        ]

        if len(cols) < 4:
            continue

        if "خرید" in " ".join(cols):
            continue

        percentage = cols[0]

        numeric = [
            c for c in cols
            if is_number_like(c.replace("%", ""))
        ]

        if len(numeric) < 3:
            continue

        buy = numeric[1]
        sell = numeric[2]

        currency_cell = cols[-1]

        code, name = split_currency_name(currency_cell)

        rates.append(
            {
                "code": code,
                "name": name,
                "buy": buy,
                "sell": sell,
                "percentage": percentage,
            }
        )

    return rates


def extract_rates(html: str):
    return extract_rates_from_main_table(html)


def build_channel_line(channel_link: str):
    if not channel_link:
        return ""

    if channel_link.startswith("http"):
        return f'کانال: <a href="{safe(channel_link)}">{safe(channel_link)}</a>'

    return f"کانال: {safe(channel_link)}"


def format_currency_title(item):
    code = item.get("code", "")
    name = item.get("name", "")

    if code:
        flag = currency_flag(code)
        return f"{flag} <b>{safe(code)}</b> — {safe(name)}"

    flag = name_flag(name)

    return f"{flag} <b>{safe(name)}</b>"


def build_message(title, rates, source_name, source_url, channel_link, icon):
    if not rates:
        return None

    time = get_tehran_time()

    lines = []

    lines.append(f"{icon} <b>{safe(title)}</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")

    for rate in rates:
        lines.append("")
        lines.append(format_currency_title(rate))
        lines.append(f"خرید: <b>{safe(rate['buy'])}</b>")
        lines.append(f"فروش: <b>{safe(rate['sell'])}</b>")
        lines.append(f"%: <b>{safe(rate['percentage'])}</b>")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"🕒 بروزرسانی: {safe(time)} به وقت تهران")
    lines.append("")
    lines.append(f"منبع: {safe(source_name)}")

    if source_url:
        lines.append(f'<a href="{safe(source_url)}">مشاهده منبع</a>')

    channel = build_channel_line(channel_link)

    if channel:
        lines.append(channel)

    return "\n".join(lines)


def send_telegram_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = session.post(url, data=payload, timeout=30)

    print(f"Telegram to {chat_id}: {response.status_code}")

    response.raise_for_status()


def get_chat_ids():
    chat_ids_raw = os.getenv("CHAT_IDS", "").strip()

    if not chat_ids_raw:
        chat_ids_raw = os.getenv("CHAT_ID", "").strip()

    if not chat_ids_raw:
        print("ERROR: Missing CHAT_IDS or CHAT_ID")
        sys.exit(1)

    chat_ids = [
        item.strip()
        for item in chat_ids_raw.split(",")
        if item.strip()
    ]

    return chat_ids


def main():
    bot_token = get_env("BOT_TOKEN")
    chat_ids = get_chat_ids()
    channel_link = get_env("CHANNEL_LINK", required=False)

    messages = []

    # SARAI
    sarai_html = fetch_url(SARAI_URL)

    if sarai_html and market_is_open(sarai_html):
        sarai_rates = extract_rates(sarai_html)
    else:
        sarai_rates = []

    sarai_message = build_message(
        "نرخ اسعار سرای شهزاده",
        sarai_rates,
        "سرای شهزاده",
        SARAI_URL,
        channel_link,
        "💱",
    )

    if sarai_message:
        messages.append(sarai_message)

    # KHORASAN
    kh_url, kh_html = fetch_first_working_url(KHORASAN_URL_CANDIDATES)

    if kh_html and market_is_open(kh_html):
        kh_rates = extract_rates(kh_html)
    else:
        kh_rates = []

    kh_message = build_message(
        "نرخ‌های مارکیت خراسان",
        kh_rates,
        "مارکیت خراسان",
        kh_url or "",
        channel_link,
        "🏪",
    )

    if kh_message:
        messages.append(kh_message)

    # DAB
    dab_html = fetch_url(DAB_URL)

    if dab_html and market_is_open(dab_html):
        dab_rates = extract_rates(dab_html)
    else:
        dab_rates = []

    dab_message = build_message(
        "نرخ‌های د افغانستان بانک",
        dab_rates,
        "د افغانستان بانک",
        DAB_URL,
        channel_link,
        "🏦",
    )

    if dab_message:
        messages.append(dab_message)

    if not messages:
        print("No markets available")
        return

    for chat_id in chat_ids:
        for message in messages:
            send_telegram_message(bot_token, chat_id, message)

    print("Done")


if __name__ == "__main__":
    main()
