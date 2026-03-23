/**
 * browser_extractor.js
 * --------------------
 * 在瀏覽器 DevTools Console 中執行此腳本，
 * 可從 CTBC 信用卡詳情頁面（卡片特色 / 專屬優惠 tab）
 * 提取優惠資料並輸出成 JSON。
 *
 * 使用步驟：
 *  1. 登入中信網路銀行
 *  2. 進入任一信用卡介紹頁（如 C_uniopen 的 卡片特色 tab）
 *  3. 打開 DevTools → Console
 *  4. 貼上下方所有程式碼並按 Enter
 *  5. 複製輸出的 JSON，交給 `python -m scraper.run import-card-feature` 匯入
 */

(function extractCardFeature() {

  /* ── 1. 取得 card_id（從 URL 解析）──────────────────────────────────────── */
  const url = window.location.href;
  const cardIdMatch = url.match(/cc_introduction_index\/([^./]+)/);
  const card_id = cardIdMatch ? 'ctbc_c_' + cardIdMatch[1].toLowerCase().replace(/^c_/, '') : 'unknown';

  /* ── 2. 解析「卡片特色」表格 ───────────────────────────────────────────── */
  const channels = [];

  // 嘗試找到回饋率表格（通常是 <table> 或 <dl>/<ul> 結構）
  const tables = document.querySelectorAll('table');
  tables.forEach(table => {
    const rows = table.querySelectorAll('tr');
    rows.forEach(row => {
      const cells = row.querySelectorAll('td, th');
      if (cells.length < 2) return;
      const label = cells[0].innerText.trim();
      const value = cells[1].innerText.trim();
      if (!label || !value) return;

      // 嘗試解析百分比
      const rateMatch = value.match(/([\d.]+)\s*%/);
      const rate = rateMatch ? parseFloat(rateMatch[1]) / 100 : null;

      channels.push({ label, value, cashback_rate: rate });
    });
  });

  // 也嘗試解析 .twrbc-tabs-collapse（Angular tab 組件）
  const tabContents = document.querySelectorAll('.twrbc-tabs-collapse, [class*="benefit"], [class*="feature"]');
  tabContents.forEach(el => {
    const text = el.innerText.trim();
    if (!text || text.length < 5) return;
    // 尋找「XXX：Y%」或「XXX消費 Y%」模式
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    lines.forEach(line => {
      const rateMatch = line.match(/([\d.]+)\s*%/);
      if (rateMatch) {
        channels.push({
          label: line.replace(/([\d.]+)\s*%.*$/, '').trim(),
          value: line,
          cashback_rate: parseFloat(rateMatch[1]) / 100,
          source: 'tab_text',
        });
      }
    });
  });

  /* ── 3. 解析「專屬優惠」（card__main 元素）──────────────────────────────── */
  const exclusiveOffers = [];
  document.querySelectorAll('.card__main, [class*="card-offer"], [class*="benefit-rate"]').forEach(el => {
    const text = el.innerText.trim();
    if (!text) return;
    const rateMatch = text.match(/([\d.]+)\s*%/);
    exclusiveOffers.push({
      benefit: text,
      cashback_rate: rateMatch ? parseFloat(rateMatch[1]) / 100 : null,
    });
  });

  /* ── 4. 輸出 ────────────────────────────────────────────────────────────── */
  const result = {
    card_id,
    page_url: url,
    extracted_at: new Date().toISOString(),
    card_feature_rows: channels,
    exclusive_offers: exclusiveOffers,
  };

  const json = JSON.stringify(result, null, 2);
  console.log('===== CTBC Card Feature Extractor =====');
  console.log(json);
  console.log('========================================');
  console.log(`\n共擷取 ${channels.length} 筆特色欄位、${exclusiveOffers.length} 筆專屬優惠。`);
  console.log('請複製以上 JSON，存成 card_feature_<card_id>.json，再執行：');
  console.log('  python -m scraper.run import-card-feature --file card_feature_<card_id>.json');

  return result;
})();
