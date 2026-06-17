import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone


SOURCE_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"


def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"ERROR: Missing environment variable: {name}")
        sys.exit(1)
    return value


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


def extract_rates(html: str):
    soup = BeautifulSoup(html, "lxml")

    rows = []

    # The page content is table-like. We collect table rows first.
    for tr in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["td", "th"])]

        if len(cells) >= 3:
            rows.append(cells)

    rates = []

    for cells in rows:
        joined = " ".join(cells)

        # Skip headers
        if "واحد پول" in joined or "خرید" == joined or "فروش" == joined:
            continue

        # We only want main exchange rates from first section.
        # Expected examples:
        # USD - دالر آمریکا | 64.30 | 64.35 | time | percent
        first = cells[0]

        if " - " not in first:
            continue

        parts = first.split(" - ", 1)
        code = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ""

        if len(cells) < 3:
            continue

        buy = cells[1]
        sell = cells[2]

        # Avoid weird rows
        if not code or not buy or not sell:
            continue

        rates.append({
            "code": code,
            "name": name,
            "buy": buy,
            "sell": sell,
        })

    return rates


def build_message(rates):
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
    lines.append("")
    lines.append("منبع: sarafi.af")

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

    html = fetch_page()
    rates = extract_rates(html)

    print(f"Extracted rates: {len(rates)}")

    if not rates:
        print("ERROR: No rates extracted.")
        sys.exit(1)

    message = build_message(rates)

    print("Message preview:")
    print(message[:1000])

    send_telegram_message(bot_token, chat_id, message)

    print("Done.")


if __name__ == "__main__":
    main()
