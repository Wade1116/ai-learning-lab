#!/usr/bin/env python3
"""Build this independent lesson and export it to its GitHub Pages subfolder.

The parent repository keeps its existing root-based Jekyll configuration.
Markdown downloads use browser Blob URLs generated from the exact original
text embedded in HTML, so they do not depend on Jekyll serving .md paths.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
REPO_RAW = "https://raw.githubusercontent.com/Wade1116/ai-learning-lab/main/week10-taichung-wiki/"


def safe_json(value):
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def main():
    subprocess.run([sys.executable, str(ROOT / "scripts/build_core.py"), *sys.argv[1:]], check=True)
    documents = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("AGENTS.md", "README.md")}
    download_js = """(()=>{'use strict';const docs=JSON.parse(document.getElementById('source-documents').textContent);document.querySelectorAll('a[data-document]').forEach(a=>{const name=a.dataset.document;if(Object.prototype.hasOwnProperty.call(docs,name)){a.href=URL.createObjectURL(new Blob([docs[name]],{type:'text/markdown;charset=utf-8'}));a.download=name;}});})();"""
    for filename in ("index.html", "slides.html", "process.html"):
        path = DIST / filename
        body = path.read_text(encoding="utf-8")
        for name in documents:
            body = body.replace('href="' + name + '" download', 'href="' + REPO_RAW + name + '" data-document="' + name + '" download')
        extra = '<script type="application/json" id="source-documents">' + safe_json(documents) + '</script><script>' + download_js + '</script>'
        body = body.replace("</body>", extra + "</body>")
        path.write_text(body, encoding="utf-8")

    import re
    index = (DIST / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="wiki-data">(.*?)</script>', index, re.S)
    if not match:
        raise ValueError("Wiki資料未嵌入HTML")
    embedded = json.loads(match.group(1))
    originals_match = all(a["markdown"].encode("utf-8") == (ROOT / "wiki" / a["filename"]).read_bytes() for a in embedded["articles"])
    if not originals_match:
        raise ValueError("嵌入的Markdown與來源檔不一致")

    # Export only inside this subproject; the parent website is untouched.
    for path in DIST.rglob("*"):
        if not path.is_file():
            continue
        target = ROOT / path.relative_to(DIST)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    checks = {
        "kind": "github_pages_export_checks",
        "markdown_count": len(embedded["articles"]),
        "embedded_markdown_matches_originals": originals_match,
        "root_html_matches_dist": all((ROOT / name).read_bytes() == (DIST / name).read_bytes() for name in ("index.html", "slides.html", "process.html")),
        "markdown_download_method": "瀏覽器由內嵌原文建立Blob，保留原始.md檔名，不依賴Pages的Markdown路徑。",
        "runtime_download_status": "此檔只記錄原文一致與匯出檢查；實際下載仍需瀏覽器驗收。",
        "files_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("index.html", "slides.html", "process.html")}
    }
    (ROOT / "data/pages_export_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"github_subfolder_export": True, "markdown_originals_verified": originals_match, "root_html_matches_dist": checks["root_html_matches_dist"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
