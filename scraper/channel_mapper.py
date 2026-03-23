"""
channel_mapper.py
-----------------
通路名稱正規化：將使用者輸入或爬蟲抓到的各種通路名稱變體
統一對應到標準 channel_id 與標準商家名稱。
"""

from __future__ import annotations
import re
from typing import Optional

# ── 標準商家名稱 → channel_id 對照 ─────────────────────────────────────────
MERCHANT_TO_CHANNEL: dict[str, str] = {
    # 超商
    "7-ELEVEN":     "convenience_store",
    "全家":          "convenience_store",
    "萊爾富":        "convenience_store",
    "OK mart":      "convenience_store",
    # 超市/量販
    "全聯":          "supermarket",
    "家樂福":        "supermarket",
    "大潤發":        "supermarket",
    "愛買":          "supermarket",
    "COSTCO":       "supermarket",
    "頂好":          "supermarket",
    # 電商
    "蝦皮":          "ecommerce",
    "momo購物":      "ecommerce",
    "PChome":       "ecommerce",
    "Yahoo購物中心": "ecommerce",
    "博客來":        "ecommerce",
    "friDay購物":    "ecommerce",
    "91APP":        "ecommerce",
    # 外送
    "Uber Eats":    "food_delivery",
    "foodpanda":    "food_delivery",
    # 交通
    "台鐵":          "transport",
    "高鐵":          "transport",
    "台北捷運":      "transport",
    "高雄捷運":      "transport",
    "Uber":         "transport",
    "計程車":        "transport",
    "YouBike":      "transport",
    "iRent":        "transport",
    "WeMo Scooter": "transport",
    # 餐飲
    "麥當勞":        "dining",
    "肯德基":        "dining",
    "摩斯漢堡":      "dining",
    "星巴克":        "dining",
    "路易莎":        "dining",
    "50嵐":          "dining",
    "清心":          "dining",
    # 旅遊
    "中華航空":      "travel",
    "長榮航空":      "travel",
    "台灣虎航":      "travel",
    "Agoda":        "travel",
    "Booking.com":  "travel",
    "Klook":        "travel",
    "KKday":        "travel",
    "易遊網":        "travel",
    # 娛樂
    "威秀影城":      "entertainment",
    "國賓影城":      "entertainment",
    "好樂迪":        "entertainment",
    "錢櫃":          "entertainment",
    "Netflix":      "entertainment",
    "Spotify":      "entertainment",
    # 加油
    "中油":          "gas_station",
    "台塑石化":      "gas_station",
    "全國加油站":    "gas_station",
    # 藥妝
    "屈臣氏":        "pharmacy",
    "康是美":        "pharmacy",
    "大樹藥局":      "pharmacy",
    "躍獅連鎖藥局":  "pharmacy",
    # 行動支付
    "LINE Pay":     "mobile_payment",
    "街口支付":      "mobile_payment",
    "台灣 Pay":      "mobile_payment",
    "Pi 拍錢包":     "mobile_payment",
    "Apple Pay":    "mobile_payment",
    "Google Pay":   "mobile_payment",
    "Samsung Pay":  "mobile_payment",
}

# ── 各種輸入變體 → 標準商家名稱 ─────────────────────────────────────────────
_SYNONYMS: dict[str, str] = {
    # 7-ELEVEN
    "7-11": "7-ELEVEN", "711": "7-ELEVEN", "小7": "7-ELEVEN",
    "seven": "7-ELEVEN", "seven eleven": "7-ELEVEN", "7eleven": "7-ELEVEN",
    "統一超商": "7-ELEVEN", "統一": "7-ELEVEN",
    "7-eleven": "7-ELEVEN",
    # 全家
    "全家便利商店": "全家", "family mart": "全家", "familymart": "全家",
    "全家familymart": "全家",
    # 萊爾富
    "hi-life": "萊爾富", "hilife": "萊爾富", "萊爾富便利商店": "萊爾富",
    # OK mart
    "ok": "OK mart", "ok超商": "OK mart", "ok便利商店": "OK mart",
    # 全聯
    "全聯福利中心": "全聯", "pxmart": "全聯", "全聯超市": "全聯",
    # 家樂福
    "carrefour": "家樂福", "家樂福量販": "家樂福",
    # 大潤發
    "rt-mart": "大潤發", "大潤發量販": "大潤發",
    # 愛買
    "a-mart": "愛買", "愛買量販": "愛買",
    # COSTCO
    "好市多": "COSTCO", "costco量販": "COSTCO", "costco": "COSTCO",
    # 蝦皮
    "蝦皮購物": "蝦皮", "shopee": "蝦皮",
    # momo
    "momo": "momo購物", "富邦媒體": "momo購物", "momoshop": "momo購物",
    # PChome
    "pchome24h": "PChome", "pchome購物": "PChome", "pc home": "PChome",
    # Yahoo
    "yahoo購物": "Yahoo購物中心", "yahoo mall": "Yahoo購物中心",
    "奇摩購物": "Yahoo購物中心",
    # 博客來
    "books.com.tw": "博客來", "博客來書店": "博客來",
    # friDay
    "friday購物": "friDay購物", "friday": "friDay購物",
    # Uber Eats
    "ubereats": "Uber Eats", "uber eat": "Uber Eats", "優食": "Uber Eats",
    # foodpanda
    "熊貓": "foodpanda", "foodpanda外送": "foodpanda", "熊貓外送": "foodpanda",
    # 台鐵
    "台灣鐵路": "台鐵", "tra": "台鐵", "火車": "台鐵",
    # 高鐵
    "台灣高速鐵路": "高鐵", "thsr": "高鐵", "hsr": "高鐵",
    # 台北捷運
    "捷運": "台北捷運", "mrt": "台北捷運", "台北mrt": "台北捷運",
    # Uber（叫車）
    "優步": "Uber", "uber叫車": "Uber",
    # 麥當勞
    "mcdonald's": "麥當勞", "mcdonalds": "麥當勞", "麥記": "麥當勞",
    # 肯德基
    "kfc": "肯德基",
    # 星巴克
    "starbucks": "星巴克",
    # 路易莎
    "路易莎咖啡": "路易莎", "louisa": "路易莎",
    # 航空
    "中華航空": "中華航空", "china airlines": "中華航空",
    "長榮航空": "長榮航空", "eva air": "長榮航空",
    "台灣虎航": "台灣虎航", "tigerair": "台灣虎航",
    # 中油
    "cpc": "中油", "台灣中油": "中油",
    # 台塑
    "台塑": "台塑石化", "fpcc": "台塑石化",
    # 屈臣氏
    "watsons": "屈臣氏", "屈臣氏藥局": "屈臣氏",
    # 康是美
    "cosmed": "康是美", "康是美藥妝": "康是美",
    # LINE Pay
    "linepay": "LINE Pay", "line支付": "LINE Pay", "line pay money": "LINE Pay",
    # 街口
    "jkopay": "街口支付", "街口": "街口支付",
    # 台灣 Pay
    "taiwan pay": "台灣 Pay", "twpay": "台灣 Pay", "台灣pay": "台灣 Pay",
    # Apple/Google/Samsung Pay
    "applepay": "Apple Pay", "googlepay": "Google Pay",
    "g pay": "Google Pay", "samsungpay": "Samsung Pay",
}

# ── 使用者輸入 channel 關鍵字 → channel_id ──────────────────────────────────
_CATEGORY_KEYWORDS: dict[str, str] = {
    # convenience_store
    "超商": "convenience_store", "便利商店": "convenience_store",
    # supermarket
    "超市": "supermarket", "量販": "supermarket", "大賣場": "supermarket",
    # ecommerce
    "電商": "ecommerce", "網購": "ecommerce", "線上購物": "ecommerce",
    "網路商城": "ecommerce",
    # food_delivery
    "外送": "food_delivery", "叫外賣": "food_delivery",
    # transport
    "交通": "transport", "大眾運輸": "transport",
    # dining
    "餐廳": "dining", "吃飯": "dining", "餐飲": "dining",
    "外食": "dining", "速食": "dining", "咖啡": "dining", "飲料": "dining",
    # travel
    "旅遊": "travel", "旅行": "travel", "機票": "travel",
    "飯店": "travel", "訂房": "travel", "出國": "travel", "住宿": "travel",
    "飛機": "travel", "搭機": "travel", "航班": "travel", "航空公司": "travel",
    "哩程": "travel", "里程": "travel", "miles": "travel", "mile": "travel",
    "ANA": "travel", "ana": "travel",
    # entertainment
    "娛樂": "entertainment", "電影": "entertainment",
    "ktv": "entertainment", "卡拉ok": "entertainment",
    # gas_station
    "加油": "gas_station", "加油站": "gas_station",
    # pharmacy
    "藥妝": "pharmacy", "藥局": "pharmacy",
    # mobile_payment
    "行動支付": "mobile_payment", "電子支付": "mobile_payment",
    # general
    "一般": "general", "一般消費": "general", "其他": "general",
    "國內消費": "general", "海外消費": "general",
}


def normalize_merchant(raw: str) -> str:
    """將各種輸入變體對應到標準商家名稱（找不到則原樣回傳）。"""
    key = raw.strip().lower()
    if key in _SYNONYMS:
        return _SYNONYMS[key]
    # 部分比對
    for syn, canonical in _SYNONYMS.items():
        if syn in key or key in syn:
            return canonical
    # 直接對照標準名稱（大小寫不敏感）
    for canonical in MERCHANT_TO_CHANNEL:
        if canonical.lower() == key:
            return canonical
    return raw.strip()


def get_channel_id(merchant_or_category: str) -> Optional[str]:
    """
    輸入商家名稱或通路分類描述，回傳 channel_id。
    例如：
        "7-11"    → "convenience_store"
        "蝦皮"    → "ecommerce"
        "超市"    → "supermarket"
    """
    normalized = normalize_merchant(merchant_or_category)
    if normalized in MERCHANT_TO_CHANNEL:
        return MERCHANT_TO_CHANNEL[normalized]

    # 嘗試 category keyword 比對
    key = merchant_or_category.strip().lower()
    for keyword, cat_id in _CATEGORY_KEYWORDS.items():
        if keyword in key:
            return cat_id

    return None


def extract_merchants_from_text(text: str) -> list[str]:
    """
    從一段中文優惠說明文字中，找出所有提到的標準商家名稱。
    例：「統一超商、全家、萊爾富消費享5%回饋」→ ["7-ELEVEN", "全家", "萊爾富"]
    """
    found: list[str] = []
    # 先用同義詞 dict
    for syn, canonical in _SYNONYMS.items():
        if syn in text.lower() and canonical not in found:
            found.append(canonical)
    # 再直接比對標準商家名稱
    for canonical in MERCHANT_TO_CHANNEL:
        if canonical in text and canonical not in found:
            found.append(canonical)
    return found


def infer_channel_id_from_merchants(merchants: list[str]) -> Optional[str]:
    """
    給定一組商家名稱，推斷最可能的 channel_id（投票多數決）。
    """
    if not merchants:
        return None
    votes: dict[str, int] = {}
    for m in merchants:
        cid = MERCHANT_TO_CHANNEL.get(m)
        if cid:
            votes[cid] = votes.get(cid, 0) + 1
    return max(votes, key=lambda k: votes[k]) if votes else None
