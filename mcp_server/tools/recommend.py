"""
recommend.py
------------
Tool 2：recommend_payment
依自然語言消費情境，從持有卡中解析通路+金額，推薦最佳刷卡選擇。
"""

from __future__ import annotations

import re

from .search import search_by_channel, _resolve_channel, _channel_display_name


# ── 情境解析 ──────────────────────────────────────────────────────────────────

# 金額抽取：「3000元」「NT$1,500」「花了500」
_AMOUNT_PATTERN = re.compile(
    r"(?:NT\$|新台幣|花(?:了|費)?|消費|共|約|大概)?\s*([\d,]+)\s*(?:元|塊|円)?",
)

# 通路關鍵字（在 channel_mapper 之外做一層快速映射）
_QUICK_CHANNEL_MAP: list[tuple[str, str]] = [
    # 超商
    (r"7-?11|小7|seven|統一超商", "7-ELEVEN"),
    (r"全家|family\s*mart", "全家"),
    (r"萊爾富|hi-?life", "萊爾富"),
    # 超市量販
    (r"全聯", "全聯"),
    (r"家樂福|carrefour", "家樂福"),
    (r"好市多|costco", "COSTCO"),
    (r"大潤發", "大潤發"),
    # 電商
    (r"蝦皮|shopee", "蝦皮"),
    (r"momo", "momo購物"),
    (r"pchome", "PChome"),
    (r"yahoo購物|奇摩購物", "Yahoo購物中心"),
    (r"博客來", "博客來"),
    # 外送
    (r"uber\s*eats|優食", "Uber Eats"),
    (r"foodpanda|熊貓", "foodpanda"),
    # 交通
    (r"台鐵|火車", "台鐵"),
    (r"高鐵|thsr", "高鐵"),
    (r"捷運|mrt", "台北捷運"),
    (r"uber(?!\s*eats)", "Uber"),
    # 餐飲
    (r"麥當勞|mcdonald", "麥當勞"),
    (r"星巴克|starbucks", "星巴克"),
    (r"路易莎|louisa", "路易莎"),
    # 旅遊
    (r"航空|機票|飛機", "travel"),
    (r"飯店|訂房|agoda|booking", "travel"),
    # 加油
    (r"中油|加油", "中油"),
    (r"台塑石化", "台塑石化"),
    # 藥妝
    (r"屈臣氏|watsons", "屈臣氏"),
    (r"康是美|cosmed", "康是美"),
    # 行動支付
    (r"line\s*pay", "LINE Pay"),
    (r"街口", "街口支付"),
    (r"apple\s*pay", "Apple Pay"),
    (r"google\s*pay", "Google Pay"),
]


def _extract_amount(text: str) -> float:
    """從情境文字中抽取金額（取最大值），無法解析時回傳 0。"""
    candidates = []
    for m in _AMOUNT_PATTERN.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
            if 1 <= val <= 10_000_000:  # 合理金額範圍
                candidates.append(val)
        except ValueError:
            pass
    return max(candidates) if candidates else 0.0


def _extract_channels(text: str) -> list[str]:
    """從情境文字中抽取所有提到的通路，回傳標準商家/通路名稱列表。"""
    text_lower = text.lower()
    found = []
    for pattern, name in _QUICK_CHANNEL_MAP:
        if re.search(pattern, text_lower):
            if name not in found:
                found.append(name)
    return found


def recommend_payment(
    scenario: str,
    cards_owned: list[str],
) -> dict:
    """
    依自然語言消費情境，從持有卡中推薦最佳刷卡選擇。

    Args:
        scenario:    消費情境描述，如 "去全聯買菜花了1500元"
        cards_owned: 使用者持有的卡 card_id 列表（必填）

    Returns:
        {
          "scenario": "去全聯買菜花了1500元",
          "parsed": {
            "channels": [{"name": "全聯", "channel_id": "supermarket"}],
            "amount": 1500
          },
          "recommendations": [
            {
              "channel_name": "超市／量販",
              "channel_id": "supermarket",
              "best_card": { ...search result... }
            }, ...
          ],
          "error": null
        }
    """
    if not cards_owned:
        return _error(scenario, "請先選擇您持有的信用卡（cards_owned 不可為空）")
    if not scenario or not scenario.strip():
        return _error("", "情境描述不可為空")

    # 解析金額
    amount = _extract_amount(scenario)

    # 解析通路
    raw_channels = _extract_channels(scenario)

    # 如果完全找不到通路，fallback 到一般消費
    if not raw_channels:
        raw_channels = ["一般消費"]

    # 去重後解析 channel_id
    parsed_channels = []
    seen_cids = set()
    for ch_name in raw_channels:
        cid = _resolve_channel(ch_name)
        if cid not in seen_cids:
            seen_cids.add(cid)
            parsed_channels.append({"name": ch_name, "channel_id": cid})

    # 對每個解析出的通路執行 search_by_channel
    recommendations = []
    for ch in parsed_channels:
        result = search_by_channel(
            channel=ch["name"],   # 保留商家名稱（如「全聯」）讓 merchant_hint 機制生效
            cards_owned=cards_owned,
            amount=amount,
            top_k=3,
        )
        if result.get("results"):
            recommendations.append({
                "channel_name": _channel_display_name(ch["channel_id"], ch["name"]),
                "channel_id":   ch["channel_id"],
                "best_options": result["results"], # 改成陣列，包含至多 3 筆推薦
            })

    return {
        "scenario": scenario,
        "parsed": {
            "channels": parsed_channels,
            "amount":   amount,
        },
        "recommendations": recommendations,
        "error": None,
    }


def _error(scenario: str, msg: str) -> dict:
    return {
        "scenario":        scenario,
        "parsed":          {"channels": [], "amount": 0},
        "recommendations": [],
        "error":           msg,
    }
