"""
run.py
------
Phase 1+2 的 CLI 入口點。

用法：
    python -m scraper.run --dump-html          # 先 dump HTML，確認 selector
    python -m scraper.run --full               # 完整爬取 + 清理 → processed/
    python -m scraper.run --full --dry-run     # 只看結果，不寫檔案
    python -m scraper.run --promotions-only    # 只更新限時活動
    python -m scraper.run --validate           # 驗證現有 processed 資料
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

PROJECT_ROOT  = Path(__file__).parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR       = PROJECT_ROOT / "data" / "raw"


def cmd_dump_html(args):
    """只 dump rendered HTML，不解析，用於第一次偵測 selector。"""
    from .ctbc_scraper import dump_debug_html
    console.print("\n[bold cyan]═══ Debug HTML Dump ═══[/bold cyan]")
    asyncio.run(dump_debug_html())


def cmd_full(args):
    """完整爬取流程：爬取 → 清理 → 輸出。"""
    from .ctbc_scraper import run_full_scrape
    from .data_cleaner import clean_and_export, diff_summary

    output_path = PROCESSED_DIR / "ctbc_cards.json"
    promo_path  = PROCESSED_DIR / "promotions.json"

    console.print("\n[bold cyan]═══ Phase 1：資料爬取 ═══[/bold cyan]")
    start = datetime.now()

    raw_cards, promotions = asyncio.run(
        run_full_scrape(
            dump_html=args.dump_html,
            promotions_only=False,
        )
    )

    console.print(f"\n[bold cyan]═══ Phase 2：資料清理 ═══[/bold cyan]")

    # 計算 diff
    diff = diff_summary(output_path, raw_cards)

    # 清理並輸出
    result = clean_and_export(raw_cards, output_path, dry_run=args.dry_run)

    # 輸出 promotions
    if not args.dry_run:
        promo_path.write_text(
            json.dumps(promotions, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 顯示摘要
    elapsed = (datetime.now() - start).seconds
    _print_summary(result, diff, promotions, elapsed)


def cmd_promotions_only(args):
    """只重新爬取限時活動，不動卡片資料。"""
    from .ctbc_scraper import run_full_scrape

    promo_path = PROCESSED_DIR / "promotions.json"
    console.print("\n[bold cyan]═══ 更新限時活動 ═══[/bold cyan]")

    _, promotions = asyncio.run(
        run_full_scrape(promotions_only=True)
    )

    if not args.dry_run:
        promo_path.write_text(
            json.dumps(promotions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]✓ 已更新 {len(promotions)} 項活動 → {promo_path}[/green]")
    else:
        console.print(f"[cyan][dry-run] 找到 {len(promotions)} 項活動（未寫入）[/cyan]")


def cmd_load_seed(args):
    """
    將種子資料複製到 processed/ctbc_cards.json，讓 MCP/Agent 可以立刻使用。
    種子資料位於 data/seed/ctbc_cards_seed.json。
    """
    from .data_cleaner import validate_card

    seed_path = PROJECT_ROOT / "data" / "seed" / "ctbc_cards_seed.json"
    output_path = PROCESSED_DIR / "ctbc_cards.json"

    if not seed_path.exists():
        console.print(f"[red]✗ 找不到種子資料：{seed_path}[/red]")
        return

    data = json.loads(seed_path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])

    # 驗證每張卡
    ok, warn = 0, 0
    for card in cards:
        errs = validate_card(card)
        if errs:
            console.print(f"[yellow]⚠ {card['card_name']}: {errs}[/yellow]")
            warn += 1
        else:
            ok += 1

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    console.print(f"\n[bold green]✓ 種子資料已載入 → {output_path}[/bold green]")
    console.print(f"  共 {len(cards)} 張卡片（{ok} 通過驗證，{warn} 有警告）")
    console.print(
        "\n[yellow]⚠ 提醒：種子資料為初始值，請至中信官網逐一驗證後更新 last_verified 欄位[/yellow]"
    )


def cmd_microsite(args):
    """爬取信用卡微型網站的精確促銷優惠資料。"""
    from .microsite_scraper import run_microsite_scrape
    run_microsite_scrape(dry_run=args.dry_run)


def cmd_card_feature(args):
    """
    爬取「卡片特色」tab 資料。

    方式 A（推薦，無需登入）：
      --direct：直接存取 /web/content/ CDN，不需任何帳號
    方式 B：
      --interactive：Playwright 可見瀏覽器，手動登入後自動爬取
    方式 C：
      --cookies <file>：注入從瀏覽器匯出的 cookies.json 自動爬取
    """
    import asyncio
    from .card_feature_scraper import scrape_direct, scrape_interactive, scrape_with_cookies

    if args.direct:
        console.print("\n[bold cyan]═══ 卡片特色爬取（Direct 模式，無需登入）═══[/bold cyan]")
        raw_ids = [args.card] if args.card else None
        scrape_direct(raw_card_ids=raw_ids, dry_run=args.dry_run)
    elif args.interactive:
        asyncio.run(scrape_interactive(card_id=args.card))
    elif args.cookies:
        card_ids = [args.card] if args.card else None
        asyncio.run(scrape_with_cookies(args.cookies, card_ids))
    else:
        console.print("[yellow]請指定爬取方式：[/yellow]")
        console.print()
        console.print("[bold green]方式 A（推薦，無需登入）[/bold green]")
        console.print("  python -m scraper.run card-feature --direct")
        console.print("  python -m scraper.run card-feature --direct --card C_uniopen")
        console.print()
        console.print("[bold]方式 B：互動模式（需手動登入）[/bold]")
        console.print("  python -m scraper.run card-feature --interactive")
        console.print()
        console.print("[bold]方式 C：Cookie 注入[/bold]")
        console.print("  1. 在已登入的 Chrome 安裝 'Cookie-Editor' Extension")
        console.print("  2. 匯出 ctbcbank.com 的 cookies 為 JSON")
        console.print("  3. python -m scraper.run card-feature --cookies cookies.json")


def cmd_validate(args):
    """驗證現有 processed 資料是否符合 schema。"""
    from .data_cleaner import validate_card

    cards_path = PROCESSED_DIR / "ctbc_cards.json"
    if not cards_path.exists():
        console.print(f"[red]✗ 找不到 {cards_path}，請先執行 --full[/red]")
        return

    data = json.loads(cards_path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])

    table = Table(title="Schema 驗證結果", show_lines=True)
    table.add_column("卡片名稱", style="cyan")
    table.add_column("card_id", style="dim")
    table.add_column("狀態", justify="center")
    table.add_column("錯誤訊息")

    error_count = 0
    for card in cards:
        errs = validate_card(card)
        if errs:
            error_count += 1
            table.add_row(
                card.get("card_name", "?"),
                card.get("card_id", "?"),
                "[red]✗[/red]",
                "\n".join(errs[:2]),
            )
        else:
            table.add_row(
                card.get("card_name", "?"),
                card.get("card_id", "?"),
                "[green]✓[/green]",
                "",
            )

    console.print(table)
    console.print(
        f"\n共 {len(cards)} 張卡片，"
        f"[green]{len(cards) - error_count} 張通過[/green]，"
        f"[red]{error_count} 張有問題[/red]"
    )


def _print_summary(result: dict, diff: dict, promotions: list, elapsed: int):
    """顯示執行摘要。"""
    console.print("\n[bold green]═══ 執行摘要 ═══[/bold green]")

    t = Table(show_header=False, box=None)
    t.add_column(style="bold")
    t.add_column()
    t.add_row("卡片總數",      str(result.get("card_count", 0)))
    t.add_row("限時活動",      str(len(promotions)))
    t.add_row("新增優惠",      f"[green]+{len(diff.get('added', []))}[/green]")
    t.add_row("修改優惠",      f"[yellow]~{len(diff.get('modified', []))}[/yellow]")
    t.add_row("移除舊優惠",    f"[red]-{len(diff.get('removed', []))}[/red]")
    t.add_row("最後更新",      result.get("last_updated", ""))
    t.add_row("耗時",          f"{elapsed} 秒")
    console.print(t)


def main():
    parser = argparse.ArgumentParser(
        prog="python -m scraper.run",
        description="CTBC 信用卡資料爬取與清理工具",
    )
    sub = parser.add_subparsers(dest="command")

    # -- dump-html
    p_dump = sub.add_parser("dump-html", help="儲存 rendered HTML 供分析（首次使用）")
    p_dump.set_defaults(func=cmd_dump_html)

    # -- full
    p_full = sub.add_parser("full", help="完整爬取 + 清理 → processed/")
    p_full.add_argument("--dry-run", action="store_true", help="不寫入 processed/，僅顯示結果")
    p_full.add_argument("--dump-html", action="store_true", help="同時儲存 debug HTML")
    p_full.set_defaults(func=cmd_full)

    # -- promotions-only
    p_promo = sub.add_parser("promotions-only", help="只更新限時活動")
    p_promo.add_argument("--dry-run", action="store_true")
    p_promo.set_defaults(func=cmd_promotions_only)

    # -- load-seed
    p_seed = sub.add_parser("load-seed", help="載入種子資料到 processed/（開發用）")
    p_seed.set_defaults(func=cmd_load_seed)

    # -- validate
    p_val = sub.add_parser("validate", help="驗證現有 processed 資料")
    p_val.set_defaults(func=cmd_validate)

    # -- microsite
    p_ms = sub.add_parser("microsite", help="爬取信用卡微型網站精確促銷優惠")
    p_ms.add_argument("--dry-run", action="store_true", help="不寫入檔案，僅顯示結果")
    p_ms.set_defaults(func=cmd_microsite)

    # -- card-feature
    p_cf = sub.add_parser("card-feature", help="爬取卡片特色 tab（支援無登入 Direct 模式）")
    p_cf.add_argument("--direct",      action="store_true", help="直接存取 CDN（無需登入，推薦）")
    p_cf.add_argument("--interactive", action="store_true", help="開啟可見瀏覽器，手動登入後自動爬取")
    p_cf.add_argument("--cookies",     help="使用匯出的 cookies.json 自動爬取")
    p_cf.add_argument("--card",        help="只爬取指定卡片 raw ID（如 C_uniopen）")
    p_cf.add_argument("--dry-run",     action="store_true", help="只顯示結果，不寫入 scraped/")
    p_cf.set_defaults(func=cmd_card_feature)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
