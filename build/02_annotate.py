"""步驟 2：套別名詞典對全文做實體標註。

三個關鍵設計：
1. 位移一律以 UTF-16 code unit 計算。全書有 10 個非 BMP 字元（𤊨𪀚𤜱𡟎𤟷），
   Python 以碼位索引、JavaScript 的 String.slice() 以 UTF-16 索引，
   若用碼位輸出，這 5 個段落之後的標註在瀏覽器會整段錯位且不會報錯。
2. 最長優先、不重疊掃描：確保「齊天大聖」不會被拆成「大聖」。
3. stopforms 會消耗字元但不產生標註，用來擋掉「覆海大聖」這類會讓
   子字串誤配的字串。
"""

import collections
import json
import sys
from pathlib import Path

from common import TMP, load_facts, load_tmp, save_tmp

ALIASES = Path(__file__).parent / "aliases.json"

KIND_META = {
    "person": ("PERSON", "人物"),
    "place": ("PLACE", "地點"),
    "artifact": ("ARTIFACT", "法寶"),
}


def u16len(s: str) -> int:
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def build_forms(spec: dict):
    """展平成 {別名字串: entity_key 或 None}；None 代表 stopform。"""
    forms: dict[str, str | None] = {}
    meta: dict[str, dict] = {}
    collisions = []

    for form in spec.get("stopforms", {}):
        if form.startswith("_"):
            continue
        forms[form] = None

    for kind, (etype, type_zh) in KIND_META.items():
        for name, info in spec.get(kind, {}).items():
            key = f"{kind}_{name}"
            meta[key] = {
                "name": name,
                "kind": etype,
                "type_zh": type_zh,
                "faction": info.get("faction", "other"),
            }
            for form in info["aliases"]:
                if form in forms and forms[form] is not None and forms[form] != key:
                    collisions.append((form, forms[form], key))
                    continue
                if form in forms and forms[form] is None:
                    # stopform 優先，別名不得覆蓋
                    continue
                forms[form] = key

    return forms, meta, collisions


def scan(text: str, forms: dict, maxlen: int, meta: dict) -> list[dict]:
    """最長優先、不重疊掃描；回傳依 start 遞增排序的標註。"""
    out = []
    i = 0
    u16 = 0
    n = len(text)
    while i < n:
        hit = None
        for length in range(min(maxlen, n - i), 0, -1):
            candidate = text[i : i + length]
            if candidate in forms:
                hit = (candidate, forms[candidate])
                break
        if hit is None:
            u16 += 2 if ord(text[i]) > 0xFFFF else 1
            i += 1
            continue

        form, key = hit
        width = u16len(form)
        if key is not None:
            m = meta[key]
            out.append(
                {
                    "key": key,
                    "label": m["name"],
                    "type": m["kind"],
                    "type_zh": m["type_zh"],
                    "text": form,
                    "start": u16,
                    "end": u16 + width,
                }
            )
        u16 += width
        i += len(form)
    return out


def main() -> int:
    spec = json.loads(ALIASES.read_text(encoding="utf-8"))
    forms, meta, collisions = build_forms(spec)
    maxlen = max(len(f) for f in forms)

    if collisions:
        print("警告：別名衝突（同一字串被指派給多個實體，已保留先出現者）", file=sys.stderr)
        for form, first, second in collisions:
            print(f"  {form}: {first} vs {second}", file=sys.stderr)

    chapters = load_tmp("chapters.json")
    annotations = {}
    form_hits = collections.Counter()
    form_samples = collections.defaultdict(list)
    matched_chapters = collections.defaultdict(set)
    total = 0

    for ch in chapters:
        for p in ch["paragraphs"]:
            ents = scan(p["text"], forms, maxlen, meta)
            if not ents:
                continue
            annotations[p["id"]] = ents
            total += len(ents)
            for e in ents:
                form_hits[(e["text"], e["key"])] += 1
                matched_chapters[e["key"]].add(ch["n"])
                if len(form_samples[e["text"]]) < 3:
                    idx = p["text"].find(e["text"])
                    form_samples[e["text"]].append(
                        p["text"][max(0, idx - 14) : idx + len(e["text"]) + 14]
                    )

    save_tmp("annotations.json", annotations)
    save_tmp("entity_meta.json", meta)

    # 以 facts 的章回集合為標準答案，檢查召回率
    facts = load_facts()
    facts_chapters = collections.defaultdict(set)
    for n in range(1, 101):
        for name in facts[n]:
            facts_chapters[f"person_{name}"].add(n)

    gaps = []
    for key, want in facts_chapters.items():
        got = matched_chapters.get(key, set())
        missing = want - got
        if missing:
            gaps.append((len(missing), meta.get(key, {}).get("name", key), sorted(missing)))
    gaps.sort(reverse=True)

    report = TMP / "report_alias.tsv"
    with report.open("w", encoding="utf-8") as f:
        f.write("form\tentity\thits\tsample\n")
        for (form, key), hits in form_hits.most_common():
            sample = form_samples[form][0].replace("\t", " ") if form_samples[form] else ""
            f.write(f"{form}\t{meta[key]['name']}\t{hits}\t{sample}\n")

    print(f"別名字串總數 : {len(forms)}（含 stopforms）")
    print(f"標註總數     : {total:,}")
    print(f"有標註的段落 : {len(annotations):,} / {sum(len(c['paragraphs']) for c in chapters):,}")
    print(f"命中的實體數 : {len(matched_chapters)} / {len(meta)}")
    print(f"抽樣報告     : {report}")
    print()
    print(f"=== facts 未被命中的角色（共 {len(gaps)} 位，目標 0）===")
    if not gaps:
        print("  無 — 全部 87 位角色的 facts 章回都被原文命中")
    for cnt, name, missing in gaps[:25]:
        shown = missing[:12]
        tail = " …" if len(missing) > 12 else ""
        print(f"  {name:<10} 缺 {cnt:>2} 回: {shown}{tail}")

    never = [meta[k]["name"] for k in meta if k not in matched_chapters]
    if never:
        print(f"\n=== 全書零命中的實體（{len(never)}）===")
        print("  " + "、".join(never))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
