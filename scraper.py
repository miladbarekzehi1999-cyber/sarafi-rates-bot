import os
import sys
import re
import html as html_escape
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone


SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"

# You gave this URL, so we scrape Da Afghanistan Bank from here directly
DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"

# I added several possible Khorasan URLs.
# If one is correct, the bot will use it automatically.
# If none works, Sarai + Da Afghanistan Bank will still send.
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
    """
    Escape text for Telegram HTML parse mode.
    """
    return html_escape.escape(str(text), quote=False)


def is_number_like(value: str) -> bool:
    """
    Checks if text looks like a price/rate.
    Examples:
    64.30
    1,230
    930.50
    """
    value = clean_text(value)
    return bool(re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", value))


def currency_flag(code: str) -> str:
    flags = {
        "USD": "🇺🇸",
        "EUR": "🇪🇺",
        "GBP": "🇬🇧",
        "IRR": "🇮🇷",
        "PKR": "🇵🇰",
        "SAR": "🇸🇦",
        "AED": "🇦🇪",
        "CHF": "🇨🇭",
        "AUD": "🇦🇺",
        "CAD": "🇨🇦",
        "RUB": "🇷🇺",
        "DKK": "🇩🇰",
        "SEK": "🇸🇪",
        "NOK": "🇳🇴",
        "TRY": "🇹🇷",
        "CNY": "🇨🇳",
        "KWD": "🇰🇼",
        "QAR": "🇶🇦",
        "BHD": "🇧🇭",
        "JPY": "🇯🇵",
        "INR": "🇮🇳",
    }

    return flags.get(str(code).upper(), "💵")


def name_flag(name: str) -> str:
    name = str(name)

    if "دالر آمریکا" in name or "دالر امريکا" in name:
        return "🇺🇸"
    if "یورو" in name:
        return "🇪🇺"
    if "پوند" in name:
        return "🇬🇧"
    if "تومان" in name or "ایران" in name:
        return "🇮🇷"
    if "روپیه پاکستان" in name:
        return "🇵🇰"
    if "روپیه هند" in name:
        return "🇮🇳"
    if "ریال سعودی" in name:
        return "🇸🇦"
    if "درهم" in name:
        return "🇦🇪"
    if "فرانک" in name:
        return "🇨🇭"
    if "آسترالیا" in name:
        return "🇦🇺"
    if "کانادا" in name:
        return "🇨🇦"
    if "روبل" in name:
        return "🇷🇺"
    if "دنمارک" in name:
        return "🇩🇰"
    if "سویدن" in name:
        return "🇸🇪"
    if "ناروی" in name:
        return "🇳🇴"
    if "ترکیه" in name:
        return "🇹🇷"
    if "چین" in name:
        return "🇨🇳"
    if "کویت" in name:
        return "🇰🇼"
    if "قطر" in name:
        return "🇶🇦"
    if "بحرین" in name:
        return "🇧🇭"
    if "جاپان" in name:
        return "🇯🇵"

    return "💵"


def fetch_url(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
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


def split_currency_name(first_cell: str):
    """
    Handles:
    USD - دالر آمریکا
    USD دالر آمریکا
    دالر آمریکا
    """
    first_cell = clean_text(first_cell)

    code = ""
    name = first_cell

    if " - " in first_cell:
        left, right = first_cell.split(" - ", 1)
        code = clean_text(left)
        name = clean_text(right)
        return code, name

    match = re.match(r"^([A-Z]{3})\s+(.+)$", first_cell)
    if match:
        code = clean_text(match.group(1))
        name = clean_text(match.group(2))
        return code, name

    return code, name


def extract_rates_from_tables(html: str):
    """
    Extracts rates from normal HTML tables.

    Supported table rows:
    USD - دالر آمریکا | 64.30 | 64.35
    دالر آمریکا | 64.26 | 64.46
    USD دالر آمریکا | 64.26 | 64.46
    """
    soup = BeautifulSoup(html, "lxml")
    rates = []

    for tr in soup.find_all("tr"):
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["td", "th"])
        ]

        cells = [cell for cell in cells if cell]

        if len(cells) < 3:
            continue

        first = cells[0]
        second = cells[1]
        third = cells[2]

        # Skip headers
        header_words = ["واحد پول", "خرید", "فروش", "Currency", "Buy", "Sell"]
        if any(word in first for word in header_words):
            continue

        if not is_number_like(second) or not is_number_like(third):
            continue

        code, name = split_currency_name(first)

        if not name:
            continue

        rates.append(
            {
                "code": code,
                "name": name,
                "buy": second,
                "sell": third,
            }
        )

    return dedupe_rates(rates)


def extract_rates_from_text(html: str):
    """
    Fallback parser for text patterns like:
    دالر آمریکا 64.60 | 64.65
    یورو اروپا 74.30 | 74.50
    """
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text("\n", strip=True)

    lines = [clean_text(line) for line in page_text.splitlines()]
    lines = [line for line in lines if line]

    rates = []

    for line in lines:
        if "|" not in line:
            continue

        parts = [clean_text(x) for x in line.split("|")]

        if len(parts) < 2:
            continue

        left = parts[0]
        sell = parts[1]

        match = re.match(r"^(.*?)\s+([0-9]+(?:[.,][0-9]+)?)$", left)

        if not match:
            continue

        name = clean_text(match.group(1))
        buy = clean_text(match.group(2))
        sell = clean_text(sell)

        if not name or not is_number_like(buy) or not is_number_like(sell):
            continue

        code, real_name = split_currency_name(name)

        rates.append(
            {
                "code": code,
                "name": real_name,
                "buy": buy,
                "sell": sell,
            }
        )

    return dedupe_rates(rates)


def dedupe_rates(rates):
    """
    Remove duplicate rows.
    """
    seen = set()
    result = []

    for item in rates:
        key = (
            item.get("code", ""),
            item.get("name", ""),
            item.get("buy", ""),
            item.get("sell", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def extract_rates(html: str):
    """
    First tries tables.
    If tables fail, tries text fallback.
    """
    table_rates = extract_rates_from_tables(html)

    if table_rates:
        return table_rates

    return extract_rates_from_text(html)


def build_channel_line(channel_link: str) -> str:
    if not channel_link:
        return ""

    if channel_link.startswith("http://") or channel_link.startswith("https://"):
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


def build_message(title: str, rates, source_name: str, source_url: str, channel_link: str, icon: str):
    if not rates:
        return None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"{icon} <b>{safe(title)}</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")

    for item in rates:
        buy = item["buy"]
        sell = item["sell"]

        lines.append("")
        lines.append(format_currency_title(item))
        lines.append(f"🟢 خرید: <b>{safe(buy)}</b>")
        lines.append(f"🔴 فروش: <b>{safe(sell)}</b>")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"🕒 بروزرسانی: {safe(now_utc)}")
    lines.append("")
    lines.append(f"منبع: {safe(source_name)}")

    if source_url:
        lines.append(f'لینک منبع: <a href="{safe(source_url)}">مشاهده</a>')

    channel_line = build_channel_line(channel_link)
    if channel_line:
        lines.append(channel_line)

    return "\n".join(lines)


def send_telegram_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = requests.post(url, data=payload, timeout=30)

    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)

    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def main():
    bot_token = get_env("BOT_TOKEN")
    chat_id = get_env("CHAT_ID")
    channel_link = get_env("CHANNEL_LINK", required=False)

    messages = []

    # 1. Sarai Shahzada
    sarai_html = fetch_url(SARAI_URL)

    if sarai_html:
        sarai_rates = extract_rates(sarai_html)
    else:
        sarai_rates = []

    print(f"Sarai Shahzada rates extracted: {len(sarai_rates)}")

    sarai_message = build_message(
        title="نرخ اسعار سرای شهزاده",
        rates=sarai_rates,
        source_name="سرای شهزاده",
        source_url=SARAI_URL,
        channel_link=channel_link,
        icon="💱",
    )

    if sarai_message:
        messages.append(sarai_message)

    # 2. Khorasan Market
    khorasan_url, khorasan_html = fetch_first_working_url(KHORASAN_URL_CANDIDATES)

    if khorasan_html:
        khorasan_rates = extract_rates(khorasan_html)
    else:
        khorasan_rates = []

    print(f"Khorasan URL used: {khorasan_url}")
    print(f"Khorasan rates extracted: {len(khorasan_rates)}")

    khorasan_message = build_message(
        title="نرخ‌های مارکیت خراسان",
        rates=khorasan_rates,
        source_name="مارکیت خراسان",
        source_url=khorasan_url or "",
        channel_link=channel_link,
        icon="🏪",
    )

    if khorasan_message:
        messages.append(khorasan_message)
    else:
        print("WARNING: Khorasan message not generated. Need exact Khorasan URL if this stays 0.")

    # 3. Da Afghanistan Bank
    dab_html = fetch_url(DAB_URL)

    if dab_html:
        dab_rates = extract_rates(dab_html)
    else:
        dab_rates = []

    print(f"Da Afghanistan Bank rates extracted: {len(dab_rates)}")

    dab_message = build_message(
        title="نرخ‌های د افغانستان بانک",
        rates=dab_rates,
        source_name="د افغانستان بانک",
        source_url=DAB_URL,
        channel_link=channel_link,
        icon="🏦",
    )

    if dab_message:
        messages.append(dab_message)

    if not messages:
        print("ERROR: No messages generated.")
        sys.exit(1)

    for index, message in enumerate(messages, start=1):
        print(f"Sending message {index}/{len(messages)}")
        send_telegram_message(bot_token, chat_id, message)

    print("Done.")


if __name__ == "__main__":
    main()
