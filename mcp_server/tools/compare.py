"""
compare.py
----------
Tool 3：compare_cards
比較使用者持有的多張卡在各通路的回饋差異。
"""

from __future__ import annotations

from ..utils.calculator import calc_estimated_cashback, is_expiring_soon
from ..utils.data_loader import get_best_channel_for_card, get_cards_by_ids
from .search import _resolve_channel, _CHANNEL_NAMES

# 標準通路列表（依重要性排序）
_ALL_CHANNEL_IDS = [
    "convenience_store",
    "supermarket",
    "ecommerce",
    "food_delivery",
    "dining",
    "transport",
    "travel",
    "mobile_payment",
    "entertainment",
    "gas_station",
    "pharmacy",
    "general",
]


def compare_cards(
    cards_owned: list[str],
    channel: str = "",
    amount: float = 1000,
) -> dict:
    """
    比較使用者持有的多張卡在指定通路（或全通路）的回饋差異。

    Args:
        cards_owned: 使用者持有的卡 card_id 列表（必填）
        channel:     指定通路，不填則比較全通路
        amount:      參考消費金額（用於計算預估回饋，預設 NT$1,000）

    Returns:
        {
          "channel_filter": "supermarket" | null,
          "amount": 1000,
          "cards": [
            {
              "card_id": "ctbc_c_linepay",
              "card_name": "LINE Pay信用卡",
            }
          ],
          "comparison": [
            {
              "channel_id": "convenience_store",
              "channel_name": "超商",
              "card_rates": [
                {
                  "card_id": "...",
                  "card_name": "...",
                  "cashback_rate": 0.05,
                  "estimated_cashback": 50.0,
                  "max_cashback_per_period": 300,
                  "expiring_soon": false,
                  "is_best": true
                }, ...
              ]
            }, ...
          ],
          "summary": [
            {
              "card_id": "...",
              "card_name": "...",
              "best_channels": ["超商", "電商"]  # 最適用的通路
            }, ...
          ],
          "error": null
        }
    """
    if not cards_owned:
        return _error("請先選擇您持有的信用卡（cards_owned 不可為空）")

    owned_cards = get_cards_by_ids(cards_owned)
    if not owned_cards:
        return _error("找不到您持有的卡片資料，請確認 card_id 是否正確")

    # 決定要比較的通路清單
    if channel:
        channel_ids = [_resolve_channel(channel)]
    else:
        channel_ids = _ALL_CHANNEL_IDS

    # 逐通路比較
    comparison = []
    for cid in channel_ids:
        cname = _CHANNEL_NAMES.get(cid, cid)
        card_rates = []

        for card in owned_cards:
            best_ch = get_best_channel_for_card(card, cid)
            rate = best_ch.get("cashback_rate") if best_ch else None
            cap  = best_ch.get("max_cashback_per_period") if best_ch else None
            est  = calc_estimated_cashback(amount, rate, cap)

            card_rates.append({
                "card_id":              card["card_id"],
                "card_name":            card["card_name"],
                "cashback_rate":        rate,
                "cashback_type":        best_ch.get("cashback_type", "cash") if best_ch else None,
                "estimated_cashback":   est,
                "max_cashback_per_period": cap,
                "expiring_soon":        is_expiring_soon(best_ch.get("valid_end")) if best_ch else False,
                "is_best":              False,  # 後面填
            })

        # 標記最優卡
        best_rate = max(
            (r.get("cashback_rate") or 0.0 for r in card_rates),
            default=0.0
        )
        if best_rate > 0:
            for r in card_rates:
                if (r.get("cashback_rate") or 0.0) == best_rate:
                    r["is_best"] = True

        # 只在全通路比較時跳過回饋率都是 0/None 的通路
        if not channel and best_rate <= 0:
            continue

        comparison.append({
            "channel_id":   cid,
            "channel_name": cname,
            "card_rates":   card_rates,
        })

    # 生成每張卡的「最強通路」摘要
    summary = _build_summary(owned_cards, comparison)

    return {
        "channel_filter": _resolve_channel(channel) if channel else None,
        "amount":         amount,
        "cards":          [{"card_id": c["card_id"], "card_name": c["card_name"]} for c in owned_cards],
        "comparison":     comparison,
        "summary":        summary,
        "error":          None,
    }


def _build_summary(owned_cards: list[dict], comparison: list[dict]) -> list[dict]:
    """為每張卡找出它「最強」的通路（is_best=True）。"""
    card_best: dict[str, list[str]] = {c["card_id"]: [] for c in owned_cards}

    for ch_entry in comparison:
        for r in ch_entry.get("card_rates", []):
            if r.get("is_best") and r.get("cashback_rate", 0) > 0:
                card_best[r["card_id"]].append(ch_entry["channel_name"])

    result = []
    for card in owned_cards:
        result.append({
            "card_id":      card["card_id"],
            "card_name":    card["card_name"],
            "best_channels": card_best.get(card["card_id"], []),
        })
    return result


def _error(msg: str) -> dict:
    return {
        "channel_filter": None,
        "amount":         0,
        "cards":          [],
        "comparison":     [],
        "summary":        [],
        "error":          msg,
    }
