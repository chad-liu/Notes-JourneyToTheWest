"""步驟 3：由章節結構與標註結果產生站台的全部 data/*.json（含 .json.js 孿生檔）。

尚未執行 02_annotate.py 時仍可運作，此時實體標註為空，
用於在投入別名工程前先打通端對端。
"""

import collections
import json
from pathlib import Path

from common import (
    TMP,
    chapter_id,
    human_size,
    load_facts,
    load_tmp,
    write_json,
)

TYPE_ZH = {"PERSON": "人物", "PLACE": "地點", "ARTIFACT": "法寶"}

FACTION_ZH = {
    "pilgrims": "取經團隊",
    "buddhist": "西天佛界",
    "heaven": "天庭道教",
    "dragon": "龍宮",
    "underworld": "地府",
    "demon": "妖魔",
    "mortal": "凡人王侯",
}


def load_annotations() -> dict:
    """回傳 {paragraph_id: [entity, ...]}；尚未標註時回傳空 dict。"""
    path = TMP / "annotations.json"
    if not path.exists():
        print("（尚無 annotations.json，本次產出不含實體標註）")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_entity_meta() -> dict:
    """回傳 {key: {name, kind, faction}}；尚未標註時回傳空 dict。"""
    path = TMP / "entity_meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_ebook(chapters, annotations):
    out = []
    for ch in chapters:
        paragraphs = []
        for p in ch["paragraphs"]:
            paragraphs.append(
                {
                    "id": p["id"],
                    "n": p["n"],
                    "text": p["text"],
                    "entities": annotations.get(p["id"], []),
                }
            )
        out.append(
            {
                "id": chapter_id(ch["n"]),
                "n": ch["n"],
                "title": ch["title"],
                "paragraphs": paragraphs,
            }
        )
    return {"chapters": out}


def build_search_index(chapters):
    documents = []
    for ch in chapters:
        cid = chapter_id(ch["n"])
        for p in ch["paragraphs"]:
            documents.append(
                {
                    "id": p["id"],
                    "chapter_id": cid,
                    "chapter_number": ch["n"],
                    "chapter_title": ch["title"],
                    "paragraph_number": p["n"],
                    "text": p["text"],
                }
            )
    return {"documents": documents}


def build_entity_index(chapters, annotations, meta):
    """精簡版實體索引：paragraphs[] 只存 ID，不重複內嵌段落全文。"""
    chapter_of = {}
    para_meta = {}
    for ch in chapters:
        for p in ch["paragraphs"]:
            chapter_of[p["id"]] = ch["n"]
            para_meta[p["id"]] = (ch["n"], ch["title"], p["n"])

    entities = {}
    occurrence_count = 0
    for ch in chapters:
        for p in ch["paragraphs"]:
            ents = annotations.get(p["id"], [])
            seen_here = collections.OrderedDict()
            for e in ents:
                occurrence_count += 1
                rec = entities.setdefault(
                    e["key"],
                    {
                        "key": e["key"],
                        "label": e["label"],
                        "entity_type": e["type"],
                        "entity_type_zh": e["type_zh"],
                        "entity_key": e["key"],
                        "canonical_name": e["label"],
                        "frequency": 0,
                        "paragraph_count": 0,
                        "surface_forms": [],
                        "paragraphs": [],
                        "cooccurrences": [],
                        "_surfaces": set(),
                        "_cooc": collections.Counter(),
                        "_chapters": set(),
                    },
                )
                rec["frequency"] += 1
                rec["_surfaces"].add(e["text"])
                rec["_chapters"].add(ch["n"])
                seen_here[e["key"]] = True

            keys = list(seen_here)
            for k in keys:
                cn, _ct, pn = para_meta[p["id"]]
                # 不存 text 與 chapter_title：前端一律從已載入的 ebook.json 解析，
                # 這讓索引從約 12MB 降到 1.5MB
                entities[k]["paragraphs"].append(
                    {
                        "chapter_number": cn,
                        "paragraph_id": p["id"],
                        "paragraph_number": pn,
                    }
                )
            for i, a in enumerate(keys):
                for b in keys[i + 1 :]:
                    entities[a]["_cooc"][b] += 1
                    entities[b]["_cooc"][a] += 1

    for rec in entities.values():
        rec["paragraph_count"] = len(rec["paragraphs"])
        rec["surface_forms"] = sorted(rec.pop("_surfaces"), key=lambda s: (-len(s), s))
        rec["chapter_count"] = len(rec.pop("_chapters"))
        cooc = rec.pop("_cooc")
        rec["cooccurrences"] = [
            {
                "key": k,
                "label": entities[k]["label"],
                "type": entities[k]["entity_type"],
                "type_zh": entities[k]["entity_type_zh"],
                "count": c,
            }
            for k, c in cooc.most_common(40)
        ]

    return {
        "metadata": {
            "included_types": sorted({e["entity_type"] for e in entities.values()}),
            "entity_count": len(entities),
            "occurrence_count": occurrence_count,
        },
        "entities": entities,
    }


def _bigrams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _anchor(fact: str, paragraphs: list[dict]) -> str | None:
    """為一條事實描述找出最相符的原文段落，讓前端能點擊跳轉。

    事實句是 LLM 改寫過的摘要，與原文用字不同，故用字元 bigram 的
    Jaccard 重疊度比對（不需分詞、無外部相依）。相似度過低則不給錨點。
    """
    fb = _bigrams(fact)
    if not fb:
        return None
    best_score, best_id = 0.0, None
    for p in paragraphs:
        pb = _bigrams(p["text"])
        if not pb:
            continue
        score = len(fb & pb) / len(fb)
        if score > best_score:
            best_score, best_id = score, p["id"]
    # 0.20 對應約 75% 錨定率；錨錯的成本很低（仍在正確的回，只是跳到鄰近段落）
    return best_id if best_score >= 0.20 else None


def build_character_facts(chapters, meta):
    """4253 條各回事實，依角色聚合成時間軸。"""
    facts = load_facts()
    title_of = {ch["n"]: ch["title"] for ch in chapters}
    paras_of = {ch["n"]: ch["paragraphs"] for ch in chapters}
    name_to_key = {v["name"]: k for k, v in meta.items() if v.get("kind") == "PERSON"}

    grouped = collections.defaultdict(list)
    for n in range(1, 101):
        for name, items in facts[n].items():
            grouped[name].append({"n": n, "facts": items})

    characters = []
    for name, chunks in grouped.items():
        key = name_to_key.get(name, f"person_{name}")
        faction = meta.get(key, {}).get("faction", "other")
        characters.append(
            {
                "key": key,
                "name": name,
                "faction": faction,
                "faction_zh": FACTION_ZH.get(faction, "其他"),
                "total_facts": sum(len(c["facts"]) for c in chunks),
                "chapter_count": len(chunks),
                "chapters": [
                    {
                        "n": c["n"],
                        "chapter_id": chapter_id(c["n"]),
                        "title": title_of[c["n"]],
                        "facts": [
                            {"text": f, "pid": _anchor(f, paras_of[c["n"]])}
                            for f in c["facts"]
                        ],
                    }
                    for c in sorted(chunks, key=lambda c: c["n"])
                ],
            }
        )

    characters.sort(key=lambda c: (-c["chapter_count"], -c["total_facts"]))
    return {"characters": characters}


def build_person_network(chapters, annotations, meta, entity_index):
    """人物共現網絡：同段落出現即建邊，權重為共同出現的段落數。"""
    people = {k for k, v in meta.items() if v["kind"] == "PERSON"}

    pair_paras = collections.Counter()
    pair_chaps = collections.defaultdict(set)
    node_paras = collections.defaultdict(set)
    node_chaps = collections.defaultdict(set)

    for ch in chapters:
        for p in ch["paragraphs"]:
            keys = {e["key"] for e in annotations.get(p["id"], [])} & people
            for k in keys:
                node_paras[k].add(p["id"])
                node_chaps[k].add(ch["n"])
            ordered = sorted(keys)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    pair_paras[(a, b)] += 1
                    pair_chaps[(a, b)].add(ch["n"])

    degree = collections.Counter()
    weighted = collections.Counter()
    for (a, b), w in pair_paras.items():
        degree[a] += 1
        degree[b] += 1
        weighted[a] += w
        weighted[b] += w

    ents = entity_index["entities"]
    nodes = []
    for k in sorted(people):
        faction = meta[k]["faction"]
        nodes.append(
            {
                "id": k,
                "name": meta[k]["name"],
                "type": "PERSON",
                "subtype": faction,
                "faction": faction,
                "frequency": ents.get(k, {}).get("frequency", 0),
                "chapter_count": len(node_chaps[k]),
                "paragraph_count": len(node_paras[k]),
                "degree": degree[k],
                "weighted_degree": weighted[k],
            }
        )

    links = [
        {
            "source": a,
            "target": b,
            "source_name": meta[a]["name"],
            "target_name": meta[b]["name"],
            "relation_type": "co_occurrence",
            "weight": w,
            "shared_paragraph_count": w,
            "chapter_count": len(pair_chaps[(a, b)]),
        }
        for (a, b), w in sorted(pair_paras.items(), key=lambda kv: -kv[1])
    ]

    return {
        "metadata": {
            "network_type": "person_cooccurrence",
            "node_type": "PERSON",
            "edge_relation": "co_occurrence",
            "edge_scope": "paragraph",
            "node_count": len(nodes),
            "edge_count": len(links),
            "note": "節點為 data/facts 收錄的 87 位角色；邊為同段落共現，權重是共同出現的段落數。",
        },
        "nodes": nodes,
        "links": links,
    }


def build_relationships(meta):
    """人工撰寫的語義關係；兩端須為既有節點，否則落入 skipped 而非靜默丟棄。"""
    spec = json.loads(
        (Path(__file__).parent / "relationships.json").read_text(encoding="utf-8")
    )
    name_to_key = {v["name"]: k for k, v in meta.items() if v["kind"] == "PERSON"}

    out, skipped = [], []
    for i, r in enumerate(spec["relationships"], 1):
        src, tgt = name_to_key.get(r["source"]), name_to_key.get(r["target"])
        if not src or not tgt:
            skipped.append(
                {
                    "source": r["source"],
                    "target": r["target"],
                    "relation_type": r["relation_type"],
                    "label": r["relation_label"],
                    "reason": "missing_node",
                }
            )
            continue
        out.append(
            {
                "relation_id": f"xiyouji_pr{i:04d}",
                "source": src,
                "target": tgt,
                "source_name": r["source"],
                "target_name": r["target"],
                "relation_type": r["relation_type"],
                "relation_label": r["relation_label"],
                "direction": "undirected",
                "confidence": r["confidence"],
                "source_method": "seed_manual_v1",
                "note": r.get("note", ""),
            }
        )
    return {"relationships": out, "skipped": skipped}


def build_statistics(chapters, entity_index, network):
    chapter_stats = [
        {
            "chapter_id": chapter_id(ch["n"]),
            "chapter_number": ch["n"],
            "title": ch["title"],
            "paragraph_count": len(ch["paragraphs"]),
            "char_count": sum(len(p["text"]) for p in ch["paragraphs"]),
        }
        for ch in chapters
    ]

    total_paragraphs = sum(c["paragraph_count"] for c in chapter_stats)
    total_chars = sum(c["char_count"] for c in chapter_stats)
    total_sentences = sum(
        sum(1 for c in p["text"] if c in "。！？；")
        for ch in chapters
        for p in ch["paragraphs"]
    )

    ents = entity_index["entities"]
    faction_of = {n["id"]: n["faction"] for n in network["nodes"]}

    # 參考站的統計圖表讀的是字串型別，此處沿用以免改動圖表程式
    entity_occurrence_summary = [
        {
            "entity_key": e["key"],
            "canonical_name": e["label"],
            "entity_type": e["entity_type"],
            "subtype": faction_of.get(e["key"], ""),
            "total_occurrences": str(e["frequency"]),
            "chapter_count": str(e.get("chapter_count", 0)),
            "surface_forms": "|".join(e["surface_forms"]),
        }
        for e in sorted(ents.values(), key=lambda e: -e["frequency"])
    ]

    # 以（類型, 陣營/類別）聚合，讓統計頁的子類圖表有內容
    ner_counter = collections.Counter()
    ner_unique = collections.Counter()
    for key, e in ents.items():
        sub = faction_of.get(key, "")
        ner_counter[(e["entity_type"], sub)] += e["frequency"]
        ner_unique[(e["entity_type"], sub)] += 1
    ner_summary = [
        {
            "entity_type": t,
            "subtype": sub,
            "source": "alias-dict",
            "count": str(c),
            "unique_entity_count": str(ner_unique[(t, sub)]),
        }
        for (t, sub), c in ner_counter.most_common()
    ]

    # 參考站的「意象」欄位在此改承載法寶統計，schema 不變
    artifacts = [e for e in ents.values() if e["entity_type"] == "ARTIFACT"]
    motif_summary = [
        {
            "motif_key": e["key"],
            "motif_type": "法寶",
            "subtype": e["label"],
            "count": str(e["frequency"]),
            "surface_forms": "|".join(e["surface_forms"]),
        }
        for e in sorted(artifacts, key=lambda e: -e["frequency"])
    ]

    return {
        "document": {
            "document_id": "xiyouji",
            "title": "西遊記",
            "author": "吳承恩",
            "source_file": "西遊記.epub",
            "language": "zh-Hant",
            "total_chapters": str(len(chapter_stats)),
            "total_paragraphs": str(total_paragraphs),
            "total_sentences": str(total_sentences),
            "total_chars": str(total_chars),
        },
        "chapter_stats": chapter_stats,
        "ner_summary": ner_summary,
        "entity_occurrence_summary": entity_occurrence_summary,
        "motif_summary": motif_summary,
        "motif_chapter_summary": [],
        "person_social_top_nodes": [
            {
                "id": n["id"],
                "name": n["name"],
                "type": n["type"],
                "subtype": n["subtype"],
                "frequency": str(n["frequency"]),
                "chapter_count": str(n["chapter_count"]),
                "paragraph_count": str(n["paragraph_count"]),
                "degree": str(n["degree"]),
                "weighted_degree": str(n["weighted_degree"]),
                "surface_forms": "|".join(
                    entity_index["entities"].get(n["id"], {}).get("surface_forms", [])
                ),
            }
            for n in sorted(network["nodes"], key=lambda x: -x["frequency"])[:30]
        ],
        "person_social_top_edges": [
            {
                "edge_id": f"person_edge_{i:06d}",
                "source": l["source"],
                "source_name": l["source_name"],
                "target": l["target"],
                "target_name": l["target_name"],
                "relation_type": l["relation_type"],
                "scope": "paragraph",
                "weight": str(l["weight"]),
                "shared_paragraph_count": str(l["shared_paragraph_count"]),
                "chapter_count": str(l["chapter_count"]),
            }
            for i, l in enumerate(network["links"][:50], 1)
        ],
    }


def main() -> int:
    chapters = load_tmp("chapters.json")
    annotations = load_annotations()
    meta = load_entity_meta()

    sizes = {}
    ebook = build_ebook(chapters, annotations)
    sizes["ebook.json"] = write_json("data/ebook.json", ebook)
    sizes["search_index.json"] = write_json(
        "data/search_index.json", build_search_index(chapters)
    )

    entity_index = build_entity_index(chapters, annotations, meta)
    sizes["basic_entity_index.json"] = write_json(
        "data/basic_entity_index.json", entity_index
    )
    sizes["character_facts.json"] = write_json(
        "data/character_facts.json", build_character_facts(chapters, meta)
    )
    network = build_person_network(chapters, annotations, meta, entity_index)
    sizes["person_social_network.json"] = write_json(
        "data/person_social_network.json", network
    )
    relationships = build_relationships(meta)
    sizes["person_relationships.json"] = write_json(
        "data/person_relationships.json", relationships
    )
    sizes["statistics.json"] = write_json(
        "data/statistics.json", build_statistics(chapters, entity_index, network)
    )

    total = 0
    for name, size in sizes.items():
        print(f"{name:28s} {human_size(size)}")
        total += size
    print(f"{'合計（單份）':26s} {human_size(total)}")
    print(f"{'含 .json.js 孿生檔':24s} {human_size(total * 2)}")
    print(f"實體數 {entity_index['metadata']['entity_count']}，"
          f"標註次數 {entity_index['metadata']['occurrence_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
