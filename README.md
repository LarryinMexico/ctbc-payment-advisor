# 💳 CTBC 信用卡支付建議系統

中信銀行（CTBC）信用卡支付建議服務，包含三種使用方式：
- **Gradio 網頁 Demo**：本地視覺化介面，勾選持卡後查詢
- **CLI 對話 Agent**：本地多輪自然語言對話
- **MCP Server**：可本地 `stdio` 使用，也可部署成遠端 `Streamable HTTP` 給 Cursor 等 MCP client 連線

資料版本：2026-03-17

---

## 開發環境

### 需求

- Python 3.10 以上
- [Groq API Key](https://console.groq.com)

### 本地安裝

建議直接從原始碼安裝：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip setuptools wheel
python3 -m pip install -e .
```

建立 `.env`：

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

`.env.example` 僅作為範本，不要填入真實金鑰。

---

## 使用方式

### 1. Gradio Demo

```bash
ctbc-demo
```

或：

```bash
python3 gradio_app.py
```

### 2. CLI Agent

```bash
ctbc-chat
```

或：

```bash
python3 main.py
```

### 3. MCP Server

#### 本地 `stdio` 模式

```bash
ctbc-mcp
```

或：

```bash
python3 -m mcp_server.server
```

#### 本地 / 遠端 `Streamable HTTP` 模式

```bash
ctbc-mcp-http
```

或：

```bash
python3 -m mcp_server.http_app
```

預設會提供：
- `GET /`
- `GET /health`
- `POST /mcp`

本地啟動後可看到：

```text
http://0.0.0.0:8000
```

實際 MCP endpoint 是：

```text
http://localhost:8000/mcp
```

---

## Cursor 連線

### 本地測試

如果 Cursor 與 MCP server 在同一台機器：

```json
{
  "mcpServers": {
    "ctbc-payment-advisor-local-http": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### 遠端 Render 測試

```json
{
  "mcpServers": {
    "ctbc-payment-advisor-remote": {
      "url": "https://your-service-name.onrender.com/mcp"
    }
  }
}
```

如果有啟用 token 保護：

```json
{
  "mcpServers": {
    "ctbc-payment-advisor-remote": {
      "url": "https://your-service-name.onrender.com/mcp",
      "headers": {
        "Authorization": "Bearer ${env:CTBC_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

注意：
- URL 必須指到 `/mcp`，不能只填根網址
- 根網址 `/` 只會回 service metadata，不是 MCP protocol endpoint

---

## Render 部署

本專案可直接部署成 Python Web Service。

### Render 設定

- Runtime：`Python`
- Build Command：

```bash
python3 -m pip install -U pip setuptools wheel && python3 -m pip install -e .
```

- Start Command：

```bash
python3 -m mcp_server.http_app
```

- Health Check Path：

```text
/health
```

### 建議環境變數

```env
PYTHONUNBUFFERED=1
MCP_AUTH_TOKEN=your_long_random_token
```

若要自訂 host / port，也可設定：

```env
HOST=0.0.0.0
PORT=8000
```

部署完成後：
- 首頁：`https://your-service-name.onrender.com/`
- 健康檢查：`https://your-service-name.onrender.com/health`
- MCP endpoint：`https://your-service-name.onrender.com/mcp`

---

## MCP Tools

目前提供 7 個 tools：

- `search_by_channel`
- `recommend_payment`
- `compare_cards`
- `get_promotions`
- `get_card_details`
- `list_all_cards`
- `reload_data`

Resources：

- `card://ctbc/{card_id}`
- `channels://ctbc/all`

---

## 驗證記錄

### Stage 1：HTTP MCP 遠端化驗證

驗證日期：2026-04-01

已完成：
- 本地 `Streamable HTTP` MCP server 啟動成功
- `/health` 回傳 `200 ok`
- Cursor 可透過本地 HTTP endpoint 連線並列出 tools
- Render 部署成功
- Cursor 可透過 Render 遠端 `/mcp` endpoint 連線

### 已驗證範例

#### `search_by_channel`

輸入：

```json
{
  "channel": "全聯",
  "cards_owned": ["fubon_b_lifestyle", "fubon_c_momo"],
  "amount": 3600,
  "top_k": 2
}
```

預期重點：
- 第 1 名：`富邦富利生活卡`
- 預估回饋：`72.0`
- 第 2 名：`富邦momo卡`
- 預估回饋：`36.0`

#### `recommend_payment`

輸入：

```json
{
  "scenario": "今天要去全聯跟 momo 購物網，各花 2000 元",
  "cards_owned": ["fubon_b_lifestyle", "fubon_c_momo"]
}
```

預期重點：
- 解析出 `supermarket`、`ecommerce`
- 全聯最佳卡：`富邦富利生活卡`
- momo 最佳卡：`富邦momo卡`

#### `compare_cards`

輸入：

```json
{
  "cards_owned": ["fubon_b_lifestyle", "ctbc_c_linepay"],
  "channel": "全聯",
  "amount": 2000
}
```

預期重點：
- `channel_filter = supermarket`
- `富邦富利生活卡` 勝出
- `富邦富利生活卡 estimated_cashback = 40.0`
- `LINE Pay信用卡 estimated_cashback = 20.0`

---

## 功能說明

### 支援的消費通路

| 輸入範例 | 對應通路 |
|---------|---------|
| `7-11`、`小7`、`全家` | 超商 |
| `全聯`、`家樂福`、`COSTCO` | 超市／量販 |
| `蝦皮`、`momo`、`網購` | 電商 |
| `foodpanda`、`Uber Eats`、`外送` | 外送 |
| `捷運`、`高鐵`、`Uber` | 交通 |
| `麥當勞`、`星巴克`、`餐廳` | 餐飲 |
| `機票`、`飯店`、`出國` | 旅遊 |
| `Netflix`、`KTV`、`電影` | 娛樂 |
| `中油`、`加油` | 加油站 |
| `屈臣氏`、`康是美`、`藥局` | 藥妝 |
| `LINE Pay`、`Apple Pay`、`街口` | 行動支付 |
| `日本`、`韓國`、`海外`、`國外` | 海外消費 |

### 回饋顯示

- 現金回饋 → NT$ 金額
- LINE Points / OPENPOINT → 點數
- 中信紅利點數 → 紅利點
- 航空哩程 → % 加碼

---

## 技術資訊

- **資料來源**：中信銀行官方 JSON API + 卡片特色頁資料
- **LLM**：Groq API
- **MCP 框架**：FastMCP
- **HTTP Server**：Uvicorn / Starlette
- **前端**：Gradio 4.x

---

## Contributors

中信銀行實習專案團隊成員：

| GitHub | 角色 |
|--------|------|
| [@Gene-Liu-portfolio](https://github.com/Gene-Liu-portfolio) | 實習生 |
| [@LarryinMexico](https://github.com/LarryinMexico) | 實習生 |
| [@Lyyyy17](https://github.com/Lyyyy17) | 實習生 |
| [@rockeywang404](https://github.com/rockeywang404) | 實習生 |
