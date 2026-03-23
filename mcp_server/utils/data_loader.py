"""
data_loader.py
--------------
資料載入工具：讀取 data/processed/ 下的 JSON 檔，
提供卡片查詢、過濾等基礎函式供所有 MCP Tools 使用。
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

# 打包安裝後資料放在 mcp_server/data/；開發時放在專案根目錄 data/
_PKG_DATA = Path(__file__).parent.parent / "data"       # 安裝後路徑
_SRC_DATA = Path(__file__).parent.parent.parent / "data" # 開發時路徑
_DATA_ROOT = _PKG_DATA if _PKG_DATA.exists() else _SRC_DATA

CARDS_PATH     = _DATA_ROOT / "processed" / "ctbc_cards.json"
FUBON_CARDS_PATH = _DATA_ROOT / "processed" / "fubon_cards.json"
PROMOS_PATH    = _DATA_ROOT / "processed" / "promotions.json"
CHANNELS_PATH  = _DATA_ROOT / "processed" / "channels.json"
MICROSITE_PATH = _DATA_ROOT / "scraped"   / "microsite_deals.json"
FEATURES_PATH  = _DATA_ROOT / "scraped"   / "card_features.json"


# ── 載入（快取，避免重複 I/O）─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_cards_data() -> dict:
    return json.loads(CARDS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_fubon_cards_data() -> dict:
    if not FUBON_CARDS_PATH.exists():
        return {"cards": []}
    return json.loads(FUBON_CARDS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_promotions_data() -> list:
    return json.loads(PROMOS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_channels_data() -> dict:
    return json.loads(CHANNELS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_microsite_data() -> dict:
    """載入微型網站爬取的精確促銷優惠資料。檔案不存在時回傳空 dict。"""
    if not MICROSITE_PATH.exists():
        return {}
    return json.loads(MICROSITE_PATH.read_text(encoding="utf-8")).get("cards", {})


@lru_cache(maxsize=1)
def _load_features_data() -> dict:
    """載入卡片特色頁直接爬取的回饋率資料（card_features.json）。"""
    if not FEATURES_PATH.exists():
        return {}
    return json.loads(FEATURES_PATH.read_text(encoding="utf-8")).get("cards", {})


def reload_all():
    """強制重新載入資料（scraper 更新後呼叫）。"""
    _load_cards_data.cache_clear()
    _load_fubon_cards_data.cache_clear()
    _load_promotions_data.cache_clear()
    _load_channels_data.cache_clear()
    _load_microsite_data.cache_clear()
    _load_features_data.cache_clear()


# ── 卡片查詢 ──────────────────────────────────────────────────────────────────

def get_all_cards() -> list[dict]:
    """回傳所有現行信用卡（中信 + 富邦合併）。"""
    ctbc = _load_cards_data().get("cards", [])
    fubon = _load_fubon_cards_data().get("cards", [])
    return ctbc + fubon


def get_card_by_id(card_id: str) -> Optional[dict]:
    """依 card_id 取得單張卡片，找不到回傳 None。"""
    for card in get_all_cards():
        if card["card_id"] == card_id:
            return card
    return None


def get_cards_by_ids(card_ids: list[str]) -> list[dict]:
    """
    依 card_id 列表取得多張卡片。
    找不到的 ID 自動忽略。
    """
    id_set = set(card_ids)
    return [c for c in get_all_cards() if c["card_id"] in id_set]


def get_cards_menu() -> list[dict]:
    """
    回傳供 CLI 選單顯示的精簡卡片列表。
    格式：[{"card_id": "...", "card_name": "...", "tags": [...]}]
    """
    return [
        {
            "card_id":   c["card_id"],
            "card_name": c["card_name"],
            "tags":      c.get("tags", []),
            "card_org":  c.get("card_org"),
        }
        for c in get_all_cards()
        if c.get("card_status") == "active"
    ]


# ── 優惠查詢 ──────────────────────────────────────────────────────────────────

def get_all_promotions(valid_only: bool = True) -> list[dict]:
    """
    取得限時優惠活動列表。
    valid_only=True 時過濾掉已到期的活動。
    """
    promos = _load_promotions_data()
    if not valid_only:
        return promos
    today = date.today().isoformat()
    result = []
    for p in promos:
        end = p.get("valid_end")
        if end is None or end >= today:
            result.append(p)
    return result


# ── 通路查詢 ──────────────────────────────────────────────────────────────────

def get_channels_map() -> dict:
    """回傳 channel_id → 通路資訊的完整對照表。"""
    return _load_channels_data()


# ── Channel 過濾（用於 search_by_channel）────────────────────────────────────

def filter_channels_by_id(card: dict, channel_id: str) -> list[dict]:
    """
    從卡片的 channels 列表中過濾出符合 channel_id 的優惠，
    同時過濾掉已過期的優惠。
    """
    today = date.today().isoformat()
    matched = []
    for ch in card.get("channels", []):
        if ch.get("channel_id") != channel_id:
            continue
        end = ch.get("valid_end")
        if end and end < today:
            continue  # 已過期
        matched.append(ch)
    return matched


def get_best_channel_for_card(card: dict, channel_id: str) -> Optional[dict]:
    """
    從卡片的 channels 中，取出指定 channel_id 中回饋率最高的那筆。
    若無匹配則嘗試 general 通路，並標記 is_fallback=True。
    """
    channels = filter_channels_by_id(card, channel_id)
    is_fallback = False

    if not channels:
        channels = filter_channels_by_id(card, "general")
        is_fallback = True
    if not channels:
        return None

    def rate_key(ch):
        r = ch.get("cashback_rate")
        return r if r is not None else 0.0

    best = max(channels, key=rate_key)
    best = dict(best)  # 複製避免污染快取物件
    best["is_fallback"] = is_fallback
    return best


# ── 微型網站精確促銷查詢 ──────────────────────────────────────────────────────

def get_microsite_deals(card_id: str, channel_id: str) -> list[dict]:
    """
    查詢微型網站資料中，指定卡片 × 通路的所有促銷優惠。
    過濾已過期的項目，回傳 list（可能為空）。
    """
    microsite = _load_microsite_data()
    card_data = microsite.get(card_id, {})
    today = date.today().isoformat()

    result = []
    for deal in card_data.get("deals", []):
        if deal.get("channel_id") != channel_id:
            continue
        # 過濾已過期
        valid_end = deal.get("valid_end")
        if valid_end and valid_end < today:
            continue
        result.append(deal)
    return result


def get_best_microsite_deal(card_id: str, channel_id: str, merchant_hint: Optional[str] = None) -> Optional[dict]:
    """
    取出微型網站資料中，指定卡片 × 通路回饋率最高的促銷。
    merchant_hint：若提供具體商家名稱（如 "蝦皮"），優先搜尋該商家的 deal；
                  找不到時退回通路最高值。沒有資料時回傳 None。
    """
    deals = get_microsite_deals(card_id, channel_id)
    if not deals:
        return None

    # 若有商家 hint，先嘗試商家層級比對
    if merchant_hint:
        hint_lower = merchant_hint.lower()
        merchant_deals = [
            d for d in deals
            if hint_lower in (d.get("merchant") or "").lower()
        ]
        if merchant_deals:
            with_rate = [d for d in merchant_deals if d.get("cashback_rate") is not None]
            pool = with_rate if with_rate else merchant_deals
            return max(pool, key=lambda d: d.get("cashback_rate") or 0.0)

    # fallback：通路最高值
    with_rate = [d for d in deals if d.get("cashback_rate") is not None]
    pool = with_rate if with_rate else deals
    return max(pool, key=lambda d: d.get("cashback_rate") or 0.0)


# ── 卡片特色頁回饋率查詢 ──────────────────────────────────────────────────────

def get_best_feature_channel(card_id: str, channel_id: str) -> Optional[dict]:
    """
    從 card_features.json（卡片特色頁直接爬取）中，
    取出指定卡片 × 通路回饋率最高的那筆。
    沒有資料時回傳 None。

    Priority：microsite_deals > card_features > ctbc_cards（base）
    """
    features = _load_features_data()
    card_data = features.get(card_id, {})
    channels = card_data.get("channels", [])

    # 過濾符合 channel_id 的項目
    matched = [ch for ch in channels if ch.get("channel_id") == channel_id]
    if not matched:
        # fallback 到 general
        matched = [ch for ch in channels if ch.get("channel_id") == "general"]
        if not matched:
            return None
        is_fallback = True
    else:
        is_fallback = False

    # 取回饋率最高的
    best = max(matched, key=lambda ch: ch.get("cashback_rate") or 0.0)
    result = dict(best)
    result["is_fallback"] = is_fallback
    return result


# ── 資料概覽 ──────────────────────────────────────────────────────────────────

def get_data_summary() -> dict:
    """回傳資料集摘要，用於 health check 或 debug。"""
    ctbc_data = _load_cards_data()
    fubon_data = _load_fubon_cards_data()
    total = len(ctbc_data.get("cards", [])) + len(fubon_data.get("cards", []))
    return {
        "version":      ctbc_data.get("version"),
        "last_updated": "2026-03-16",
        "card_count":   total,
        "bank":         "CTBC + Fubon",
    }
