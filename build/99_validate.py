"""步驟 9：守門員。跨檔 ID 契約、標註結構、孿生檔同步與前端殘留字串的硬性檢查。

任何一項失敗即以非 0 結束，方便串進 CI 或建置腳本。
"""

import json
import re
import sys
from pathlib import Path

from common import SITE, load_facts

DATA = SITE / "data"
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}  {detail}")
        FAILURES.append(f"{label} {detail}".strip())


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def u16len(s: str) -> int:
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def main() -> int:
    ebook = load("ebook.json")
    search = load("search_index.json")
    index = load("basic_entity_index.json")
    facts_data = load("character_facts.json")
    network = load("person_social_network.json")
    rels = load("person_relationships.json")
    stats = load("statistics.json")

    chapters = ebook["chapters"]
    all_pids, all_cids = [], []
    for ch in chapters:
        all_cids.append(ch["id"])
        for p in ch["paragraphs"]:
            all_pids.append(p["id"])
    pid_set, cid_set = set(all_pids), set(all_cids)

    print("\n[1] 書籍結構")
    check("100 回", len(chapters) == 100, f"實得 {len(chapters)}")
    check("回 ID 格式與序號一致",
          all(ch["id"] == f"xiyouji_ch{ch['n']:03d}" for ch in chapters))
    check("段落 ID 全書唯一", len(all_pids) == len(pid_set),
          f"{len(all_pids)} vs {len(pid_set)}")
    check("段落 ID 連號",
          all_pids == [f"xiyouji_p{i:05d}" for i in range(1, len(all_pids) + 1)])
    check("每回段落數合理",
          all(40 <= len(ch["paragraphs"]) <= 200 for ch in chapters))

    print("\n[2] 標註結構（renderMarkedParagraph 的硬前提）")
    bad_off = bad_sort = bad_overlap = bad_oob = 0
    total_ents = 0
    for ch in chapters:
        for p in ch["paragraphs"]:
            limit = u16len(p["text"])
            prev_end = prev_start = -1
            buf = p["text"].encode("utf-16-le")
            for e in p["entities"]:
                total_ents += 1
                # 以 UTF-16 單位重切，等同瀏覽器 String.slice() 的語意
                sliced = buf[e["start"] * 2 : e["end"] * 2].decode("utf-16-le", "replace")
                if sliced != e["text"]:
                    bad_off += 1
                if e["start"] < prev_start:
                    bad_sort += 1
                if e["start"] < prev_end:
                    bad_overlap += 1
                if e["start"] < 0 or e["end"] > limit:
                    bad_oob += 1
                prev_start, prev_end = e["start"], e["end"]
    check(f"標註總數 {total_ents:,}", 10000 <= total_ents <= 40000)
    check("UTF-16 位移可正確還原原字串", bad_off == 0, f"{bad_off} 筆錯位")
    check("實體依 start 遞增", bad_sort == 0, f"{bad_sort} 筆亂序")
    check("實體互不重疊", bad_overlap == 0, f"{bad_overlap} 筆重疊")
    check("位移未越界", bad_oob == 0, f"{bad_oob} 筆越界")

    print("\n[3] 跨檔 ID 契約")
    s_ids = {d["id"] for d in search["documents"]}
    check("search_index 段落集合 == ebook", s_ids == pid_set,
          f"差 {len(s_ids ^ pid_set)} 筆")
    check("search_index 章 ID 有效",
          all(d["chapter_id"] in cid_set for d in search["documents"]))
    idx_pids = {q["paragraph_id"] for e in index["entities"].values() for q in e["paragraphs"]}
    check("實體索引段落 ID 均存在", idx_pids <= pid_set,
          f"未知 {len(idx_pids - pid_set)} 筆")
    ebook_keys = {e["key"] for ch in chapters for p in ch["paragraphs"] for e in p["entities"]}
    check("實體索引 key 集合 == ebook 用到的 key",
          set(index["entities"]) == ebook_keys)
    check("statistics 章 ID 有效",
          {c["chapter_id"] for c in stats["chapter_stats"]} == cid_set)
    check("人物事蹟章 ID 有效",
          all(c["chapter_id"] in cid_set
              for p in facts_data["characters"] for c in p["chapters"]))
    anchors = {f["pid"] for p in facts_data["characters"]
               for c in p["chapters"] for f in c["facts"] if f["pid"]}
    check("事蹟錨點段落 ID 有效", anchors <= pid_set,
          f"未知 {len(anchors - pid_set)} 筆")

    print("\n[4] 人物網絡與語義關係")
    node_ids = {n["id"] for n in network["nodes"]}
    check("87 個人物節點", len(node_ids) == 87, f"實得 {len(node_ids)}")
    check("節點都帶 faction 欄（取代硬編的 inferFamily）",
          all(n.get("faction") for n in network["nodes"]))
    check("共現邊端點均為既有節點",
          all(l["source"] in node_ids and l["target"] in node_ids
              for l in network["links"]))
    check("語義關係端點均為既有節點",
          all(r["source"] in node_ids and r["target"] in node_ids
              for r in rels["relationships"]))
    check("無關係被靜默丟棄", not rels["skipped"],
          f"{len(rels['skipped'])} 筆進入 skipped")
    fact_keys = {c["key"] for c in facts_data["characters"]}
    check("事蹟角色集合 == 網絡節點集合", fact_keys == node_ids,
          f"差 {len(fact_keys ^ node_ids)} 個")

    print("\n[5] 事實資料完整性")
    raw = load_facts()
    raw_total = sum(len(v) for n in range(1, 101) for v in raw[n].values())
    got_total = sum(len(c["facts"]) for p in facts_data["characters"] for c in p["chapters"])
    check(f"事實總數 {got_total} == 原始 {raw_total}", got_total == raw_total)
    anchored = sum(1 for p in facts_data["characters"]
                   for c in p["chapters"] for f in c["facts"] if f["pid"])
    print(f"    （錨定率 {anchored * 100 // got_total}%，未錨定者退化為跳至該回開頭）")

    print("\n[6] 別名召回（以 facts 章回為標準答案）")
    matched = {}
    for ch in chapters:
        for p in ch["paragraphs"]:
            for e in p["entities"]:
                matched.setdefault(e["key"], set()).add(ch["n"])
    want = {}
    for n in range(1, 101):
        for name in raw[n]:
            want.setdefault(f"person_{name}", set()).add(n)
    gaps = {k: sorted(v - matched.get(k, set())) for k, v in want.items()
            if v - matched.get(k, set())}
    # 高太公：第 20/22/100 回原文只出現地名「高老莊」而未提及其人，屬正確行為
    allowed = {"person_高太公"}
    unexpected = {k: v for k, v in gaps.items() if k not in allowed}
    check("facts 章回全數被原文命中（高太公除外）", not unexpected,
          "; ".join(f"{k}:{v}" for k, v in unexpected.items()))
    for k, v in gaps.items():
        print(f"    已知豁免 {k.replace('person_', '')} 缺 {v} —— 該回原文僅提及地名")

    print("\n[7] 孿生檔同步（file:// 模式的命脈）")
    for jf in sorted(DATA.glob("*.json")):
        twin = DATA / f"{jf.name}.js"
        if not twin.exists():
            check(f"{jf.name} 有 .json.js", False, "缺孿生檔")
            continue
        body = twin.read_text(encoding="utf-8")
        key = f'window.DEMO_JSON["data/{jf.name}"] = '
        ok_key = key in body
        payload = body.split(key, 1)[1].rsplit(";", 1)[0].strip() if ok_key else ""
        same = ok_key and json.loads(payload) == json.loads(jf.read_text(encoding="utf-8"))
        check(f"{jf.name} 孿生檔鍵值與內容一致", same,
              "" if ok_key else "註冊鍵不含 data/ 前綴")

    print("\n[8] 前端殘留字串")
    for name in ("index.html", "cooccurrence_graph.html", "person_social_graph.html"):
        html = (SITE / name).read_text(encoding="utf-8")
        check(f"{name} 無 hongloumeng 前綴殘留", "hongloumeng" not in html)
        check(f"{name} 無紅樓夢字樣殘留", "紅樓夢" not in html)
    idx = (SITE / "index.html").read_text(encoding="utf-8")
    check("index.html 無硬編的 120 回", "第120回" not in idx and "120 回" not in idx)
    check("index.html 已移除死碼", "initArticles" not in idx and "networkCanvas" not in idx)

    print("\n[9] 圖頁三份平行清單同步")
    psg = (SITE / "person_social_graph.html").read_text(encoding="utf-8")
    css = (SITE / "assets" / "person-social-graph.css").read_text(encoding="utf-8")
    boxes = set(re.findall(r'class="edgeType" value="(\w+)"', psg))
    names = set(re.findall(r"^\s*(\w+): \"",
                           re.search(r"const relationNames = \{(.*?)\};", psg, re.S).group(1),
                           re.M))
    css_rel = set(re.findall(r"\.link\.rel-(\w+)", css))
    check("核取方塊 ⊆ relationNames", boxes <= names, f"缺 {sorted(boxes - names)}")
    check("核取方塊 ⊆ CSS 樣式", boxes <= css_rel, f"缺 {sorted(boxes - css_rel)}")
    cog = (SITE / "cooccurrence_graph.html").read_text(encoding="utf-8")
    cog_boxes = set(re.findall(r'type="checkbox" value="(\w+)"', cog))
    type_meta = set(re.findall(r"^\s*(\w+): \{label:",
                               re.search(r"const typeMeta = \{(.*?)\};", cog, re.S).group(1),
                               re.M))
    check("共現圖核取方塊 == typeMeta 的 key", cog_boxes == type_meta,
          f"{sorted(cog_boxes)} vs {sorted(type_meta)}")

    print(f"\n{'=' * 46}")
    if FAILURES:
        print(f"失敗 {len(FAILURES)} / {CHECKS} 項：")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"全部 {CHECKS} 項檢查通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
