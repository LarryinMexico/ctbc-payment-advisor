"""
tests/test_user_stories.py
--------------------------
Phase 5 User Story 端對端測試。

執行方式：
    python -m tests.test_user_stories          # 執行全部
    python -m tests.test_user_stories --story 1  # 只執行 Story 1

每個 Story 會顯示：
  - 持卡設定、測試輸入
  - Agent 實際回覆
  - 通過 / 待確認（關鍵字檢查）
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ── 確保 project root 在 sys.path ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# ──────────────────────────────────────────────────────────────────────
# User Story 定義
# ──────────────────────────────────────────────────────────────────────

@dataclass
class UserStory:
    id: int
    title: str
    description: str
    cards: list[dict]          # [{card_id, card_name}, ...]
    user_input: str
    expected_keywords: list[str]  # 回覆中應出現的關鍵字（any of）
    check_all: bool = False       # True = ALL keywords must appear

USER_STORIES: list[UserStory] = [
    UserStory(
        id=1,
        title="超商消費推薦（單通路）",
        description="持有現金回饋鈦金卡 + LINE Pay 卡，詢問 7-11 最優刷法",
        cards=[
            {"card_id": "ctbc_b_cashback_titanium", "card_name": "中信現金回饋鈦金卡"},
            {"card_id": "ctbc_c_linepay",            "card_name": "LINE Pay信用卡"},
        ],
        user_input="我要去 7-11 買東西，大概花 500 元，哪張卡最優惠？",
        expected_keywords=["LINE Pay", "現金回饋鈦金", "超商", "回饋", "7"],
    ),
    UserStory(
        id=2,
        title="電商消費推薦",
        description="持有現金回饋鈦金卡 + Yahoo 聯名卡，詢問網路購物最優刷法",
        cards=[
            {"card_id": "ctbc_b_cashback_titanium", "card_name": "中信現金回饋鈦金卡"},
            {"card_id": "ctbc_c_yahoo",              "card_name": "Yahoo聯名卡"},
        ],
        user_input="我要在 Yahoo 購物網站買東西，大概花 2000 元，哪張卡回饋比較多？",
        expected_keywords=["Yahoo", "電商", "購物", "回饋", "2000"],
    ),
    UserStory(
        id=3,
        title="多卡全通路比較",
        description="持有三張卡，詢問各卡最適合的使用場合",
        cards=[
            {"card_id": "ctbc_b_cashback_titanium", "card_name": "中信現金回饋鈦金卡"},
            {"card_id": "ctbc_c_linepay",            "card_name": "LINE Pay信用卡"},
            {"card_id": "ctbc_c_fp",                 "card_name": "foodpanda聯名卡"},
        ],
        user_input="我有這三張卡，各自最適合用在哪些場合？幫我整理一下使用建議。",
        expected_keywords=["LINE Pay", "foodpanda", "現金回饋", "建議"],
    ),
    UserStory(
        id=4,
        title="快到期優惠查詢",
        description="查詢持有卡中即將到期的優惠活動",
        cards=[
            {"card_id": "ctbc_b_cashback_titanium", "card_name": "中信現金回饋鈦金卡"},
            {"card_id": "ctbc_c_linepay",            "card_name": "LINE Pay信用卡"},
        ],
        user_input="我的卡片最近有哪些優惠快到期了？請幫我列出來。",
        expected_keywords=["優惠", "到期", "活動", "卡"],
    ),
    UserStory(
        id=5,
        title="複合情境自動拆解",
        description="同一天有兩筆不同通路消費，詢問各別最優刷卡方式",
        cards=[
            {"card_id": "ctbc_b_cashback_titanium", "card_name": "中信現金回饋鈦金卡"},
            {"card_id": "ctbc_c_linepay",            "card_name": "LINE Pay信用卡"},
            {"card_id": "ctbc_c_fp",                 "card_name": "foodpanda聯名卡"},
        ],
        user_input=(
            "今天要去全聯買菜大概花 3000 元，晚上還要訂 foodpanda 外送，"
            "請幫我建議這兩筆消費分別要刷哪張卡最划算？"
        ),
        expected_keywords=["全聯", "foodpanda", "超市", "外送", "建議"],
    ),
]

# ──────────────────────────────────────────────────────────────────────
# 測試執行器
# ──────────────────────────────────────────────────────────────────────

def _check_keywords(reply: str, story: UserStory) -> tuple[bool, list[str]]:
    """回傳 (passed, matched_keywords)"""
    reply_lower = reply.lower()
    matched = [kw for kw in story.expected_keywords if kw.lower() in reply_lower]
    if story.check_all:
        passed = len(matched) == len(story.expected_keywords)
    else:
        passed = len(matched) >= 1
    return passed, matched


def run_story(story: UserStory, verbose: bool = True) -> dict:
    """執行單一 User Story，回傳結果 dict。"""
    from agent.payment_agent import PaymentAgent

    card_ids = [c["card_id"] for c in story.cards]
    agent = PaymentAgent(cards_owned=card_ids, cards_info=story.cards)

    if verbose:
        console.print()
        console.print(Panel.fit(
            f"[bold cyan]Story {story.id}：{story.title}[/bold cyan]\n"
            f"[dim]{story.description}[/dim]",
            border_style="cyan",
        ))
        # 持卡
        cards_str = "、".join(c["card_name"] for c in story.cards)
        console.print(f"[dim]持卡：{cards_str}[/dim]")
        console.print(f"[bold]問：[/bold]{story.user_input}\n")
        console.print("[dim]Agent 思考中...[/dim]", end="\r")

    start = time.time()
    try:
        reply = agent.chat(story.user_input)
        elapsed = time.time() - start
        passed, matched = _check_keywords(reply, story)
        error = None
    except Exception as e:
        reply = ""
        elapsed = time.time() - start
        passed = False
        matched = []
        error = str(e)

    if verbose:
        console.print(" " * 30, end="\r")  # clear "思考中"
        if error:
            console.print(f"[red]✗ 錯誤：{error}[/red]\n")
        else:
            console.print(f"[bold green]答：[/bold green]{reply}\n")
            status = "[green]✓ PASS[/green]" if passed else "[yellow]△ 請確認[/yellow]"
            console.print(
                f"{status}  "
                f"命中關鍵字：{matched or '（無）'}  "
                f"[dim]耗時 {elapsed:.1f}s[/dim]"
            )

    return {
        "story_id": story.id,
        "title": story.title,
        "input": story.user_input,
        "reply": reply,
        "passed": passed,
        "matched": matched,
        "elapsed": elapsed,
        "error": error,
    }


def run_all(story_ids: list[int] | None = None) -> list[dict]:
    """執行所有（或指定）User Story，最後顯示摘要表。"""
    stories = USER_STORIES
    if story_ids:
        stories = [s for s in USER_STORIES if s.id in story_ids]

    results = []
    for story in stories:
        result = run_story(story, verbose=True)
        results.append(result)
        time.sleep(0.5)  # 避免 API rate limit

    # ── 摘要表 ──
    console.print()
    console.print(Panel.fit("[bold]測試摘要[/bold]", border_style="magenta"))

    table = Table(box=box.ROUNDED, show_lines=True)
    table.add_column("#",     style="bold", width=4)
    table.add_column("Story",               min_width=20)
    table.add_column("結果",  justify="center", width=10)
    table.add_column("命中關鍵字",          min_width=20)
    table.add_column("耗時", justify="right", width=8)

    passed_count = 0
    for r in results:
        if r["error"]:
            status = "[red]ERROR[/red]"
        elif r["passed"]:
            status = "[green]PASS[/green]"
            passed_count += 1
        else:
            status = "[yellow]待確認[/yellow]"

        table.add_row(
            str(r["story_id"]),
            r["title"],
            status,
            "、".join(r["matched"]) if r["matched"] else "-",
            f"{r['elapsed']:.1f}s",
        )

    console.print(table)
    total = len(results)
    console.print(
        f"\n結果：[green]{passed_count} PASS[/green] / "
        f"[yellow]{total - passed_count} 待確認[/yellow]  共 {total} 個 Story\n"
    )
    return results


# ──────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="python -m tests.test_user_stories",
        description="CTBC Agent User Story 端對端測試",
    )
    parser.add_argument(
        "--story",
        nargs="+",
        type=int,
        metavar="N",
        help="只執行指定編號的 Story（如 --story 1 3）",
    )
    args = parser.parse_args()

    console.print(Panel(
        "[bold cyan]CTBC Agent × MCP — User Story 測試[/bold cyan]\n"
        "[dim]測試 5 個真實消費情境，驗證 Agent 回覆正確性[/dim]",
        border_style="cyan",
    ))

    run_all(story_ids=args.story)


if __name__ == "__main__":
    main()
