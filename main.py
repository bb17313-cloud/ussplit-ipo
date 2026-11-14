from datetime import datetime, timedelta, timezone
import html
from html.parser import HTMLParser
import json
import os
import time
import urllib.parse
import urllib.request


class GoogleMarketsListParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.stocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if "/quote/" in href and ":" in href:
                clean_part = href.split("/quote/")[-1].split("?")
                if ":" in clean_part:
                    ticker, exchange = clean_part.split(":", 1)
                    if exchange in ["NASDAQ", "NYSE", "NYSEAMERICAN"]:
                        pair = (ticker.upper(), exchange.upper())
                        if pair not in self.stocks:
                            self.stocks.append(pair)


class GoogleStockDetailParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.in_price_div = False
        self.in_title_div = False
        self.prices = []
        self.company_name = ""
        self.full_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            for k, v in attrs:
                if k == "class" and v == "YMlKec fxKbKc":
                    self.in_price_div = True
                elif k == "class" and v == "zzDege":
                    self.in_title_div = True

    def handle_data(self, data):
        clean_data = html.unescape(data).strip()
        if not clean_data:
            return
        self.full_text.append(clean_data)
        if self.in_price_div:
            self.prices.append(clean_data)
            self.in_price_div = False
        if self.in_title_div:
            self.company_name += clean_data
            self.in_title_div = False

    def handle_endtag(self, tag):
        if tag == "div":
            self.in_price_div = False
            self.in_title_div = False


def is_fund_or_bank(company_name):
    excluded = [
        "etf",
        "fund",
        "trust",
        "index",
        "proshares",
        "ishares",
        "vanguard",
        "spdr",
        "invesco",
        "schwab",
        "ark ",
        "wisdomtree",
        "bank",
        "bancorp",
        "bancshares",
        "banking",
        "jpmorgan",
        "citigroup",
        "wells fargo",
        "goldman sachs",
        "morgan stanley",
    ]
    return any(k in company_name.lower() for k in excluded)


def clean_price(price_str):
    if not price_str:
        return None
    try:
        return float(price_str.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def is_us_market_open_hours():
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    ksa_tz = timezone(timedelta(hours=3))
    now_ksa = datetime.now(ksa_tz)
    if now_ksa.weekday() == 5 and now_ksa.hour >= 4:
        return False
    if now_ksa.weekday() == 6:
        return False
    if 4 <= now_ksa.hour < 11:
        return False
    return True


def get_google_market_movers(category="gainers"):
    url = f"https://google.com{category}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode("utf-8")
        parser = GoogleMarketsListParser()
        parser.feed(html_content)
        return parser.stocks
    except Exception:
        return []


def fetch_stock_info(ticker, exchange):
    url = f"https://google.com{ticker}:{exchange}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode("utf-8")
        parser = GoogleStockDetailParser()
        parser.feed(html_content)
        if not parser.prices or is_fund_or_bank(parser.company_name):
            return None
        main_price = clean_price(parser.prices)
        if not main_price:
            return None
        active_price = main_price
        session_type = "Main-Market Movers"
        pct_change = 0.0
        page_text = " ".join(parser.full_text)
        if len(parser.prices) > 1:
            ext_price = clean_price(parser.prices)
            if ext_price:
                active_price = ext_price
                pct_change = ((ext_price - main_price) / main_price) * 100
                if "Pre-market" in page_text:
                    session_type = "Pre-Market Movers"
                elif "After Hours" in page_text:
                    session_type = "Post-Market Movers"
        else:
            for word in parser.full_text:
                if (
                    word.endswith("%")
                    and "(" not in word
                    and any(c.isdigit() for c in word)
                ):
                    try:
                        val = float(
                            word.replace("%", "").replace("+", "").strip()
                        )
                        if val > 0:
                            pct_change = val
                            break
                    except ValueError:
                        continue
        return {
            "ticker": ticker,
            "exchange": exchange,
            "price": active_price,
            "pct": pct_change,
            "session": session_type,
        }
    except Exception:
        return None


def build_telegram_messages(stocks_list, title="Market Movers"):
    ksa_tz = timezone(timedelta(hours=3))
    current_time = datetime.now(ksa_tz).strftime("%H:%M")
    header = [f"🚨 <b>{title}</b>", f"⏰ <code>{current_time}</code>", ""]
    footer = ["", "📊 المصدر: Google Finance"]
    sorted_stocks = sorted(stocks_list, key=lambda x: x["pct"], reverse=True)
    stock_lines = []
    for idx, item in enumerate(sorted_stocks, start=1):
        t = item["ticker"]
        ex = item["exchange"]
        p = item["price"]
        pct = item["pct"]
        tv_url = f"https://tradingview.com{ex}:{t}"
        p_str = f"${p:.2f}" if p >= 1 else f"${p:.3f}"
        pct_str = f"{pct:.2f}%"
        line = (
            f'{idx}. <a href="{tv_url}"><b><code>{t}</code></b></a>  · '
            f"<code>{p_str}</code>  ·  <code>{pct_str}</code>"
        )
        stock_lines.append(line)
    messages = []
    current_chunk = list(header)
    current_length = sum(len(l) + 1 for l in current_chunk)
    for line in stock_lines:
        if current_length + len(line) + 50 > 3800:
            current_chunk.extend(footer)
            messages.append("\n".join(current_chunk))
            current_chunk = [
                f"🚨 <b>{title} (تابع)</b>",
                f"⏰ <code>{current_time}</code>",
                "",
                line,
            ]
            current_length = sum(len(l) + 1 for l in current_chunk)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
    if len(current_chunk) > len(header):
        current_chunk.extend(footer)
        messages.append("\n".join(current_chunk))
    return messages


def send_to_telegram(message_text):
    bot_token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID")
    if not bot_token or not chat_id:
        print(message_text)
        return
    url = f"https://telegram.org{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode("utf-8"))
            print("Sent:", res.get("ok"))
    except Exception as e:
        print("Error:", e)


def main():
    if not is_us_market_open_hours():
        print("Market closed.")
        return
    raw_gainers = get_google_market_movers("gainers")
    raw_active = get_google_market_movers("most-active")
    combined_raw = []
    for pair in raw_gainers + raw_active:
        if pair not in combined_raw:
            combined_raw.append(pair)
    valid_stocks = []
    detected_session = "Market Movers"
    for ticker, exchange in combined_raw:
        info = fetch_stock_info(ticker, exchange)
        if info and info["pct"] > 0:
            valid_stocks.append(info)
            if info["session"] != "Main-Market Movers":
                detected_session = info["session"]
        time.sleep(0.5)
    if valid_stocks:
        msgs = build_telegram_messages(valid_stocks, title=detected_session)
        for msg in msgs:
            send_to_telegram(msg)
            time.sleep(1.0)
    else:
        print("No stocks found.")


if __name__ == "__main__":
    main()
