# Notes-JourneyToTheWest

《西遊記》知識圖譜 —— 全文閱讀與實體標註、全文檢索、人物關係圖、實體共現圖、人物事蹟時間軸與統計視覺化。

網站在 [`xiyouji-demo/`](xiyouji-demo/)，純靜態，雙擊 `xiyouji-demo/index.html` 即可離線使用。詳細說明見 [`xiyouji-demo/README.md`](xiyouji-demo/README.md)。

## 目錄

| 路徑 | 內容 |
|---|---|
| `xiyouji-demo/` | 網站本體（HTML／CSS／JS 與靜態 JSON，可直接部署） |
| `build/` | 資料建置流程：epub 解析、別名標註、資料產生、完整性驗證 |
| `build/aliases.json` | 人工維護的別名詞典 —— 本專案品質的關鍵 |
| `build/relationships.json` | 118 條人工撰寫的人物語義關係 |
| `data/facts/` | 逐回事實描述，來自 [pondahai/xiyouji-wiki](https://github.com/pondahai/xiyouji-wiki) |

原文 `data/西遊記.epub` 未納入版本控制，重建資料需自備。

## 資料規模

100 回 · 8,143 段 · 714,602 字 · 17,645 筆實體標註 · 4,253 條逐回事實 · 87 位角色

## 授權

GPL-3.0（見 [`LICENSE`](LICENSE)）。本專案衍生自 [cclintw/red-chamber-dream](https://github.com/cclintw/red-chamber-dream)（GPL-3.0），修改內容詳列於 [`xiyouji-demo/README.md`](xiyouji-demo/README.md#授權與出處)。
