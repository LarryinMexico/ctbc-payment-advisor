"""
main.py
-------
CTBC 支付建議助理 CLI 入口點。

使用方式：
    python main.py                     # 正常啟動（需 GROQ_API_KEY）
    python main.py --list-cards        # 列出所有可選卡片後離開
    python main.py --cards ctbc_c_linepay ctbc_b_cashback_titanium  # 直接指定持卡

流程：
  1. 顯示持卡選擇選單
  2. 使用者選擇持有的卡片
  3. 進入多輪對話模式（Agent 自動帶入持卡資訊）
  4. 輸入 'q' 或 Ctrl+C 離開
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

load_dotenv()

console = Console()

PROJECT_ROOT = Path(__file__).parent


# ── 持卡選擇 ──────────────────────────────────────────────────────────────────

def select_cards_interactive() -> tuple[list[str], list[dict]]:
    """
    互動式持卡選擇流程。
    回傳 (card_id_list, card_info_list)。
    """
    from agent.mcp_bridge import get_all_cards_for_menu

    all_cards = get_all_cards_for_menu()
    if not all_cards:
        console.print("[red]✗ 無法載入卡片資料，請先執行：python -m scraper.run full[/red]")
        sys.exit(1)

    while True:
        _display_card_menu(all_cards)

        raw = Prompt.ask(
            "\n[bold cyan]請輸入卡片編號[/bold cyan]（空格分隔，如 [dim]1 3 5[/dim]，或 [dim]a[/dim] 全選）"
        ).strip()

        if raw.lower() == "a":
            selected = list(range(len(all_cards)))
        else:
            try:
                selected = [int(x) - 1 for x in raw.split()]
                selected = [i for i in selected if 0 <= i < len(all_cards)]
            except ValueError:
                console.print("[yellow]⚠ 輸入格式錯誤，請重新輸入[/yellow]")
                continue

        if not selected:
            console.print("[yellow]⚠ 請至少選擇一張卡片[/yellow]")
            continue

        # 確認
        chosen = [all_cards[i] for i in selected]
        _display_selected(chosen)

        confirm = Prompt.ask(
            "[bold]確認以上選擇？[/bold]",
            choices=["y", "n", "r"],
            default="y",
            show_choices=True,
        )
        if confirm == "y":
            card_ids  = [c["card_id"] for c in chosen]
            card_info = [{"card_id": c["card_id"], "card_name": c["card_name"]} for c in chosen]
            return card_ids, card_info
        elif confirm == "n":
            console.print("[yellow]已取消，請重新選擇[/yellow]\n")
        # 'r' or 'n' both loop back


def _display_card_menu(cards: list[dict]):
    """顯示卡片選擇選單（rich table）。"""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]CTBC 支付建議助理[/bold cyan]\n"
        "[dim]請選擇您目前持有的中信信用卡（可多選）[/dim]",
        border_style="cyan",
    ))
    console.print()

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#", style="bold cyan", width=4, justify="right")
    table.add_column("卡片名稱", style="white", min_width=30)
    table.add_column("回饋類型", style="dim", min_width=20)
    table.add_column("卡片 ID", style="dim", min_width=20)

    for i, card in enumerate(cards, 1):
        tags = "、".join(card.get("tags", [])[:3])
        table.add_row(
            str(i),
            card["card_name"],
            tags or "-",
            card["card_id"],
        )

    console.print(table)


def _display_selected(cards: list[dict]):
    """顯示已選擇的卡片確認清單。"""
    console.print("\n[bold green]已選擇的卡片：[/bold green]")
    for c in cards:
        console.print(f"  [green]✓[/green] {c['card_name']}  [dim]({c['card_id']})[/dim]")
    console.print()


# ── 對話循環 ──────────────────────────────────────────────────────────────────

def chat_loop(agent):
    """多輪對話主迴圈。"""
    console.print(Panel(
        "[bold green]對話開始！[/bold green]\n"
        "[dim]輸入您的消費情境或問題，助理會為您推薦最適合的信用卡。[/dim]\n"
        "[dim]指令：'q' 離開 | 'r' 重置對話記憶 | 'h' 查看對話記錄[/dim]",
        border_style="green",
    ))
    console.print()

    while True:
        try:
            user_input = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n[dim]再見！[/dim]")
            break

        if not user_input:
            continue

        # 指令處理
        if user_input.lower() in ("q", "quit", "exit", "離開"):
            console.print("[dim]再見！[/dim]")
            break
        elif user_input.lower() in ("r", "reset"):
            agent.reset_history()
            console.print("[yellow]✓ 對話記憶已清空[/yellow]\n")
            continue
        elif user_input.lower() in ("h", "history"):
            console.print(f"[dim]{agent.get_history_summary()}[/dim]\n")
            continue

        # 呼叫 Agent
        console.print("[dim]思考中...[/dim]", end="\r")
        try:
            reply = agent.chat(user_input)
        except Exception as e:
            console.print(f"[red]✗ 發生錯誤：{e}[/red]\n")
            continue

        # 清除「思考中」提示並顯示回覆
        console.print(" " * 20, end="\r")
        console.print(f"\n[bold cyan]助理：[/bold cyan]{reply}\n")


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="CTBC 信用卡支付建議助理（Agent × MCP）",
    )
    parser.add_argument(
        "--list-cards",
        action="store_true",
        help="列出所有可選卡片後離開",
    )
    parser.add_argument(
        "--cards",
        nargs="+",
        metavar="CARD_ID",
        help="直接指定持有的卡片 card_id，跳過選單",
    )
    args = parser.parse_args()

    # --list-cards（不需 API key）
    if args.list_cards:
        from agent.mcp_bridge import get_all_cards_for_menu
        cards = get_all_cards_for_menu()
        table = Table(title="所有可選中信信用卡", show_lines=True)
        table.add_column("#", width=4)
        table.add_column("卡片名稱")
        table.add_column("card_id", style="dim")
        for i, c in enumerate(cards, 1):
            table.add_row(str(i), c["card_name"], c["card_id"])
        console.print(table)
        return

    # 檢查 API Key（在持卡選擇前）
    if not os.getenv("GROQ_API_KEY"):
        console.print(
            "[red]✗ 找不到 GROQ_API_KEY！[/red]\n"
            "請在專案目錄下建立 [bold].env[/bold] 檔案，內容：\n"
            "  [cyan]GROQ_API_KEY=your_key_here[/cyan]\n"
            "  至 https://console.groq.com 免費申請 API Key"
        )
        sys.exit(1)

    # 持卡選擇
    if args.cards:
        # 直接從 CLI 參數帶入
        from mcp_server.utils.data_loader import get_cards_by_ids
        card_objs = get_cards_by_ids(args.cards)
        if not card_objs:
            console.print("[red]✗ 找不到指定的卡片，請確認 card_id 是否正確[/red]")
            sys.exit(1)
        card_ids  = [c["card_id"] for c in card_objs]
        card_info = [{"card_id": c["card_id"], "card_name": c["card_name"]} for c in card_objs]
        _display_selected(card_info)
    else:
        card_ids, card_info = select_cards_interactive()

    # 建立 Agent
    from agent.payment_agent import PaymentAgent
    agent = PaymentAgent(cards_owned=card_ids, cards_info=card_info)

    # 對話
    chat_loop(agent)


if __name__ == "__main__":
    main()
