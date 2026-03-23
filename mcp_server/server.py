"""
server.py
---------
Phase 3：CTBC 支付建議 MCP Server（FastMCP）

啟動方式：
    python -m mcp_server.server          # stdio 模式（給 Agent 使用）
    mcp dev mcp_server/server.py         # 開發模式（帶 Inspector UI）

Tools（5個）：
    search_by_channel     → 依通路搜尋最優卡
    recommend_payment     → 依情境推薦最佳刷卡
    compare_cards         → 多卡回饋比較
    get_promotions        → 取得持有卡的優惠活動
    get_card_details      → 取得卡片完整資訊

Resources（2個）：
    card://ctbc/{card_id}  → 單張卡片 JSON
    channels://ctbc/all    → 通路分類表
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .tools.compare import compare_cards as _compare_cards
from .tools.promotions import get_card_details as _get_card_details
from .tools.promotions import get_promotions as _get_promotions
from .tools.recommend import recommend_payment as _recommend_payment
from .tools.search import search_by_channel as _search_by_channel
from .utils.data_loader import (
    get_all_cards,
    get_card_by_id,
    get_cards_menu,
    get_channels_map,
    get_data_summary,
    reload_all,
)

# ── FastMCP 初始化 ────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="CTBC Payment Advisor",
    instructions=(
        "你是中國信託銀行（CTBC）信用卡支付建議服務。"
        "根據使用者持有的卡片和消費情境，提供最優的刷卡建議。"
        "所有 Tool 的 cards_owned 參數都必須填入使用者實際持有的 card_id 清單。"
    ),
)


# ── Tool 1：search_by_channel ─────────────────────────────────────────────────

@mcp.tool()
def search_by_channel(
    channel: str,
    cards_owned: list[str],
    amount: float = 0,
    top_k: int = 3,
) -> dict:
    """
    從使用者持有的信用卡中，找出在指定通路回饋最高的卡片。

    支援模糊通路輸入，例如：
    - "711" / "小7" / "統一超商" → 超商
    - "全聯" / "家樂福" / "量販" → 超市/量販
    - "蝦皮" / "momo" / "電商" → 電商
    - "Uber Eats" / "外送" → 外送
    - "LINE Pay" / "行動支付" → 行動支付

    Args:
        channel:     通路名稱（支援商家名稱或類別關鍵字）
        cards_owned: 使用者持有的卡 card_id 列表（必填，不可為空）
        amount:      預計消費金額（新台幣），用於計算預估回饋（0 = 不計算）
        top_k:       最多回傳幾張卡的結果（預設 3）
    """
    return _search_by_channel(
        channel=channel,
        cards_owned=cards_owned,
        amount=amount,
        top_k=top_k,
    )


# ── Tool 2：recommend_payment ─────────────────────────────────────────────────

@mcp.tool()
def recommend_payment(
    scenario: str,
    cards_owned: list[str],
) -> dict:
    """
    根據自然語言消費情境，從使用者持有的卡中推薦最佳刷卡選擇。

    自動解析情境中的消費通路和金額，支援多通路情境，例如：
    - "去全聯買菜花了1500元"
    - "今天要叫 Uber Eats 外送，大概花 300 元"
    - "早上在星巴克喝咖啡，晚上要訂高鐵票"

    Args:
        scenario:    自然語言消費情境描述
        cards_owned: 使用者持有的卡 card_id 列表（必填，不可為空）
    """
    return _recommend_payment(
        scenario=scenario,
        cards_owned=cards_owned,
    )


# ── Tool 3：compare_cards ─────────────────────────────────────────────────────

@mcp.tool()
def compare_cards(
    cards_owned: list[str],
    channel: str = "",
    amount: float = 1000,
) -> dict:
    """
    比較使用者持有的多張信用卡，在指定通路（或全通路）的回饋差異。

    可以用來回答：
    - "我的這幾張卡哪張在超商最划算？"
    - "幫我比較我的所有卡各自最適合用在哪？"
    - "LINE Pay 卡和現金回饋卡哪個適合刷電商？"

    Args:
        cards_owned: 使用者持有的卡 card_id 列表（必填，不可為空）
        channel:     指定比較通路，不填則比較全通路
        amount:      參考消費金額（新台幣，預設 NT$1,000）
    """
    return _compare_cards(
        cards_owned=cards_owned,
        channel=channel,
        amount=amount,
    )


# ── Tool 4：get_promotions ────────────────────────────────────────────────────

@mcp.tool()
def get_promotions(
    cards_owned: list[str],
    category: str = "",
    valid_only: bool = True,
) -> dict:
    """
    取得目前有效的信用卡優惠活動，以及持有卡中即將到期的優惠提醒。

    可以用來回答：
    - "我的卡最近有哪些優惠？"
    - "有沒有外送相關的優惠快到期了？"
    - "最近有哪些電商優惠活動？"

    Args:
        cards_owned: 使用者持有的卡 card_id 列表（必填，不可為空）
        category:    通路分類篩選（如 "ecommerce"、"dining"），不填回傳全部
        valid_only:  是否只回傳有效優惠（預設 True）
    """
    return _get_promotions(
        cards_owned=cards_owned,
        category=category,
        valid_only=valid_only,
    )


# ── Tool 5：get_card_details ──────────────────────────────────────────────────

@mcp.tool()
def get_card_details(card_id: str) -> dict:
    """
    取得單張信用卡的完整優惠資訊，包含所有通路、條件、截止日、備註。

    適合用於：
    - 使用者想了解某張卡的完整優惠
    - Agent 需要確認特定卡片的詳細資料

    Args:
        card_id: 卡片 ID，格式如 "ctbc_c_linepay"（可用 list_all_cards 查詢）
    """
    return _get_card_details(card_id=card_id)


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("card://ctbc/{card_id}")
def get_card_resource(card_id: str) -> str:
    """
    提供單張卡片的完整 JSON 資料作為 MCP Resource。
    URI 格式：card://ctbc/ctbc_c_linepay
    """
    card = get_card_by_id(card_id)
    if not card:
        return json.dumps({"error": f"找不到卡片：{card_id}"}, ensure_ascii=False)
    return json.dumps(card, ensure_ascii=False, indent=2)


@mcp.resource("channels://ctbc/all")
def get_channels_resource() -> str:
    """
    提供完整的通路分類對照表 JSON。
    URI 格式：channels://ctbc/all
    """
    return json.dumps(get_channels_map(), ensure_ascii=False, indent=2)


# ── 輔助 Tools（供 Agent 查詢可用 ID）───────────────────────────────────────

@mcp.tool()
def list_all_cards() -> dict:
    """
    列出資料集中所有現行中信信用卡的 card_id 和名稱，
    用於 CLI 持卡選單或 Agent 確認可用的 card_id。

    Returns:
        {
          "last_updated": "2026-03-06",
          "card_count": 47,
          "cards": [{"card_id": "...", "card_name": "...", "tags": [...]}]
        }
    """
    summary = get_data_summary()
    return {
        "last_updated": summary.get("last_updated"),
        "card_count":   summary.get("card_count"),
        "cards":        get_cards_menu(),
    }


@mcp.tool()
def reload_data() -> dict:
    """
    強制重新從磁碟載入最新的 data/processed/ 資料（scraper 更新後使用）。
    """
    reload_all()
    summary = get_data_summary()
    return {
        "status":       "reloaded",
        "last_updated": summary.get("last_updated"),
        "card_count":   summary.get("card_count"),
    }


# ── 啟動入口 ──────────────────────────────────────────────────────────────────

def main():
    """套件安裝後的指令入口（ctbc-mcp）。"""
    mcp.run()


if __name__ == "__main__":
    main()
