"""
merge.py
--------
將三層資料源合併成單一 merged_cards.json。

合併規則：
- 基礎資料：ctbc_cards.json + fubon_cards.json
- 通路覆蓋：card_features.json 的 channel 資料精確度更高，
  相同 channel_id 時以 card_features 為準（Method A）
- 商家優惠：microsite_deals.json 的 deals 保留為獨立 deals 陣列（Method B）
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PROCESSED = BASE_DIR / "data" / "processed"
DATA_SCRAPED = BASE_DIR / "data" / "scraped"
OUTPUT_PATH = DATA_PROCESSED / "merged_cards.json"


# ── 特定通路「最高回饋」條件補充 ─────────────────────────────────────────────
# 針對描述含「最高」但 conditions 欄位為空的通路，補充必要的達成條件說明。
# 以 (card_id, channel_id) 為 key，避免錯誤套用到其他卡片。
# 每次重新 merge 時自動生效，不會被 scraper 覆蓋。
_CONDITION_WARNINGS: dict[tuple[str, str], str] = {
    ("ctbc_c_uniopen", "general"): (
        "⚠️ 最高 11% 需同時達成：①基本消費 1% + ②綁定 icash Pay 加碼 4% + "
        "③指定統一集團多品牌消費加碼回饋，一般刷卡消費僅有基本回饋約 1–3%。"
    ),
    ("ctbc_c_linepay", "general"): (
        "⚠️ 最高 16% 為特定通路（如指定電商、外送平台）的回饋上限，"
        "非所有通路皆適用此比率，實際回饋依消費通路而異，請確認通路專屬回饋。"
    ),
    ("ctbc_c_cs", "dining"): (
        "⚠️ 最高 20% 僅限遠東 SOGO 館內指定餐飲消費，一般餐廳或館外消費不適用。"
    ),
    ("ctbc_c_cs", "mobile_payment"): (
        "⚠️ 最高 10% 需以悠遊卡功能自動加值且單次消費滿 NT$500，"
        "且每月最高回饋上限 50 元（以 SOGO 金點數回饋）。"
    ),
    ("ctbc_c_hanshin", "general"): (
        "⚠️ 最高 3% 僅限漢神洲際館內消費（1% 基本回饋 + 2% 館內加碼），"
        "館外一般消費不適用加碼，且加碼回饋設有每月上限。"
    ),
}


def _apply_condition_warnings(card_id: str, channels: list[dict]) -> list[dict]:
    """
    對特定卡片 × 通路組合補充「最高回饋的達成條件」說明。
    僅在 conditions 欄位為空時補入，不覆蓋原有說明。
    """
    for ch in channels:
        key = (card_id, ch.get("channel_id", ""))
        if key in _CONDITION_WARNINGS and not (ch.get("conditions") or "").strip():
            ch["conditions"] = _CONDITION_WARNINGS[key]
    return channels


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dedup_channels(channels: list[dict]) -> list[dict]:
    """
    對同一 channel_id 的多筆條目去重。

    card_feature_scraper 會把頁面上每段行銷文案都當作獨立條目，
    造成同一 channel_id 出現 10+ 筆。去重策略：
    - 同 channel_id + 同 cashback_type 取 cashback_rate 最高者
    - 不同 cashback_type（如 cash vs points）各保留一筆最佳
    - cashback_rate 為 None 的條目被有值的條目取代
    """
    # key: (channel_id, cashback_type) → best entry
    best: dict[tuple[str, str], dict] = {}
    for ch in channels:
        cid = ch.get("channel_id", "")
        ctype = ch.get("cashback_type", "cash")
        rate = ch.get("cashback_rate") or 0.0
        key = (cid, ctype)
        existing = best.get(key)
        if existing is None:
            best[key] = ch
        else:
            existing_rate = existing.get("cashback_rate") or 0.0
            if rate > existing_rate:
                best[key] = ch
    return list(best.values())


def _merge_channels(
    base_channels: list[dict],
    feature_channels: list[dict],
) -> list[dict]:
    """
    合併 channels：card_features 的資料優先（Method A）。

    同一個 channel_id 只保留精確度較高的來源。
    由於 base_channels 可能有多個相同 channel_id 的條目（如 general），
    而 card_features 也可能有多個，採用以下策略：
    - 先收集 card_features 中出現的所有 channel_id
    - 對於這些 channel_id，使用 card_features 的版本（全部替換）
    - 對於 card_features 中沒有的 channel_id，保留 base 的版本
    - 最後對所有 channels 去重（同 channel_id + cashback_type 取最高回饋率）
    """
    feature_channel_ids = {ch["channel_id"] for ch in feature_channels}

    merged = []

    # 保留 base 中 card_features 沒有的 channel
    for ch in base_channels:
        if ch["channel_id"] not in feature_channel_ids:
            entry = dict(ch)
            entry["data_source"] = entry.pop("data_source", "api")
            merged.append(entry)

    # 加入 card_features 的 channel（精確度更高）
    for ch in feature_channels:
        entry = dict(ch)
        # 統一 source → data_source
        entry["data_source"] = entry.pop("source", "card_feature")
        merged.append(entry)

    # 去重：同 channel_id + cashback_type 只保留回饋率最高者
    return _dedup_channels(merged)


def merge() -> dict:
    """執行合併，回傳完整的 merged_cards dict。"""
    # ── 載入所有資料源 ──
    ctbc_data = _load_json(DATA_PROCESSED / "ctbc_cards.json")
    fubon_data = _load_json(DATA_PROCESSED / "fubon_cards.json")
    features_data = _load_json(DATA_SCRAPED / "card_features.json")
    microsite_data = _load_json(DATA_SCRAPED / "microsite_deals.json")

    features_cards = features_data.get("cards", {})    # dict keyed by card_id
    microsite_cards = microsite_data.get("cards", {})   # dict keyed by card_id

    # ── 合併所有卡片 ──
    all_base_cards = ctbc_data["cards"] + fubon_data["cards"]
    merged_cards = []

    for card in all_base_cards:
        card_id = card["card_id"]
        merged = dict(card)

        # 合併 channels（card_features 優先）
        feature_entry = features_cards.get(card_id, {})
        feature_channels = feature_entry.get("channels", [])

        if feature_channels:
            merged["channels"] = _merge_channels(
                card.get("channels", []),
                feature_channels,
            )
        else:
            # 沒有 card_features 資料，保留 base 的 channels 並標記 data_source + 去重
            merged["channels"] = _dedup_channels([
                {**ch, "data_source": ch.get("data_source", "api")}
                for ch in card.get("channels", [])
            ])

        # 補充「最高回饋」達成條件說明（避免 Agent 誤以為無條件適用）
        merged["channels"] = _apply_condition_warnings(card_id, merged["channels"])

        # 附加 microsite deals（Method B：獨立 deals 陣列）
        microsite_entry = microsite_cards.get(card_id, {})
        deals = microsite_entry.get("deals", [])
        if deals:
            # 過濾已過期的 deals
            today = date.today().isoformat()
            active_deals = [
                d for d in deals
                if not d.get("valid_end") or d["valid_end"] >= today
            ]
            if active_deals:
                merged["deals"] = active_deals

        merged_cards.append(merged)

    result = {
        "version": "2.0",
        "description": "合併自 ctbc_cards + fubon_cards + card_features + microsite_deals",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "merge_sources": {
            "ctbc_cards": str(DATA_PROCESSED / "ctbc_cards.json"),
            "fubon_cards": str(DATA_PROCESSED / "fubon_cards.json"),
            "card_features": str(DATA_SCRAPED / "card_features.json"),
            "microsite_deals": str(DATA_SCRAPED / "microsite_deals.json"),
        },
        "cards": merged_cards,
    }

    return result


def main():
    result = merge()
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 統計
    total = len(result["cards"])
    with_features = sum(
        1 for c in result["cards"]
        if any(ch.get("data_source") == "card_feature" or ch.get("data_source") == "card_feature_direct"
               for ch in c.get("channels", []))
    )
    with_deals = sum(1 for c in result["cards"] if c.get("deals"))
    total_deals = sum(len(c.get("deals", [])) for c in result["cards"])

    print(f"✓ 合併完成 → {OUTPUT_PATH}")
    print(f"  卡片總數：{total}")
    print(f"  含 card_features 通路資料：{with_features} 張")
    print(f"  含 microsite deals：{with_deals} 張（共 {total_deals} 筆）")


if __name__ == "__main__":
    main()
