"""步驟 1：解析 西遊記.epub，輸出乾淨的章節/段落結構到 build/tmp/chapters.json。"""

import re
import sys

from common import human_size, paragraph_id, read_epub_chapters, save_tmp

# 好讀書櫃版在第 1 回開頭夾帶的版本標記
# 涵蓋《二○一七年三月三日版》與《好讀書櫃》典藏版兩種寫法（後者的 》在字中間）
JUNK_RE = re.compile(r"^《.*版》?$")
# toc.ncx 的回目含「第一回　」前綴，站台 UI 會另外渲染回次，故此處剝掉
TITLE_PREFIX_RE = re.compile(r"^第[一二三四五六七八九十百零〇]+回\s*")


def clean_title(raw: str) -> str:
    return TITLE_PREFIX_RE.sub("", raw).replace("　", " ").strip()


def strip_leading_noise(paragraphs: list[str], title: str) -> list[str]:
    """剔除回首的版本標記與重複出現的回目行。"""
    # 段落已移除 U+3000，故回目行比對時也要移除
    title_compact = title.replace(" ", "")
    out = list(paragraphs)
    while out:
        head = out[0]
        is_junk = JUNK_RE.match(head)
        is_title_line = head.startswith("第") and title_compact and title_compact in head
        if is_junk or is_title_line:
            out.pop(0)
            continue
        break
    return out


def main() -> int:
    chapters = read_epub_chapters()
    if len(chapters) != 100:
        print(f"錯誤：預期 100 回，實得 {len(chapters)} 回", file=sys.stderr)
        return 1

    out = []
    pid = 0
    total_chars = 0
    for ch in chapters:
        title = clean_title(ch["title"])
        paragraphs = strip_leading_noise(ch["paragraphs"], title)

        items = []
        for n, text in enumerate(paragraphs, 1):
            pid += 1
            items.append({"id": paragraph_id(pid), "n": n, "text": text})
            total_chars += len(text)

        out.append({"n": ch["n"], "title": title, "paragraphs": items})

    save_tmp("chapters.json", out)

    counts = [len(c["paragraphs"]) for c in out]
    print(f"回數        : {len(out)}")
    print(f"段落總數    : {pid}")
    print(f"總字數      : {total_chars:,}")
    print(f"每回段落    : {min(counts)} – {max(counts)}（平均 {pid / len(out):.1f}）")
    print(f"第 1 回標題 : {out[0]['title']}")
    print(f"第 1 回首段 : {out[0]['paragraphs'][0]['text'][:40]}")
    print(f"第 100 回   : {out[-1]['title']}")
    print(f"tmp 檔大小  : {human_size((len(str(out))))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
