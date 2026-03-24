# 💳 CTBC 信用卡支付建議系統

中信銀行（CTBC）信用卡支付建議服務，包含兩種免費使用方式：
- **Gradio 網頁 Demo**：視覺化介面，勾選持有信用卡即可查詢
- **CLI 對話 Agent**：多輪自然語言對話

資料版本：2026-03-08（47 張中信現行信用卡）

---

## 安裝

### 需求

- Python 3.10 以上
- [Groq API Key](https://console.groq.com)（免費申請）

### 安裝步驟

**Step 1：安裝套件**

```bash
pip install ctbc_payment_advisor-1.0.0-py3-none-any.whl
```

**Step 2：建立環境變數檔**

在任意目錄建立 `.env` 檔案，填入你的 Groq API Key：

```
GROQ_API_KEY=your_groq_api_key_here
```

> 到 https://console.groq.com 免費申請，額度足夠日常使用。

---

## 使用方式

安裝完成後，有兩個免費指令可以使用：

### 方式一：Gradio 網頁 Demo（推薦）

```bash
ctbc-demo
```

瀏覽器會自動開啟，在網頁上勾選持有的信用卡、輸入消費金額與情境，即可獲得刷卡建議。

- 左側：勾選持有的信用卡（支援全選/清除）
- 右側：選擇偏好回饋種類（現金/點數/哩程等）、輸入金額與消費情境
- 結果：自動顯示最優刷卡建議與持卡比較表

---

### 方式二：CLI 多輪對話 Agent

```bash
ctbc-chat
```

啟動後以數字選擇持有的信用卡，接著輸入自然語言問題：

```
> 我今天要去全聯買菜花了 1500 元，哪張卡最划算？
> 下週要出國去日本，海外消費用哪張？
> 我的卡最近有哪些快到期的優惠？
```

輸入 `q` 離開，`r` 重置對話記憶。

---

## 功能說明

### 支援的消費通路

輸入時支援模糊輸入，系統自動對應到正確通路：

| 輸入範例 | 對應通路 |
|---------|---------|
| `7-11`、`小7`、`全家` | 超商 |
| `全聯`、`家樂福`、`COSTCO` | 超市／量販 |
| `蝦皮`、`momo`、`網購` | 電商 |
| `foodpanda`、`Uber Eats`、`外送` | 外送 |
| `捷運`、`高鐵`、`Uber` | 交通 |
| `麥當勞`、`星巴克`、`餐廳` | 餐飲 |
| `機票`、`飯店`、`出國`、`哩程` | 旅遊 |
| `Netflix`、`KTV`、`電影` | 娛樂 |
| `中油`、`加油` | 加油站 |
| `屈臣氏`、`康是美`、`藥局` | 藥妝 |
| `LINE Pay`、`Apple Pay`、`街口` | 行動支付 |
| `日本`、`韓國`、`海外`、`國外` | 海外消費（自動辨識）|

### 回饋種類顯示

系統自動區分不同回饋種類，並以對應單位顯示：
- 現金回饋 → NT$ 金額
- LINE Points / OPENPOINT → 點數
- 中信紅利點數 → 紅利點
- 航空哩程 → % 加碼（依航空公司計算）

### 海外消費自動辨識

輸入情境中包含國家名稱（日本、韓國、泰國...）或海外關鍵字時，系統會自動：
1. 優先顯示各卡的海外消費回饋率
2. 加入提醒：「國外消費可能有限定條件，詳情請洽中信官網」

---

## 常見問題

**Q：安裝後找不到 `ctbc-demo` / `ctbc-chat` 指令？**

```bash
# macOS / Linux：確認 pip bin 在 PATH 中
export PATH="$HOME/.local/bin:$PATH"

# 或直接用 Python 執行
python -m gradio_app    # Gradio Demo
python -m main          # CLI Agent
```

**Q：需要自己的 Groq API Key 嗎？**

是的，Key 是必要的（用於 CLI Agent 對話與海外消費辨識）。
到 https://console.groq.com 免費申請，沒有信用卡要求。

**Q：資料是最新的嗎？**

套件內建資料版本為 **2026-03-08**，涵蓋 47 張中信現行信用卡。

---

## 技術資訊

- **資料來源**：中信銀行官方 JSON API + 卡片特色頁直接爬取
- **LLM**：Groq API（`llama-3.3-70b-versatile` 主模型，`llama-3.1-8b-instant` 海外辨識）
- **MCP 框架**：FastMCP（Python mcp SDK）
- **前端**：Gradio 4.x

---

## Contributors

中信銀行實習專案團隊成員：

| GitHub | 角色 |
|--------|------|
| [@Gene-Liu-portfolio](https://github.com/Gene-Liu-portfolio) | 專案負責人 |
| [@LarryinMexico](https://github.com/LarryinMexico) | 實習生 |
| [@Lyyyy17](https://github.com/Lyyyy17) | 實習生 |
| [@rockeywang404](https://github.com/rockeywang404) | 實習生 |
