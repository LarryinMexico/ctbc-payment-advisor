"""
ctbc_scraper.py
---------------
Phase 1：透過 CTBC 官方 API 取得所有信用卡資料（不需 Playwright）。

API 端點（公開，無需驗證）：
  - 卡片清單：/web/content/twrbo/setting/creditcards.cardlist.json
  - 優惠活動：/web/content/twrbo/setting/offerdata.offerdatalist.json

執行方式：
  python -m scraper.run full
  python -m scraper.run promotions-only
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

# ── URL 設定 ──────────────────────────────────────────────────────────────────
BASE_URL      = "https://www.ctbcbank.com"
CARD_LIST_API = f"{BASE_URL}/web/content/twrbo/setting/creditcards.cardlist.json"
OFFER_API     = f"{BASE_URL}/web/content/twrbo/setting/offerdata.offerdatalist.json"

# ── 目錄設定 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR      = PROJECT_ROOT / "data" / "raw"
DEBUG_DIR    = PROJECT_ROOT / "data" / "debug"

# ── HTTP 設定 ─────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Referer": BASE_URL + "/",
}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _fetch_json(url: str, retries: int = 3) -> Optional[dict | list]:
    """取得 JSON API 資料，失敗時重試。"""
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            console.print(f"  [yellow]⚠ 請求失敗（{attempt + 1}/{retries}）：{e}[/yellow]")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def _strip_html(html_str: str) -> str:
    """移除 HTML 標籤，回傳純文字。"""
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    return soup.get_text(separator="，", strip=True)


# ── Phase 1A：取得卡片清單 ─────────────────────────────────────────────────────

def fetch_all_cards() -> list[dict]:
    """
    從官方 API 取得所有現行信用卡基本資料。

    回傳格式（raw card dict，供 data_cleaner.clean_card 使用）：
    [
      {
        "card_id": "C_LINEPay",
        "card_name": "LINE Pay信用卡",
        "card_status": "active",
        "card_org": "VISA",
        "annual_fee": "首年免年費...",
        "card_url": "https://www.ctbcbank.com/content/twrbo/...",
        "apply_url": "https://www.ctbcbank.com/content/twrbo/...",
        "raw_benefits": [{"text": "...", "source": "api"}],
        "tags": ["行動支付", "國外消費"],
        ...
      }
    ]
    """
    console.print(f"[cyan]▶ 取得信用卡清單[/cyan]")
    console.print(f"  [dim]→ {CARD_LIST_API}[/dim]")

    data = _fetch_json(CARD_LIST_API)
    if not data:
        console.print("[red]✗ 無法取得卡片清單[/red]")
        return []

    raw_cards = data.get("creditCards", [])
    console.print(f"  [green]✓ 取得 {len(raw_cards)} 張卡片資料[/green]")

    result = []
    for card in raw_cards:
        # 只保留目前上線的卡片
        if not card.get("isOnline", False):
            continue

        raw_benefits = _extract_raw_benefits(card)

        result.append({
            "card_id":      card.get("cardId", ""),
            "card_name":    card.get("cardName", "").strip(),
            "card_status":  "active",
            "card_org":     _parse_card_org(card),
            "annual_fee":   _strip_html(card.get("annualFee", "")),
            "annual_fee_waiver": None,
            "card_url":     _absolute_url(card.get("introLink", "")),
            "apply_url":    _absolute_url(card.get("applyLink", "")),
            "tags":         card.get("rewardType", []),
            "notes":        None,
            "data_source":  "api",
            "last_verified": None,
            "raw_benefits": raw_benefits,
            "scraped_at":   datetime.now().isoformat(),
        })

    console.print(f"[green]✓ 共 {len(result)} 張現行信用卡[/green]")
    return result


def _extract_raw_benefits(card: dict) -> list[dict]:
    """
    從 API 卡片資料中提取 raw_benefits 文字列表。
    來源：cardFeature（條列功能）+ specialOffer（限時優惠）。
    """
    benefits: list[dict] = []

    # 1. cardFeature：主要功能列表（已是純文字）
    for feat in card.get("cardFeature", []):
        feat_clean = _strip_html(feat)
        if feat_clean and len(feat_clean) > 3:
            benefits.append({"text": feat_clean, "source": "cardFeature"})

    # 2. specialOffer：限時優惠（HTML 轉純文字）
    special = _strip_html(card.get("specialOffer", ""))
    if special and len(special) > 5:
        # 拆成多行
        for line in re.split(r"[，。；\n]", special):
            line = line.strip()
            if line and len(line) > 3:
                benefits.append({"text": line, "source": "specialOffer"})

    # 3. shortIntro：簡短介紹
    intro = _strip_html(card.get("shortIntro", ""))
    if intro and len(intro) > 3:
        benefits.append({"text": intro, "source": "shortIntro"})

    return benefits


def _parse_card_org(card: dict) -> Optional[str]:
    """從 issueGroup 列表取得卡組織（以第一個有效值為主）。"""
    valid = {"VISA", "Mastercard", "JCB", "AE", "UnionPay"}
    groups = card.get("issueGroup", [])
    for g in groups:
        if g in valid:
            return g
    return None


def _absolute_url(path: str) -> Optional[str]:
    if not path:
        return None
    if path.startswith("http"):
        return path
    if path.startswith("/"):
        return BASE_URL + path
    return None


# ── Phase 1B：取得限時優惠活動 ────────────────────────────────────────────────

def fetch_promotions() -> list[dict]:
    """
    從官方 API 取得所有限時優惠活動。

    回傳格式：
    [
      {
        "title": "【IKEA】最高享1,000元刷卡金(需登錄)",
        "description": "...",
        "valid_start": "2026-01-01",
        "valid_end": "2026-03-31",
        "offer_url": "https://...",
        "category": "cc_offer",
        "scraped_at": "..."
      }
    ]
    """
    console.print(f"[cyan]▶ 取得限時優惠活動[/cyan]")
    console.print(f"  [dim]→ {OFFER_API}[/dim]")

    data = _fetch_json(OFFER_API)
    if not data or not isinstance(data, list):
        console.print("[red]✗ 無法取得優惠活動[/red]")
        return []

    promotions: list[dict] = []
    for item in data:
        category = item.get("offerCategory", [])
        # 只取信用卡類優惠
        if not any("cc" in str(c).lower() for c in category):
            continue

        valid_start = _parse_api_date(item.get("offerStart", ""))
        valid_end   = _parse_api_date(item.get("offerEnd", ""))

        promotions.append({
            "title":       item.get("offerTitle", "").strip(),
            "description": item.get("offerTitle", "").strip(),
            "valid_start": valid_start,
            "valid_end":   valid_end,
            "offer_url":   item.get("offerPath", ""),
            "category":    ",".join(category),
            "scraped_at":  datetime.now().isoformat(),
        })

    console.print(f"[green]✓ 共 {len(promotions)} 項信用卡優惠活動[/green]")
    return promotions


def _parse_api_date(date_str: str) -> Optional[str]:
    """把 '2026/01/01' 或 '2026/3/31' 轉為 'YYYY-MM-DD'。"""
    if not date_str:
        return None
    try:
        # Try YYYY/M/D format
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    except Exception:
        pass
    return None


# ── Debug：dump 原始 API 資料 ──────────────────────────────────────────────────

def dump_debug_html():
    """
    儲存 API 原始回應供人工分析。
    （保留此函式名以相容 run.py 的 cmd_dump_html）
    """
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    console.print("[bold cyan]── Debug API Dump 模式 ──[/bold cyan]")
    console.print("目的：儲存 API 原始回應，確認資料結構\n")

    # 卡片清單
    console.print(f"[1/2] 卡片清單 API")
    card_data = _fetch_json(CARD_LIST_API)
    if card_data:
        path = DEBUG_DIR / f"{timestamp}_cardlist_api.json"
        path.write_text(json.dumps(card_data, ensure_ascii=False, indent=2), encoding="utf-8")
        cards = card_data.get("creditCards", [])
        console.print(f"  → {len(cards)} 張卡片")
        console.print(f"  → 已儲存：{path}")
        for c in cards[:5]:
            console.print(f"     - [{c.get('cardId')}] {c.get('cardName')}")
    else:
        console.print("  [red]✗ 取得失敗[/red]")

    # 優惠活動
    console.print(f"\n[2/2] 優惠活動 API")
    offer_data = _fetch_json(OFFER_API)
    if offer_data:
        path = DEBUG_DIR / f"{timestamp}_offers_api.json"
        path.write_text(json.dumps(offer_data, ensure_ascii=False, indent=2), encoding="utf-8")
        cc_offers = [o for o in offer_data if any("cc" in str(c).lower() for c in o.get("offerCategory", []))]
        console.print(f"  → {len(cc_offers)} 項信用卡優惠")
        console.print(f"  → 已儲存：{path}")
    else:
        console.print("  [red]✗ 取得失敗[/red]")

    console.print("\n[bold green]✓ Dump 完成！[/bold green]")
    console.print(f"請開啟 [cyan]{DEBUG_DIR}[/cyan] 查看 JSON 檔案")


# ── 完整爬取流程 ───────────────────────────────────────────────────────────────

async def run_full_scrape(
    dump_html: bool = False,
    promotions_only: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    完整爬取流程（已改為 API 方式，async 包裝保持介面相容）。
    回傳 (raw_cards, promotions)。
    """
    raw_cards: list[dict] = []
    promotions: list[dict] = []

    if not promotions_only:
        raw_cards = fetch_all_cards()
        # 儲存原始資料
        for card in raw_cards:
            _save_raw_card(card)

    promotions = fetch_promotions()
    _save_raw_promotions(promotions)

    if dump_html:
        dump_debug_html()

    return raw_cards, promotions


# ── 儲存 raw 資料 ─────────────────────────────────────────────────────────────

def _save_raw_card(card: dict):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff]", "_", card.get("card_name", "unknown"))
    path = RAW_DIR / f"{safe}.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_raw_promotions(promotions: list[dict]):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "promotions_raw.json"
    path.write_text(json.dumps(promotions, ensure_ascii=False, indent=2), encoding="utf-8")
