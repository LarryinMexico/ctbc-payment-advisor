"""
microsite_scraper.py
--------------------
爬取 CTBC 信用卡微型網站（/content/dam/minisite/）的詳細促銷優惠資料。

目前已知有微型網站的卡片：
  - ctbc_c_linepay  → LINEPay

輸出：data/scraped/microsite_deals.json
格式：{card_id: {card_name, deals: [{merchant, channel_id, cashback_rate, ...}]}}
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_PATH  = PROJECT_ROOT / "data" / "scraped" / "microsite_deals.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

# ── 已知有微型網站的卡片設定 ─────────────────────────────────────────────────

MICROSITE_BASE = "https://www.ctbcbank.com/content/dam/minisite/long/creditcard"

MICROSITE_CARDS: dict[str, dict] = {
    "ctbc_c_linepay": {
        "card_name": "LINE Pay信用卡",
        "slug":      "LINEPay",
        "pages":     [
            "page_food",
            "page_shopping",
            "page_fashion",
            "page_pet",
            "page_life",
            "page_travel",
        ],
    },
}

# 子頁面預設的 channel_id（按商家名稱再精細化）
PAGE_DEFAULT_CHANNEL: dict[str, str] = {
    "page_food":     "dining",
    "page_shopping": "ecommerce",
    "page_fashion":  "pharmacy",
    "page_pet":      "general",
    "page_life":     "general",
    "page_travel":   "travel",
}

# ── 商家名稱 → channel_id 精細化對照 ─────────────────────────────────────────

_MERCHANT_CHANNEL_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"foodpanda|panda",           re.I), "food_delivery"),
    (re.compile(r"uber\s*eats",               re.I), "food_delivery"),
    (re.compile(r"7-eleven|7eleven|711|全家|萊爾富|ok超商|hi-life", re.I), "convenience_store"),
    (re.compile(r"全聯|家樂福|costco|好市多|大潤發|愛買|小北百貨|唐吉訶德|donki|don don", re.I), "supermarket"),
    (re.compile(r"momo|蝦皮|shopee|pchome|yahoo|淘寶|博客來|東森|etmall|global mall|환球", re.I), "ecommerce"),
    (re.compile(r"星巴克|starbucks|摩斯|mos|麥當勞|mcdonald|kfc|肯德基|pizza|壽司郎|藏壽司|客美多|早餐|咖啡|餐廳|飯店", re.I), "dining"),
    (re.compile(r"netflix|kkbox|spotify|youtube|disney|遊戲|電影|ktv|錢櫃|好樂迪|娛樂", re.I), "entertainment"),
    (re.compile(r"kkday|klook|booking|hotels|agoda|airbnb|機票|旅遊|hotel", re.I), "travel"),
    (re.compile(r"捷運|公車|bus|台鐵|高鐵|uber(?!\s*eats)|計程車|加油|中油|台塑", re.I), "transport"),
    (re.compile(r"屈臣氏|watson|康是美|大樹藥局|藥局|藥妝|美妝|資生堂|SK-?II|蘭蔻", re.I), "pharmacy"),
    (re.compile(r"ikea|宜得利|無印良品|muji|dyson|studio a|under armour|outlet", re.I), "general"),
    (re.compile(r"line\s*pay|行動支付|apple\s*pay|google\s*pay|街口|悠遊",        re.I), "mobile_payment"),
]


def _infer_channel(merchant: str, page_name: str) -> str:
    """從商家名稱推斷 channel_id，失敗時用頁面預設值。"""
    for pattern, channel_id in _MERCHANT_CHANNEL_MAP:
        if pattern.search(merchant):
            return channel_id
    return PAGE_DEFAULT_CHANNEL.get(page_name, "general")


# ── 日期解析 ──────────────────────────────────────────────────────────────────

def _parse_date_range(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    解析 "2026/1/1~2026/3/31" 或 "即日起至2026/6/30" 等格式。
    回傳 (valid_start, valid_end)，格式為 YYYY-MM-DD 或 None。
    """
    text = text.strip()
    # 形如 YYYY/M/D~YYYY/M/D
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s*[~～至\-]\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if m:
        y1, mo1, d1, y2, mo2, d2 = m.groups()
        start = f"{y1}-{int(mo1):02d}-{int(d1):02d}"
        end   = f"{y2}-{int(mo2):02d}-{int(d2):02d}"
        return start, end

    # 只有結束日
    m = re.search(r"(?:至|截止|~|～)\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return None, f"{y}-{int(mo):02d}-{int(d):02d}"

    # 單一日期
    m = re.search(r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return None, f"{y}-{int(mo):02d}-{int(d):02d}"

    return None, None


# ── 回饋率解析 ────────────────────────────────────────────────────────────────

def _parse_cashback_rate(text: str) -> Optional[float]:
    """從 benefit 文字中提取回饋率（0.05 = 5%）。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return float(m.group(1)) / 100.0
    return None


# ── 單頁解析 ──────────────────────────────────────────────────────────────────

def _parse_page(soup: BeautifulSoup, page_name: str) -> list[dict]:
    """
    解析單一微型網站子頁面，回傳優惠項目清單。
    每個項目對應一個 <li class="card-list__item">。
    """
    deals = []

    # ── 1. 解析 card-list 卡片 ──
    for li in soup.find_all("li", class_="card-list__item"):
        card_div = li.find("div", class_="card")
        if not card_div:
            continue

        # 商家名稱：優先從 img alt，其次從 gtl_ class
        merchant = ""
        img = card_div.find("img")
        if img and img.get("alt"):
            merchant = img["alt"].strip()
        if not merchant:
            btn = card_div.find("a", class_=lambda c: c and any("gtl_" in x for x in (c or [])))
            if btn:
                gtl = next((x for x in (btn.get("class") or []) if x.startswith("gtl_")), "")
                parts = gtl.split("_")
                merchant = parts[2] if len(parts) > 2 else ""

        # 付款方式（card__tag）
        tag_span = card_div.find("span", class_="card__tag")
        payment_method = tag_span.get_text(strip=True) if tag_span else ""

        # 主要優惠（card__main）
        main_tag = card_div.find("strong", class_="card__main")
        benefit = main_tag.get_text(strip=True) if main_tag else ""

        # 日期（card__date）
        date_span = card_div.find("span", class_="card__date")
        date_text = date_span.get_text(strip=True) if date_span else ""
        valid_start, valid_end = _parse_date_range(date_text)

        # 條件（card__text）
        cond_span = card_div.find("span", class_="card__text")
        conditions = cond_span.get_text(" ", strip=True) if cond_span else ""

        # 詳情連結
        btn = card_div.find("a", class_="card__button")
        detail_url = btn.get("href", "") if btn else ""

        # 回饋率
        cashback_rate = _parse_cashback_rate(benefit)

        # channel_id
        channel_id = _infer_channel(merchant, page_name)

        if not merchant and not benefit:
            continue

        deals.append({
            "merchant":       merchant,
            "payment_method": payment_method,
            "benefit":        benefit,
            "cashback_rate":  cashback_rate,
            "conditions":     conditions,
            "valid_start":    valid_start,
            "valid_end":      valid_end,
            "channel_id":     channel_id,
            "detail_url":     detail_url,
            "source_page":    page_name,
        })

    # ── 2. 解析 SHOPBACK 型 table（商店名稱 | 合計總回饋 | 商家率 | 卡片率 | ...）──
    for tbl in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
        if not headers or "商店名稱" not in headers[0]:
            continue

        # 找欄位索引
        try:
            name_idx  = 0
            total_idx = next(i for i, h in enumerate(headers) if "合計" in h or "總回饋" in h)
        except StopIteration:
            continue

        for row in tbl.find_all("tr")[1:]:  # 跳過 header
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells or len(cells) <= total_idx:
                continue

            merchant   = cells[name_idx]
            total_rate = _parse_cashback_rate(cells[total_idx])
            channel_id = _infer_channel(merchant, page_name)

            if not merchant:
                continue

            deals.append({
                "merchant":       merchant,
                "payment_method": "SHOPBACK",
                "benefit":        cells[total_idx] if len(cells) > total_idx else "",
                "cashback_rate":  total_rate,
                "conditions":     "透過 SHOPBACK 專區消費",
                "valid_start":    None,
                "valid_end":      None,
                "channel_id":     channel_id,
                "detail_url":     "",
                "source_page":    page_name,
            })

    return deals


# ── 單卡爬取 ──────────────────────────────────────────────────────────────────

def scrape_card_microsite(card_id: str, config: dict) -> list[dict]:
    """爬取單張卡片的所有微型網站子頁面，回傳合併後的 deals 清單。"""
    slug  = config["slug"]
    pages = config["pages"]
    all_deals: list[dict] = []

    for page_name in pages:
        url = f"{MICROSITE_BASE}/{slug}/{page_name}.html"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            r.encoding = "utf-8"
        except requests.RequestException as e:
            console.print(f"  [yellow]⚠ {page_name} 無法取得：{e}[/yellow]")
            continue

        soup = BeautifulSoup(r.text, "lxml")
        deals = _parse_page(soup, page_name)
        console.print(f"  [dim]{page_name:<20}[/dim] → {len(deals)} 筆優惠")
        all_deals.extend(deals)
        time.sleep(0.5)

    return all_deals


# ── 完整爬取流程 ──────────────────────────────────────────────────────────────

def run_microsite_scrape(dry_run: bool = False) -> dict:
    """
    爬取所有已知有微型網站的卡片，輸出 data/scraped/microsite_deals.json。
    """
    console.print("\n[bold cyan]微型網站優惠爬取開始[/bold cyan]")

    result: dict = {
        "version":      "1.0",
        "last_updated": date.today().isoformat(),
        "source":       "CTBC 信用卡微型網站",
        "cards":        {},
    }

    for card_id, config in MICROSITE_CARDS.items():
        console.print(f"\n[bold]{config['card_name']}[/bold] ({card_id})")
        deals = scrape_card_microsite(card_id, config)
        result["cards"][card_id] = {
            "card_name": config["card_name"],
            "deals":     deals,
        }
        console.print(f"  共 {len(deals)} 筆促銷優惠")

    if not dry_run:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total = sum(len(v["deals"]) for v in result["cards"].values())
        console.print(f"\n[green]✓ 輸出完成 → {OUTPUT_PATH}[/green]")
        console.print(f"  共 {len(result['cards'])} 張卡片，{total} 筆促銷優惠")
    else:
        console.print("\n[cyan][dry-run] 未寫入檔案[/cyan]")

    return result
