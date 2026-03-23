"""
gradio_app.py
-------------
CTBC 信用卡支付建議 — Gradio Demo 前端

啟動方式：
    python gradio_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

from mcp_server.utils.data_loader import get_cards_menu
from mcp_server.tools.search import search_by_channel, _resolve_channel, _channel_display_name
from mcp_server.tools.recommend import _extract_channels

# ── Groq 客戶端（海外辨識用） ─────────────────────────────────────────────────

_groq_client: Groq | None = None

def _get_groq() -> Groq | None:
    global _groq_client
    if _groq_client is None:
        key = os.getenv("GROQ_API_KEY")
        if key:
            _groq_client = Groq(api_key=key)
    return _groq_client


def _detect_overseas(scenario: str) -> bool:
    """
    使用 Groq llama-3.1-8b-instant 判斷使用者描述的情境是否為海外消費。
    回傳 True 表示海外消費，False 表示國內消費。
    若 API 不可用，fallback 到關鍵字判斷。
    """
    # fallback：關鍵字快速判斷（避免 API 失敗時無回應）
    _OVERSEAS_KW = ("日本", "韓國", "美國", "歐洲", "英國", "法國", "德國", "泰國",
                    "香港", "澳門", "新加坡", "馬來西亞", "澳洲", "加拿大", "中國",
                    "出國", "國外", "海外", "境外", "overseas", "abroad", "foreign",
                    "旅外", "出境", "飛去", "去國外")
    if any(kw in scenario for kw in _OVERSEAS_KW):
        return True

    client = _get_groq()
    if client is None:
        return False

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一個判斷消費情境的分類器。"
                        "你的任務是判斷使用者描述的消費是否發生在台灣以外的地區（海外消費）。"
                        "只回答 yes 或 no，不要有其他文字。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"這是海外消費嗎？情境：{scenario}",
                },
            ],
            max_tokens=5,
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().lower()
        return answer.startswith("yes") or answer.startswith("y")
    except Exception:
        return False

# ── 卡片清單（啟動時載入一次）────────────────────────────────────────────────

_cards = get_cards_menu()
CARD_CHOICES = [(c["card_name"], c["card_id"]) for c in _cards]

# ── 偏好回饋種類選項 ──────────────────────────────────────────────────────────

REWARD_TYPE_CHOICES = [
    ("現金回饋", "cash"),
    ("LINE Points", "line_points"),
    ("OPENPOINT", "openpoint"),
    ("航空哩程", "miles"),
    ("中信紅利點數", "ctbc_points"),
    ("其他點數", "other_points"),
]

# ── 回饋種類輔助函式 ──────────────────────────────────────────────────────────

def _reward_label(cashback_type: str | None, description: str) -> str:
    """從 cashback_type + 說明文字推斷回饋種類的顯示標籤。"""
    desc = (description or "").lower()
    if cashback_type == "miles" or any(kw in desc for kw in ("哩程", "里程", "miles", "哩")):
        return "哩程"
    if cashback_type == "points" or "點數" in desc or "紅利" in desc or "point" in desc:
        if "line points" in desc or "line point" in desc:
            return "LINE Points"
        if "openpoint" in desc:
            return "OPENPOINT"
        if "紅利" in (description or ""):
            return "中信紅利點數"
        return "點數"
    if "openpoint" in desc:
        return "OPENPOINT"
    return "現金回饋"


def _reward_category(cashback_type: str | None, description: str) -> str:
    """將回饋標籤對應到偏好種類 key，用於偏好篩選。"""
    label = _reward_label(cashback_type, description)
    return {
        "哩程":       "miles",
        "LINE Points": "line_points",
        "OPENPOINT":  "openpoint",
        "中信紅利點數": "ctbc_points",
        "點數":        "other_points",
        "現金回饋":    "cash",
    }.get(label, "cash")


def _format_estimated(rate: float, amount: float, label: str) -> str:
    """依回饋種類輸出對應單位的預估回饋字串。"""
    estimated = amount * rate
    if label == "哩程":
        return f"哩程加碼 {rate * 100:.0f}%（實際哩程依航空公司規則計算）"
    if label in ("LINE Points", "OPENPOINT"):
        return f"{estimated:,.0f} {label}"
    if label == "中信紅利點數":
        return f"{estimated:,.0f} 紅利點"
    if label == "點數":
        return f"{estimated:,.0f} 點"
    return f"NT$ {estimated:,.0f} 元"


def _condition_note(result: dict) -> str:
    """若回饋率附有條件，回傳提示字串。"""
    desc = result.get("cashback_description", "")
    if "踩點" in desc or "任務" in desc:
        return "　⚠️ 需完成踩點任務，詳情請看中信信用卡官網"
    if any(kw in desc for kw in ("滿額", "指定", "加碼", "限")):
        return "　⚠️ 需符合指定條件，詳情請看中信信用卡官網"
    return ""


def _sort_results(results: list[dict], preferred_types: list[str]) -> list[dict]:
    """
    依偏好種類 + 預估回饋排序：
      1. 偏好種類的卡放前面
      2. 同層內依預估回饋金額降序
    若未選偏好，僅依預估回饋排序。
    """
    def key(r):
        cat = _reward_category(r.get("cashback_type"), r.get("cashback_description", ""))
        is_pref = 1 if (preferred_types and cat in preferred_types) else 0
        est = r.get("estimated_cashback") or 0.0
        return (is_pref, est)

    return sorted(results, key=key, reverse=True)


# ── 核心格式化邏輯 ────────────────────────────────────────────────────────────

def _format_single_channel(
    ch_display: str,
    results: list[dict],
    amount: float,
    preferred_types: list[str],
) -> str:
    valid = [r for r in results if r.get("cashback_rate") is not None]

    if not valid:
        return (
            f"### 📋 通路：{ch_display}\n\n"
            f"目前所持有的信用卡皆無相關優惠，若想要申辦其他張信用卡請詳閱"
            f"[中信官網](https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/index.html)。"
        )

    # 依偏好 + 金額重排
    sorted_valid = _sort_results(valid, preferred_types)

    rates = [r["cashback_rate"] for r in sorted_valid]
    all_same = len(set(round(r, 6) for r in rates)) == 1

    if all_same:
        rate = rates[0]
        card_names = "、".join(r["card_name"] for r in sorted_valid)
        reward_labels = "、".join(
            dict.fromkeys(
                _reward_label(r.get("cashback_type"), r.get("cashback_description", ""))
                for r in sorted_valid
            )
        )

        if len(sorted_valid) == 1:
            best = sorted_valid[0]
            desc = best.get("cashback_description", "")
            label = _reward_label(best.get("cashback_type"), desc)
            note = _condition_note(best)
            return (
                f"### 📋 通路：{ch_display}\n\n"
                f"🏆 **最推薦：{best['card_name']}**\n\n"
                f"- **回饋率**：{rate * 100:.1f}%（{label}）{note}\n"
                f"- **預估回饋**：{_format_estimated(rate, amount, label)}\n"
                + (f"- **說明**：{desc[:100]}\n" if desc else "")
            )

        est_str = _format_estimated(rate, amount, _reward_label(
            sorted_valid[0].get("cashback_type"), sorted_valid[0].get("cashback_description", "")
        ))
        return (
            f"### 📋 通路：{ch_display}\n\n"
            f"💡 您持有的卡片在「{ch_display}」**回饋率相同（{rate * 100:.1f}%）**，"
            f"刷哪張信用卡都可以！\n\n"
            f"- **適用卡片**：{card_names}\n"
            f"- **回饋種類**：{reward_labels}\n"
            f"- **預估回饋**：{est_str}\n"
        )

    # 有差異 → 顯示最優 + 比較表
    best = sorted_valid[0]
    best_rate = best["cashback_rate"]
    best_desc = best.get("cashback_description", "")
    best_label = _reward_label(best.get("cashback_type"), best_desc)
    best_note = _condition_note(best)

    # 比較表（只顯示有回饋率的卡片）
    all_sorted = _sort_results(results, preferred_types)
    no_data_count = sum(1 for r in all_sorted if r.get("cashback_rate") is None)
    rows = []
    for r in all_sorted:
        r_rate = r.get("cashback_rate")
        if r_rate is None:
            continue   # 無回饋率資料，略過不顯示
        r_label = _reward_label(r.get("cashback_type"), r.get("cashback_description", ""))
        cat = _reward_category(r.get("cashback_type"), r.get("cashback_description", ""))
        is_pref = preferred_types and cat in preferred_types
        pref_star = " ⭐" if is_pref else ""
        note_col = "需符合條件" if _condition_note(r) else ""
        marker = " 🏆" if r["card_id"] == best["card_id"] else ""
        est_col = _format_estimated(r_rate, amount, r_label)
        note_str = "⚠️ 需符合條件" if _condition_note(r) else ""
        rows.append(
            f"| {r['card_name']}{marker}{pref_star} | {r_rate * 100:.1f}% "
            f"| {r_label} | {est_col} | {note_str} |"
        )

    table = "\n".join(rows)
    _PREF_DISPLAY = {v: k for k, v in dict(REWARD_TYPE_CHOICES).items()}
    pref_hint = (
        f"\n> ⭐ 標示為您偏好的回饋種類（"
        f"{', '.join(_PREF_DISPLAY.get(p, p) for p in preferred_types)}）\n"
        if preferred_types else ""
    )

    no_data_note = (
        f"\n> *另有 {no_data_count} 張持有卡在此通路查無回饋率資料，已省略不顯示。*\n"
        if no_data_count else ""
    )

    return (
        f"### 📋 通路：{ch_display}\n\n"
        f"🏆 **最推薦：{best['card_name']}**\n\n"
        f"- **回饋率**：{best_rate * 100:.1f}%（{best_label}）{best_note}\n"
        f"- **預估回饋**：{_format_estimated(best_rate, amount, best_label)}\n"
        + (f"- **說明**：{best_desc[:100]}\n" if best_desc else "")
        + pref_hint
        + f"\n**持卡回饋比較**\n\n"
        f"| 卡片 | 回饋率 | 回饋種類 | 預估回饋 | 備註 |\n"
        f"|------|:------:|:--------:|:--------:|:----:|\n"
        f"{table}\n"
        + no_data_note
    )


def recommend(
    selected_ids: list[str],
    amount: float | None,
    scenario: str,
    preferred_types: list[str],
) -> str:
    if not selected_ids:
        return "⚠️ 請先勾選您目前持有的信用卡。"
    if not amount or amount <= 0:
        return "⚠️ 請輸入有效的消費金額（須大於 0）。"
    if not scenario or not scenario.strip():
        return "⚠️ 請描述您的消費情境（例如：我要去 7-11 買東西）。"

    # ── 海外消費辨識 ──
    is_overseas = _detect_overseas(scenario.strip())

    raw_channels = _extract_channels(scenario)
    if not raw_channels:
        raw_channels = ["一般消費"]

    seen: set[str] = set()
    parsed: list[tuple[str, str]] = []

    # 若偵測到海外消費，優先加入 overseas_general 通路
    if is_overseas:
        seen.add("overseas_general")
        parsed.append(("海外消費", "overseas_general"))

    for ch_name in raw_channels:
        cid = _resolve_channel(ch_name)
        if cid not in seen:
            seen.add(cid)
            parsed.append((_channel_display_name(cid, ch_name), cid))

    parts: list[str] = []
    for ch_display, ch_id in parsed:
        result = search_by_channel(
            channel=ch_id,
            cards_owned=selected_ids,
            amount=amount,
            top_k=len(selected_ids),
        )
        parts.append(
            _format_single_channel(
                ch_display, result.get("results", []), amount, preferred_types or []
            )
        )

    _pref_labels = {v: k for k, v in dict(REWARD_TYPE_CHOICES).items()}
    pref_line = (
        f"**偏好回饋**：{'、'.join(_pref_labels.get(p, p) for p in preferred_types)}　｜　"
        if preferred_types else ""
    )
    overseas_warning = (
        "\n\n> ⚠️ **海外消費提示**：國外消費可能有限定條件，詳情請洽[中信官網](https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/index.html)。"
        if is_overseas else ""
    )
    header = (
        f"## 💳 刷卡建議結果\n\n"
        f"**消費金額**：NT$ {amount:,.0f} 元　｜　"
        f"{pref_line}"
        f"**消費情境**：{scenario.strip()}"
        f"{overseas_warning}"
        f"\n\n---\n\n"
    )
    return header + "\n\n---\n\n".join(parts)


# ── Gradio UI ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="💳 CTBC & 富邦信用卡支付建議系統") as demo:

    gr.Markdown(
        "# 💳 CTBC & 富邦信用卡支付建議\n"
        "中國信託銀行 × 台北富邦銀行熱門信用卡 | 選擇持有的信用卡與偏好回饋種類，輸入消費金額與情境，立即獲得最佳刷卡建議。"
    )

    with gr.Row():
        # ── 左欄：持卡勾選 ────────────────────────────────────────────────
        with gr.Column(scale=4):
            with gr.Row():
                select_all_btn = gr.Button("全選", size="sm", variant="secondary")
                clear_btn = gr.Button("清除", size="sm", variant="secondary")
            cards_input = gr.CheckboxGroup(
                choices=CARD_CHOICES,
                value=[],
                label="✅ 選擇持有的信用卡（中信 + 富邦）",
            )

        # ── 右欄：偏好 + 輸入 + 結果 ──────────────────────────────────────
        with gr.Column(scale=6):
            preferred_input = gr.CheckboxGroup(
                choices=REWARD_TYPE_CHOICES,
                value=[],
                label="⭐ 偏好回饋種類（可複選，結果將優先顯示此類型）",
            )
            amount_input = gr.Number(
                label="消費金額（新台幣）",
                minimum=1,
                value=None,
                info="輸入這次要消費的金額",
            )
            scenario_input = gr.Textbox(
                label="消費情境",
                placeholder="例如：我要去 7-11 買東西 / 今晚訂 foodpanda / 在蝦皮購物",
                lines=2,
                info="描述消費地點，系統自動辨識通路",
            )
            submit_btn = gr.Button("查詢最優刷卡 →", variant="primary", size="lg")

            output = gr.Markdown(
                value="*查詢結果將顯示於此。*",
                label="推薦結果",
            )

    _all_ids = [card_id for _, card_id in CARD_CHOICES]
    select_all_btn.click(fn=lambda: _all_ids, outputs=cards_input)
    clear_btn.click(fn=lambda: [], outputs=cards_input)

    _inputs = [cards_input, amount_input, scenario_input, preferred_input]
    submit_btn.click(fn=recommend, inputs=_inputs, outputs=output)
    scenario_input.submit(fn=recommend, inputs=_inputs, outputs=output)

    gr.Markdown(
        "---\n*資料來源：中信銀行官網 API（2026-03-07）+ 富邦銀行官網人工整理（2026-03-16）。"
        "回饋率僅供參考，實際以各銀行官網公告為準。*"
    )


def main():
    """套件安裝後的指令入口（ctbc-demo）。"""
    demo.launch(
        server_name="127.0.0.1",
        server_port=None,
        share=False,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
