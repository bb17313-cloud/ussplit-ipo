
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

# SEC
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "StockBot your-email@example.com")
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}

NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
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
# دوال التقسيم العكسي (Reverse Splits) فقط
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
    """تحديد موثوق هل التقسيم عكسي فقط (يمنع Forward / Stock Dividend مثل 1.5:1)"""
    if num is None or den is None:
        s = str(ratio_str).lower()
        return "reverse" in s or "consolidation" in s
    # عكسي فقط عندما يكون الرقم الأول أصغر (مثل 1:10 أو 1-for-16)
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
        return False, 1.0, 0.0, 0.0
    factor = max(num, den) / min(num, den)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d&includePrePost=true"
        res = requests.get(url, headers=headers, timeout=8).json()
        result = res.get('chart', {}).get('result', [])
        if not result:
            return True, factor, 0.0, 0.0
        meta = result[0].get('meta', {})
        prev_close = meta.get('previousClose') or meta.get('chartPreviousClose') or 0.0
        current_price = (meta.get('regularMarketPrice') or
                         meta.get('preMarketPrice') or
                         meta.get('postMarketPrice') or 0.0)
        if prev_close <= 0 or current_price <= 0:
            return True, factor, current_price, prev_close
        expected = prev_close * factor
        if current_price < (prev_close * (factor * 0.35)) and current_price < 1.5:
            print(f"🚫 [استبعاد قوي] {ticker}: السعر ${current_price} بعيد جدًا عن المتوقع ≈${round(expected, 2)}")
            return False, factor, current_price, prev_close
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
                else:
                    print(f"❌ تم استبعاد {symbol} (نسبة: {ratio_str})")
    except Exception as e:
        print(f"❌ Nasdaq API Error ({date_str}):", e)
    return list(splits_dict.values())

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
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {
        'found': False, 'is_valid_stock': True, 'price': 0.0, 'change_pct': 0.0, 'raw_float': 0.0,
        'total_shares': 0.0, 'sector': 'غير متوفر', 'industry': 'غير متوفر', 'country': 'غير متوفر',
        'volume': 0.0, 'market_cap': 0.0
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
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
    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=8).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for item in splits.values():
            if item.get('numerator', 1) < item.get('denominator', 1):
                count += 1
    except Exception:
        pass
    return count

def get_split_candle_open(ticker):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
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
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
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
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
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
        for i, t in enumerate(ts):
            o, h, l, c, v = q['open'][i], q['high'][i], q['low'][i], q['close'][i], q['volume'][i]
            if None in (o, h, l, c, v):
                continue
            snap['last'] = c
            if t >= target_start:
                if snap['open'] is None:
                    snap['open'] = o
                snap['high'] = h if snap['high'] is None else max(snap['high'], h)
                snap['low'] = l if snap['low'] is None else min(snap['low'], l)
                calc_vol += v
        if official_vol and official_vol > 0:
            snap['vol'] = official_vol
        else:
            snap['vol'] = calc_vol
        if snap['vol'] <= 0:
            tv_meta = get_tradingview_stock_data(ticker)
            snap['vol'] = tv_meta.get('volume', 0.0)
        return snap if snap['last'] else None
    except Exception as e:
        print(f"Live snapshot error ({ticker}):", e)
        return None

def build_live_card(sym, snap, trend_word, ksa_time_str, ratio_str="", split_open=None, activated_at="", sector="غير متوفر", industry="غير متوفر", country="غير متوفر"):
    tv_url = f"https://www.tradingview.com/chart/?symbol={sym}"
    session = snap.get('session', 'REG')
    if session == "PRE":
        status = "🟡 ما قبل الافتتاح (Pre-Market)"
    elif session == "AH":
        status = "🌙 ما بعد الإغلاق (After-Hours)"
    else:
        status = "🟢 مفتوح (الجلسة الرسمية)"
    if snap['open'] and snap['open'] > 0:
        open_str = f"${round(snap['open'], 4)}"
        base = snap['base_price'] or snap['open']
        chg = ((snap['last'] / base) - 1) * 100 if base > 0 else 0.0
        chg_str = f"{'+' if chg >= 0 else ''}{round(chg, 2)}%"
        hl_str = f"${round(snap['high'], 4)} / ${round(snap['low'], 4)}"
        vol_val = snap.get('vol', 0)
        vol_str = f"{int(vol_val):,} سهم" if vol_val > 0 else "—"
    else:
        open_str = "بانتظار التداول"
        chg_str = "—"
        hl_str = "—"
        vol_str = "—"
    if split_open and split_open > 0 and snap.get('last') and snap['last'] > 0:
        split_chg = ((snap['last'] - split_open) / split_open) * 100
        split_chg_line = f"التغير من شمعة التقسيم ٪+-: <b>{'+' if split_chg >= 0 else ''}{round(split_chg, 2)}%</b>\n"
    else:
        split_chg_line = ""
    ratio_line = f"نسبة التقسيم : <b>{html.escape(ratio_str)}</b>\n" if ratio_str else ""
    activation_line = f"وقت وتاريخ التفعيل: <b>{activated_at}</b>\n" if activated_at else ""
    return (
        f"🔴 <b>LIVE | ${sym}</b>\n"
        f"القطاع: <b>{html.escape(sector)}</b>\n"
        f"الصناعة: <b>{html.escape(industry)}</b>\n"
        f"الدولة: <b>{html.escape(country)}</b>\n"
        f"{ratio_line}"
        f"{activation_line}"
        f"الحالة: <b>{status}</b>\n"
        f"بداية الجلسة: <b>{open_str}</b>\n"
        f"السعر الآن: <b>${round(snap['last'], 4)}</b>\n"
        f"التغير للجلسة: <b>{chg_str}</b>\n"
        f"{split_chg_line}"
        f"الاتجاه (9 شموع / 3د): <b>{trend_word}</b>\n"
        f"أعلى / أدنى بالجلسة: <b>{hl_str}</b>\n"
        f"فوليوم الجلسة: <b>{vol_str}</b>\n"
        f"آخر تحديث: <b>{ksa_time_str} (السعودية)</b>\n"
        f"الشارت: <a href='{tv_url}'>TradingView</a>"
    )

def run_splits_task():
    print("=" * 50)
    now_ksa = get_ksa_now()
    print(f"🔄 [SPLITS] بداية الدورة: {now_ksa.strftime('%Y-%m-%d %H:%M:%S')}")
    watchlist = load_watchlist(SPLITS_WATCHLIST_FILE)
    now_est = get_est_now()
    today_est_str = now_est.strftime("%Y-%m-%d")
    ksa_date_str = now_ksa.strftime("%Y-%m-%d")
    ksa_datetime_str = now_ksa.strftime("%Y-%m-%d %H:%M")
    ksa_time_str = now_ksa.strftime("%H:%M")
    sent_today_key = f"sent_today_{today_est_str}"
    cleaned_watchlist = {}
    for sym, item in watchlist.items():
        if sym == sent_today_key:
            cleaned_watchlist[sym] = item
        elif isinstance(item, dict) and item.get("added_date") == today_est_str:
            cleaned_watchlist[sym] = item
    watchlist = cleaned_watchlist
    splits = get_today_reverse_splits()
    snapshot_next_day_floats()
    if not watchlist.get(sent_today_key):
        updates = []
        for item in splits:
            symbol = item['symbol']
            num = item['num']
            den = item['den']
            tv_data = get_tradingview_stock_data(symbol)
            if not tv_data['is_valid_stock']:
                continue
            current_price = tv_data['price']
            change_pct = tv_data['change_pct']
            price_curr_display = f"${round(current_price, 4)}"
            split_open = get_split_candle_open(symbol) or current_price
            if split_open and split_open > 0 and current_price > 0:
                split_chg = ((current_price - split_open) / split_open) * 100
                split_candle_change_str = f"{'+' if split_chg >= 0 else ''}{round(split_chg, 2)}%"
            else:
                split_candle_change_str = "غير متوفر"
            watchlist[symbol] = {
                "added_date": today_est_str,
                "ratio": item['raw_text'],
                "split_open": split_open,
                "activated_at": ksa_datetime_str,
                "sector": tv_data['sector'],
                "industry": tv_data['industry'],
                "country": tv_data['country']
            }
            base_shares = resolve_post_split_float(
                symbol, get_base_shares(tv_data, current_price), item.get('factor', 1.0)
            )
            post_split_float_str = format_shares_count(base_shares)
            prior_splits = get_prior_splits_count(symbol)
            ratio_ar = format_ratio_ar(num, den, item['raw_text'])
            sector_and_industry = f"{tv_data['sector']} / {tv_data['industry']}"
            tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"
            change_pct_str = f"{'+' if change_pct >= 0 else ''}{round(change_pct, 2)}%"
            info = (
                f"🔷 <b>${symbol}</b>\n"
                f"تاريخ التقسيم: <b>اليوم ({ksa_date_str})</b>\n"
                f"وقت التنفيذ والتفعيل: <b>{ksa_datetime_str} (السعودية)</b>\n"
                f"نسبة التقسيم : <b>{html.escape(ratio_ar)}</b>\n"
                f"السعر الان : <b>{price_curr_display}</b>\n"
                f"Free float بعد التقسيم: <b>{post_split_float_str}</b>\n"
                f"القطاع والنشاط: <b>{html.escape(sector_and_industry)}</b>\n"
                f"الدولة: <b>{html.escape(tv_data['country'])}</b>\n"
                f"تقسيمات سابقه: ( <b>{prior_splits}</b> )\n"
                f"التغير الحالي ٪+-: <b>{change_pct_str}</b>\n"
                f"التغير من شمعة التقسيم ٪+-: <b>{split_candle_change_str}</b>\n"
                f"الشارت: <a href='{tv_url}'>TradingView Chart</a>"
            )
            updates.append(info)
        if updates:
            header = f"📌 <b>أسهم التقسيم العكسي المؤكد تنفيذها اليوم ({ksa_date_str})</b>\n\n"
            msg = header + "\n\n───────────────\n\n".join(updates)
            send_telegram_message(msg)
            print(f"✅ تم إرسال الأسهم المؤكدة ({len(updates)} أسهم)")
        else:
            send_telegram_message(f"📌 <b>أسهم التقسيم العكسي — اليوم ({ksa_date_str})</b>\n\nلا توجد تقسيمات عكسية مؤكدة ومطبقة فعلياً في البورصة حتى الآن.")
            print("ℹ️ لا توجد تقسيمات مؤكدة اليوم")
        watchlist[sent_today_key] = True
    for sym, item_data in list(watchlist.items()):
        if sym.startswith("sent_today_"):
            continue
        snap = get_live_snapshot(sym)
        if not snap:
            continue
        trend = analyze_3m_trend(sym)
        if trend and trend['direction'] == "up":
            trend_word = "📈 صاعد قوي"
        elif trend and trend['direction'] == "down":
            trend_word = "📉 هابط قوي"
        else:
            candles = get_3m_candles(sym, 3)
            if len(candles) >= 3:
                c0, c1, c2 = candles[-3]['c'], candles[-2]['c'], candles[-1]['c']
                if c0 < c1 < c2:
                    trend_word = "📈 صاعد"
                elif c0 > c1 > c2:
                    trend_word = "📉 هابط"
                else:
                    trend_word = "➡️ عرضي"
            else:
                trend_word = "غير كافٍ"
        ratio_str = item_data.get("ratio", "")
        split_open_saved = item_data.get("split_open")
        activated_at_saved = item_data.get("activated_at", ksa_datetime_str)
        sec_saved = item_data.get("sector", "غير متوفر")
        ind_saved = item_data.get("industry", "غير متوفر")
        cnt_saved = item_data.get("country", "غير متوفر")
        card = build_live_card(
            sym, snap, trend_word, ksa_time_str,
            ratio_str=ratio_str,
            split_open=split_open_saved,
            activated_at=activated_at_saved,
            sector=sec_saved,
            industry=ind_saved,
            country=cnt_saved
        )
        msg_id = item_data.get("live_msg_id")
        if msg_id:
            success = edit_telegram_message(msg_id, card)
            if not success:
                new_id = send_telegram_get_id(card)
                if new_id:
                    watchlist[sym]["live_msg_id"] = new_id
        else:
            new_id = send_telegram_get_id(card)
            if new_id:
                watchlist[sym]["live_msg_id"] = new_id
    print("✅ تم تحديث بطاقات LIVE المباشرة (تقسيم عكسي)")
    save_watchlist(watchlist, SPLITS_WATCHLIST_FILE)
    print("🏁 [SPLITS] انتهت الدورة")
    print("=" * 50)

# ---------------------------------------------------------
# دوال IPO
# ---------------------------------------------------------
def load_ipo_watchlist():
    if os.path.exists(IPO_WATCHLIST_FILE):
        try:
            with open(IPO_WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_ipo_watchlist(watchlist):
    with open(IPO_WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def get_today_ipos():
    today = get_est_now().date()
    month_str = today.strftime("%Y-%m")
    target = today.strftime("%m/%d/%Y")
    ipos = {}
    try:
        url = f"https://api.nasdaq.com/api/ipo/calendar?date={month_str}"
        res = requests.get(url, headers=NASDAQ_HEADERS, timeout=10)
        if res.status_code != 200:
            print(f"❌ Nasdaq IPO status: {res.status_code}")
            return []
        data = (res.json() or {}).get('data') or {}
        priced = ((data.get('priced') or {}).get('rows')) or []
        upcoming = (((data.get('upcoming') or {}).get('upcomingTable') or {}).get('rows')) or []
        for rows, date_key, status in ((upcoming, 'expectedPriceDate', 'upcoming'),
                                       (priced, 'pricedDate', 'priced')):
            for row in rows:
                if not row:
                    continue
                if str(row.get(date_key, '')).strip() != target:
                    continue
                symbol = str(row.get('proposedTickerSymbol', '')).strip().upper()
                if not symbol:
                    continue
                price_raw = str(row.get('proposedSharePrice', '') or '').strip()
                nums = parse_numbers(price_raw)
                price_num = (sum(nums) / len(nums)) if nums else 0.0
                shares_nums = parse_numbers(row.get('sharesOffered', ''))
                ipos[symbol] = {
                    'symbol': symbol,
                    'name': str(row.get('companyName', '') or '').strip(),
                    'price_raw': price_raw,
                    'price_num': price_num,
                    'shares_offered': shares_nums[0] if shares_nums else 0.0,
                    'cal_status': status
                }
    except Exception as e:
        print("❌ Nasdaq IPO API Error:", e)
    return list(ipos.values())

REG_A_FORMS = ("253G1", "253G2", "253G3", "253G4", "1-A", "1-A/A", "QUALIF", "1-A POS")
TRAD_FORMS = ("424B4", "424B1", "424B3", "S-1", "S-1/A", "F-1", "F-1/A")

def sec_find_filings(company_name):
    if not company_name:
        return []
    start = (get_est_now().date() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    end = get_est_now().date().strftime("%Y-%m-%d")
    params = {
        "q": f'"{company_name}"',
        "forms": ",".join(REG_A_FORMS + TRAD_FORMS),
        "dateRange": "custom", "startdt": start, "enddt": end
    }
    try:
        res = requests.get("https://efts.sec.gov/LATEST/search-index",
                           params=params, headers=SEC_HEADERS, timeout=20)
        if res.status_code == 200:
            return (res.json().get("hits") or {}).get("hits") or []
    except Exception as e:
        print(f"SEC search error ({company_name}):", e)
    return []

def hit_form(hit):
    src = hit.get("_source", {}) or {}
    return str(src.get("form") or src.get("file_type") or "").upper()

def hit_url(hit):
    try:
        adsh, fname = str(hit.get("_id", "")).split(":", 1)
        ciks = (hit.get("_source", {}) or {}).get("ciks") or []
        cik = str(ciks[0]).lstrip("0")
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}"
    except Exception:
        return None

def detect_greenshoe_in_doc(url):
    try:
        res = requests.get(url, headers=SEC_HEADERS, timeout=30)
        if res.status_code != 200:
            return None
        text = html.unescape(re.sub(r'<[^>]+>', ' ', res.text[:4_000_000]))
        text = re.sub(r'\s+', ' ', text)
        m = re.search(
            r'option[^.]{0,200}?(?:purchase|buy)[^.]{0,60}?up to\s+([\d,]+)\s+(?:additional\s+)?(?:ordinary\s+|common\s+|class [a-z]\s+)?shares',
            text, re.I)
        if m:
            return f"✅ نعم — حتى {m.group(1)} سهم إضافي"
        if re.search(r'over-?allotment|greenshoe', text, re.I):
            return "✅ نعم (الكمية غير مستخرجة)"
        return "❌ غير مذكور في النشرة"
    except Exception as e:
        print("Greenshoe parse error:", e)
        return None

def analyze_offering(company_name):
    hits = sec_find_filings(company_name)
    if not hits:
        return None, None
    forms = [hit_form(h) for h in hits]
    if any(f in REG_A_FORMS for f in forms):
        return "Regulation A Tier 2", "❌ غير متاح عادةً في Reg A"
    trad_hits = [h for h in hits if hit_form(h) in TRAD_FORMS]
    if trad_hits:
        trad_hits.sort(key=lambda h: 0 if hit_form(h).startswith("424B") else 1)
        green = None
        url = hit_url(trad_hits[0])
        if url:
            green = detect_greenshoe_in_doc(url)
        return "IPO تقليدي", green
    return None, None

def fmt_pct(v):
    return f"{'+' if v >= 0 else ''}{round(v, 2)}%"

def build_ipo_card(sym, item, tv, ksa_time_str, ksa_date_str):
    tv_url = f"https://www.tradingview.com/chart/?symbol={sym}"
    price_raw = item.get('price_raw', '')
    if price_raw:
        price_disp = price_raw if '$' in price_raw else f"${price_raw}"
    else:
        price_disp = "غير معلن"
    if tv['raw_float'] > 0:
        float_disp = format_shares_count(tv['raw_float'])
    elif item.get('shares_offered', 0) > 0:
        float_disp = f"{format_shares_count(item['shares_offered'])} (المطروحة)"
    else:
        float_disp = "غير متوفر"
    executed = tv['found'] and tv['price'] > 0 and tv['volume'] > 0
    ipo_price = item.get('price_num', 0.0)
    if executed:
        status = "✅ تم التنفيذ (بدأ التداول)"
        cur_price = f"${round(tv['price'], 4)}"
        if ipo_price > 0 and item.get('cal_status') == 'priced':
            chg_str = fmt_pct(((tv['price'] / ipo_price) - 1) * 100)
        elif ipo_price > 0:
            chg_str = f"{fmt_pct(((tv['price'] / ipo_price) - 1) * 100)} (مقابل السعر المتوقع)"
        else:
            chg_str = "غير متوفر"
        vol_str = f"{int(tv['volume']):,} سهم"
    else:
        status = "⏳ بانتظار التنفيذ"
        cur_price = "—"
        chg_str = "—"
        vol_str = "—"
    offering_type = item.get('offering_type') or "غير محدد"
    greenshoe = item.get('greenshoe') or "غير محدد"
    name_line = f"الشركة: <b>{html.escape(item.get('name', ''))}</b>\n" if item.get('name') else ""
    return (
        f"🆕 <b>IPO | ${sym}</b>\n"
        f"{name_line}"
        f"تاريخ الاكتتاب: <b>اليوم ({ksa_date_str})</b>\n"
        f"القطاع: <b>{html.escape(tv['sector'])}</b>\n"
        f"الصناعة: <b>{html.escape(tv['industry'])}</b>\n"
        f"الدولة: <b>{html.escape(tv['country'])}</b>\n"
        f"سعر الاكتتاب المتوقع: <b>{html.escape(price_disp)}</b>\n"
        f"Free float: <b>{float_disp}</b>\n"
        f"نوع الطرح (Reg A Tier 2 / IPO تقليدي): <b>{html.escape(offering_type)}</b>\n"
        f"خيار الاكتتاب الزائد (Greenshoe): <b>{html.escape(greenshoe)}</b>\n"
        f"حالة التنفيذ: <b>{status}</b>\n"
        f"السعر الحالي: <b>{cur_price}</b>\n"
        f"السعر من التنفيذ ٪+-: <b>{chg_str}</b>\n"
        f"Vol: <b>{vol_str}</b>\n"
        f"آخر تحديث: <b>{ksa_time_str} (السعودية)</b>\n"
        f"الشارت: <a href='{tv_url}'>TradingView</a>"
    )

def run_ipo_task():
    print("=" * 50)
    now_ksa = get_ksa_now()
    now_est = get_est_now()
    print(f"🔄 [IPO] بداية الدورة: {now_ksa.strftime('%Y-%m-%d %H:%M:%S')}")
    today_est_str = now_est.strftime("%Y-%m-%d")
    ksa_date_str = now_ksa.strftime("%Y-%m-%d")
    ksa_time_str = now_ksa.strftime("%H:%M")
    sent_today_key = f"sent_today_{today_est_str}"
    watchlist = load_ipo_watchlist()
    cleaned = {}
    for sym, item in watchlist.items():
        if sym == sent_today_key:
            cleaned[sym] = item
        elif isinstance(item, dict) and item.get("added_date") == today_est_str:
            cleaned[sym] = item
    watchlist = cleaned
    todays = get_today_ipos()
    
    # إرسال رسالة "لا توجد" دائماً عند عدم وجود اكتتابات (لإثبات أن الفحص يعمل)
    if not todays:
        send_telegram_get_id(f"📌 <b>أسهم الاكتتاب IPO — اليوم ({ksa_date_str})</b>\n\nلا توجد اكتتابات مجدولة اليوم.")
        watchlist[sent_today_key] = True
        print("ℹ️ تم إرسال رسالة عدم وجود اكتتابات (تأكيد الفحص)")
    else:
        if sent_today_key in watchlist:
            del watchlist[sent_today_key]
        for ipo in todays:
            sym = ipo['symbol']
            if sym not in watchlist:
                watchlist[sym] = {"added_date": today_est_str, "sec_attempts": 0}
            entry = watchlist[sym]
            entry['name'] = ipo['name']
            entry['price_raw'] = ipo['price_raw']
            entry['price_num'] = ipo['price_num']
            entry['shares_offered'] = ipo['shares_offered']
            entry['cal_status'] = ipo['cal_status']
        for sym, item in list(watchlist.items()):
            if sym.startswith("sent_today_"):
                continue
            if (not item.get('offering_type')) and item.get('sec_attempts', 0) < 5:
                item['sec_attempts'] = item.get('sec_attempts', 0) + 1
                otype, green = analyze_offering(item.get('name', ''))
                if otype:
                    item['offering_type'] = otype
                    item['greenshoe'] = green or "غير محدد"
            tv = get_tradingview_stock_data(sym)
            if tv['found'] and not tv['is_valid_stock']:
                continue
            card = build_ipo_card(sym, item, tv, ksa_time_str, ksa_date_str)
            msg_id = item.get("live_msg_id")
            if msg_id:
                if not edit_telegram_message(msg_id, card):
                    new_id = send_telegram_get_id(card)
                    if new_id:
                        watchlist[sym]["live_msg_id"] = new_id
            else:
                new_id = send_telegram_get_id(card)
                if new_id:
                    watchlist[sym]["live_msg_id"] = new_id
    save_ipo_watchlist(watchlist)
    print("🏁 [IPO] انتهت الدورة")
    print("=" * 50)

# ---------------------------------------------------------
# التشغيل (دورة واحدة فقط - مناسب لـ GitHub Actions)
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🔄 تم تشغيل البوت المدمج (IPO + Reverse Splits) - دورة واحدة")
    try:
        run_splits_task()
        run_ipo_task()
        print("✅ انتهت الدورة بنجاح")
    except Exception as e:
        print(f"❌ حدث خطأ غير متوقع: {e}")
