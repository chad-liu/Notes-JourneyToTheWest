"""西遊記知識圖譜建置 — 共用工具。"""

import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPUB = ROOT / "data" / "西遊記.epub"
FACTS_DIR = ROOT / "data" / "facts"
SITE = ROOT / "xiyouji-demo"
TMP = ROOT / "build" / "tmp"

SLUG = "xiyouji"


def chapter_id(n: int) -> str:
    return f"{SLUG}_ch{n:03d}"


def paragraph_id(n: int) -> str:
    return f"{SLUG}_p{n:05d}"


def write_json(rel_path: str, obj) -> int:
    """輸出 data/xxx.json 與其孿生的 .json.js，兩者永遠同步。

    rel_path 例如 "data/ebook.json"，同時也是 window.DEMO_JSON 的鍵值。
    """
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    target = SITE / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")

    twin = SITE / f"{rel_path}.js"
    twin.write_text(
        "window.DEMO_JSON = window.DEMO_JSON || {};\n"
        f'window.DEMO_JSON["{rel_path}"] = {text};\n',
        encoding="utf-8",
    )
    return len(text.encode("utf-8"))


def load_tmp(name: str):
    return json.loads((TMP / name).read_text(encoding="utf-8"))


def save_tmp(name: str, obj) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / name).write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def load_facts() -> dict[int, dict[str, list[str]]]:
    """讀入 100 回的事實描述，回傳 {回次: {角色: [事實, ...]}}。"""
    facts = {}
    for n in range(1, 101):
        path = FACTS_DIR / f"ch_{n:03d}.json"
        facts[n] = json.loads(path.read_text(encoding="utf-8"))
    return facts


def human_size(n_bytes: int) -> str:
    return f"{n_bytes / 1048576:.2f} MB"


_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_H3_RE = re.compile(r"<h3>.*?</h3>", re.S | re.I)


def read_epub_chapters() -> list[dict]:
    """解出 100 回：[{n, title, paragraphs: [str, ...]}, ...]。

    回目標題取自 toc.ncx（比各回的 <h3> 乾淨，第 1 回的 <h3> 是書名）。
    """
    with zipfile.ZipFile(EPUB) as z:
        ncx = z.read("OEBPS/toc.ncx").decode("utf-8")
        # 第 1 個 <text> 是書名、第 2 個是「目錄」，其後 100 個才是回目
        titles = re.findall(r"<text>([^<]*)</text>", ncx)[2:102]

        chapters = []
        for n in range(1, 101):
            raw = z.read(f"OEBPS/{n}.xhtml").decode("utf-8")
            body = raw.split("<body>")[1].split("</body>")[0]
            body = _H3_RE.sub("", body)
            paragraphs = []
            for chunk in _BR_RE.split(body):
                text = _TAG_RE.sub("", chunk).replace("　", "").strip()
                if text:
                    paragraphs.append(text)
            chapters.append({"n": n, "title": titles[n - 1], "paragraphs": paragraphs})

    return chapters
