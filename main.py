from datetime import datetime, timedelta, timezone
import html
from html.parser import HTMLParser
import json
import os
import time
import urllib.parse
import urllib.request


# 1. محلل صفحات القوائم (Gainers / Most Active) في Google Finance
class GoogleMarketsListParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.stocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if "/quote/" in href and ":" in href:
                clean_part = href.split("/quote/")[-1].split("?")
                if ":" in clean_part:
                    ticker, exchange = clean_part.split(":", 1)
                    # البورصات الأمريكية الرئيسية فقط (استبعاد BATS, OTCMKTS, NYSEARCA)
                    if exchange in ["NASDAQ", "NYSE", "NYSEAMERICAN"]:
                        pair = (ticker.upper(), exchange.upper())
                        if pair not in self.stocks:
                            self.stocks.append(pair)


# 2. محلل صفحة السهم لاستخراج الاسم، السعر، ونسبة التغير لكل جلسة
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
            for attr_name, attr_value in attrs:
                if attr_name == "class" and attr_value == "YMlKec fxKbKc":
                    self.in_price_div = True
                elif attr_name == "class" and attr_value == "zzDege":
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
    """شرط استبعاد الصناديق والبنوك"""
    excluded_keywords = [
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
    return any(k in company_name.lower() for k in excluded_keywords)


def clean_price(price_str):
    if not price_str:
        return None
    try:
        return float(price_str.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def is_us_market_open_hours():
    """التحقق من أن الوقت الحالي يقع ضمن ساعات التداول (Pre + Main + Post) بتوقيت السعودية"""
    # السماح بالتشغيل دائماً إذا تم تشغيله يدوياً من زر Run workflow في GitHub
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True

    ksa_tz = timezone(timedelta(hours=3))
    now_ksa = datetime.now(ksa_tz)

    # يوم السبت (5) بعد الساعة 4 فجراً ويوم الأحد (6) بالكامل السوق مغلق
    if now_ksa.weekday() == 5 and now_ksa.hour >= 4:
        return False
    if now_ksa.weekday() == 6:
        return False

    # فترة التوقف اليومية بين إغلاق Post وافتتاح Pre (من 4:00 فجراً إلى 11:00 صباحاً بتوقيت السعودية)
    if 4 <= now_ksa.hour < 11:
        return False

    return True


def get_google_market_movers(category="gainers"):
    """جلب كامل الرموز المتاحة في الصفحة دون تحديد حد أقصى"""
    url = f"https://google.com{category}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode("utf-8")
        list_parser = GoogleMarketsListParser()
        list_parser.feed(html_content)
        return list_parser.stocks
    except Exception as e:
        print(f"خطأ في جلب قائمة {category}: {e}")
        return []


def fetch_stock_info(ticker, exchange):
    url = f"https://google.com{ticker}:{exchange}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

        # التحقق من جلسات Pre-market أو Post-market
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
            # استخراج نسبة التغير للجلسة الرئيسية
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
    """بناء الرسائل بترقيم مفتوح وتقسيمها تلقائياً إذا تجاوزت حد تيليجرام"""
    ksa_tz = timezone(timedelta(hours=3))
    current_time = datetime.now(ksa_tz).strftime("%H:%M")

    header = [f"🚨 <b>{title}</b>", f"⏰ <code>{current_time}</code>", ""]

    footer = ["", "📊 المصدر: Google Finance"]

    sorted_stocks = sorted(stocks_list, key=lambda x: x["pct"], reverse=True)

    stock_lines = []
    for idx, item in enumerate(sorted_stocks, start=1):
        ticker = item["ticker"]
        exchange = item["exchange"]
        price = item["price"]
        pct = item["pct"]

        # رابط شارت TradingView المباشر
        tv_url = (
            f"https://tradingview.com{exchange}:{ticker}"
        )
        price_str = f"${price:.2f}" if price >= 1 else f"${price:.3f}"
        pct_str = f"{pct:.2f}%"

        # الرمز بخلفية قابلة للضغط تفتح الشارت مباشرة
        line = (
            f'{idx}. <a href="{tv_url}"><b><code>{ticker}</code></b></a>  · '
            f"<code>{price_str}</code>  ·  <code>{pct_str}</code>"
        )
        stock_lines.append(line)

    # تقسيم الرسالة تلقائياً إذا تجاوزت 3800 حرف
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
    """إرسال الرسالة إلى تيليجرام"""
    bot_token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID")

    if not bot_token or not chat_id:
        print("تنبيه: لم يتم العثور على TELEGRAM_TOKEN أو TELEGRAM_CHAT_ID.")
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
            result = json.loads(response.read().decode("utf-8"))
            if result.get("ok"):
                print("تم إرسال الرسالة إلى تيليجرام بنجاح.")
            else:
