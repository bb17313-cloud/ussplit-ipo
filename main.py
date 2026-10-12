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
# أدوات عامة مشتركة وإحصاءات السيولة والدايموند
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
            return res.json()['result']['message_id']
    except Exception as e:
        print("❌ send_telegram_get_id:", e)
    return None

def edit_telegram_message(message_id, message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.ok
    except Exception as e:
        print("❌ edit_telegram_message:", e)
        return False

def parse_numbers(s):
    out = []
    for x in re.findall(r'\d[\d,]*\.?\d*', str(s or '')):
        try:
            out.append(float(x.replace(',', '')))
        except (ValueError, TypeError):
            pass
    return out

def format_shares_count(num):
    if not num or num <= 0:
        return "غير متوفر"
    num = float(num)
    if num >= 995_000:
        millions = round(num / 1_000_000, 2)
        val_str = f"{int(millions)}" if millions.is_integer() else f"{millions}"
        return f"{val_str} مليون سهم"
    elif num >= 1_000:
        thousands = round(num / 1_000, 2)
        val_str = f"{int(thousands)}" if thousands.is_integer() else f"{thousands}"
        return f"{val_str} ألف سهم"
    return f"{int(round(num))} سهم"

# ---------------------------------------------------------
# محلل شمعة السيولة السوداء وإشارات الدايموند
# ---------------------------------------------------------
def analyze_liquidity_and_diamond(ticker):
    result = {
        "has_black_candle": False,
        "black_high": 0.0,
        "diamond_breakout": False,
        "volume_ratio": 1.0
    }
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d&includePrePost=true"
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        r = res.get('chart', {}).get('result', [])
        if not r:
            return result
        
        q = r[0].get('indicators', {}).get('quote', [{}])[0]
        highs = q.get('high', [])
        closes = q.get('close', [])
        volumes = q.get('volume', [])
        
        if len(closes) < 10:
            return result
        
        lookback = min(20, len(closes) - 3)
        black_highs = []
        for i in range(max(5, lookback), len(closes)):
            vol_slice = [v for v in volumes[max(0, i-20):i] if v is not None and v > 0]
            if not vol_slice:
                continue
            avg_vol = sum(vol_slice) / len(vol_slice)
            curr_vol = volumes[i] or 0.0
            
            if avg_vol > 0 and curr_vol >= avg_vol * 1.8:
                h = highs[i]
                if h is not None:
                    result["has_black_candle"] = True
                    result["black_high"] = h
                    black_highs.append(h)
                    result["volume_ratio"] = round(curr_vol / avg_vol, 1)
        
        if black_highs:
            last_blk_high = black_highs[-1]
            current_price = closes[-1]
            result["black_high"] = last_blk_high
            if current_price >= last_blk_high:
                result["diamond_breakout"] = True

    except Exception as e:
        print(f"⚠️ خطأ في تحليل السيولة والدايموند لـ {ticker}: {e}")
    
    return result

# ---------------------------------------------------------
# استخراج سبب التقسيم العكسي ونوع إعادة الهيكلة بالعربي
# ---------------------------------------------------------
def get_split_reason_ar(ticker):
    try:
        url = f"https://efts.sec.gov/LATEST/search-index"
        params = {"q": f'"{ticker}" "reverse split"', "forms": "8-K,6-K", "dateRange": "custom",
                  "startdt": (get_est_now().date() - datetime.timedelta(days=90)).strftime("%Y-%m-%d"),
                  "enddt": get_est_now().date().strftime("%Y-%m-%d")}
        res = requests.get(url, params=params, headers=SEC_HEADERS, timeout=10)
        text_content = ""
        if res.status_code == 200:
            hits = (res.json().get("hits") or {}).get("hits") or []
            if hits:
                text_content = str(hits[0].get("_source", {}).get("display_names", ""))
        
        text_lower = text_content.lower()
        if "asset sale" in text_lower or "divestiture" in text_lower or "sale of assets" in text_lower:
            return "إعادة هيكلة أصول (بيع/تصفية قطاعات تابعة)"
        elif "compliance" in text_lower or "minimum bid" in text_lower or "deficiency" in text_lower:
            return "إعادة هيكلة رأس المال (لاستيفاء شرط الحد الأدنى لسعر السهم بالبورصة)"
        elif "debt" in text_lower or "restructuring agreement" in text_lower or "chapter 11" in text_lower:
            return "إعادة هيكلة ديون وتغيير التزامات مالية"
        elif "merger" in text_lower or "acquisition" in text_lower:
            return "إعادة هيكلة شاملة (اندماج واستحواذ)"
        else:
            return "إعادة هيكلة رأس المال (لرفع سعر السهم السوقي وتفادي الحذف)"
    except Exception as e:
        print(f"⚠️ خطأ في استخراج سبب التقسيم لـ {ticker}: {e}")
        return "إعادة هيكلة رأس المال (لتعديل القيمة السوقية والسعر)"

def get_benzinga_split_news(ticker):
    try:
        import xml.etree.ElementTree as ET
        from urllib.parse import quote
        q = quote(f'"{ticker}" "reverse stock split" site:benzinga.com when:1d')
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        if res.status_code != 200:
            return None
        root = ET.fromstring(res.content)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if title and link:
                return {"title": title, "link": link}
    except Exception as e:
        print(f"Benzinga news error ({ticker}): {e}")
    return None

# ---------------------------------------------------------
# دوال التقسيم العكسي (Reverse Splits)
# ---------------------------------------------------------
def load_watchlist(file_path=SPLITS_WATCHLIST_FILE):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_watchlist(watchlist, file_path=SPLITS_WATCHLIST_FILE):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    match = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to|\/)\s*(\d+(?:\.\d+)?)',
        ratio_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def is_reverse_split(num, den, ratio_str=""):
    if num is None or den is None:
        s = str(ratio_str).lower()
        return "reverse" in s or "consolidation" in s
    if num < den and den / num >= 1.5:
        return True
    s = str(ratio_str).lower()
    if "reverse" in s or "consolidation" in s:
        return True
    return False

def format_ratio_ar(num, den, raw_str=""):
    if num and den and num > 0 and den > 0:
        factor = max(num, den) / min(num, den)
        return f"1 مقابل {int(factor) if factor == int(factor) else round(factor, 2)}"
    return raw_str or "تقسيم عكسي"

def verify_actual_execution(ticker, num, den):
    if not num or not den:
        return True, 1.0, 0.0, 0.0
    factor = max(num, den) / min(num, den)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d&includePrePost=true"
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        result = res.get('chart', {}).get('result', [])
        if not result:
            return True, factor, 0.0, 0.0
        meta = result[0].get('meta', {})
        prev_close = meta.get('previousClose') or meta.get('chartPreviousClose') or 0.0
        current_price = (meta.get('regularMarketPrice') or
                         meta.get('preMarketPrice') or
                         meta.get('postMarketPrice') or 0.0)
        return True, factor, current_price, prev_close
    except Exception as e:
        print(f"⚠️ خطأ أثناء التحقق لـ {ticker}: {e} → نمرر السهم")
        return True, factor, 0.0, 0.0

def get_today_reverse_splits():
    today_est = get_est_now().date()
    date_str = today_est.strftime("%Y-%m-%d")
    splits_dict = {}
    try:
        url = f"https://api.nasdaq.com/api/calendar/splits?date={date_str}"
        res = requests.get(url, headers=NASDAQ_HEADERS, timeout=12)
        if res.status_code != 200:
            print(f"⚠️ Nasdaq Splits API status {res.status_code}")
            rows = []
        else:
            rows = (res.json() or {}).get('data', {}).get('rows') or []
        for row in rows:
            if not row:
                continue
            symbol = str(row.get('symbol', '')).strip().upper()
            ratio_str = str(row.get('ratio', '') or row.get('ratioDescription', ''))
            num, den = extract_ratio_numbers(ratio_str)
            if not symbol:
                continue
            if is_reverse_split(num, den, ratio_str):
                is_executed, factor, curr_p, prev_p = verify_actual_execution(symbol, num, den)
                if is_executed:
                    if num and den and num > den:
                        num, den = den, num
                    splits_dict[symbol] = {
                        'symbol': symbol,
                        'num': num,
                        'den': den,
                        'raw_text': ratio_str,
                        'split_date': date_str,
                        'factor': factor
                    }
    except Exception as e:
        print(f"❌ Nasdaq API Error ({date_str}):", e)
    return list(splits_dict.values())

def get_unscheduled_reverse_splits(known_symbols):
    today_est = get_est_now().date()
    date_str = today_est.strftime("%Y-%m-%d")
    candidates = []
    for field in ("change", "premarket_change"):
        try:
            payload = {
                "filter": [
                    {"left": field, "operation": "greater", "right": 80},
                    {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
                    {"left": "type", "operation": "equal", "right": "stock"}
                ],
                "columns": ["name", field],
                "sort": {"sortBy": field, "sortOrder": "desc"},
                "range": [0, 60]
            }
            res = requests.post("https://scanner.tradingview.com/america/scan",
                                json=payload, headers=COMMON_HEADERS, timeout=12)
            if res.status_code == 200:
                for row in res.json().get("data", []):
                    d = row.get("d", [])
                    if d and d[0] and d[0].upper() not in candidates:
                        candidates.append(d[0].upper())
        except Exception as e:
            print(f"Unscheduled scan error ({field}):", e)
    found = []
    for sym in candidates[:60]:
        if sym in known_symbols:
            continue
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?events=splits&interval=1d&range=5d")
            r = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()['chart']['result'][0]
            splits = (r.get('events') or {}).get('splits', {})
            for s in splits.values():
                n, d_ = s.get('numerator'), s.get('denominator')
                sdate = s.get('date')
                if not n or not d_ or sdate is None:
                    continue
                s_day = datetime.datetime.fromtimestamp(sdate, ZoneInfo("America/New_York")).date()
                if n < d_ and s_day == today_est:
                    found.append({
                        'symbol': sym,
                        'num': float(n),
                        'den': float(d_),
                        'raw_text': f"{int(n)}-for-{int(d_)}",
                        'split_date': date_str,
                        'factor': float(d_) / float(n),
                        'unscheduled': True
                    })
                    break
        except Exception as e:
            print(f"Unscheduled verify error ({sym}):", e)
    return found

def get_tradingview_stock_data(ticker):
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "name", "operation": "equal", "right": ticker.upper()},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]}
        ],
        "columns": [
            "name", "close", "change", "float_shares_outstanding", "total_shares_outstanding",
            "sector", "industry", "type", "subtype", "premarket_close", "premarket_change",
            "premarket_volume", "postmarket_close", "postmarket_change", "postmarket_volume",
            "volume", "market_cap_basic", "country"
        ]
    }
    data = {
        'found': False, 'is_valid_stock': True, 'price': 0.0, 'change_pct': 0.0, 'raw_float': 0.0,
        'total_shares': 0.0, 'sector': 'غير متوفر', 'industry': 'غير متوفر', 'country': 'غير متوفر',
        'volume': 0.0, 'market_cap': 0.0
    }
    try:
        res = requests.post(url, json=payload, headers=COMMON_HEADERS, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", [])
            if rows:
                cols = rows[0].get("d", [])
                data['found'] = True
                data['price'] = float(cols[1] or 0.0)
                data['change_pct'] = float(cols[2] or 0.0)
                data['raw_float'] = float(cols[3] or 0.0)
                data['total_shares'] = float(cols[4] or 0.0)
                raw_sec = cols[5] or ''
                raw_ind = cols[6] or ''
                entity_type = str(cols[7] or '').lower()
                entity_subtype = str(cols[8] or '').lower()
                invalid_types = ['fund', 'etf', 'cef', 'right', 'warrant', 'bond']
                if any(inv in entity_type or inv in entity_subtype for inv in invalid_types):
                    data['is_valid_stock'] = False
                if raw_sec:
                    data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if raw_ind:
                    data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
                data['volume'] = float(cols[15] or 0.0)
                data['market_cap'] = float(cols[16] or 0.0)
                raw_country = cols[17] if len(cols) > 17 and cols[17] else ''
                if raw_country:
                    data['country'] = COUNTRY_MAP.get(raw_country, raw_country)
    except Exception as e:
        print(f"TradingView API Error ({ticker}): {e}")
    return data

def load_presplit():
    if os.path.exists(PRESPLIT_FILE):
        try:
            with open(PRESPLIT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_presplit(data):
    with open(PRESPLIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_base_shares(tv_data, price):
    base = tv_data['raw_float'] if tv_data['raw_float'] > 0 else tv_data['total_shares']
    if base <= 0 and tv_data['market_cap'] > 0 and price > 0:
        base = tv_data['market_cap'] / price
    return base

def snapshot_next_day_floats():
    now_est = get_est_now()
    next_day = now_est.date() + datetime.timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += datetime.timedelta(days=1)
    date_str = next_day.strftime("%Y-%m-%d")
    store = load_presplit()
    done_key = f"_done_{date_str}"
    if store.get(done_key):
        return
    try:
        url = f"https://api.nasdaq.com/api/calendar/splits?date={date_str}"
        res = requests.get(url, headers=NASDAQ_HEADERS, timeout=10)
        if res.status_code != 200:
            return
        rows = (res.json() or {}).get('data', {}).get('rows') or []
        for row in rows:
            if not row:
                continue
            symbol = str(row.get('symbol', '')).strip().upper()
            num, den = extract_ratio_numbers(str(row.get('ratio', '')))
            if not symbol or num is None or den is None:
                continue
            if not is_reverse_split(num, den, str(row.get('ratio', ''))):
                continue
            tv = get_tradingview_stock_data(symbol)
            if not tv['is_valid_stock']:
                continue
            base = get_base_shares(tv, tv['price'])
            if base > 0:
                store[symbol] = {"date": date_str, "pre_float": base}
        store[done_key] = True
        save_presplit(store)
    except Exception as e:
        print("snapshot_next_day_floats error:", e)

def resolve_post_split_float(symbol, current_base, factor):
    if current_base <= 0:
        return 0.0
    if not factor or factor <= 1:
        return current_base
    pre = load_presplit().get(symbol, {}).get("pre_float", 0.0)
    if pre > 0:
        expected = pre / factor
        if abs(current_base - expected) / expected <= 0.30:
            return current_base
        return expected
    return current_base / factor

def get_prior_splits_count(ticker):
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for item in splits.values():
            if item.get('numerator', 1) < item.get('denominator', 1):
                count += 1
    except Exception:
        pass
    return count

def get_prior_split_candle_drops(ticker):
    out = {'weekly': None, 'monthly': None}
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    try:
        for key, interval in (('weekly', '1wk'), ('monthly', '1mo')):
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                   f"?events=splits&interval={interval}&range=10y")
            r = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()['chart']['result'][0]
            ts = r.get('timestamp') or []
            q = r['indicators']['quote'][0]
            splits = (r.get('events') or {}).get('splits', {})
            for item in splits.values():
                if not item.get('numerator', 1) < item.get('denominator', 1):
                    continue
                sdate = item.get('date')
                if sdate is None or sdate > now_ts - 86400:
                    continue
                idx = None
                for i, t in enumerate(ts):
                    if t <= sdate:
                        idx = i
                    else:
                        break
                if idx is None:
                    continue
                o, c = q['open'][idx], q['close'][idx]
                if not o or not c:
                    continue
                chg = (c / o - 1) * 100
                if out[key] is None or chg < out[key]:
                    out[key] = chg
    except Exception as e:
        print(f"Prior split drops error ({ticker}):", e)
    return out

def evaluate_mm_criteria(ticker, factor, post_split_float, prior_splits, unscheduled=False):
    matched = []
    if 0 < post_split_float < 900_000:
        matched.append("Float بعد التقسيم أقل من 900 ألف")
    drops = get_prior_split_candle_drops(ticker)
    if drops['weekly'] is not None and drops['weekly'] <= -40:
        matched.append(f"تقسيم سابق تبعه هبوط أسبوعي {round(drops['weekly'], 1)}%")
    if drops['monthly'] is not None and drops['monthly'] <= -30:
        matched.append(f"تقسيم سابق تبعه هبوط شهري {round(drops['monthly'], 1)}%")
    if factor and factor > 30:
        matched.append("نسبة تقسيم أعلى من 1:30")
    if prior_splits + 1 > 3:
        matched.append("تقسيم مكرر أكثر من 3 مرات")
    if unscheduled:
        matched.append("غير مجدول (غير معلن بتقويم Nasdaq)")
    return matched

def get_split_candle_open(ticker):
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        r = res['chart']['result'][0]
        q = r['indicators']['quote'][0]
        opens = q.get('open', [])
        for o in opens:
            if o is not None and o > 0:
                return float(o)
    except Exception as e:
        print(f"Split candle open error ({ticker}):", e)
    return None

def get_3m_candles(ticker, limit=9):
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        r = res['chart']['result'][0]
        ts = r['timestamp']
        q = r['indicators']['quote'][0]
        buckets = {}
        for i, t in enumerate(ts):
            o, h, l, c, v = q['open'][i], q['high'][i], q['low'][i], q['close'][i], q['volume'][i]
            if None in (o, h, l, c, v):
                continue
            key = t - (t % 180)
            b = buckets.get(key)
            if not b:
                buckets[key] = {'o': o, 'h': h, 'l': l, 'c': c, 'v': v}
            else:
                b['h'] = max(b['h'], h)
                b['l'] = min(b['l'], l)
                b['c'] = c
                b['v'] += v
        candles = [buckets[k] for k in sorted(buckets)]
        if len(candles) > 1:
            candles = candles[:-1]
        return candles[-limit:]
    except Exception as e:
        print(f"3m candles error ({ticker}):", e)
        return []

def analyze_3m_trend(ticker):
    candles = get_3m_candles(ticker, 9)
    if len(candles) < 3:
        return None
    last3 = candles[-3:]
    prev = candles[:-3] if len(candles) >= 6 else candles[:1]
    avg_prev_vol = (sum(c['v'] for c in prev) / len(prev)) if prev else 1.0
    vol_ratio = (last3[-1]['v'] / avg_prev_vol) if avg_prev_vol > 0 else 1.0
    closes_up = last3[0]['c'] < last3[1]['c'] < last3[2]['c']
    closes_down = last3[0]['c'] > last3[1]['c'] > last3[2]['c']
    direction = None
    if closes_up and last3[-1]['c'] > last3[-1]['o']:
        direction = "up"
    elif closes_down and last3[-1]['c'] < last3[-1]['o']:
        direction = "down"
    return {'direction': direction, 'vol_ratio': vol_ratio}

def get_live_snapshot(ticker):
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=COMMON_HEADERS, timeout=8).json()
        r = res['chart']['result'][0]
        meta = r.get('meta', {})
        periods = meta.get('currentTradingPeriod', {})
        reg_start = periods.get('regular', {}).get('start', 0)
        reg_end = periods.get('regular', {}).get('end', 0)
        post_start = periods.get('post', {}).get('start', reg_end)
        ts = r.get('timestamp', [])
        q = r['indicators']['quote'][0]
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if now_ts < reg_start:
            session_type = "PRE"
            target_start = periods.get('pre', {}).get('start', 0)
            base_price = meta.get('previousClose') or meta.get('chartPreviousClose')
            official_vol = meta.get('preMarketVolume') or meta.get('regularMarketVolume') or 0
        elif reg_start <= now_ts < reg_end:
            session_type = "REG"
            target_start = reg_start
            base_price = meta.get('previousClose') or meta.get('chartPreviousClose')
            official_vol = meta.get('regularMarketVolume') or 0
        else:
            session_type = "AH"
            target_start = post_start
            base_price = meta.get('regularMarketPrice') or meta.get('previousClose')
            official_vol = meta.get('postMarketVolume') or meta.get('regularMarketVolume') or 0
        snap = {
            'session': session_type, 'open': None, 'last': meta.get('regularMarketPrice'),
            'high': None, 'low': None, 'vol': official_vol, 'base_price': base_price
        }
        calc_vol = 0.0
