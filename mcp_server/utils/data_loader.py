"""
data_loader.py
--------------
資料載入工具：讀取 merged_cards.json（合併後的單一資料源），
提供卡片查詢、過濾等基礎函式供所有 MCP Tools 使用。

merged_cards.json 已在 build time 完成三層資料合併：
- channels：card_features 優先覆蓋 API 基礎資料（同 channel_id 取高精確度來源）
- deals：microsite 商家層級促銷保留為獨立陣列
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

# 資料路徑：優先使用環境變數，否則用專案根目錄 data/
import os
_DATA_ROOT = Path(os.environ.get("DATA_ROOT", Path(__file__).parent.parent.parent / "data"))

MERGED_PATH   = _DATA_ROOT / "processed" / "merged_cards.json"
PROMOS_PATH   = _DATA_ROOT / "processed" / "promotions.json"
CHANNELS_PATH = _DATA_ROOT / "processed" / "channels.json"


# ── 載入（快取，避免重複 I/O）─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_merged_data() -> dict:
    return json.loads(MERGED_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_promotions_data() -> list:
    return json.loads(PROMOS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_channels_data() -> dict:
    return json.loads(CHANNELS_PATH.read_text(encoding="utf-8"))


def reload_all():
    """強制重新載入資料（scraper 更新後呼叫）。"""
    _load_merged_data.cache_clear()
    _load_promotions_data.cache_clear()
    _load_channels_data.cache_clear()


# ── 卡片查詢 ──────────────────────────────────────────────────────────────────

def get_all_cards() -> list[dict]:
    """回傳所有現行信用卡（已合併中信 + 富邦）。"""
    return _load_merged_data().get("cards", [])


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
    channels 已在 build time 合併（card_features 優先），直接查即可。
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


# ── Deals 查詢（原 microsite 促銷，現已合併進卡片的 deals 陣列）──────────────

def get_deals_for_card(card: dict, channel_id: str) -> list[dict]:
    """
    查詢卡片的 deals 陣列中，指定通路的所有促銷優惠。
    過濾已過期的項目，回傳 list（可能為空）。
    """
    today = date.today().isoformat()
    result = []
    for deal in card.get("deals", []):
        if deal.get("channel_id") != channel_id:
            continue
        valid_end = deal.get("valid_end")
        if valid_end and valid_end < today:
            continue
        result.append(deal)
    return result


def get_best_deal_for_card(
    card: dict,
    channel_id: str,
    merchant_hint: Optional[str] = None,
) -> Optional[dict]:
    """
    取出卡片 deals 中，指定通路回饋率最高的促銷。
    merchant_hint：若提供具體商家名稱（如 "蝦皮"），優先搜尋該商家的 deal；
                  找不到時退回通路最高值。沒有資料時回傳 None。
    """
    deals = get_deals_for_card(card, channel_id)
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
        else:
            # strict_merchant：使用者明確找某商家，但找不到對應 deal -> 直接放棄
            # 讓上層 search 退回一般頻道回饋，不要拿同通路的其他商家來湊數
            return None

    # fallback：通路最高值（確保沒有 merchant_hint）
    with_rate = [d for d in deals if d.get("cashback_rate") is not None]
    pool = with_rate if with_rate else deals
    if not pool:
        return None
    return max(pool, key=lambda d: d.get("cashback_rate") or 0.0)


# ── 資料概覽 ──────────────────────────────────────────────────────────────────

def get_data_summary() -> dict:
    """回傳資料集摘要，用於 health check 或 debug。"""
    data = _load_merged_data()
    return {
        "version":      data.get("version"),
        "last_updated": data.get("last_updated"),
        "card_count":   len(data.get("cards", [])),
        "bank":         "CTBC + Fubon",
    }
