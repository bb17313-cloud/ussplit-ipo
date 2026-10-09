import os
import sys
import json
import datetime
import time
import re
import html
import requests
from zoneinfo import ZoneInfo

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ملفات المراقبة المنفصلة
SPLITS_WATCHLIST_FILE = "splits_watchlist.json"
IPO_WATCHLIST_FILE = "ipo_watchlist.json"
PRESPLIT_FILE = "presplit_floats.json"

# SEC & Common Headers
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "StockBot your-email@example.com")
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

NASDAQ_HEADERS = {
    **COMMON_HEADERS,
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/market-activity/stock-splits",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
}

SECTOR_MAP = {
    "Health Technology": "الرعاية الصحية - تكنولوجيا",
    "Health Services": "الخدمات الصحية",
    "Commercial Services": "الخدمات التجارية",
    "Consumer Durables": "السلع الاستهلاكية المعمرة",
    "Consumer Non-Durables": "السلع الاستهلاكية غير المعمرة",
    "Consumer Services": "الخدمات الاستهلاكية",
    "Electronic Technology": "التكنولوجيا الإلكترونية",
    "Technology Services": "خدمات التكنولوجيا",
    "Finance": "الخدمات المالية",
    "Energy Minerals": "معادن الطاقة",
    "Non-Energy Minerals": "المعادن غير الطاقية",
    "Process Industries": "الصناعات التحويلية",
    "Producer Manufacturing": "التصنيع الإنتاجي",
    "Industrial Services": "الخدمات الصناعية",
    "Utilities": "المرافق العامة",
    "Retail Trade": "تجارة التجزئة",
    "Transportation": "النقل والمواصلات",
    "Communications": "الاتصالات",
    "Distribution Services": "خدمات التوزيع"
}

INDUSTRY_MAP = {
    "Software - Infrastructure": "البرمجيات - البنية التحتية",
    "Software - Application": "البرمجيات - التطبيقات",
    "Biotechnology": "التكنولوجيا الحيوية",
    "Medical Specialties": "التخصصات الطبية",
    "Pharmaceuticals: Major": "صناعة الأدوية - الكبرى",
    "Pharmaceuticals: Generic": "صناعة الأدوية - العامة",
    "Wholesale Distributors": "موزعو الجملة",
    "Auto Parts: OEM": "قطع غيار السيارات",
    "Motor Vehicles": "صناعة السيارات",
    "Industrial Machinery": "الآلات الصناعية",
    "Aerospace & Defense": "الفضاء والدفاع",
    "Semiconductors": "أشباه الموصلات",
    "Internet Software/Services": "برمجيات وخدمات الإنترنت",
    "Real Estate Development": "التطوير العقاري",
    "Financial Publishing/Services": "الخدمات المالية",
    "Engineering & Construction": "الهندسة والإنشاءات"
}

COUNTRY_MAP = {
    "US": "الولايات المتحدة", "USA": "الولايات المتحدة", "United States": "الولايات المتحدة",
    "CA": "كندا", "Canada": "كندا", "CN": "الصين", "China": "الصين",
    "IL": "إسرائيل", "Israel": "إسرائيل", "KY": "جزر كايمان", "Cayman Islands": "جزر كايمان",
    "BM": "برمودا", "Bermuda": "برمودا", "GB": "المملكة المتحدة", "United Kingdom": "المملكة المتحدة",
    "HK": "هونغ كونغ", "Hong Kong": "هونغ كونغ", "SG": "سنغافورة", "Singapore": "سنغافورة",
    "JP": "اليابان", "Japan": "اليابان", "DE": "ألمانيا", "Germany": "ألمانيا",
    "FR": "فرنسا", "France": "فرنسا", "AU": "أستراليا", "Australia": "أستراليا",
    "IE": "أيرلندا", "Ireland": "أيرلندا", "CH": "سويسرا", "Switzerland": "سويسرا",
    "NL": "هولندا", "Netherlands": "هولندا", "SE": "السويد", "Sweden": "السويد",
    "GR": "اليونان", "Greece": "اليونان", "KR": "كوريا الجنوبية", "South Korea": "كوريا الجنوبية"
}

# ---------------------------------------------------------
# أدوات عامة مشتركة
# ---------------------------------------------------------
def get_est_now():
    return datetime.datetime.now(ZoneInfo("America/New_York"))

def get_ksa_now():
    return datetime.datetime.now(ZoneInfo("Asia/Riyadh"))

def is_market_active():
    now_est = get_est_now()
    if now_est.weekday() >= 5:
        return False
    return 4 <= now_est.hour < 20

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID غير موجود")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.ok:
            print("✅ تم إرسال الرسالة بنجاح")
            return True
        else:
            print(f"❌ Telegram Error: {res.status_code} - {res.text}")
            clean_text = re.sub(r'<[^>]+>', '', message)
            res_retry = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean_text}, timeout=15)
            return res_retry.ok
    except Exception as e:
        print("❌ استثناء التليجرام:", e)
        return False

def send_telegram_get_id(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    url = f"
