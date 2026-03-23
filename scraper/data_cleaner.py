"""
data_cleaner.py
---------------
Phase 2：將爬蟲抓回的 raw JSON 清理、正規化，
輸出符合 card_schema.json 的結構化資料。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import jsonschema
from rich.console import Console

from .channel_mapper import (
    extract_merchants_from_text,
    get_channel_id,
    infer_channel_id_from_merchants,
)

console = Console()

SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schemas" / "card_schema.json"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


# ── 基本欄位正規化 ────────────────────────────────────────────────────────────

def normalize_cashback_rate(raw: str | float | int | None) -> Optional[float]:
    """
    把各種形式的回饋率轉為小數（0.05 = 5%）。
    支援：
        "5%", "5 %", "5.5%"  → 0.05 / 0.055
        "0.05"               → 0.05
        5 (int/float > 1)    → 0.05
        "5倍" (x5 of base)   → 回傳 None（需特殊處理）
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val <= 1.0 else val / 100.0

    text = str(raw).strip()

    # 百分比字串
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1)) / 100.0

    # 純數字字串
    try:
        val = float(text)
        return val if val <= 1.0 else val / 100.0
    except ValueError:
        pass

    return None


def normalize_amount(raw: str | int | None) -> Optional[int]:
    """
    把「NT$1,000」「1000元」「1,000」等格式轉成整數。
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    cleaned = re.sub(r"[NT$,\s元，]", "", str(raw))
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def normalize_date(raw: str | None) -> Optional[str]:
    """
    把各種日期格式轉成 ISO 8601（YYYY-MM-DD）。
    """
    if not raw:
        return None
    raw = str(raw).strip()
    formats = [
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",
        "%Y年%m月%d日", "%m/%d/%Y",
        "%Y/%m", "%Y-%m",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 嘗試只提取年月日數字
    nums = re.findall(r"\d+", raw)
    if len(nums) >= 3:
        try:
            return f"{nums[0]}-{nums[1].zfill(2)}-{nums[2].zfill(2)}"
        except Exception:
            pass
    return None


def is_expiring_soon(valid_end: str | None, threshold_days: int = 30) -> bool:
    """判斷優惠是否在 threshold_days 天內到期。"""
    if not valid_end:
        return False
    try:
        end = datetime.strptime(valid_end, "%Y-%m-%d").date()
        return 0 < (end - date.today()).days <= threshold_days
    except ValueError:
        return False


def generate_card_id(card_name: str) -> str:
    """
    從卡片名稱生成穩定的 card_id。
    「中信 LINE Pay 卡」→ "ctbc_line_pay"
    """
    name = card_name
    for prefix in ["中國信託", "中信"]:
        name = name.replace(prefix, "")
    name = name.strip()
    # 保留英數、中文，其他換底線
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "_", name.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"ctbc_{slug}"


# ── 優惠文字解析 ─────────────────────────────────────────────────────────────

def parse_benefit_text(text: str) -> dict:
    """
    從一段中文優惠說明中抽取結構化欄位。

    輸入範例：
        「統一超商、全家、萊爾富消費享5%現金回饋，每期回饋金額上限300元」
        「LINE Pay消費享3%現金回饋，每期上限200元，有效期至2026/06/30」
        「國內一般消費回饋1%」

    回傳 dict（缺欄位填 None）：
        channel_id, channel_name, merchants,
        cashback_type, cashback_rate, cashback_description,
        max_cashback_per_period, conditions,
        valid_forever, valid_start, valid_end, expiring_soon
    """
    result: dict = {
        "channel_id":             None,
        "channel_name":           None,
        "merchants":              [],
        "cashback_type":          "cash",
        "cashback_rate":          None,
        "cashback_description":   text.strip(),
        "max_cashback_per_period": None,
        "min_spend":              None,
        "conditions":             text.strip(),
        "valid_forever":          True,
        "valid_start":            None,
        "valid_end":              None,
        "expiring_soon":          False,
    }

    # ── 回饋率 ──
    rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if rate_match:
        result["cashback_rate"] = float(rate_match.group(1)) / 100.0

    # ── 回饋類型 ──
    if re.search(r"哩程|里程|mile|航空點", text, re.I):
        result["cashback_type"] = "miles"
    elif re.search(r"點數|紅利|回饋金|point|積點", text, re.I):
        result["cashback_type"] = "points"
    else:
        result["cashback_type"] = "cash"

    # ── 每期上限 ──
    cap_match = re.search(
        r"(?:每期|每月|每季)?(?:回饋金額?)?上限\s*(?:NT\$|新台幣)?\s*([\d,]+)\s*元?",
        text
    )
    if cap_match:
        result["max_cashback_per_period"] = normalize_amount(cap_match.group(1))

    # ── 最低消費 ──
    min_match = re.search(
        r"(?:單筆|每筆|每月)?(?:消費)?(?:滿|達|需)\s*(?:NT\$|新台幣)?\s*([\d,]+)\s*元",
        text
    )
    if min_match:
        result["min_spend"] = normalize_amount(min_match.group(1))

    # ── 截止日期 ──
    date_match = re.search(
        r"(?:有效期(?:限|至)|至|~|到)\s*(\d{4}[/\-年]\d{1,2}[/\-月]\d{1,2}日?)",
        text
    )
    if date_match:
        result["valid_end"] = normalize_date(date_match.group(1))
        result["valid_forever"] = False
        result["expiring_soon"] = is_expiring_soon(result["valid_end"])

    # ── 商家 & channel_id ──
    merchants = extract_merchants_from_text(text)
    if merchants:
        result["merchants"] = merchants
        result["channel_id"] = infer_channel_id_from_merchants(merchants)
    else:
        # fallback：從文字關鍵字推斷 channel
        result["channel_id"] = get_channel_id(text) or "general"

    # ── 海外消費 override ──
    # 若描述文字包含國外/海外/境外等關鍵字，覆蓋為 overseas_general
    _OVERSEAS_KEYWORDS = ("國外", "海外", "境外", "overseas", "foreign", "國際", "出國")
    if any(kw in text.lower() for kw in _OVERSEAS_KEYWORDS):
        result["channel_id"] = "overseas_general"

    # ── channel_name（從 channels.json 或預設） ──
    CHANNEL_NAMES = {
        "convenience_store": "超商",
        "supermarket": "超市／量販",
        "ecommerce": "電商",
        "food_delivery": "外送",
        "transport": "交通",
        "dining": "餐飲",
        "travel": "旅遊",
        "entertainment": "娛樂",
        "gas_station": "加油站",
        "pharmacy": "藥妝",
        "mobile_payment": "行動支付",
        "general": "一般消費",
        "overseas_general": "海外消費",
    }
    result["channel_name"] = CHANNEL_NAMES.get(result["channel_id"], result["channel_id"])

    return result


# ── 整張卡片清理 ─────────────────────────────────────────────────────────────

def clean_card(raw: dict) -> dict:
    """
    將爬蟲抓回的 raw card dict 轉成符合 schema 的乾淨格式。

    raw 格式範例（由 ctbc_scraper.py 輸出）：
    {
        "card_name": "中信 LINE Pay 卡",
        "card_url": "https://...",
        "apply_url": "https://...",
        "card_status": "active",
        "raw_benefits": [
            {"text": "LINE Pay 消費享5%回饋，每期上限200元"},
            ...
        ],
        "scraped_at": "2026-03-06T10:00:00"
    }
    """
    card_name = raw.get("card_name", "").strip()
    # API 回傳的 card_id（如 "C_LINEPay"）直接使用，否則自動生成
    raw_card_id = raw.get("card_id", "")
    if raw_card_id and not raw_card_id.startswith("ctbc_"):
        card_id = f"ctbc_{raw_card_id.lower()}"
    else:
        card_id = raw_card_id or generate_card_id(card_name)

    # 解析每條 benefit 文字
    channels: list[dict] = []
    for b in raw.get("raw_benefits", []):
        text = b.get("text", "") if isinstance(b, dict) else str(b)
        if not text.strip():
            continue
        channel_data = parse_benefit_text(text)
        # 補充 cashback_description
        channel_data["cashback_description"] = text.strip()
        channels.append(channel_data)

    # 若沒有 channels，加一筆 unknown
    if not channels:
        channels = [{
            "channel_id": "general",
            "channel_name": "一般消費",
            "merchants": [],
            "cashback_type": "cash",
            "cashback_rate": None,
            "cashback_description": "待補充",
            "max_cashback_per_period": None,
            "min_spend": None,
            "conditions": "待補充",
            "valid_forever": True,
            "valid_start": None,
            "valid_end": None,
            "expiring_soon": False,
        }]

    cleaned = {
        "card_id":          card_id,
        "card_name":        card_name,
        "card_status":      raw.get("card_status", "unknown"),
        "card_org":         raw.get("card_org"),
        "annual_fee":       normalize_amount(raw.get("annual_fee")),
        "annual_fee_waiver": raw.get("annual_fee_waiver"),
        "card_url":         raw.get("card_url"),
        "apply_url":        raw.get("apply_url"),
        "tags":             raw.get("tags", []),
        "notes":            raw.get("notes"),
        "data_source":      raw.get("data_source", "scraper"),
        "last_verified":    raw.get("last_verified"),
        "channels":         channels,
    }
    return cleaned


def validate_card(card: dict) -> list[str]:
    """
    用 JSON Schema 驗證 card dict。
    回傳錯誤訊息列表（空列表代表驗證通過）。
    """
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(instance=card, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [e.message]
    except Exception as e:
        return [str(e)]


# ── 輸出 ──────────────────────────────────────────────────────────────────────

def clean_and_export(
    raw_cards: list[dict],
    output_path: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Phase 2 完整流程：
      1. 逐張卡片清理 (clean_card)
      2. Schema 驗證 (validate_card)
      3. 輸出 data/processed/ctbc_cards.json

    回傳輸出的完整 JSON dict。
    """
    if output_path is None:
        output_path = PROCESSED_DIR / "ctbc_cards.json"

    cleaned_cards: list[dict] = []
    errors: list[str] = []

    for raw in raw_cards:
        try:
            card = clean_card(raw)
            errs = validate_card(card)
            if errs:
                console.print(f"[yellow]⚠ {card['card_name']} 驗證警告：{errs}[/yellow]")
                errors.append(f"{card['card_name']}: {errs}")
            cleaned_cards.append(card)
        except Exception as e:
            console.print(f"[red]✗ 清理失敗 ({raw.get('card_name', '?')}): {e}[/red]")

    output = {
        "version":      "1.0",
        "last_updated": date.today().isoformat(),
        "bank":         "CTBC",
        "card_count":   len(cleaned_cards),
        "cards":        cleaned_cards,
    }

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]✓ 輸出完成 → {output_path}[/green]")
        console.print(f"  共 {len(cleaned_cards)} 張卡片，{len(errors)} 筆驗證警告")
    else:
        console.print(f"[cyan][dry-run] 未寫入檔案，共 {len(cleaned_cards)} 張卡片[/cyan]")

    return output


def diff_summary(old_path: Path, new_cards: list[dict]) -> dict:
    """
    比較新舊資料集的差異，輸出摘要。
    回傳：{"added": [...], "modified": [...], "removed": [...]}
    """
    if not old_path.exists():
        return {"added": [c["card_id"] for c in new_cards], "modified": [], "removed": []}

    old_data = json.loads(old_path.read_text(encoding="utf-8"))
    old_map = {c["card_id"]: c for c in old_data.get("cards", [])}
    new_map = {c["card_id"]: c for c in new_cards}

    added    = [cid for cid in new_map if cid not in old_map]
    removed  = [cid for cid in old_map if cid not in new_map]
    modified = [
        cid for cid in new_map
        if cid in old_map and new_map[cid] != old_map[cid]
    ]
    return {"added": added, "modified": modified, "removed": removed}
