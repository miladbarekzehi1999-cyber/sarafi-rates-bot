import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SARAI_URL = "https://m.sarafi.af/public/fa/exchange-rates/sarai-shahzada"
DAB_URL = "https://sarafi.af/fa/exchange-rates/da-afg-bank"

KHORASAN_URLS = [
    "https://sarafi.af/fa/exchange-rates/khorasan-market",
    "https://sarafi.af/fa/exchange-rates/khorasan",
    "https://sarafi.af/fa/exchange-rates/markit-khorasan"
]


# ---------- SESSION WITH RETRIES ----------
def create_session():
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


session = create_session()


# ---------- FETCH PAGE ----------
def fetch(url):
    try:
        r = session.get(url, timeout=30)

        if r.status_code != 200:
            return None

        return r.text

    except Exception as e:
        print("Fetch error:", e)
        return None


# ---------- FIND WORKING KHORASAN URL ----------
def find_khorasan():

    for url in KHORASAN_URLS:

        html = fetch(url)

        if html:
            return url, html

    return None, None


# ---------- PARSE TABLE ----------
def parse_rates(html):

    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")

    if not table:
        return []

    rates = []

    for row in table.find_all("tr"):

        cols = [c.get_text(strip=True) for c in row.find_all("td")]

        if len(cols) < 4:
            continue

        percent = cols[0]
        buy = cols[1]
        sell = cols[2]
        currency = cols[3]

        if "خرید" in percent:
            continue

        rates.append({
            "currency": currency,
            "buy": buy,
            "sell": sell,
            "percent": percent
        })

    return rates


# ---------- SCRAPERS ----------
def get_sarai_rates():

    html = fetch(SARAI_URL)

    if not html:
        return None

    return parse_rates(html)


def get_khorasan_rates():

    url, html = find_khorasan()

    if not html:
        return None

    return parse_rates(html)


def get_dab_rates():

    html = fetch(DAB_URL)

    if not html:
        return None

    return parse_rates(html)


# ---------- MAIN TEST ----------
if __name__ == "__main__":

    print("Sarai Shahzada")
    print(get_sarai_rates())

    print("\nKhorasan Market")
    print(get_khorasan_rates())

    print("\nDa Afghanistan Bank")
    print(get_dab_rates())
