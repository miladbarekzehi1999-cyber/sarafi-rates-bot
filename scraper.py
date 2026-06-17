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
        "TRY": "🇹🇷",
        "CNY": "🇨🇳",
        "JPY": "🇯🇵",
        "INR": "🇮🇳",
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
    if "هند" in name:
        return "🇮🇳"
    if "سعودی" in name:
        return "🇸🇦"
    if "درهم" in name or "امارات" in name:
        return "🇦🇪"

    return "💵"


def fetch_url(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        print(f"Fetch {url} => {r.status_code}")

        if r.status_code != 200:
            return None

        return r.text

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
    """
    Detects whether the market page says the market is open or closed.

    If status is unclear, we assume OPEN so that the scraper does not miss data
    because of a wording/layout change.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True).lower()

    closed_words = [
        "مارکیت بسته",
        "بازار بسته",
        "تعطیل",
        "بسته است",
        "closed",
    ]

    open_words = [
        "مارکیت باز",
        "بازار باز",
        "باز است",
        "open",
    ]

    for word in closed_words:
        if word in text:
            print("Market detected as CLOSED")
            return False

    for word in open_words:
        if word in text:
            print("Market detected as OPEN")
            return True

    print("Market status unclear — assuming OPEN")
    return True


def split_currency_name(first_cell: str):
    """
    Splits something like:
    USD - دالر آمریکا
    or
    USD دالر آمریکا

    into:
    code = USD
    name = دالر آمریکا
    """
    first_cell = clean_text(first_cell)

    if " - " in first_cell:
        left, right = first_cell.split(" - ", 1)
        return clean_text(left), clean_text(right)

    match = re.match(r"^([A-Z]{3})\s+(.+)$", first_cell)
    if match:
        return clean_text(match.group(1)), clean_text(match.group(2))

    return "", first_cell


def normalize_region(region: str) -> str:
    region = clean_text(region)

    replacements = {
        "مارکیت خراسان": "مارکیت خراسان",
        "خراسان": "مارکیت خراسان",
        "تهران": "تهران",
        "دوبی": "دوبی",
        "دبی": "دوبی",
    }

    for key, value in replacements.items():
        if key in region:
            return value

    return region


def extract_rates_from_main_table(html: str):
    """
    Extracts rates from the main HTML table.

    Expected columns may include:
    currency/name, buy, sell, time, change, status, region

    The site is RTL, so depending on the HTML structure, visible order can be confusing.
    This parser tries to be flexible:
    - finds numeric buy/sell cells
    - stores the first text as currency name
    - stores possible region from the last non-empty text cell
    """
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")

    if not table:
        print("WARNING: No table found")
        return []

    rates = []
    rows = table.find_all("tr")

    for row in rows:
        cols = [
            clean_text(c.get_text(" ", strip=True))
            for c in row.find_all(["td", "th"])
        ]

        cols = [c for c in cols if c]

        if len(cols) < 3:
            continue

        # Skip header rows
        joined = " ".join(cols)
        if "خرید" in joined and "فروش" in joined:
            continue

        # Find all number-like cells
        numeric_indexes = [
            i for i, c in enumerate(cols)
            if is_number_like(c)
        ]

        if len(numeric_indexes) < 2:
            continue

        # Usually buy and sell are the first two numeric cells after currency name
        buy_idx = numeric_indexes[0]
        sell_idx = numeric_indexes[1]

        buy = cols[buy_idx]
        sell = cols[sell_idx]

        # Currency name is usually before buy/sell or one of edge cells in RTL layouts.
        # First try the cell before buy.
        first = ""

        if buy_idx > 0:
            first = cols[buy_idx - 1]

        # If that does not look like a currency/name, try first or last cells.
        if not first or is_number_like(first):
            first = cols[0]

        # In some RTL tables, currency name can be the last column.
        if (
            "دالر" not in first
            and "دلار" not in first
            and "درهم" not in first
            and "یورو" not in first
            and "پوند" not in first
            and len(cols) >= 1
        ):
            possible_last = cols[-1]
            if (
                "دالر" in possible_last
                or "دلار" in possible_last
                or "درهم" in possible_last
                or "یورو" in possible_last
                or "پوند" in possible_last
            ):
                first = possible_last

        code, name = split_currency_name(first)

        if not name:
            continue

        # Region is often the far-left visible column, and in HTML it is often
        # one of the edge cells. We try to detect it by known words.
        region = ""

        known_regions = ["مارکیت خراسان", "خراسان", "تهران", "دوبی", "دبی"]

        for c in cols:
            if any(r in c for r in known_regions):
                region = normalize_region(c)
                break

        rates.append(
            {
                "code": code,
                "name": name,
                "buy": buy,
                "sell": sell,
                "region": region,
            }
        )

    return rates


def extract_rates_from_text(html: str):
    """
    Fallback parser if the table parser fails.
    """
    soup = BeautifulSoup(html, "lxml")

    text = soup.get_text("\n", strip=True)
    lines = text.splitlines()

    rates = []

    for line in lines:
        if "|" not in line:
            continue

        parts = line.split("|")

        if len(parts) < 2:
            continue

        left = clean_text(parts[0])
        sell = clean_text(parts[1])

        m = re.match(r"^(.*?)\s+([0-9]+(?:[.,][0-9]+)?)$", left)

        if not m:
            continue

        name = clean_text(m.group(1))
        buy = clean_text(m.group(2))

        if not is_number_like(buy) or not is_number_like(sell):
            continue

        code, real_name = split_currency_name(name)

        rates.append(
            {
                "code": code,
                "name": real_name,
                "buy": buy,
                "sell": sell,
                "region": "",
            }
        )

    return rates


def extract_rates(html: str):
    rates = extract_rates_from_main_table(html)

    if rates:
        return rates

    return extract_rates_from_text(html)


def refine_khorasan_rates(rates):
    """
    Improves Khorasan labels.

    If the scraper captures the region column, it uses the real region:
    - مارکیت خراسان
    - تهران
    - دوبی

    If region is missing, it falls back to row order:
    1st dollar row = مارکیت خراسان
    2nd dollar row = تهران
    1st dirham row = دوبی
    """
    dollar_count = 0
    dirham_count = 0

    for item in rates:
        name = item.get("name", "")
        region = normalize_region(item.get("region", ""))

        is_dollar = "دالر" in name or "دلار" in name
        is_dirham = "درهم" in name or "امارات" in name

        if is_dollar:
            dollar_count += 1

            if region:
                item["name"] = f"دالر آمریکا در مقابل تومان ({region})"
            else:
                if dollar_count == 1:
                    item["name"] = "دالر آمریکا در مقابل تومان (مارکیت خراسان)"
                elif dollar_count == 2:
                    item["name"] = "دالر آمریکا در مقابل تومان (تهران)"
                else:
                    item["name"] = f"دالر آمریکا در مقابل تومان"

        elif is_dirham:
            dirham_count += 1

            if region:
                item["name"] = f"درهم امارات در مقابل تومان ({region})"
            else:
                if dirham_count == 1:
                    item["name"] = "درهم امارات در مقابل تومان (دوبی)"
                else:
                    item["name"] = "درهم امارات در مقابل تومان"

    return rates


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

    for r in rates:
        lines.append("")
        lines.append(format_currency_title(r))
        lines.append(f"🟢 خرید: <b>{safe(r['buy'])}</b>")
        lines.append(f"🔴 فروش: <b>{safe(r['sell'])}</b>")

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

    r = requests.post(url, data=payload, timeout=30)

    print("Telegram:", r.status_code)

    r.raise_for_status()


def main():
    bot_token = get_env("BOT_TOKEN")
    chat_id = get_env("CHAT_ID")
    channel_link = get_env("CHANNEL_LINK", required=False)

    messages = []

    # =========================
    # SARAI SHAHZADA
    # =========================
    sarai_html = fetch_url(SARAI_URL)

    if sarai_html and market_is_open(sarai_html):
        sarai_rates = extract_rates(sarai_html)
    else:
        print("Sarai market closed")
        sarai_rates = []

    print("Sarai rates:", len(sarai_rates))

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

    # =========================
    # KHORASAN MARKET
    # =========================
    kh_url, kh_html = fetch_first_working_url(KHORASAN_URL_CANDIDATES)

    if kh_html and market_is_open(kh_html):
        kh_rates = extract_rates(kh_html)
        kh_rates = refine_khorasan_rates(kh_rates)
    else:
        print("Khorasan market closed")
        kh_rates = []

    print("Khorasan rates:", len(kh_rates))

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

    # =========================
    # DA AFGHANISTAN BANK
    # =========================
    dab_html = fetch_url(DAB_URL)

    if dab_html and market_is_open(dab_html):
        dab_rates = extract_rates(dab_html)
    else:
        print("DAB market closed")
        dab_rates = []

    print("DAB rates:", len(dab_rates))

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

    # =========================
    # SEND TELEGRAM MESSAGES
    # =========================
    if not messages:
        print("All markets closed — nothing to send")
        return

    for message in messages:
        send_telegram_message(bot_token, chat_id, message)

    print("Done")


if __name__ == "__main__":
    main()
