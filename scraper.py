import os
import sys
import re
import html as html_escape
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone


SOURCE_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"


def get_env(name: str, required: bool = True) -> str:
    value = os.getenv(name)

    if required and not value:
        print(f"ERROR: Missing environment variable: {name}")
        sys.exit(1)

    return value or ""


def fetch_page() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    response = requests.get(SOURCE_URL, headers=headers, timeout=30)
    print("Scrape status:", response.status_code)

    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def safe(text) -> str:
    """
    Escape text for Telegram HTML parse mode.
    """
    return html_escape.escape(str(text), quote=False)


def currency_flag(code: str) -> str:
    """
    Adds flag emoji for common currency codes.
    """
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
    }

    return flags.get(code.upper(), "💵")


def name_flag(name: str) -> str:
    """
    Adds flag emoji for currencies in lower market sections.
    """
    if "دالر آمریکا" in name:
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

    return "💵"


def extract_main_rates(html: str):
    """
    Extracts all currency pairs from the main Sarai Shahzada table.

    Example rows:
    USD - دالر آمریکا | 64.30 | 64.35 | ...
    EUR - یورو اروپا | 74.10 | 74.30 | ...
    """
    soup = BeautifulSoup(html, "lxml")
    rates = []

    for tr in soup.find_all("tr"):
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["td", "th"])
        ]

        if len(cells) < 3:
            continue

        first = cells[0]

        if "واحد پول" in first:
            continue

        if " - " not in first:
            continue

        code, name = first.split(" - ", 1)
        buy = cells[1]
        sell = cells[2]

        if code and name and buy and sell:
            rates.append(
                {
                    "code": code.strip(),
                    "name": name.strip(),
                    "buy": buy.strip(),
                    "sell": sell.strip(),
                }
            )

    return rates


def extract_section_rates(page_text: str, section_name: str):
    """
    Extracts lower text sections like:

    مارکیت خراسان | خرید | فروش
    دالر آمریکا 64.60 | 64.65
    یورو اروپا 74.30 | 74.50

    د افغانستان بانک | خرید | فروش
    دالر آمریکا 64.26 | 64.46
    ...
    """
    lines = [clean_text(line) for line in page_text.splitlines()]
    lines = [line for line in lines if line]

    header = f"{section_name} | خرید | فروش"

    start = None
    for i, line in enumerate(lines):
        if line == header:
            start = i
            break

    if start is None:
        print(f"WARNING: Section not found: {section_name}")
        return []

    rates = []
    i = start + 1

    stop_markers = {
        "مارکیت خراسان | خرید | فروش",
        "د افغانستان بانک | خرید | فروش",
        "* سرای شهزاده",
        "افغانی",
        "خرید",
        "فروش",
    }

    while i < len(lines):
        line = lines[i]

        if line in stop_markers and line != header:
            break

        # Expected pattern:
        # دالر آمریکا 64.60 | 64.65
        if "|" in line:
            parts = [clean_text(x) for x in line.split("|")]

            if len(parts) >= 2:
                left = parts[0]
                sell = parts[1]

                # Split currency name and buy price from the right side
                match = re.match(r"^(.*)\s+([0-9.,]+)$", left)

                if match:
                    name = match.group(1).strip()
                    buy = match.group(2).strip()
                    sell = sell.strip()

                    rates.append(
                        {
                            "name": name,
                            "buy": buy,
                            "sell": sell,
                        }
                    )

        i += 1

    return rates


def build_channel_line(channel_link: str) -> str:
    if not channel_link:
        return ""

    # If it is a Telegram link, make it clickable in HTML mode
    if channel_link.startswith("http://") or channel_link.startswith("https://"):
        return f'کانال: <a href="{safe(channel_link)}">{safe(channel_link)}</a>'

    return f"کانال: {safe(channel_link)}"


def build_main_message(rates, channel_link: str):
    if not rates:
        return None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("💱 <b>نرخ اسعار سرای شهزاده</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")

    for item in rates:
        code = item["code"]
        name = item["name"]
        buy = item["buy"]
        sell = item["sell"]
        flag = currency_flag(code)

        lines.append("")
        lines.append(f"{flag} <b>{safe(code)}</b> — {safe(name)}")
        lines.append(f"🟢 خرید: <b>{safe(buy)}</b>")
        lines.append(f"🔴 فروش: <b>{safe(sell)}</b>")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"🕒 بروزرسانی: {safe(now_utc)}")
    lines.append("")
    lines.append("منبع: سرای شهزاده")

    channel_line = build_channel_line(channel_link)
    if channel_line:
        lines.append(channel_line)

    return "\n".join(lines)


def build_section_message(title: str, rates, source_name: str, channel_link: str, icon: str):
    if not rates:
        return None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"{icon} <b>{safe(title)}</b>")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")

    for item in rates:
        name = item["name"]
        buy = item["buy"]
        sell = item["sell"]
        flag = name_flag(name)

        lines.append("")
        lines.append(f"{flag} <b>{safe(name)}</b>")
        lines.append(f"🟢 خرید: <b>{safe(buy)}</b>")
        lines.append(f"🔴 فروش: <b>{safe(sell)}</b>")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"🕒 بروزرسانی: {safe(now_utc)}")
    lines.append("")
    lines.append(f"منبع: {safe(source_name)}")

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

    html = fetch_page()

    main_rates = extract_main_rates(html)

    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text("\n", strip=True)

    khorasan_rates = extract_section_rates(page_text, "مارکیت خراسان")
    dab_rates = extract_section_rates(page_text, "د افغانستان بانک")

    print(f"Main rates extracted: {len(main_rates)}")
    print(f"Khorasan rates extracted: {len(khorasan_rates)}")
    print(f"Da Afghanistan Bank rates extracted: {len(dab_rates)}")

    messages = []

    main_message = build_main_message(main_rates, channel_link)
    if main_message:
        messages.append(main_message)

    khorasan_message = build_section_message(
        title="نرخ‌های مارکیت خراسان",
        rates=khorasan_rates,
        source_name="مارکیت خراسان",
        channel_link=channel_link,
        icon="🏪",
    )
    if khorasan_message:
        messages.append(khorasan_message)

    dab_message = build_section_message(
        title="نرخ‌های د افغانستان بانک",
        rates=dab_rates,
        source_name="د افغانستان بانک",
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
