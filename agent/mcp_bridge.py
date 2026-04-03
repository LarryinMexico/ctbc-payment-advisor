"""
mcp_bridge.py
-------------
MCP Tools 與 Groq Function Calling 的橋接層。

功能：
1. 定義 Groq 相容的 Tool Schema（不含 cards_owned，由 Agent 自動注入）
2. 提供 execute_tool() 函式，透過 HTTP 呼叫遠端 MCP Server
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

MCP_SERVER_URL = os.environ.get(
    "MCP_SERVER_URL",
    "https://ctbc-payment-advisor.onrender.com/mcp",
)

_session_id: str | None = None


def _get_session_id() -> str:
    """初始化 MCP session，回傳 session ID（同一 process 內只初始化一次）。"""
    global _session_id
    if _session_id:
        return _session_id

    resp = requests.post(
        MCP_SERVER_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ctbc-agent", "version": "1.0"},
            },
            "id": 1,
        },
        timeout=30,
    )
    resp.raise_for_status()
    _session_id = resp.headers.get("mcp-session-id")
    if not _session_id:
        raise RuntimeError("MCP server 未回傳 session ID，請確認 server 是否正常運作")
    return _session_id


def _call_tool(tool_name: str, arguments: dict) -> dict:
    """透過 HTTP 呼叫遠端 MCP tool，回傳 result dict。"""
    session_id = _get_session_id()
    resp = requests.post(
        MCP_SERVER_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 2,
        },
        timeout=30,
    )
    resp.raise_for_status()

    # Streamable HTTP 回傳 SSE 格式，正確處理跨行 data: 欄位
    # 強制 UTF-8 解碼（避免 requests 自動用 ISO-8859-1 導致中文 byte 觸發 splitlines 斷行）
    # SSE 規範：同一 event 的多行 data: 需要先 join 再解析
    body = resp.content.decode("utf-8")
    events: list[str] = []
    current_data_lines: list[str] = []
    for line in body.split("\n"):
        if line.startswith("data:"):
            current_data_lines.append(line[len("data:"):].lstrip())
        elif line.strip() == "" and current_data_lines:
            events.append("\n".join(current_data_lines))
            current_data_lines = []
    if current_data_lines:
        events.append("\n".join(current_data_lines))

    for event_data in events:
        try:
            payload = json.loads(event_data)
        except json.JSONDecodeError:
            continue
        if "error" in payload:
            return {"error": payload["error"].get("message", "未知錯誤")}
        content = payload.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return payload.get("result", {})

    return {"error": "MCP server 回傳格式無法解析"}


def _get_cards_menu_remote() -> list[dict]:
    """從遠端取得卡片選單。"""
    result = _call_tool("list_all_cards", {})
    return result.get("cards", [])


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
    透過 HTTP 呼叫遠端 MCP Server。

    Args:
        tool_name:   工具名稱
        arguments:   LLM 生成的參數（不含 cards_owned）
        cards_owned: 本 session 的持卡清單（自動注入）

    Returns:
        工具執行結果的 JSON 字串
    """
    args = dict(arguments)
    args["cards_owned"] = cards_owned  # 自動注入，不讓 LLM 控制

    try:
        result = _call_tool(tool_name, args)
    except Exception as e:
        result = {"error": f"工具執行失敗：{e}"}

    return json.dumps(result, ensure_ascii=False)


def get_all_card_ids() -> list[str]:
    """取得所有卡片的 card_id 清單（供選單使用）。"""
    return [c["card_id"] for c in _get_cards_menu_remote()]


def get_all_cards_for_menu() -> list[dict]:
    """取得供選單顯示的卡片清單。"""
    return _get_cards_menu_remote()
