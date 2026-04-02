"""
search.py
---------
Tool 1：search_by_channel
依通路搜尋使用者持有的卡中回饋最高的選擇。
"""

from __future__ import annotations

from typing import Optional

from ..utils.calculator import calc_estimated_cashback, is_expiring_soon
from ..utils.data_loader import (
    get_best_channel_for_card,
    get_best_feature_channel,
    get_best_microsite_deal,
    get_cards_by_ids,
)

# 從 scraper 的 channel_mapper 重用通路正規化邏輯
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scraper.channel_mapper import get_channel_id, normalize_merchant


def search_by_channel(
    channel: str,
    cards_owned: list[str],
    amount: float = 0,
    top_k: int = 3,
) -> dict:
    """
    從使用者持有的信用卡中，找出在指定通路回饋最高的卡片。

    Args:
        channel:     通路名稱，支援模糊輸入（如 "711"、"超商"、"全聯"）
        cards_owned: 使用者持有的卡 card_id 列表（必填）
        amount:      消費金額（新台幣），用於計算預估回饋（0 = 不計算）
        top_k:       回傳前幾名（預設 3）

    Returns:
        {
          "channel_id": "convenience_store",
          "channel_name": "超商",
          "query": "711",
          "amount": 500,
          "results": [
            {
              "rank": 1,
              "card_id": "ctbc_c_linepay",
              "card_name": "LINE Pay信用卡",
              "cashback_rate": 0.05,
              "cashback_type": "cash",
              "cashback_description": "5%回饋",
              "estimated_cashback": 25.0,
              "max_cashback_per_period": 300,
              "valid_end": "2026-06-30",
              "expiring_soon": false,
              "conditions": "...",
            }, ...
          ],
          "error": null   # 若有錯誤則填入訊息
        }
    """
    # 驗證持卡清單
    if not cards_owned:
        return _error("請先選擇您持有的信用卡（cards_owned 不可為空）")

    # 正規化通路 → channel_id
    channel_id = _resolve_channel(channel)
    channel_display = _channel_display_name(channel_id, channel)

    # 載入持有卡
    owned_cards = get_cards_by_ids(cards_owned)
    if not owned_cards:
        return _error("找不到您持有的卡片資料，請確認 card_id 是否正確")

    # 若輸入是已知商家，保留商家名稱作為 hint（供 microsite 商家層級比對）
    normalized = normalize_merchant(channel)
    from scraper.channel_mapper import MERCHANT_TO_CHANNEL
    merchant_hint = normalized if normalized in MERCHANT_TO_CHANNEL else None

    # 對每張持有卡查最優通路回饋
    results = []
    for card in owned_cards:
        card_id = card["card_id"]

        # ── 優先使用微型網站精確促銷資料 ──
        microsite_deal = get_best_microsite_deal(
            card_id,
            channel_id,
            merchant_hint=merchant_hint,
            strict_merchant=bool(merchant_hint),
        )
        if microsite_deal:
            rate = microsite_deal.get("cashback_rate")
            cap  = None
            est  = calc_estimated_cashback(amount, rate, cap) if amount > 0 else None
            results.append({
                "card_id":              card_id,
                "card_name":            card["card_name"],
                "cashback_rate":        rate,
                "cashback_type":        "cash",
                "cashback_description": microsite_deal.get("benefit", ""),
                "estimated_cashback":   est,
                "max_cashback_per_period": cap,
                "valid_end":            microsite_deal.get("valid_end"),
                "expiring_soon":        is_expiring_soon(microsite_deal.get("valid_end")),
                "conditions":           microsite_deal.get("conditions", ""),
                "merchant":             microsite_deal.get("merchant", ""),
                "payment_method":       microsite_deal.get("payment_method", ""),
                "data_source":          "microsite",
                "is_fallback":          False,
            })
            continue

        # ── 次優先：使用卡片特色頁直接爬取的回饋率 ──
        feature_ch = get_best_feature_channel(card_id, channel_id)
        if feature_ch and feature_ch.get("cashback_rate") is not None:
            if merchant_hint and feature_ch.get("is_fallback") and not _is_generic_general_fallback(feature_ch):
                continue
            rate = feature_ch.get("cashback_rate")
            cap  = feature_ch.get("max_cashback_per_period")
            est  = calc_estimated_cashback(amount, rate, cap) if amount > 0 else None
            results.append({
                "card_id":              card_id,
                "card_name":            card["card_name"],
                "cashback_rate":        rate,
                "cashback_type":        feature_ch.get("cashback_type", "cash"),
                "cashback_description": feature_ch.get("cashback_description", ""),
                "estimated_cashback":   est,
                "max_cashback_per_period": cap,
                "valid_end":            feature_ch.get("valid_end"),
                "expiring_soon":        is_expiring_soon(feature_ch.get("valid_end")),
                "conditions":           feature_ch.get("conditions", ""),
                "data_source":          "card_feature",
                "is_fallback":          feature_ch.get("is_fallback", False),
            })
            continue

        # ── 最後 fallback：使用主資料集（API 行銷文案）──
        best_ch = get_best_channel_for_card(card, channel_id)
        if best_ch is None:
            continue
        if merchant_hint and best_ch.get("is_fallback") and not _is_generic_general_fallback(best_ch):
            continue

        rate = best_ch.get("cashback_rate")
        cap  = best_ch.get("max_cashback_per_period")
        est  = calc_estimated_cashback(amount, rate, cap) if amount > 0 else None

        results.append({
            "card_id":              card_id,
            "card_name":            card["card_name"],
            "cashback_rate":        rate,
            "cashback_type":        best_ch.get("cashback_type", "cash"),
            "cashback_description": best_ch.get("cashback_description", ""),
            "estimated_cashback":   est,
            "max_cashback_per_period": cap,
            "valid_end":            best_ch.get("valid_end"),
            "expiring_soon":        is_expiring_soon(best_ch.get("valid_end")),
            "conditions":           best_ch.get("conditions", ""),
            "data_source":          "api",
            "is_fallback":          best_ch.get("is_fallback", False),
        })

    # 排序：預估回饋↓ → 回饋率↓
    def sort_key(r):
        est  = r.get("estimated_cashback") or 0.0
        rate = r.get("cashback_rate") or 0.0
        return (est, rate)

    results.sort(key=sort_key, reverse=True)
    results = results[:top_k]

    # 加 rank
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return {
        "channel_id":    channel_id,
        "channel_name":  channel_display,
        "query":         channel,
        "amount":        amount,
        "merchant_hint": merchant_hint or "",
        "results":       results,
        "error":         None,
    }


# ── 內部工具 ──────────────────────────────────────────────────────────────────

_VALID_CHANNEL_IDS = {
    "convenience_store", "supermarket", "ecommerce", "food_delivery",
    "transport", "dining", "travel", "entertainment", "gas_station",
    "pharmacy", "mobile_payment", "general", "overseas_general",
}


def _resolve_channel(raw: str) -> str:
    """
    把使用者輸入的通路文字映射到 channel_id。
    若輸入本身就是合法 channel_id，直接回傳（避免部分比對誤判）。
    再試 normalize_merchant，再試 category keyword，fallback 到 general。
    """
    if raw in _VALID_CHANNEL_IDS:
        return raw
    cid = get_channel_id(raw)
    return cid if cid else "general"


_CHANNEL_NAMES = {
    "convenience_store": "超商",
    "supermarket":       "超市／量販",
    "ecommerce":         "電商",
    "food_delivery":     "外送",
    "transport":         "交通",
    "dining":            "餐飲",
    "travel":            "旅遊",
    "entertainment":     "娛樂",
    "gas_station":       "加油站",
    "pharmacy":          "藥妝",
    "mobile_payment":    "行動支付",
    "general":           "一般消費",
    "overseas_general":  "海外消費",
}


def _channel_display_name(channel_id: str, fallback: str) -> str:
    return _CHANNEL_NAMES.get(channel_id, fallback)


_GENERIC_FALLBACK_EXCLUDE_KEYWORDS = {
    "保險", "道路救援", "旅行平安險", "旅平險", "旅遊", "海外", "高鐵", "台鐵",
    "捷運", "機票", "航空", "飯店", "訂房", "停車", "加油", "餐廳", "餐飲",
    "超市", "量販", "外送", "藥妝", "影城", "樂園", "行動支付",
}

_GENERIC_FALLBACK_INCLUDE_KEYWORDS = {
    "一般消費", "國內一般消費", "國內消費", "不分通路", "不分級距",
}


def _is_generic_general_fallback(channel_data: dict) -> bool:
    """
    僅接受真正泛用的一般消費 fallback。
    若文案含有明確品類/情境（如保險、超市、旅遊），
    即使資料被掛在 general，也不應拿來回答明確商家查詢。
    """
    text = " ".join(
        str(channel_data.get(key) or "")
        for key in ("cashback_description", "conditions", "channel_name")
    )
    if not text:
        return False

    if any(keyword in text for keyword in _GENERIC_FALLBACK_EXCLUDE_KEYWORDS):
        return False

    if any(keyword in text for keyword in _GENERIC_FALLBACK_INCLUDE_KEYWORDS):
        return True

    return False


def _error(msg: str) -> dict:
    return {
        "channel_id":   None,
        "channel_name": None,
        "query":        None,
        "amount":       0,
        "results":      [],
        "error":        msg,
    }
