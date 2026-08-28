# 西遊記知識圖譜

《西遊記》（吳承恩，一百回）的知識圖譜展示網站。純 HTML、CSS、JavaScript 與靜態 JSON，不需要後端、資料庫或建置流程。

本專案是 [cclintw/red-chamber-dream](https://github.com/cclintw/red-chamber-dream)（紅樓夢知識圖譜，GPL-3.0）的**衍生作品**，沿用其前端架構並改以《西遊記》為題材。依 GPL-3.0 規定，本專案同樣以 GPL-3.0 釋出，授權全文見專案根目錄的 `LICENSE`。

## 六個視圖

| 視圖 | 內容 |
|---|---|
| 瀏覽 | 一百回全文，人物／地點／法寶三類實體以顏色標記，可點擊查看詞頻、段落與共現 |
| 查詢 | 全文檢索，支援精確字串與實體擴展（依別名表擴展，查「孫悟空」也會找到「行者」「大聖」） |
| 人物關係圖 | 87 位角色的力導向圖：同段共現 ＋ 118 條人工撰寫的師徒／收服／結拜／親屬等語義關係 |
| 共現圖 | 人物、地點、法寶三類實體的共現網絡 |
| **人物事蹟** | 87 位角色、4253 條逐回事實描述的時間軸，可點擊跳回原文對應段落 |
| 統計 | 人物出現次數、實體標註分布、法寶統計、章回篇幅趨勢 |

「人物事蹟」是本站相對參考站多出的視圖，資料來自 [pondahai/xiyouji-wiki](https://github.com/pondahai/xiyouji-wiki) 的逐回事實抽取。

## 使用方式

直接雙擊 `index.html` 即可離線使用。

若瀏覽器限制本機檔案讀取，可改用本機伺服器：

```bash
python -m http.server 8767 --directory xiyouji-demo
```

然後開啟 `http://127.0.0.1:8767/`。

## 目錄結構

```text
xiyouji-demo/
├── index.html                 主頁（六個視圖）
├── person_social_graph.html   人物關係圖（iframe 載入）
├── cooccurrence_graph.html    實體共現圖（iframe 載入）
├── assets/                    樣式
├── vendor/                    D3 v7（本機，不走 CDN）
└── data/                      靜態資料，*.json 與 *.json.js 成對
```

`data/` 中每個 `X.json` 都有孿生的 `X.json.js`。前者供 `http://` 下的 `fetch` 使用，後者把同一份資料註冊到 `window.DEMO_JSON`，讓 `file://` 直接開啟時也能載入（`fetch` 在 `file://` 下會被 CORS 擋掉）。**兩者必須同步更新。**

請保留完整資料夾結構，不要只複製 `index.html`。

## 資料規模

| 項目 | 數量 |
|---|---|
| 回數 / 段落 / 字數 | 100 / 8,143 / 714,602 |
| 實體標註 | 17,645 筆（人物 87、地點 45、法寶 22） |
| 逐回事實描述 | 4,253 條，75% 已錨定到原文段落 |
| 人物關係 | 480 條共現邊 ＋ 118 條人工語義關係 |
| 資料總量 | 約 19 MB（含 `.json.js` 孿生檔） |

## 資料來源與重建

- 原文：`data/西遊記.epub`（好讀書櫃典藏版）。**此檔未納入版本控制**，重建資料需自行取得並放到該路徑。
- 逐回事實：`data/facts/ch_001.json` ～ `ch_100.json`，來自 [pondahai/xiyouji-wiki](https://github.com/pondahai/xiyouji-wiki)
- 別名與關係：`build/aliases.json`、`build/relationships.json`（本專案人工維護）

重建全部資料：

```bash
cd build
python 01_parse_epub.py     # epub → 章節/段落
python 02_annotate.py       # 套別名詞典做實體標註
python 03_build_data.py     # 產生全部 data/*.json 與孿生檔
python 99_validate.py       # 43 項完整性檢查
```

### 關於別名

《西遊記》極少使用角色全名 —— 「行者」出現 4,326 次而「孫悟空」僅 126 次，「八戒」1,672 次而「豬八戒」129 次，「玉帝」191 次而「玉皇大帝」僅 6 次。因此 `build/aliases.json` 是本站品質的關鍵，掃描採**最長優先、不重疊**策略，並以 stopforms 阻擋誤配（例如「覆海大聖」中的「大聖」不應算成孫悟空、「木叉行者」不應算成孫悟空）。

高歧義的泛稱（師父、菩薩、長老、國王、大王、那怪、白馬）一律不納入任何角色的別名 —— 寧可漏抓也不錯抓，因為誤標會直接汙染共現圖的邊權重。

`99_validate.py` 以逐回事實的章回集合作為標準答案自動檢查召回率：87 位角色中僅「高太公」有 3 回未命中，且那三回原文確實只提及地名「高老莊」而未提及其人。

## 授權與出處

本專案以 **GPL-3.0** 釋出（見 `LICENSE`）。

**衍生自** [cclintw/red-chamber-dream](https://github.com/cclintw/red-chamber-dream)（GPL-3.0）。相對於原作，本專案的修改包括：

- 資料層全部替換為《西遊記》：改寫 epub 解析、實體標註、索引與統計的產生流程（`build/`）
- 實體本體論由「人物／身份／建築／地點／花草」改為「人物／地點／法寶」
- 新增第六個視圖「人物事蹟」及其資料檔 `character_facts.json`
- 實體索引改為精簡版（不內嵌段落全文，由前端從 `ebook.json` 解析）
- 人物關係圖的陣營歸屬改為資料驅動（新增節點 `faction` 欄位），移除原作中硬編角色 ID 的 `inferFamily()`
- 關係類型改為西遊記體系（師徒／收服／結拜／親屬／婚姻／協助／敵對）
- 實體位移改以 UTF-16 code unit 計算，修正含非 BMP 字元段落的標註錯位
- 移除原作中未被引用的資料檔與死碼

**第三方素材**

- 逐回事實描述取自 [pondahai/xiyouji-wiki](https://github.com/pondahai/xiyouji-wiki)（該專案未宣告授權）
- `vendor/d3.v7.min.js` 為 [D3.js](https://d3js.org/)，ISC 授權
- 《西遊記》原文為公有領域（吳承恩，明代）
