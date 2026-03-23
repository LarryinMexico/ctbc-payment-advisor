"""
mcp_bridge.py
-------------
MCP Tools 與 Groq Function Calling 的橋接層。

功能：
1. 定義 Groq 相容的 Tool Schema（不含 cards_owned，由 Agent 自動注入）
2. 提供 execute_tool() 函式，依工具名稱呼叫對應的 MCP 工具函式
"""

from __future__ import annotations

import json
from typing import Any

from mcp_server.tools.compare import compare_cards
from mcp_server.tools.promotions import get_card_details, get_promotions
from mcp_server.tools.recommend import recommend_payment
from mcp_server.tools.search import search_by_channel
from mcp_server.utils.data_loader import get_cards_menu


# ── Groq Tool Definitions（不含 cards_owned，由 Agent 注入）──────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_by_channel",
            "description": (
                "從使用者持有的信用卡中，找出在指定通路回饋最高的卡片。"
                "支援模糊通路輸入，如 '711'、'小7'、'統一超商'、'全聯'、'蝦皮'、'外送'、'LINE Pay' 等。"
                "必要時使用此工具查詢特定通路的最優卡片。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "通路名稱或商家名稱，如 '7-ELEVEN'、'超商'、'全聯'、'蝦皮'、'Uber Eats'、'LINE Pay'",
                    },
                    "amount": {
                        "type": "number",
                        "description": "預計消費金額（新台幣），用於計算預估回饋。不確定則填 0",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "最多回傳幾張卡的結果，預設 3",
                    },
                },
                "required": ["channel"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_payment",
            "description": (
                "根據自然語言消費情境，從使用者持有的卡中推薦最佳刷卡選擇。"
                "自動解析情境中的通路和金額，支援多通路情境。"
                "當使用者描述一個完整的消費情境時優先使用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario": {
                        "type": "string",
                        "description": "消費情境的自然語言描述，如 '去全聯買菜花了1500元' 或 '今天要叫外送，大概300元'",
                    },
                },
                "required": ["scenario"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_cards",
            "description": (
                "比較使用者持有的多張信用卡在特定通路（或全通路）的回饋差異。"
                "適合用於 '我的卡哪張比較好'、'幫我比較這幾張卡' 等整體比較需求。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "指定比較的通路，不填則比較全通路",
                    },
                    "amount": {
                        "type": "number",
                        "description": "參考消費金額（新台幣），預設 1000",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_promotions",
            "description": (
                "取得目前有效的信用卡優惠活動清單，以及持有卡中即將到期的優惠提醒。"
                "適合用於 '最近有什麼優惠'、'有什麼活動快到期' 等查詢。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            "通路分類篩選，如 'ecommerce'（電商）、'dining'（餐飲）、"
                            "'food_delivery'（外送）、'travel'（旅遊）。不填回傳全部。"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_details",
            "description": (
                "取得單張信用卡的完整優惠資訊，包含所有通路、條件、截止日、備註。"
                "當使用者想了解特定卡片的詳細內容時使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "string",
                        "description": "卡片 ID，格式如 'ctbc_c_linepay'",
                    },
                },
                "required": ["card_id"],
            },
        },
    },
]


# ── 工具執行（自動注入 cards_owned）─────────────────────────────────────────

def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    cards_owned: list[str],
) -> str:
    """
    執行指定的 MCP 工具，自動注入 cards_owned 後回傳 JSON 字串。

    Args:
        tool_name:   工具名稱
        arguments:   LLM 生成的參數（不含 cards_owned）
        cards_owned: 本 session 的持卡清單（自動注入）

    Returns:
        工具執行結果的 JSON 字串
    """
    args = dict(arguments)

    # cards_owned 自動注入（不讓 LLM 控制）
    args["cards_owned"] = cards_owned

    try:
        if tool_name == "search_by_channel":
            result = search_by_channel(
                channel=args.get("channel", ""),
                cards_owned=args["cards_owned"],
                amount=float(args.get("amount", 0)),
                top_k=int(args.get("top_k", 3)),
            )
        elif tool_name == "recommend_payment":
            result = recommend_payment(
                scenario=args.get("scenario", ""),
                cards_owned=args["cards_owned"],
            )
        elif tool_name == "compare_cards":
            result = compare_cards(
                cards_owned=args["cards_owned"],
                channel=args.get("channel", ""),
                amount=float(args.get("amount", 1000)),
            )
        elif tool_name == "get_promotions":
            result = get_promotions(
                cards_owned=args["cards_owned"],
                category=args.get("category", ""),
                valid_only=bool(args.get("valid_only", True)),
            )
        elif tool_name == "get_card_details":
            result = get_card_details(card_id=args.get("card_id", ""))
        else:
            result = {"error": f"未知工具：{tool_name}"}

    except Exception as e:
        result = {"error": f"工具執行失敗：{e}"}

    return json.dumps(result, ensure_ascii=False)


def get_all_card_ids() -> list[str]:
    """取得所有卡片的 card_id 清單（供選單使用）。"""
    return [c["card_id"] for c in get_cards_menu()]


def get_all_cards_for_menu() -> list[dict]:
    """取得供選單顯示的卡片清單。"""
    return get_cards_menu()
