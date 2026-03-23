"""
promotions.py
-------------
Tool 4：get_promotions  — 取得持有卡的優惠活動
Tool 5：get_card_details — 取得單張卡片完整資訊
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..utils.calculator import is_expiring_soon
from ..utils.data_loader import (
    get_all_promotions,
    get_card_by_id,
    get_cards_by_ids,
)
from .search import _resolve_channel, _CHANNEL_NAMES


# ── Tool 4：get_promotions ────────────────────────────────────────────────────

def get_promotions(
    cards_owned: list[str],
    category: str = "",
    valid_only: bool = True,
) -> dict:
    """
    取得使用者持有的卡，在指定類別中目前有效的優惠活動。

    注意：promotions.json 是全行活動，目前未區分到個別卡片，
    所以本工具回傳的是全體信用卡活動（需至官網確認適用卡片）。
    cards_owned 用於確認使用者已登錄，避免空查詢。

    Args:
        cards_owned: 使用者持有的卡 card_id 列表（必填）
        category:    通路分類（如 "ecommerce"、"dining"），不填回傳全部
        valid_only:  是否只回傳有效優惠（預設 True）

    Returns:
        {
          "category_filter": "ecommerce" | null,
          "valid_only": true,
          "total": 5,
          "promotions": [
            {
              "title": "...",
              "description": "...",
              "valid_start": "2026-01-01",
              "valid_end": "2026-03-31",
              "offer_url": "https://...",
              "expiring_soon": false,
              "days_remaining": 25
            }, ...
          ],
          "card_channels": [
            {
              "card_id": "...",
              "card_name": "...",
              "channels": [...]  # 卡片本身的通路優惠（含即將到期）
            }
          ],
          "error": null
        }
    """
    if not cards_owned:
        return _promo_error("請先選擇您持有的信用卡（cards_owned 不可為空）")

    # 1. 取全行促活動
    promos = get_all_promotions(valid_only=valid_only)

    # 2. category 過濾（用 keyword 方式，因 promotions 沒有 channel_id）
    cat_id = _resolve_channel(category) if category else None
    if cat_id and cat_id != "general":
        keywords = _get_category_keywords(cat_id)
        promos = [
            p for p in promos
            if any(kw in p.get("title", "") for kw in keywords)
        ]

    # 3. 整理欄位
    today = date.today().isoformat()
    formatted_promos = []
    for p in promos:
        end = p.get("valid_end")
        days_remaining = None
        if end:
            try:
                days_remaining = (date.fromisoformat(end) - date.today()).days
            except ValueError:
                pass

        formatted_promos.append({
            "title":          p.get("title", ""),
            "description":    p.get("description", ""),
            "valid_start":    p.get("valid_start"),
            "valid_end":      end,
            "offer_url":      p.get("offer_url", ""),
            "expiring_soon":  is_expiring_soon(end),
            "days_remaining": days_remaining,
        })

    # 按截止日升序排（即將到期的優先顯示）
    formatted_promos.sort(
        key=lambda p: (p["valid_end"] or "9999-12-31")
    )

    # 4. 卡片本身的通路優惠（即將到期提醒）
    card_channels = _get_expiring_card_channels(cards_owned)

    return {
        "category_filter": cat_id,
        "valid_only":      valid_only,
        "total":           len(formatted_promos),
        "promotions":      formatted_promos,
        "card_channels":   card_channels,
        "error":           None,
    }


# ── Tool 5：get_card_details ──────────────────────────────────────────────────

def get_card_details(card_id: str) -> dict:
    """
    取得單張信用卡的完整優惠詳情，包含所有通路、條件、備註。

    Args:
        card_id: 卡片 ID（如 "ctbc_c_linepay"）

    Returns:
        完整卡片 dict，加上 expiring_soon 標記，
        或 {"error": "..."} 若找不到卡片。
    """
    if not card_id:
        return {"error": "card_id 不可為空"}

    card = get_card_by_id(card_id)
    if not card:
        return {"error": f"找不到卡片：{card_id}"}

    # 為每個 channel 加上 expiring_soon
    channels_annotated = []
    for ch in card.get("channels", []):
        ch_copy = dict(ch)
        ch_copy["expiring_soon"] = is_expiring_soon(ch.get("valid_end"))
        ch_copy["channel_name"] = _CHANNEL_NAMES.get(ch.get("channel_id", ""), ch.get("channel_name", ""))
        channels_annotated.append(ch_copy)

    return {
        **card,
        "channels": channels_annotated,
        "error":    None,
    }


# ── 內部工具 ──────────────────────────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "convenience_store": ["超商", "7-11", "全家", "萊爾富"],
    "supermarket":       ["超市", "量販", "全聯", "家樂福", "COSTCO"],
    "ecommerce":         ["電商", "網購", "蝦皮", "momo", "PChome"],
    "food_delivery":     ["外送", "foodpanda", "Uber Eats"],
    "transport":         ["交通", "捷運", "高鐵", "台鐵"],
    "dining":            ["餐飲", "餐廳", "美食", "咖啡"],
    "travel":            ["旅遊", "機票", "飯店", "航空"],
    "mobile_payment":    ["行動支付", "LINE Pay", "街口", "Apple Pay"],
    "entertainment":     ["娛樂", "電影", "KTV"],
    "gas_station":       ["加油", "中油", "台塑"],
    "pharmacy":          ["藥妝", "屈臣氏", "康是美"],
}


def _get_category_keywords(channel_id: str) -> list[str]:
    return _CATEGORY_KEYWORDS.get(channel_id, [])


def _get_expiring_card_channels(card_ids: list[str]) -> list[dict]:
    """取得持有卡中即將到期（30天內）的通路優惠。"""
    result = []
    for card in get_cards_by_ids(card_ids):
        expiring = [
            {
                "channel_id":   ch.get("channel_id"),
                "channel_name": _CHANNEL_NAMES.get(ch.get("channel_id", ""), ch.get("channel_name", "")),
                "cashback_rate": ch.get("cashback_rate"),
                "valid_end":    ch.get("valid_end"),
                "cashback_description": ch.get("cashback_description", ""),
            }
            for ch in card.get("channels", [])
            if is_expiring_soon(ch.get("valid_end"))
        ]
        if expiring:
            result.append({
                "card_id":   card["card_id"],
                "card_name": card["card_name"],
                "channels":  expiring,
            })
    return result


def _promo_error(msg: str) -> dict:
    return {
        "category_filter": None,
        "valid_only":      True,
        "total":           0,
        "promotions":      [],
        "card_channels":   [],
        "error":           msg,
    }
