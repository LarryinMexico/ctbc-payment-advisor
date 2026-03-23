"""
payment_agent.py
----------------
Phase 4 Agent 核心：Groq API + MCP Tool Calling + 多輪對話。

流程：
  1. 接收使用者訊息
  2. 連同對話記憶 + System Prompt 送入 Groq LLM
  3. 若 LLM 呼叫 Tool → 執行 MCP Tool（自動注入 cards_owned）→ 回送結果
  4. 重複步驟 2-3 直到生成最終自然語言回覆
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

from .mcp_bridge import TOOL_DEFINITIONS, execute_tool
from .prompts import build_system_prompt

load_dotenv()

# ── 模型設定 ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 5  # 防止無限 tool-call loop


class PaymentAgent:
    """
    CTBC 支付建議 Agent。

    Attributes:
        cards_owned:   本 session 持有卡的 card_id 列表
        cards_info:    持有卡的基本資訊（card_id + card_name），用於 System Prompt
        model:         Groq 模型名稱
        history:       多輪對話記憶（user / assistant / tool 訊息）
    """

    def __init__(
        self,
        cards_owned: list[str],
        cards_info: list[dict],
        model: str = DEFAULT_MODEL,
    ):
        self.cards_owned = cards_owned
        self.cards_info  = cards_info
        self.model       = model
        self.history:    list[dict] = []
        self._client     = Groq(api_key=os.environ["GROQ_API_KEY"])
        self._system_prompt = build_system_prompt(cards_info)

    # ── 公開介面 ──────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """
        單輪對話：送入使用者訊息，回傳助理的自然語言回覆。
        對話記憶自動累積在 self.history。
        """
        self.history.append({"role": "user", "content": user_message})

        messages = [
            {"role": "system", "content": self._system_prompt},
        ] + self.history

        # Tool-calling loop
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=2048,
            )

            message = response.choices[0].message

            # 若無 tool call → 生成最終回覆
            if not message.tool_calls:
                reply = message.content or ""
                self.history.append({"role": "assistant", "content": reply})
                return reply

            # 有 tool call → 執行並回送結果
            messages.append(message)
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = execute_tool(
                    tool_name=fn_name,
                    arguments=fn_args,
                    cards_owned=self.cards_owned,
                )

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      tool_result,
                })

        # 超過 tool round 限制（理論上不應發生）
        return "抱歉，處理您的請求時發生內部錯誤，請重試。"

    def reset_history(self):
        """清空對話記憶，開始新對話。"""
        self.history = []

    def get_history_summary(self) -> str:
        """回傳對話輪次摘要（用於 debug）。"""
        turns = sum(1 for m in self.history if m["role"] == "user")
        return f"對話記憶：{turns} 輪 / {len(self.history)} 則訊息"
