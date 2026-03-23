"""
card_feature_scraper.py
-----------------------
從 CTBC 信用卡詳情頁面爬取「卡片特色」tab 資料。

發現：卡片詳情頁面以 iframe 方式嵌入，iframe URL 為：
  https://www.ctbcbank.com/web/content/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index/{cardId}.html
此路徑可直接用 requests 存取（無需登入）。

Mode Direct（推薦，無需登入）：
    直接 requests 存取 /web/content/ 路徑，解析卡片特色 HTML。
    python -m scraper.run card-feature --direct

Mode A（cookie 注入）：
    從瀏覽器匯出 cookies.json，再由 Playwright 注入後爬取。

Mode B（互動模式）：
    Playwright 開啟可見瀏覽器，使用者手動登入後，
    腳本自動爬取所有卡片詳情頁。

執行方式：
    python -m scraper.run card-feature --direct
    python -m scraper.run card-feature --direct --card C_uniopen
    python -m scraper.run card-feature --cookies cookies.json
    python -m scraper.run card-feature --interactive
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_PATH  = PROJECT_ROOT / "data" / "scraped" / "card_features.json"
CARD_LIST_API = "https://www.ctbcbank.com/web/content/twrbo/setting/creditcards.cardlist.json"
CARD_INTRO_BASE = "https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index"
CARD_CONTENT_BASE = "https://www.ctbcbank.com/web/content/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index"

_HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Referer": "https://www.ctbcbank.com/",
}

# ── channel_id 推斷 ───────────────────────────────────────────────────────────

_CHANNEL_PATTERNS = [
    (re.compile(r"便利商店|超商|7-?eleven|711|全家|萊爾富|ok mart|統一超商|統一企業集團", re.I), "convenience_store"),
    (re.compile(r"超市|量販|全聯|家樂福|costco|大潤發|愛買", re.I), "supermarket"),
    (re.compile(r"電商|網購|網路購物|momo|蝦皮|pchome|yahoo|線上", re.I), "ecommerce"),
    (re.compile(r"外送|foodpanda|uber\s*eats", re.I), "food_delivery"),
    (re.compile(r"交通|捷運|公車|台鐵|高鐵|bus|uber(?!\s*eats)", re.I), "transport"),
    (re.compile(r"餐飲|餐廳|飲食|咖啡|早餐|美食|dining", re.I), "dining"),
    (re.compile(r"旅遊|飯店|機票|訂房|航空|agoda|飛機|搭機|航班|哩程|里程|miles?\b|ANA", re.I), "travel"),
    (re.compile(r"娛樂|電影|遊戲|kkbox|spotify|netflix|ktv", re.I), "entertainment"),
    (re.compile(r"加油|中油|台塑|油站", re.I), "gas_station"),
    (re.compile(r"藥妝|藥局|屈臣氏|康是美|watson", re.I), "pharmacy"),
    (re.compile(r"行動支付|line\s*pay|apple\s*pay|google\s*pay|街口|悠遊|icash", re.I), "mobile_payment"),
    (re.compile(r"國外|海外|境外|foreign|實體商店消費.*%|overseas|國際", re.I), "overseas_general"),
    (re.compile(r"一般消費|其他消費|all|general", re.I), "general"),
]


def _infer_channel(label: str) -> str:
    for pattern, channel_id in _CHANNEL_PATTERNS:
        if pattern.search(label):
            return channel_id
    return "general"


def _parse_rate(text: str) -> Optional[float]:
    """從文字中提取第一個百分比數值（0.05 = 5%）。"""
    m = re.search(r"([\d.]+)\s*%", text)
    return float(m.group(1)) / 100.0 if m else None


# ── Direct 模式（無需登入）────────────────────────────────────────────────────

def _fetch_card_ids_from_api() -> list[str]:
    """從官方 cardlist API 取得所有現行卡片的 raw card ID（如 C_uniopen）。"""
    try:
        r = requests.get(CARD_LIST_API, headers=_HTML_HEADERS, timeout=15)
        r.raise_for_status()
        return [
            c["cardId"]
            for c in r.json().get("creditCards", [])
            if c.get("isOnline", False) and c.get("cardId")
        ]
    except Exception as e:
        console.print(f"[red]✗ 無法取得卡片清單：{e}[/red]")
        return []


def _parse_feature_tab(html: str) -> list[dict]:
    """
    解析卡片詳情頁 HTML，提取「卡片特色」tab 的回饋率資料。

    HTML 結構：
      <div class="twrbo-c-tabs">
        <ul class="twrbo-c-tabs__navs">
          <li><a data-tab-target="C_uniopen_Tab2" href="#">卡片特色</a></li>
        </ul>
        <div class="twrbo-c-tabs__content">
          <div id="C_uniopen_Tab2" class="twrbo-c-tabs__panel">...</div>
        </div>
      </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    # 找「卡片特色」tab 的導覽連結
    feature_link = soup.find("a", string=lambda s: s and "卡片特色" in s)
    if not feature_link:
        # 嘗試更寬鬆的比對（含 whitespace）
        for a in soup.find_all("a"):
            if a.get_text(strip=True) == "卡片特色":
                feature_link = a
                break

    tab_content = None
    if feature_link:
        tab_target = feature_link.get("data-tab-target", "")
        if tab_target:
            tab_content = soup.find(id=tab_target)
            if not tab_content:
                tab_content = soup.find(attrs={"data-tab-id": tab_target})

    # 若找不到特定 tab div，fallback 到整個 soup
    if not tab_content:
        tab_content = soup

    # 非回饋率的雜訊關鍵字
    _NOISE_KEYWORDS = (
        "循環年利率", "預借現金", "手續費", "基準日", "違約金",
        "遲繳", "遲付", "利率基準", "上限為15%", "5.97%",
    )

    # 逐行抽取含百分比的文字
    text = tab_content.get_text(separator="\n", strip=True)
    channels: list[dict] = []
    seen: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        # 跳過非回饋率的雜訊行
        if any(kw in line for kw in _NOISE_KEYWORDS):
            continue
        m = re.search(r"([\d.]+)\s*%", line)
        if not m:
            continue
        rate = float(m.group(1)) / 100.0
        if rate <= 0 or rate > 0.5:          # 超出合理回饋範圍
            continue
        key = f"{line[:40]}_{rate}"
        if key in seen:
            continue
        seen.add(key)

        channels.append({
            "channel_id":           _infer_channel(line),
            "cashback_rate":        rate,
            "cashback_type":        "points" if "點" in line else "cash",
            "cashback_description": line[:150],
            "conditions":           "",
            "valid_end":            None,
            "source":               "card_feature_direct",
        })

    return channels


def scrape_direct(raw_card_ids: list[str] | None = None, dry_run: bool = False) -> dict:
    """
    直接透過 /web/content/ CDN 路徑爬取「卡片特色」資料（無需登入）。

    CTBC 卡片詳情頁面是 Angular SPA，實際內容用 iframe 嵌入：
      https://www.ctbcbank.com/web/content/twrbo/zh_tw/cc_index/cc_product/
      cc_introduction_index/{cardId}.html
    此 URL 可直接用 requests 存取（繞過 WAF）。

    Args:
        raw_card_ids: 要爬取的 raw card ID 列表（如 ["C_uniopen"]）；
                      None 則爬取所有現行卡片。
        dry_run:      True 時只印結果，不寫入檔案。

    Returns:
        dict: { processed_card_id: { card_id, raw_card_id, page_url, channels } }
    """
    if not raw_card_ids:
        console.print("[cyan]▶ 取得卡片清單...[/cyan]")
        raw_card_ids = _fetch_card_ids_from_api()
        if not raw_card_ids:
            return {}
        console.print(f"  [green]✓ 共 {len(raw_card_ids)} 張卡片[/green]")

    results: dict = {}
    sess = requests.Session()
    sess.headers.update(_HTML_HEADERS)

    for raw_id in raw_card_ids:
        url = f"{CARD_CONTENT_BASE}/{raw_id}.html"
        console.print(f"  [dim]{raw_id:<25}[/dim]", end="")

        try:
            resp = sess.get(url, timeout=15)
            resp.encoding = "utf-8"

            if resp.status_code != 200:
                console.print(f" [yellow]⚠ HTTP {resp.status_code}[/yellow]")
                continue

            channels = _parse_feature_tab(resp.text)
            processed_id = f"ctbc_{raw_id.lower()}"

            if channels:
                results[processed_id] = {
                    "card_id":     processed_id,
                    "raw_card_id": raw_id,
                    "page_url":    url,
                    "channels":    channels,
                }
                console.print(f" [green]✓ {len(channels)} 筆回饋率[/green]")
            else:
                console.print(f" [dim]（0 筆）[/dim]")

        except Exception as e:
            console.print(f" [red]✗ {e}[/red]")

        time.sleep(0.3)  # 避免對伺服器造成過大壓力

    if not dry_run:
        _save_results(results)

    return results


# ── 頁面解析 ──────────────────────────────────────────────────────────────────

async def _extract_card_feature(page) -> list[dict]:
    """
    從已載入的信用卡詳情頁面，提取「卡片特色」回饋率資料。
    回傳 channels 格式的 list，供直接寫入 ctbc_cards.json。
    """
    channels = []
    seen = set()

    # ── 策略 1：找 twrbc-tabs-collapse 內的表格 ──
    html = await page.content()

    # 解析含有百分比的文字行
    lines = re.findall(r'[^<>\n]{3,100}[\d.]+\s*%[^<>\n]{0,80}', html)
    for line in lines:
        # 去 HTML tag
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if not clean or len(clean) < 4:
            continue
        rate = _parse_rate(clean)
        if rate is None or rate > 0.5:  # 超過 50% 不合理
            continue
        key = f"{clean[:30]}_{rate}"
        if key in seen:
            continue
        seen.add(key)

        channel_id = _infer_channel(clean)
        channels.append({
            "channel_id":          channel_id,
            "cashback_rate":       rate,
            "cashback_type":       "points" if "點" in clean else "cash",
            "cashback_description": clean[:120],
            "conditions":          "",
            "valid_end":           None,
            "source":              "card_feature",
        })

    # ── 策略 2：嘗試點擊「卡片特色」tab ──
    try:
        tab_btn = await page.query_selector('[data-tab-id="feature"], button:has-text("卡片特色"), a:has-text("卡片特色")')
        if tab_btn:
            await tab_btn.click()
            await asyncio.sleep(2)
            html2 = await page.content()
            lines2 = re.findall(r'[^<>\n]{3,100}[\d.]+\s*%[^<>\n]{0,80}', html2)
            for line in lines2:
                clean = re.sub(r'<[^>]+>', '', line).strip()
                if not clean:
                    continue
                rate = _parse_rate(clean)
                if rate is None or rate > 0.5:
                    continue
                key = f"{clean[:30]}_{rate}"
                if key in seen:
                    continue
                seen.add(key)
                channel_id = _infer_channel(clean)
                channels.append({
                    "channel_id":          channel_id,
                    "cashback_rate":       rate,
                    "cashback_type":       "points" if "點" in clean else "cash",
                    "cashback_description": clean[:120],
                    "conditions":          "",
                    "valid_end":           None,
                    "source":              "card_feature_tab",
                })
    except Exception:
        pass

    return channels


# ── 主爬取流程 ────────────────────────────────────────────────────────────────

async def scrape_with_cookies(cookies_path: str, card_ids: list[str] | None = None):
    """使用匯出的 cookie 進行認證並爬取。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[red]✗ 請先安裝 playwright：pip install playwright && playwright install chromium[/red]")
        return

    cookies_data = json.loads(Path(cookies_path).read_text(encoding="utf-8"))

    # 取得所有卡片 card_id 列表
    if not card_ids:
        import requests
        r = requests.get(CARD_LIST_API, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        card_ids = [c["cardId"] for c in r.json().get("creditCards", [])]

    results: dict = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        await context.add_cookies(cookies_data)

        page = await context.new_page()

        for card_id in card_ids:
            url = f"{CARD_INTRO_BASE}/{card_id}.html"
            console.print(f"  [dim]{card_id:<25}[/dim] → {url[-50:]}")

            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(2)
                # 若頁面還是 IB 錯誤頁，跳過
                body_text = await page.inner_text("body")
                if "APP-1053" in body_text or "系統忙碌" in body_text:
                    console.print(f"    [yellow]⚠ IB portal 錯誤，請確認 cookie 已登入狀態[/yellow]")
                    continue

                channels = await _extract_card_feature(page)
                if channels:
                    results[card_id] = {
                        "card_id":   card_id,
                        "page_url":  url,
                        "channels":  channels,
                    }
                    console.print(f"    [green]✓[/green] 擷取 {len(channels)} 筆回饋率")
                else:
                    console.print(f"    [yellow]⚠ 未找到回饋率資料[/yellow]")

            except Exception as e:
                console.print(f"    [red]✗ {e}[/red]")

            time.sleep(0.5)

        await browser.close()

    _save_results(results)


async def scrape_interactive(card_id: str | None = None):
    """開啟可見瀏覽器，讓使用者手動登入後自動爬取。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[red]✗ 請先安裝 playwright：pip install playwright && playwright install chromium[/red]")
        return

    import requests
    r = requests.get(CARD_LIST_API, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    all_cards = [c["cardId"] for c in r.json().get("creditCards", [])]
    card_ids = [card_id] if card_id else all_cards

    results: dict = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # 先讓使用者登入
        console.print("\n[bold cyan]互動模式：請在開啟的瀏覽器中登入中信帳號[/bold cyan]")
        console.print("[dim]登入後請勿關閉瀏覽器，程式將自動繼續[/dim]")
        await page.goto("https://www.ctbcbank.com/twrbo/zh_tw/login_index.html")

        # 等待登入完成（偵測到登入後的導向或頁面變化）
        console.print("[dim]等待登入...（最多 120 秒）[/dim]")
        try:
            await page.wait_for_url(
                lambda url: "/login_index" not in url and "ctbcbank.com" in url,
                timeout=120000,
            )
        except Exception:
            console.print("[yellow]⚠ 登入等待超時，嘗試繼續爬取[/yellow]")

        await asyncio.sleep(2)
        console.print("[green]✓ 開始爬取卡片特色資料...[/green]")

        for cid in card_ids:
            url = f"{CARD_INTRO_BASE}/{cid}.html"
            console.print(f"  [dim]{cid:<25}[/dim]", end="")
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(2)

                body_text = await page.inner_text("body")
                if "APP-1053" in body_text or "系統忙碌" in body_text:
                    console.print(f" [yellow]⚠ 需登入[/yellow]")
                    continue

                channels = await _extract_card_feature(page)
                if channels:
                    results[cid] = {"card_id": cid, "page_url": url, "channels": channels}
                    console.print(f" [green]✓ {len(channels)} 筆[/green]")
                else:
                    console.print(f" [dim]0 筆[/dim]")
            except Exception as e:
                console.print(f" [red]✗ {e}[/red]")

            await asyncio.sleep(0.5)

        await browser.close()

    _save_results(results)


def _save_results(results: dict):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "version":      "1.0",
        "last_updated": __import__("datetime").date.today().isoformat(),
        "source":       "CTBC IB Portal 卡片特色",
        "cards":        results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"\n[bold green]✓ 已儲存 {len(results)} 張卡片的特色資料 → {OUTPUT_PATH}[/bold green]")


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="從 CTBC IB Portal 爬取信用卡特色（需已登入）"
    )
    parser.add_argument("--cookies",     help="匯出的 cookies JSON 檔路徑")
    parser.add_argument("--interactive", action="store_true", help="互動模式（開啟可見瀏覽器）")
    parser.add_argument("--card",        help="只爬取指定卡片（如 C_uniopen）")
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(scrape_interactive(card_id=args.card))
    elif args.cookies:
        card_ids = [args.card] if args.card else None
        asyncio.run(scrape_with_cookies(args.cookies, card_ids))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
