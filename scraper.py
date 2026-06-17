import os
import sys
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
    return " ".join(text.split())


def extract_main_rates(html: str):
    """
    Extracts the first/main Sarai Shahzada table:
    USD, EUR, GBP, IRR, PKR, etc.
    """
    soup = BeautifulSoup(html, "lxml")

    rows = []

    for tr in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]

        if len(cells) >= 3:
            rows.append(cells)

    rates = []

    for cells in rows:
        joined = " ".join(cells)

        # Skip table headers
        if "واحد پول" in joined:
            continue

        first = cells[0]

        # Main currencies look like:
        # USD - دالر آمریکا
        if " - " not in first:
            continue

        parts = first.split(" - ", 1)
        code = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ""

        if len(cells) < 3:
            continue

        buy = cells[1]
        sell = cells[2]

        if not code or not buy or not sell:
            continue

        rates.append(
            {
                "code": code,
                "name": name,
                "buy": buy,
                "sell": sell,
            }
        )

    return rates


def extract_text_lines(html: str):
    """
    Converts page text into clean lines.
    This helps extract the lower market sections:
    - مارکیت خراسان
    - د افغانستان بانک
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    lines = []
    for line in text.splitlines():
        line = clean_text(line)
        if line:
            lines.append(line)

    return lines


def extract_named_market(lines, market_name: str):
    """
    Extracts lower page markets like:
    مارکیت خراسان | خرید | فروش
    دالر آمریکا 64.60 | 64.65
    یورو اروپا 74.30 | 74.50

    Returns:
    [
      {"name": "دالر آمریکا", "buy": "64.60", "sell": "64.65"},
      ...
    ]
    """
    rates = []
    start_index = None

    for i, line in enumerate(lines):
        if line == market_name:
            start_index = i
            break

    if start_index is None:
        print(f"WARNING: Market not found: {market_name}")
        return rates

    # Data usually starts after:
    # market name
    # خرید
    # فروش
    i = start_index + 1

    # Skip headers like خرید / فروش
    while i < len(lines) and lines[i] in ["خرید", "فروش"]:
        i += 1

    # Read until another known section starts
    stop_markers = {
        "مارکیت خراسان",
        "د افغانستان بانک",
        "سرای شهزاده",
        "افغانی",
        "Other Currencies",
        "مارکیت باز است",
    }

    while i < len(lines):
        line = lines[i]

        if line in stop_markers and line != market_name:
            break

        # Expected pattern from page text:
        # دالر آمریکا 64.60
        # 64.65
        #
        # Or sometimes:
        # دالر آمریکا 64.60 | 64.65
        if "|" in line:
            parts = [clean_text(x) for x in line.split("|")]
            if len(parts) >= 3:
                name_buy = parts[0]
                sell = parts[1]

                name_parts = name_buy.rsplit(" ", 1)
                if len(name_parts) == 2:
                    name = name_parts[0]
                    buy = name_parts[1]
                    rates.append({"name": name, "buy": buy, "sell": sell})

        else:
            # Handle line-based format:
            # "دالر آمریکا 64.60"
            # next line: "64.65"
            if i + 1 < len(lines):
                current = line
                next_line = lines[i + 1]

                # Split from right side to separate name and buy price
                parts = current.rsplit(" ", 1)

                if len(parts) == 2:
                    name = parts[0]
                    buy = parts[1]
                    sell = next_line

                    # Basic number check
                    if looks_like_number(buy) and looks_like_number(sell):
                        rates.append({"name": name, "buy": buy, "sell": sell})
                        i += 2
                        continue

        i += 1

    return rates


def looks_like_number(value: str) -> bool:
    value = value.replace(",", "").replace(".", "").strip()
    return value.isdigit()


def footer(source_name: str, channel_link: str):
    lines = []
    lines.append("")
    lines.append(f"منبع: {source_name}")

    if channel_link:
        lines.append(f"کانال: {channel_link}")

    return "\n".join(lines)


def build_main_message(rates, channel_link: str):
    if not rates:
        return None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("💱 نرخ‌های سرای شهزاده")
    lines.append("")
    lines.append("واحد | خرید | فروش")
    lines.append("------------")

    for item in rates:
        code = item["code"]
        name = item["name"]
        buy = item["buy"]
        sell = item["sell"]

        lines.append(f"{code} - {name}")
        lines.append(f"خرید: {buy} | فروش: {sell}")
        lines.append("")

    lines.append(f"🕒 بروزرسانی: {now_utc}")
    lines.append(footer("سرای شهزاده", channel_link))

    return "\n".join(lines)


def build_market_message(title: str, rates, source_name: str, channel_link: str):
    if not rates:
        return None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"💱 {title}")
    lines.append("")
    lines.append("واحد | خرید | فروش")
    lines.append("------------")

    for item in rates:
        name = item["name"]
        buy = item["buy"]
        sell = item["sell"]

        lines.append(f"{name}")
        lines.append(f"خرید: {buy} | فروش: {sell}")
        lines.append("")

    lines.append(f"🕒 بروزرسانی: {now_utc}")
    lines.append(footer(source_name, channel_link))

    return "\n".join(lines)


def send_telegram_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
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

    lines = extract_text_lines(html)
    khorasan_rates = extract_named_market(lines, "مارکیت خراسان")
    dab_rates = extract_named_market(lines, "د افغانستان بانک")

    print(f"Main rates extracted: {len(main_rates)}")
    print(f"Khorasan rates extracted: {len(khorasan_rates)}")
    print(f"Da Afghanistan Bank rates extracted: {len(dab_rates)}")

    messages = []

    main_message = build_main_message(main_rates, channel_link)
    if main_message:
        messages.append(main_message)

    khorasan_message = build_market_message(
        title="نرخ‌های مارکیت خراسان",
        rates=khorasan_rates,
        source_name="مارکیت خراسان",
        channel_link=channel_link,
    )
    if khorasan_message:
        messages.append(khorasan_message)

    dab_message = build_market_message(
        title="نرخ‌های د افغانستان بانک",
        rates=dab_rates,
        source_name="د افغانستان بانک",
        channel_link=channel_link,
    )
    if dab_message:
        messages.append(dab_message)

    if not messages:
        print("ERROR: No messages generated.")
        sys.exit(1)

    for index, message in enumerate(messages, start=1):
        print(f"Sending message {index}/{len(messages)}")
        print(message[:1000])
        send_telegram_message(bot_token, chat_id, message)

    print("Done.")


if __name__ == "__main__":
    main()
