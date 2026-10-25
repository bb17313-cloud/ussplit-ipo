python
import os
import sys
import json
import datetime
import time
import re
import random
import requests
from html.parser import HTMLParser  # مكتبة مدمجة في بايثون لا تحتاج تثبيت
from zoneinfo import ZoneInfo

# إعدادات التليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# ملف الذاكرة لمنع التكرار وحفظ الأسهم المراقبة اليومية
CACHE_FILE = "market_tracker_cache.json"

# قائمة البروكسيات الخاصة بك (أدرج البروكسيات هنا بصيغة IP:Port أو User:Pass@IP:Port)
PROXIES_POOL = [
    "http://username:password@proxy_ip1:port",
    "http://username:password@proxy_ip2:port",
    # أضف المزيد من البروكسيات هنا...
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------
# محلل الـ HTML المدمج (HTMLParser) لقراءة جدول Nasdaq
# ---------------------------------------------------------
class NasdaqSplitsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_row = []
        self.all_rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = []
        elif tag in ["td", "th"] and self.in_tr:
            self.in_td = True

    def handle_data(self, data):
        if self.in_td:
            self.current_row.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_tbody:
            self.in_tr = False
            if self.current_row:
                self.all_rows.append(self.current_row)
        elif tag in ["td", "th"] and self.in_tr:
            self.in_td = False

# ---------------------------------------------------------
# محرك إدارة البروكسي والطلبات
# ---------------------------------------------------------
def get_proxy():
    if PROXIES_POOL and not PROXIES_POOL[0].startswith("http://username"):
        p = random.choice(PROXIES_POOL)
        return {"http": p, "https": p}
    return None

def make_request(url, headers=COMMON_HEADERS):
    proxies = get_proxy()
    try:
        res = requests.get(url, headers=headers, proxies=proxies, timeout=12)
        if res.ok:
            return res
    except Exception as e:
        print(f"⚠️ خطأ اتصال بالرابط {url}: {e}")
    return None

# ---------------------------------------------------------
# التوقيت والجلسات (توقيت نيويورك EST)
# ---------------------------------------------------------
def get_est_now():
    return datetime.datetime.now(ZoneInfo("America/New_York"))

def get_market_session():
    now = get_est_now()
    if now.weekday() >= 5:
        return "CLOSED"
        
    t = now.time()
    if datetime.time(4, 0) <= t < datetime.time(9, 30):
        return "PRE_MARKET"
    elif datetime.time(9, 30) <= t < datetime.time(16, 0):
        return "REGULAR"
    elif datetime.time(16, 0) <= t < datetime.time(20, 0):
        return "POST_MARKET"
    return "CLOSED"

# ---------------------------------------------------------
# إدارة الذاكرة ومنع التكرار (State Management)
# ---------------------------------------------------------
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"date": "", "morning_sent": False, "tracked_tickers": [], "last_prices": {}}

def save_cache(cache_data):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache_data, f, indent=4)

# ---------------------------------------------------------
# جلب البيانات والتحليل
# ---------------------------------------------------------
def parse_numbers(s):
    return [float(x.replace(',', '')) for x in re.findall(r'\d[\d,]*\.?\d*', str(s or '')) if x]

def parse_nasdaq_splits_html():
    url = "https://nasdaq.com"
    today_str = get_est_now().strftime("%Y-%m-%d")
    tickers = []
    
    res = make_request(url)
    if not res:
        return tickers
        
    # استخدام المحلل المدمج لتفكيك الصفحة
    parser = NasdaqSplitsParser()
    parser.feed(res.text)
    
    for row in parser.all_rows:
        if len(row) < 4:
            continue
        try:
            ticker = row[0]       # الرمز يكون غالباً في العمود الأول
            ratio_str = row[2]    # نسبة التقسيم
            exec_date = row[3]    # تاريخ التنفيذ
            
            if today_str in exec_date or exec_date == today_str:
                nums = parse_numbers(ratio_str)
                if len(nums) == 2 and nums[0] < nums[1]: # شرط التقسيم العكسي (1:10)
                    if ticker and ticker not in tickers:
                        tickers.append(ticker)
        except Exception:
            continue
    return tickers

def fetch_live_price(ticker):
    url = f"https://yahoo.com{ticker}?interval=1m&range=1d&includePrePost=true"
    res = make_request(url)
    if not res:
        return None, None
    try:
        data = res.json()
        meta = data["chart"]["result"][0]["meta"]
        current_price = meta.get("regularMarketPrice")
        
        if get_market_session() in ["PRE_MARKET", "POST_MARKET"]:
            current_price = meta.get("customMarketPrice") or meta.get("regularMarketPrice")
            
        indicators = data["chart"]["result"][0]["indicators"]["quote"][0]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        total_volume = sum(volumes) if volumes else 0
        
        return current_price, total_volume
    except:
        return None, None

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        print(message)
        return
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=10)
    except Exception as e: print(f"❌ خطأ إرسال تليجرام: {e}")

# ---------------------------------------------------------
# المحرك الرئيسي للتتبع المستمر اللحظي
# ---------------------------------------------------------
def run_pipeline():
    today_str = get_est_now().strftime("%Y-%m-%d")
    cache = load_cache()
    
    if cache["date"] != today_str:
        cache = {"date": today_str, "morning_sent": False, "tracked_tickers": [], "last_prices": {}}
        save_cache(cache)
        
    session = get_market_session()
    if session == "CLOSED":
        print("😴 السوق مغلق الآن خارج نطاق جلسات التداول الممتدة الثلاث.")
        return

    now_est = get_est_now()
    
    # 1. مرحلة ما قبل الافتتاح بساعة (الإشعار الصباحي الرئيسي) عند الساعة 8:30 صباحاً بتوقيت نيويورك
    if now_est.time() >= datetime.time(8, 30) and not cache["morning_sent"]:
        print("🌅 جاري جمع التقسيمات العكسية وإرسال تقرير ما قبل الافتتاح...")
        discovered_tickers = parse_nasdaq_splits_html()
        
        if discovered_tickers:
            cache["tracked_tickers"] = discovered_tickers
            msg = f"⚠️ <b>تقرير الأسهم الخاضعة لتقسيم عكسي اليوم {today_str}</b>\n"
            msg += f"⏰ <i>أُرسل قبل الافتتاح بساعة</i>\n\n"
            for t in discovered_tickers:
                price, vol = fetch_live_price(t)
                price_str = f"${price:.2f}" if price else "غير متوفر"
                msg += f"• الرمز: <code>{t}</code> | السعر الحالي: {price_str}\n"
            send_telegram(msg)
        else:
            print(f"ℹ️ لا توجد أسهم تقسيم عكسي اليوم {today_str}.")
            
        cache["morning_sent"] = True
        save_cache(cache)
        return

    # 2. مرحلة المتابعة أثناء جلسات السوق الثلاث بدون تكرار
    if cache["tracked_tickers"]:
        print(f"🔄 يراقب الآن الأسهم المقسمة في جلسة: {session}...")
        
        for ticker in cache["tracked_tickers"]:
            current_price, total_volume = fetch_live_price(ticker)
            if not current_price:
                continue
                
            last_price = cache["last_prices"].get(ticker)
            
            if last_price:
                change_pct = abs((current_price - last_price) / last_price) * 100
                should_alert = change_pct >= 4.0
            else:
                should_alert = True
                
            if should_alert:
                cache["last_prices"][ticker] = current_price
                save_cache(cache)
                
                direction = "🔺 صعود" if (not last_price or current_price > last_price) else "🔻 هبوط"
                msg_alert = f"🔄 <b>تحديث تداول سهم تقسيم عكسي ({session})</b>\n\n"
                msg_alert += f"• الرمز: <code>{ticker}</code>\n"
                msg_alert += f"• السعر الفوري: <b>${current_price:.4f}</b> ({direction})\n"
                msg_alert += f"• حجم التداول الكلي اليوم: {total_volume:,} سهم\n"
                msg_alert += f"• توقيت الرصد: {get_est_now().strftime('%H:%M:%S')} EST\n"
                send_telegram(msg_alert)

# ---------------------------------------------------------
# تشغيل الحلقة اللانهائية (Loop)
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 تم تشغيل سكريبت المراقبة المعتمد على HTMLParser المدمج بنجاح...")
    while True:
        try:
            run_pipeline()
        except Exception as e:
            print(f"❌ حدث خطأ في الحلقة الرئيسية: {e}")
            
