# CTBC & Fubon Credit Card Payment Advisor

**中國信託 × 台北富邦 信用卡支付建議系統**

基於 **Agent × MCP（Model Context Protocol）** 架構的智慧刷卡建議服務。透過自然語言輸入消費情境，從使用者持有的 **13 張熱門信用卡**（中信 6 + 富邦 7）中推薦最佳刷卡選擇。

> 資料版本：2026-04-22 | 架構版本：v7.0

---

## Features

- **情境推薦** — 輸入「去全聯買菜 1500 元」，自動推薦最優卡與預估回饋
- **多通路解析** — 一次輸入可辨識多個通路（如全聯 + foodpanda），分別推薦
- **海外消費辨識** — 關鍵字 + LLM 雙層偵測，自動查詢海外通路回饋率
- **持卡比較** — 全通路一覽表，標記每個通路的最優卡
- **回饋種類區分** — 現金 / LINE Points / OPENPOINT / 哩程 / 紅利點數
- **偏好篩選** — Gradio 介面支援勾選偏好回饋種類，結果優先排序
- **優惠提醒** — 查看目前有效的優惠活動，提醒即將到期的優惠
- **多輪對話** — CLI Agent 記憶上下文，支援連續追問

---

## Supported Cards（13 張）

**中信銀行（CTBC）**

| Card ID | 卡名 |
|---------|------|
| `ctbc_c_hanshin` | 漢神聯名卡 |
| `ctbc_c_uniopen` | uniopen聯名卡 |
| `ctbc_c_cs` | 遠東SOGO聯名卡 |
| `ctbc_c_linepay` | LINE Pay信用卡 |
| `ctbc_c_cal` | 中華航空聯名卡 |
| `ctbc_c_cpc` | 中油聯名卡 |

**台北富邦銀行（Fubon）**

| Card ID | 卡名 |
|---------|------|
| `fubon_c_j` | 富邦J卡 |
| `fubon_c_j_travel` | 富邦J Travel卡 |
| `fubon_c_costco` | 富邦Costco聯名卡 |
| `fubon_c_diamond` | 富邦鑽保卡 |
| `fubon_c_momo` | 富邦momo卡 |
| `fubon_b_lifestyle` | 富邦富利生活卡 |
| `fubon_c_twm` | 台灣大哥大Open Possible聯名卡 |

---

## Architecture

```
 User Interface          Agent Layer              MCP Server             Data Layer
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐
│ Gradio Web   │───>│                  │    │  FastMCP Server  │    │ merged_cards   │
│ gradio_app.py│    │  PaymentAgent    │    │  (7 Tools)       │    │   .json        │
│              │    │  Groq LLM        │───>│                  │───>│ (build-time    │
│ CLI Agent    │───>│  llama-3.3-70b   │    │  search          │    │  3-layer merge)│
│ main.py      │    │                  │    │  recommend       │    │                │
│              │    │  mcp_bridge.py   │    │  compare         │    │ promotions     │
│              │    │  (dynamic tool   │    │  promotions      │    │   .json        │
│              │    │   discovery)     │    │  card_details    │    │                │
└──────────────┘    └──────────────────┘    └──────────────────┘    └────────────────┘
                         │                          │
                    cards_owned               deals → channels
                    auto-injection            (2-layer priority)
```

**Key Design Decisions:**

- **Build-time merge** — 三層資料（API + card_features + microsite_deals）在 build time 合併為 `merged_cards.json`，runtime 只需查兩層
- **Dynamic tool discovery** — Agent 啟動時透過 MCP `tools/list` 動態發現工具，不硬編碼 Schema
- **cards_owned injection** — 持卡清單由 Agent 自動注入，LLM 無法偽造或推薦未持有的卡
- **Gradio 解耦** — 前端自帶通路解析邏輯，不 import MCP Server 內部模組

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Groq API Key](https://console.groq.com)（免費申請）

### Installation

```bash
git clone https://github.com/Gene-Liu-portfolio/ctbc-payment-advisor.git
cd ctbc-payment-advisor

python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### Usage

**Gradio Web Demo（推薦）**

```bash
python gradio_app.py
```

勾選持有的信用卡 → 選擇偏好回饋種類 → 輸入消費金額與情境 → 查詢最優刷卡

**CLI Agent 多輪對話**

```bash
python main.py
```

```
> 我今天要去全聯買菜花了 1500 元，哪張卡最划算？
> 下週要去日本旅遊，海外消費用哪張？
> 我的卡最近有哪些快到期的優惠？
```

輸入 `q` 離開，`r` 重置對話記憶。

**MCP Server（獨立啟動）**

```bash
# HTTP 模式（本地測試 / 部署）
python -m mcp_server.http_app

# stdio 模式（Claude Desktop 整合）
python -m mcp_server.server
```

---

## Supported Channels

系統支援模糊輸入，自動對應到 17 種標準通路：

| 輸入範例 | 對應通路 |
|---------|---------|
| `7-11`、`小7`、`全家` | 超商 |
| `全聯`、`家樂福`、`COSTCO` | 超市／量販 |
| `蝦皮`、`momo`、`網購` | 電商 |
| `foodpanda`、`Uber Eats` | 外送 |
| `捷運`、`高鐵`、`Uber` | 交通 |
| `麥當勞`、`星巴克` | 餐飲 |
| `機票`、`飯店`、`出國` | 旅遊 |
| `中油`、`加油` | 加油站 |
| `屈臣氏`、`康是美` | 藥妝 |
| `LINE Pay`、`Apple Pay` | 行動支付 |
| `日本`、`韓國`、`海外` | 海外消費（自動辨識）|

---

## Data Pipeline

```bash
# 1. 爬取中信基礎資料（6 張熱門卡 + 優惠活動）
python -m scraper.run full

# 2. 爬取卡片特色頁回饋率
python -m scraper.run card-feature --direct

# 3. Build-time 三層合併
python -m scraper.merge

# 4. 驗證
python -m pytest tests/test_mcp_tools.py -v
```

### Merge Strategy（`scraper/merge.py`）

```
ctbc_cards.json + fubon_cards.json     → 基礎卡片（13 張）
    + card_features.json               → channels 覆蓋（同 channel_id 取 card_features 優先）
    + microsite_deals.json             → deals 獨立陣列（過濾已過期）
    → merged_cards.json (v2.0)
```

---

## Testing

```bash
# 單元測試（103 tests, 0.06s, 不需 LLM API）
python -m pytest tests/test_mcp_tools.py -v

# User Story 端對端測試（需 Groq API + MCP Server）
python -m tests.test_user_stories
```

### Test Coverage

| 類別 | 數量 | 涵蓋 |
|------|------|------|
| Calculator | 12 | 回饋計算、日期判斷 |
| DataLoader | 12 | 資料載入、查詢、fallback |
| SearchByChannel | 12 | 通路查詢、排序、結構 |
| RecommendPayment | 13 | 金額抽取、通路識別、情境推薦 |
| CompareCards | 7 | 比較邏輯、is_best 標記 |
| Promotions | 5 | 優惠查詢、卡片詳情 |
| Accuracy | 8 | 具體回饋率驗證 |
| EdgeCases | 8 | 空值、特殊字元、邊界條件 |
| ChannelMapping | 18 | 18 種通路映射正確性 |

---

## Project Structure

```
ctbc-payment-advisor/
├── main.py                    # CLI Agent 入口
├── gradio_app.py              # Gradio Web Demo（解耦設計）
├── CTBC_Project_Overview.md   # 完整專案架構文件
│
├── agent/
│   ├── payment_agent.py       # Groq LLM + Tool Calling
│   ├── mcp_bridge.py          # Dynamic tool discovery + HTTP bridge
│   └── prompts.py             # Dynamic system prompt
│
├── mcp_server/
│   ├── server.py              # FastMCP Server (7 tools + 2 resources)
│   ├── http_app.py            # HTTP deployment (uvicorn + Bearer token)
│   ├── tools/
│   │   ├── search.py          # search_by_channel (deals → channels)
│   │   ├── recommend.py       # recommend_payment (scenario parsing)
│   │   ├── compare.py         # compare_cards (multi-card comparison)
│   │   └── promotions.py      # get_promotions + get_card_details
│   └── utils/
│       ├── data_loader.py     # Unified data access (merged_cards.json)
│       ├── calculator.py      # Cashback calculation
│       └── channel_mapper.py  # Channel name normalization
│
├── scraper/
│   ├── ctbc_scraper.py        # CTBC official JSON API
│   ├── card_feature_scraper.py # Card feature page scraping
│   ├── microsite_scraper.py   # Microsite deals scraping
│   ├── merge.py               # Build-time 3-layer merge
│   └── channel_mapper.py      # Channel mapping (source of truth)
│
├── data/
│   ├── processed/
│   │   ├── merged_cards.json  # ★ Unified data source (build-time merged)
│   │   ├── promotions.json    # 24 promotions (CTBC 19 + Fubon 5)
│   │   └── channels.json      # Channel taxonomy
│   └── scraped/               # Raw scraped data (input for merge)
│
└── tests/
    ├── test_mcp_tools.py      # 103 unit tests (deterministic)
    └── test_user_stories.py   # 7 E2E scenarios (LLM-based)
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Groq API（`llama-3.3-70b-versatile` + `llama-3.1-8b-instant`） |
| MCP Framework | FastMCP (Python mcp SDK) |
| Transport | Streamable HTTP (SSE) |
| Frontend | Gradio 4.x |
| Data | JSON files (build-time merged) |
| Testing | pytest (103 deterministic tests) |

---

## FAQ

**Q: 需要 Groq API Key 嗎？**

CLI Agent 和海外消費辨識需要。到 https://console.groq.com 免費申請，無需信用卡。
Gradio Demo 的通路查詢不需要 LLM（直接呼叫 MCP Server）。

**Q: 富邦卡的資料來源？**

富邦銀行無公開 JSON API，資料為手動整理。需定期人工更新。

**Q: 如何新增卡片或更新資料？**

1. 修改 `data/processed/` 中的原始 JSON
2. 執行 `python -m scraper.merge` 重新合併
3. 重啟 MCP Server

---

## Contributors

中信銀行實習專案團隊：

| GitHub | 角色 |
|--------|------|
| [@Gene-Liu-portfolio](https://github.com/Gene-Liu-portfolio) | 實習生 |
| [@LarryinMexico](https://github.com/LarryinMexico) | 實習生 |
| [@Lyyyy17](https://github.com/Lyyyy17) | 實習生 |
| [@rockeywang404](https://github.com/rockeywang404) | 實習生 |
