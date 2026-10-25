import os
import sys
import json
import datetime
import time
import re
import random
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

# إعدادات التليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# ملف الذاكرة لمنع التكرار وحفظ الأسهم المراقبة اليومية
CACHE_FILE = "market_tracker_cache.json"

# قائمة البروكسيات الخاصة بك (أدرج البروكسيات هنا بصيغة IP:Port أو User:Pass@IP:Port)
# الكود مبرمج لاختيار بروكسي عشوائي عند كل طلب لمنع حظر السيرفر
PROXIES_POOL = [
    "http://username:password@proxy_ip1:port",
    "http://username:password@proxy_ip2:port",
    "http://username:password@proxy_ip3:port",
    # أضف المزيد من البروكسيات هنا...
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------
# محرك إدارة البروكسي والطلبات
# ---------------------------------------------------------
def get_proxy():
    """يختار بروكسي عشوائياً من القائمة إذا كانت متوفرة"""
    if PROXIES_POOL and PROXIES_POOL[0] != "http://username:password@proxy_ip1:port":
        p = random.choice(PROXIES_POOL)
        return {"http": p, "https": p}
    return None

def make_request(url, headers=COMMON_HEADERS):
    """يرسل الطلب مع حماية من الأخطاء وتدوير البروكسيات"""
    proxies = get_proxy()
    try:
        res = requests.get(url, headers=headers, proxies=proxies, timeout=12)
        if res.ok:
            return res
    except Exception as e:
        print(f"⚠️ خطأ اتصال عبر البروكسي بالرابط {url}: {e}")
    return None

# ---------------------------------------------------------
# التوقيت والجلسات (توقيت نيويورك EST)
# ---------------------------------------------------------
def get_est_now():
    return datetime.datetime.now(ZoneInfo("America/New_York"))

def get_market_session():
    """
    يحدد الجلسة الحالية بدقة بناءً على توقيت وول ستريت:
    - Pre-Market: من 4:00 صباحاً إلى 9:30 صباحاً
    - Regular Market: من 9:30 صباحاً إلى 4:00 مساءً
    - Post-Market: من 4:00 مساءً إلى 8:00 مساءً
    """
    now = get_est_now()
    if now.weekday() >= 5: # عطلة نهاية الأسبوع
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

def scrape_nasdaq_splits():
    """كشط صفحة التقسيمات لاستخراج الرموز التي يطبق عليها تقسيم عكسي اليوم"""
    url = "https://www.nasdaq.com/market-activity/stock-splits"
    today_str = get_est_now().strftime("%Y-%m-%d")
    tickers = []
    
    res = make_request(url)
    if not res:
        return tickers
        
    soup = BeautifulSoup(res.text, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 4:
            continue
        try:
            ticker = cells[0].get_text(strip=True)
            ratio_str = cells[2].get_text(strip=True)
            exec_date = cells[3].get_text(strip=True)
            
            if today_str in exec_date or exec_date == today_str:
                nums = parse_numbers(ratio_str)
                if len(nums) == 2 and nums[0] < nums[1]: # شرط التقسيم العكسي (1:10 مثلاً)
                    if ticker and ticker not in tickers:
                        tickers.append(ticker)
        except Exception:
            continue
    return tickers

def fetch_live_price(ticker):
    """جلب السعر الحالي الفوري وحجم التداول من ياهو فاينانشال للجلسات الثلاث"""
    url = f"https://yahoo.com{ticker}?interval=1m&range=1d&includePrePost=true"
    res = make_request(url)
    if not res:
        return None, None
    try:
        data = res.json()
        meta = data["chart"]["result"][0]["meta"]
        current_price = meta.get("regularMarketPrice")
        
        # في فترات ما قبل وبعد السوق، نحاول جلب السعر الممتد (Extended Price)
        if get_market_session() in ["PRE_MARKET", "POST_MARKET"]:
            current_price = meta.get("customMarketPrice") or meta.get("regularMarketPrice")
            
        indicators = data["chart"]["result"][0]["indicators"]["quote"][0]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        total_volume = sum(volumes) if volumes else 0
        
        return current_price, total_volume
    except:
        return None, None

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
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
    
    # تصفير الذاكرة اليومية مع بداية يوم جديد
    if cache["date"] != today_str:
        cache = {"date": today_str, "morning_sent": False, "tracked_tickers": [], "last_prices": {}}
        save_cache(cache)
        
    session = get_market_session()
    if session == "CLOSED":
        print("😴 السوق مغلق الآن خارج نطاق جلسات التداول الممتدة الثلاث.")
        return

    now_est = get_est_now()
    
    # 1. مرحلة ما قبل الافتتاح بساعة (الإشعار الصباحي الرئيسي)
    # تطلق من الساعة 8:30 صباحاً بتوقيت نيويورك (ساعة قبل الجلسة الرسمية 9:30)
    if now_est.time() >= datetime.time(8, 30) and not cache["morning_sent"]:
        print("🌅 جاري جمع التقسيمات العكسية وإرسال تقرير ما قبل الافتتاح...")
        discovered_tickers = scrape_nasdaq_splits()
        
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
            send_telegram(f"ℹ️ لا توجد أسهم خاضعة لتقسيم عكسي مدرجة اليوم في تقويم Nasdaq لليوم {today_str}.")
            
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
            
            # منع التكرار: نرسل الإشعار فقط إذا تحرك السهر بنسبة تتجاوز 4% صعوداً أو هبوطاً عن آخر سعر أرسلناه
            if last_price:
                change_pct = abs((current_price - last_price) / last_price) * 100
                should_alert = change_pct >= 4.0
            else:
                should_alert = True # أول رصد في الجلسة المفتوحة
                
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
# تشغيل الحلقة اللانهائية (Looping)
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 تم تشغيل سكريبت المراقبة المطور والمحمي بالبروكيسات لجلسات وول ستريت الثلاث...")
    while True:
        try:
            run_pipeline()
        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع في الحلقة الرئيسية: {e}")
            
        # معدل الفحص أثناء الجلسات (كل دقيقتين للتحديث اللحظي)
        time.sleep(120)
