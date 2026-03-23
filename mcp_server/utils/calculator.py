"""
calculator.py
-------------
回饋金額計算邏輯。
"""

from __future__ import annotations

from datetime import date
from typing import Optional


def calc_estimated_cashback(
    amount: float,
    cashback_rate: Optional[float],
    max_per_period: Optional[int],
) -> Optional[float]:
    """
    計算預估回饋金額。

    規則：
      estimated = amount × cashback_rate
      若 max_per_period 不為 None，取 min(estimated, max_per_period)
      cashback_rate 為 None 時回傳 None
    """
    if cashback_rate is None or cashback_rate <= 0:
        return None
    estimated = amount * cashback_rate
    if max_per_period is not None:
        estimated = min(estimated, float(max_per_period))
    return round(estimated, 1)


def is_expiring_soon(valid_end: Optional[str], threshold_days: int = 30) -> bool:
    """判斷優惠是否在 threshold_days 天內到期。"""
    if not valid_end:
        return False
    try:
        end = date.fromisoformat(valid_end)
        delta = (end - date.today()).days
        return 0 < delta <= threshold_days
    except ValueError:
        return False


def is_expired(valid_end: Optional[str]) -> bool:
    """判斷優惠是否已過期。"""
    if not valid_end:
        return False
    try:
        return date.fromisoformat(valid_end) < date.today()
    except ValueError:
        return False


def rank_channels(
    channel_results: list[dict],
    amount: float = 0,
) -> list[dict]:
    """
    對一組通路回饋結果依「預估回饋金額 → 回饋率」排序。

    每個 result 格式：
    {
        "card_id": ...,
        "card_name": ...,
        "channel": {...},  # channel dict from card data
    }
    """
    def sort_key(item):
        ch = item.get("channel", {})
        rate = ch.get("cashback_rate") or 0.0
        est  = calc_estimated_cashback(amount, rate, ch.get("max_cashback_per_period"))
        return (est or 0.0, rate)

    return sorted(channel_results, key=sort_key, reverse=True)
