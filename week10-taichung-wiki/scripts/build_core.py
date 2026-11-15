#!/usr/bin/env python3
"""Rebuild a static teaching site from reviewed Markdown Wiki pages.

Only Python's standard library is required. This does not call an LLM or
silently retrieve live information. The source snapshots and Wiki pages are
the reviewed inputs from the documented AI-assisted authoring session.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TEMPLATES = ROOT / "templates"
NOW = dt.datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")


def read_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def esc(value):
    return html.escape(str(value), quote=True)


def script_json(data):
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def remove_source_markers(value):
    return re.sub(r"\[S\d{2}\]", "", value).strip()


def parse_wiki(path: Path, source_index: dict):
    raw = path.read_text(encoding="utf-8")
    front, body = {}, raw
    if raw.startswith("---\n"):
        front_text, body = raw[4:].split("\n---\n", 1)
        for line in front_text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = [x.strip().strip("\"'") for x in value[1:-1].split(",") if x.strip()]
            front[key.strip()] = value
    wiki_id = front["wiki_id"]
    sections = {}
    current = "opening"
    sections[current] = []
    for line in body.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        else:
            sections[current].append(line)
    joined = {k: "\n".join(v).strip() for k, v in sections.items()}
    facts = [remove_source_markers(line[2:]) for line in sections.get("可回查的資料", []) if line.startswith("- ")]
    related = re.findall(r"\]\((W\d{2})-[^)]+\.md\)", joined.get("關聯頁面", ""))
    source_ids = front.get("source_ids", [])
    theme = source_index[source_ids[0]]["theme"] if wiki_id <= "W06" else ("跨景點比較" if wiki_id == "W07" else "來源判讀與資訊限制")
    render_parts = [joined.get("opening", "")]
    for name, text in joined.items():
        if name not in ("opening", "來源", "關聯頁面"):
            render_parts.append("## " + name + "\n\n" + text)
    article = {
        "wiki_id": wiki_id,
        "title": front["title"],
        "filename": path.name,
        "source_ids": source_ids,
        "theme": theme,
        "summary": joined.get("opening", ""),
        "facts": facts,
        "teaching_point": joined.get("學習重點", ""),
        "sections": joined,
        "related": list(dict.fromkeys(related)),
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "search_text": body,
        "markdown": raw,
    }
    article["html"] = markdown("\n\n".join(render_parts), source_index)
    return article


def inline(text: str, source_index: dict):
    # A small, deliberately bounded renderer for the reviewed local Wiki.
    saved = []

    def token(value):
        saved.append(value)
        return "\x00" + str(len(saved) - 1) + "\x00"

    def md_link(match):
        label, url = match.group(1), match.group(2)
        wiki_match = re.match(r"(W\d{2})-.+\.md$", url)
        if wiki_match:
            return token('<a href="#' + wiki_match.group(1) + '">' + esc(label) + "</a>")
        if url.startswith("https://"):
            return token('<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + "</a>")
        return label

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", md_link, text)
    text = re.sub(r"https://[^\s<>]+", lambda m: token('<a href="' + esc(m[0]) + '" target="_blank" rel="noopener noreferrer">' + esc(m[0]) + "</a>"), text)
    text = re.sub(r"\[(S\d{2})\]", lambda m: token('<a href="' + esc(source_index[m[1]]["canonical_url"]) + '" target="_blank" rel="noopener noreferrer">[' + m[1] + "]</a>") if m[1] in source_index else m[0], text)
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub("\x00(\\d+)\x00", lambda m: saved[int(m[1])], text)
    return text


def markdown(text: str, source_index: dict):
    lines = text.splitlines()
    result, paragraph, listing = [], [], []
    i = 0

    def flush():
        if paragraph:
            result.append("<p>" + inline("".join(paragraph), source_index) + "</p>")
            paragraph.clear()
        if listing:
            result.append("<ul>" + "".join("<li>" + inline(x, source_index) + "</li>" for x in listing) + "</ul>")
            listing.clear()

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            flush()
        elif line.startswith("## "):
            flush()
            result.append("<h2>" + esc(line[3:]) + "</h2>")
        elif line.startswith("### "):
            flush()
            result.append("<h3>" + esc(line[4:]) + "</h3>")
        elif line.startswith("- "):
            if paragraph:
                flush()
            listing.append(line[2:])
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"\|[-|: ]+\|", lines[i + 1]):
            flush()
            headings = [x.strip() for x in line.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([x.strip() for x in lines[i].strip().strip("|").split("|")])
                i += 1
            result.append('<div class="table-scroll"><table><thead><tr>' + "".join("<th scope=\"col\">" + inline(x, source_index) + "</th>" for x in headings) + "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + inline(x, source_index) + "</td>" for x in row) + "</tr>" for row in rows) + "</tbody></table></div>")
            continue
        else:
            if listing:
                flush()
            paragraph.append(line)
        i += 1
    flush()
    return "\n".join(result)


def header(current):
    links = [("wiki", "index.html", "Wiki知識庫"), ("slides", "slides.html", "教學簡報"), ("process", "process.html", "製作流程與紀錄")]
    return '<a class="skip-link" href="#main">跳到主要內容</a><header class="site-header"><div class="header-inner"><a class="brand" href="index.html">台中景點入門</a><nav class="top-nav" aria-label="主要導覽">' + "".join('<a href="' + url + '"' + (' aria-current="page"' if key == current else "") + ">" + name + "</a>" for key, url, name in links) + "</nav></div></header>"


def page(title, content, current, script="", extra_head=""):
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    return '<!doctype html>\n<html lang="zh-Hant-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="以6篇官方資料整理的台中景點Wiki、12頁教學HTML簡報與實際製作紀錄。"><title>' + esc(title) + "</title><style>" + css + "</style>" + extra_head + "</head><body>" + header(current) + content + ("<script>" + script + "</script>" if script else "") + "</body></html>\n"


def icon(kind, title="景點主題示意圖"):
    shapes = {
        "W01": '<path d="M20 160q40-20 80 0t80 0t80 0M20 185q40-20 80 0t80 0t80 0M70 145V65m0 35q-35-5-28-33 30 3 28 33m0 20q32-2 28-28-30 0-28 28M170 135l20-20 18 0 13-11-2 17-10 12h-21l-8 15m8-13v24m16-24v24"/><path d="M214 64q15-17 31 0m-31 0q-15-17-31 0"/>',
        "W02": '<path d="M25 195h250M45 185V75l45-30 45 30v110M135 185V75l45-30 45 30v110M65 85h18v25H65zm32 0h18v25H97zm58 0h18v25h-18zm32 0h18v25h-18zM73 185v-47h36v47m54 0v-47h36v47M235 146h26v39h-26"/>',
        "W03": '<path d="M24 195h252M45 190V80l47-32 47 32v110M139 190V80l47-32 47 32v110M63 126q26-42 58 0M64 144q25-36 55 0m-55 17q24-27 54 0"/><circle cx="183" cy="110" r="16"/><path d="m169 154 14-18 14 18-14 17zM224 54l16-16m-4 20 18-5"/>',
        "W04": '<path d="M30 195h240M50 185V65h200v120M43 65l107-24 107 24M77 185V98h48v87m50 0V98h48v87M50 83h200m-100-20v122M60 83v102m180-102v102M78 112h46m53 0h46M79 132h45m53 0h46M80 152h44m53 0h46"/>',
        "W05": '<path d="M30 195h240M50 185V60h200v125M50 78h200M70 100h160v55H70zM70 100q26 10 24 55m136-55q-26 10-24 55M90 174h10m20 0h10m20 0h10m20 0h10m20 0h10M63 40h174"/>',
        "W06": '<path d="M25 190q35-12 70 0t70 0t110 0M30 212q35-12 70 0t70 0t110 0M125 176q25-35 50 0M50 172V94m0 22c-40 2-28-43-10-40-8-31 38-34 37 0 31-5 35 42-5 40M230 170v-55m-20 0h40m-38-23h36m-30-21h25M108 60h65"/>',
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 240" role="img" aria-label="' + esc(title) + '"><title>' + esc(title) + '</title><g fill="none" stroke="#000" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">' + shapes.get(kind, shapes["W06"]) + "</g></svg>"


def hero_art():
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 410 300" role="img" aria-label="從來源到Wiki再到教學的示意圖"><title>從來源到Wiki再到教學</title><g fill="none" stroke="#000" stroke-width="2"><path d="M40 45h110v140H40zm14-12h110v140M62 73h65M62 96h65M62 119h48M62 142h65M175 130h55m-12-12 12 12-12 12M250 52h110v140H250M263 69h84v105h-84M278 86h53M278 110h53M278 135h36M96 225h217M202 200v50"/><circle cx="96" cy="225" r="8" fill="#fff"/><circle cx="202" cy="225" r="8" fill="#fff"/><circle cx="313" cy="225" r="8" fill="#fff"/></g><g font-size="19" text-anchor="middle" fill="#000"><text x="99" y="275">官方資料</text><text x="202" y="275">Wiki整理</text><text x="313" y="275">教學簡報</text></g></svg>'


def build_wiki(articles, sources, date):
    cards = "".join('<a class="article-link" data-wiki="' + a["wiki_id"] + '" href="#' + a["wiki_id"] + '"><span class="index">' + a["wiki_id"] + "／" + esc(a["theme"]) + "</span><h3>" + esc(a["title"]) + "</h3><p>" + esc(a["teaching_point"] or a["summary"].split("。")[0] + "。") + "</p></a>" for a in articles)
    nav = "".join('<a data-wiki="' + a["wiki_id"] + '" href="#' + a["wiki_id"] + '">' + a["wiki_id"] + esc(a["title"]) + "</a>" for a in articles)
    data = {"articles": articles, "sources": sources, "date": date}
    content = f'''<main id="main" class="wrap">
    <div id="wiki-home"><section class="hero"><div><p class="eyebrow">第十週作業1110／LLM Wiki</p><h1>台中景點入門<br>從自然生態到城市文化</h1><p class="lead">先理解景點的特色，再練習比較和查證。這份Wiki把官方資料整理成彼此連結的知識頁，讓教學簡報的每個重點都能回到來源。</p><div class="hero-actions"><a class="button" href="slides.html">開始教學簡報<span aria-hidden="true">→</span></a><a class="button" href="#W07">先看主題比較</a></div><div class="inline-stats"><span><strong>6</strong>篇官方資料</span><span><strong>8</strong>篇Wiki內容</span><span><strong>12</strong>頁教學簡報</span></div></div><div class="hero-art">{hero_art()}</div></section>
    <section class="section" aria-labelledby="knowledge-heading"><div class="section-heading"><h2 id="knowledge-heading">從一個問題開始閱讀</h2><a class="small" href="process.html">查看建立流程與紀錄</a></div><div class="search-row"><label class="sr-only" for="wiki-search">搜尋Wiki</label><input id="wiki-search" type="search" placeholder="搜尋景點、自然生態、老屋再利用…" autocomplete="off"><span id="search-status" class="search-status" aria-live="polite"></span></div><div class="article-grid">{cards}</div><p id="empty-result" class="empty-result" hidden>目前沒有符合的內容，請改用景點名稱或主題關鍵字。</p></section>
    <section class="section"><div class="rule-list"><div><h3>這份Wiki能告訴你什麼</h3><p>景點的基本特色、空間用途與主題比較。每頁保留來源編號、官方連結和資料讀取日期，方便核對。</p></div><div><h3>哪些問題需要再查一次</h3><p>即時天氣、潮汐、票價、營業時間和交通時間都不在這份教材的資料範圍。資料中沒有的答案，會直接說明不足。</p></div></div></section>
    <footer class="site-footer"><p>資料讀取日期：{esc(date)}。本教材的分類是教學整理，並非官方排名或一日遊動線。</p><div class="link-row"><a href="data/sources.json" download>下載來源紀錄</a><a href="data/ingest.json" download>下載讀取紀錄</a><a href="data/slide_map.json" download>下載簡報對應表</a><a href="process.html#checks">查看檢查紀錄</a></div></footer></div>
    <div id="wiki-reader" hidden><div class="wiki-layout"><aside class="wiki-nav" aria-label="Wiki目錄"><p><a href="index.html">←回Wiki首頁</a></p>{nav}<p class="small">先看資料，再看資料不能回答什麼。</p></aside><article class="article-view"><p class="breadcrumbs">台中景點入門／Wiki知識頁</p><h1 id="article-title"></h1><p id="article-meta" class="article-meta"></p><div id="article-content" class="article-content"></div><section class="related"><h2>回到官方來源</h2><ol id="article-sources" class="source-list"></ol><h3>接著可以閱讀</h3><div id="article-related" class="link-row"></div><p class="small" style="margin-top:22px"><a id="article-markdown" download>下載這一頁的Markdown</a>｜<a href="slides.html">開啟教學簡報</a></p></section></article></div></div>
    </main><script type="application/json" id="wiki-data">{script_json(data)}</script>'''
    return page("台中景點入門LLM Wiki", content, "wiki", (TEMPLATES / "wiki.js").read_text(encoding="utf-8"))


def source_footer(wiki_ids, source_ids, articles, source_index, note=""):
    wlinks = "、".join('<a href="index.html#' + wid + '">' + wid + esc(articles[wid]["title"]) + "</a>" for wid in wiki_ids)
    slinks = "、".join('<a href="' + esc(source_index[sid]["canonical_url"]) + '" target="_blank" rel="noopener noreferrer">' + sid + "</a>" for sid in source_ids)
    return '<div class="slide-source">Wiki：' + (wlinks or "本教材自編教學引導") + ("<br>來源：" + slinks if slinks else "") + ("<br>" + esc(note) if note else "") + "</div>"


def build_slides(article_list, sources):
    articles = {a["wiki_id"]: a for a in article_list}
    source_index = {s["source_id"]: s for s in sources}
    all_sources = list(source_index)
    slides = []

    def add(title, wiki_ids, source_ids, body, points=None, note=""):
        n = len(slides) + 1
        slides.append({"page": n, "title": title, "wiki_ids": wiki_ids, "source_ids": source_ids, "wiki_files": [articles[w]["filename"] for w in wiki_ids], "points": points or [], "html": '<section class="slide' + (' active' if n == 1 else '') + '" id="slide-' + str(n) + '" data-title="' + esc(title) + '" aria-label="第' + str(n) + '頁，共12頁"><p class="slide-number">' + str(n).zfill(2) + '／12</p>' + body + source_footer(wiki_ids, source_ids, articles, source_index, note) + '</section>'})

    add("台中景點入門", [], [], '<div class="slide-columns"><div><p class="eyebrow">從自然生態到城市文化</p><h1>認識台中的6種景點特色</h1><p class="slide-lead">透過6個景點，練習從自然、空間改造、藝術與城市生活理解一個地方。</p><ul class="slide-bullets"><li>說出6個景點各自的學習重點。</li><li>比較相近主題的共同點與差異。</li><li>分辨資料能回答和不能回答的問題。</li></ul></div><div class="hero-art">' + hero_art() + '</div></div>', ["認識6個景點", "比較共同點與差異", "練習來源判讀"], "學習目標與教學順序為本教材自編，景點內容從後續Wiki頁面取得。")

    overview = '<h2>先用主題建立概念</h2><p class="slide-lead">不是把地名背起來，而是知道每一頁可以幫你理解什麼。</p><div class="overview-grid">' + "".join('<div class="overview-entry"><p class="small">' + s["wiki_id"] + '</p><h3>' + esc(s["attraction"]) + '</h3><p>' + esc(s["theme"]) + '</p></div>' for s in sources) + '</div><p class="takeaway">分類是為了學習，不是官方排名，也不是一日遊動線。</p>'
    add("先用主題建立概念", ["W07"], all_sources, overview, [s["attraction"] + "：" + s["theme"] for s in sources])

    for s in sources:
        a = articles[s["wiki_id"]]
        facts = a["facts"]
        # Facts and teaching point come from the Wiki, never straight from JSON.
        if len(facts) < 3 or not a["teaching_point"]:
            raise ValueError("Wiki缺少可回查的資料或學習重點：" + a["wiki_id"])
        body = '<h2>' + esc(a["title"]) + '</h2><div class="slide-columns"><div><p class="eyebrow">' + esc(a["theme"]) + '</p><ul class="slide-bullets">' + "".join('<li>' + esc(fact) + '</li>' for fact in facts) + '</ul><p class="takeaway">學習重點：' + esc(a["teaching_point"]) + '</p></div><div><div class="slide-art">' + icon(a["wiki_id"], a["theme"] + "主題示意圖") + '</div><p class="slide-art-label">主題示意圖，並非現場照片或建築測繪。</p><p class="note">想一想：' + esc(a["sections"]["想一想"].split("\n\n")[0]) + '</p></div></div>'
        add(a["title"] + "的學習重點", [a["wiki_id"]], a["source_ids"], body, facts)

    comparisons = [
        ("想認識自然與城市空間", "先查高美濕地與臺中公園。", "高美濕地著重環境與生物棲地；臺中公園可連到城市歷史與休閒設施。兩者都有戶外空間，但學習重點不同。"),
        ("想理解老屋如何重新使用", "先查審計新村與宮原眼科。", "審計新村的資料重點是宿舍轉型與青年創業；宮原眼科則可觀察保留的建築元素與新設計。"),
        ("想看藝術和空間的關係", "比較彩虹村與臺中國家歌劇院。", "彩虹村可從彩繪與後續共創理解空間變化；歌劇院可從劇場和公共空間的用途理解表演藝術。這是本教材的比較整理。"),
    ]
    body = '<h2>先看共同點，再說出差異</h2><p class="slide-lead">同樣與空間有關的景點，也可以有不同的觀察角度。</p><div class="scenario-grid">' + "".join('<section class="scenario"><h3>' + esc(t) + '</h3><p>' + esc(p) + '</p><button type="button" data-scenario="scenario-' + str(i) + '" aria-expanded="false" aria-controls="scenario-' + str(i) + '">查看比較理由</button><p class="scenario-response" id="scenario-' + str(i) + '" hidden>' + esc(answer) + '</p></section>' for i, (t, p, answer) in enumerate(comparisons, 1)) + '</div>'
    add("先看共同點再說出差異", ["W07", "W03", "W05"], all_sources, body, [x[2] for x in comparisons], "情境問題為本教材自編；比較結論依所列Wiki整理，不推定交通、票價或現場狀況。")

    boundary = articles["W08"]
    body = '<h2>有景點資料，不代表每題都有答案</h2><div class="knowledge-columns"><section><h3>可以依資料回答</h3><p>' + esc(boundary["sections"]["什麼可以回答"]) + '</p><p>回答時保留Wiki編號與來源，讓讀者能回去核對。</p></section><section><h3>需要重新查詢</h3><p>' + esc(boundary["sections"]["什麼需要重新查詢"]) + '</p></section></div><p class="takeaway">例如問"高美濕地現在幾度？"，這份Wiki應說明缺少即時氣象資料，不能自己補一個溫度。</p>'
    add("資料的邊界", ["W08"], all_sources, body, [boundary["sections"]["什麼可以回答"], boundary["sections"]["什麼需要重新查詢"]])

    quizzes = [
        {"q": "想理解濕地環境和生物棲息的關係，應先閱讀哪一頁？", "choices": [("高美濕地", True, "W01把濕地環境與生物棲息連在一起。"), ("宮原眼科", False, "W04的重點是建築元素與老屋再利用。") ]},
        {"q": "想比較舊空間如何被重新使用，哪一組最直接？", "choices": [("審計新村與宮原眼科", True, "W07比較宿舍轉型和舊建築加入新設計。"), ("高美濕地與臺中公園", False, "這組可比較自然生態與城市休閒空間。") ]},
        {"q": "Wiki沒有今天的天氣資料時，應該怎麼做？", "choices": [("依印象補上今天的溫度", False, "景點介紹無法證明即時氣溫。"), ("說明資料不足，再查最新官方資訊", True, "W08要求把已有資料與需要重新查詢的資訊分開。") ]},
    ]
    quiz_html = '<h2>用3題確認自己看懂了</h2><p class="slide-lead">選擇答案後會出現回饋，可以回到Wiki找到理由。</p><div class="quiz-grid">'
    for i, q in enumerate(quizzes, 1):
        quiz_html += '<section class="quiz-card" data-question="' + str(i) + '"><h3>' + str(i) + '.' + esc(q["q"]) + '</h3><div class="quiz-options">'
        for label, correct, feedback in q["choices"]:
            quiz_html += '<button type="button" aria-pressed="false" data-correct="' + str(correct).lower() + '" data-feedback="' + esc(feedback) + '">' + esc(label) + '</button>'
        quiz_html += '</div><p class="quiz-feedback" aria-live="polite">選擇一個答案。</p></section>'
    quiz_html += '</div><p id="quiz-total" class="quiz-total" aria-live="polite">已作答0/3題。</p><p class="print-note">列印版參考答案：第1題高美濕地；第2題審計新村與宮原眼科；第3題說明資料不足，再查最新官方資訊。</p>'
    add("學習檢核", ["W01", "W04", "W07", "W08"], all_sources, quiz_html, [q["q"] for q in quizzes], "測驗題與選項為本教材自編，答案依Wiki內容判斷。")

    sources_html = '<h2>帶走3個重點，保留6個來源</h2><p class="deck-summary">用主題理解景點；用比較看見差異；用來源確認答案。</p><div class="deck-source-grid">' + "".join('<p><strong>' + s["source_id"] + esc(s["attraction"]) + '</strong><br>' + esc(s["publisher"]) + '<br><a href="' + esc(s["canonical_url"]) + '" target="_blank" rel="noopener noreferrer">' + esc(s["title"]) + '</a></p>' for s in sources) + '</div><p class="takeaway">下一步：回到<a href="index.html">Wiki知識庫</a>，挑2個景點，說出一個共同點和一個差異。</p>'
    add("總結與資料來源", ["W07", "W08"], all_sources, sources_html, ["用主題理解景點", "用比較看見差異", "用來源確認答案"])

    options = "".join('<option value="' + str(s["page"] - 1) + '">' + str(s["page"]).zfill(2) + '.' + esc(s["title"]) + '</option>' for s in slides)
    content = '<main id="main" class="deck-shell"><div class="deck-topline"><p>台中景點入門／教學HTML簡報</p><label for="slide-select"><span class="sr-only">跳到指定頁面</span><select id="slide-select">' + options + '</select></label></div><div class="deck-progress" aria-hidden="true"><span id="progress-fill" style="width:8.333%"></span></div>' + "".join(s["html"] for s in slides) + '</main><footer class="deck-controls"><div class="deck-controls-inner"><div class="control-buttons"><button id="previous" type="button" aria-label="上一頁">←上一頁</button><button id="next" type="button" aria-label="下一頁">下一頁→</button></div><span id="current-page" class="page-count" aria-live="polite">1/12</span><span class="keyboard-hint">←→換頁／Home回首頁／End到最後</span><button id="print-deck" class="print-button" type="button">列印全部簡報</button></div></footer>'
    serializable = [{k: v for k, v in s.items() if k != "html"} for s in slides]
    return page("台中景點入門教學HTML簡報", content, "slides", (TEMPLATES / "slides.js").read_text(encoding="utf-8")), serializable


def workflow_svg():
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 820" role="img" aria-labelledby="workflow-title"><title id="workflow-title">Wiki到教學HTML簡報的檢查流程</title><rect width="1040" height="820" fill="#fff"/><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#000"/></marker></defs><g fill="#fff" stroke="#000" stroke-width="2"><rect x="330" y="20" width="370" height="60"/><rect x="330" y="120" width="370" height="60"/><path d="M515 220l180 80-180 80-180-80z" fill="#f5f5f2"/><rect x="30" y="270" width="220" height="60"/><rect x="330" y="420" width="370" height="60"/><rect x="330" y="520" width="370" height="60"/><rect x="330" y="620" width="370" height="60"/><rect x="330" y="730" width="370" height="60"/><rect x="780" y="520" width="230" height="60"/></g><g fill="none" stroke="#000" stroke-width="2" marker-end="url(#arrow)"><path d="M515 80v40M515 180v40M515 380v40M515 480v40M515 580v40M515 680v50M335 300h-85M140 270V150h190M700 550h80M895 520V450H700M700 650h195v-70"/></g><g fill="#000" font-family="Times New Roman,標楷體,DFKai-SB,serif" font-size="25" text-anchor="middle"><text x="515" y="59">討論需求與資料範圍</text><text x="515" y="159">取得官方資料</text><text x="515" y="293">正文與來源</text><text x="515" y="325">完整嗎</text><text x="140" y="308">替換來源再讀取</text><text x="515" y="458">寫入Wiki與建立關聯</text><text x="515" y="558">查詢Wiki與核對教學重點</text><text x="515" y="658">產生HTML與操作檢查</text><text x="515" y="768">確認結果與完成報告</text><text x="895" y="558">修正對應內容</text></g><g fill="#000" font-family="Times New Roman,標楷體,DFKai-SB,serif" font-size="20"><text x="270" y="285">否</text><text x="530" y="410">是</text><text x="705" y="505">來源不符</text><text x="710" y="638">內容或版面問題</text><text x="530" y="715">通過</text></g></svg>'''


def browser_checks_html(browser_checks):
    if not browser_checks:
        return '<p>瀏覽器互動檢查尚未登錄。本頁不把靜態檢查當成實際點擊或版面檢查成功。</p>'
    if isinstance(browser_checks, dict):
        records = browser_checks.get("checks", browser_checks.get("results", []))
        checked_at = browser_checks.get("checked_at", browser_checks.get("timestamp", ""))
    else:
        records, checked_at = browser_checks, ""
    output = '<p>檢查時間：' + esc(checked_at) + '</p>' if checked_at else ""
    if isinstance(browser_checks, dict) and browser_checks.get("environment"):
        output += '<p class="small">本次操作環境：' + esc(browser_checks["environment"]) + '</p>'
    for check in records:
        if isinstance(check, str):
            output += '<p>' + esc(check) + '</p>'
        else:
            title = check.get("name", check.get("check", check.get("id", "操作檢查")))
            result = check.get("result", check.get("status", "已記錄"))
            detail = check.get("detail", check.get("details", check.get("observed", "")))
            output += '<div class="check-item"><strong>' + esc(title) + '</strong><p>' + esc(str(result)) + ('。' + esc(detail) if detail else '') + '</p></div>'
    if isinstance(browser_checks, dict) and browser_checks.get("limitations"):
        output += '<p class="small">驗收範圍：' + esc("".join(browser_checks["limitations"])) + '</p>'
    return output


def build_process(ingest, validation, browser_checks, source_data):
    attempts = ingest.get("operations", ingest.get("attempts", ingest.get("records", []))) if isinstance(ingest, dict) else ingest
    if isinstance(ingest, dict):
        summary = ingest.get("summary", {})
    else:
        summary = {}
    # Preserve the source agent's complete log as a download; this table is a
    # display of each recorded attempt, not a manufactured failure statistic.
    rows = []
    for n, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            continue
        aid = attempt.get("operation_id", attempt.get("attempt_id", attempt.get("id", str(n))))
        attraction = attempt.get("attraction", attempt.get("target", attempt.get("source_id", "")))
        status = attempt.get("status", attempt.get("result", "已記錄"))
        status_labels = {"accepted": "採用為主要來源", "supplementary": "補充查核", "rejected": "未取得正文", "needs_body_window": "待補讀正文區段", "no_match": "未找到指定字串"}
        status = status_labels.get(status, status)
        url = attempt.get("url", attempt.get("canonical_url", ""))
        reason = attempt.get("reason", attempt.get("notes", attempt.get("detail", "")))
        if isinstance(reason, (list, dict)):
            reason = json.dumps(reason, ensure_ascii=False)
        body = attempt.get("body_present")
        if body is True:
            status += "，正文已取得"
        elif body is False:
            status = "未取得正文"
        linked = '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(attraction or aid) + '</a>' if url else esc(attraction or aid)
        rows.append('<tr><td>' + esc(aid) + '</td><td>' + linked + '</td><td>' + esc(status) + '</td><td>' + esc(reason) + '</td></tr>')
    table = '<details><summary>展開' + str(len(rows)) + '筆實際open與find紀錄</summary><div class="table-scroll" style="margin-top:18px"><table><thead><tr><th scope="col">紀錄</th><th scope="col">景點與來源</th><th scope="col">讀取結果</th><th scope="col">檢查與處理</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>' if rows else '<p>逐筆讀取紀錄保存在<a href="data/ingest.json">ingest.json</a>，此處依原始紀錄顯示，不另推算次數。</p>'
    rounds = '<div class="table-scroll" style="margin-bottom:22px"><table><thead><tr><th scope="col">階段</th><th scope="col">本次實際結果</th><th scope="col">後續處理</th></tr></thead><tbody><tr><td>首輪讀取</td><td>' + str(summary.get("initial_body_missing", 0)) + '份未取得正文；0份納入Wiki</td><td>改查可讀到正文的官方來源</td></tr><tr><td>補讀與核對後</td><td>接受' + str(summary.get("final_accepted_primary_sources", 0)) + '篇不同主要來源</td><td>編寫Wiki並保留原文定位</td></tr></tbody></table></div><p class="small">資料研究階段記錄' + str(summary.get("read_operations", 0)) + '次open與' + str(summary.get("find_operations", 0)) + '次find；補查與重讀不重複計成新的ingest篇數。這些數字只描述本次執行。</p>'
    stats = '<div class="metric-line"><div><strong>6</strong>篇主要來源</div><div><strong>8</strong>篇Wiki</div><div><strong>12</strong>頁HTML簡報</div><div><strong>' + str(validation["passed_count"]) + '/' + str(validation["check_count"]) + '</strong>項靜態檢查通過</div></div>'
    check_list = ''.join('<div class="check-item"><strong>' + esc(c["name"]) + '</strong><p>' + ('通過' if c["passed"] else '未通過') + '。' + esc(c["detail"]) + '</p></div>' for c in validation["checks"])
    content = '<main id="main" class="wrap"><section class="hero"><div><p class="eyebrow">流程設計與實際紀錄</p><h1>先把資料查清楚<br>再產生教學內容</h1><p class="lead">這一頁保留生成前的設計摘要、來源讀取紀錄、檢查規則與改動原因。資料不足就回到前一步，避免錯誤一路進入簡報。</p></div><div class="hero-art">' + hero_art() + '</div></section>'
    content += '<section class="process-block" id="discussion"><h2>生成前需求與設計討論</h2><p>以下為本次需求與AI協作決策的整理，並非聊天介面的原始截圖。使用ChatGPT的GPT-6AstraPro協助整理資料、建立Wiki、撰寫HTML與檢查；網頁本身不會呼叫LLM。</p><div class="discussion-list"><div class="discussion-entry"><h3>1.先確定主題與閱讀者</h3><p>延續先前台中旅遊小嚮導的題目，這次改成台中景點入門教材，對象是原本不熟悉這些景點的人。</p></div><div class="discussion-entry"><h3>2.先決定資料範圍</h3><p>以6篇可讀到正文的官方資料為基礎，只整理景點特色與空間用途，不推測即時天氣、票價、營業時間或交通時間。</p></div><div class="discussion-entry"><h3>3.再決定知識與簡報的結構</h3><p>建立6篇景點Wiki、1篇主題比較與1篇資料邊界；以學習目標、分類、案例、比較、資料判讀與測驗安排12頁簡報。</p></div><div class="discussion-entry"><h3>4.決定通過條件後才生成</h3><p>來源要有標題、正文、網址與讀取日期；Wiki要有來源編號和關聯頁面；每張簡報都要能回查Wiki。最後再檢查換頁、測驗、連結和版面。</p></div></div><p class="small">維護規則已整理為<a href="AGENTS.md" download>AGENTS.md</a>，新增內容時沿用同一套規則。</p></section>'
    content += '<section class="process-block" id="workflow"><h2>loop與graph如何設計</h2><div class="flow-diagram">' + workflow_svg() + '</div><p class="flow-legend">取得資料時逐篇重複檢查；Wiki或簡報內容不符來源時回去修正；HTML操作或版面有問題時只重做受影響部分。</p><div class="rule-list"><div><h3>資料讀取的loop</h3><p>取得一篇資料後，先確認有景點正文和來源資訊。缺少正文就替換官方來源再讀取，完成後才進入Wiki。</p></div><div><h3>教學內容的loop</h3><p>查詢Wiki、整理重點、比對來源。若來源不支持某個說法，先刪除或修正，再生成對應頁面。</p></div></div></section>'
    content += '<section class="process-block" id="ingest"><h2>一次實際資料讀取的結果</h2>' + stats + '<p>原始臺中觀光頁雖能開啟，但本次讀取到的內容缺少景點正文。這些頁面沒有算入成功篇數；改用國家公園署、觀光署及官方開放資料頁，確認正文後才建立6篇主要來源。</p>' + rounds + table + '<p class="small" style="margin-top:18px">完整紀錄：<a href="data/ingest.json" download>ingest.json</a>。主要來源與正文定位：<a href="data/sources.json" download>sources.json</a>。</p></section>'
    content += '<section class="process-block" id="checks"><h2>實際檢查紀錄</h2><h3>靜態內容與程式檢查</h3><p class="small">本次建置時間：' + esc(validation["checked_at"]) + '。以下由scripts/build.py實際執行，涵蓋資料結構與程式語法。</p>' + check_list + '<h3 style="margin-top:28px">瀏覽器操作與版面檢查</h3>' + browser_checks_html(browser_checks) + '<p class="small" style="margin-top:20px"><a href="validation.json" download>下載靜態檢查結果</a>｜<a href="data/slide_map.json" download>下載Wiki與簡報對應表</a></p></section>'
    content += '<section class="process-block" id="reflection"><h2>為什麼把檢查往前移</h2><p>這次最明顯的問題出現在取得資料的節點：網址可以開啟，不代表真的取得了景點介紹。如果直接把導覽和頁尾當作資料，後面的Wiki就可能沒有足夠依據。</p><p>因此流程增加了正文完整性檢查，放在ingest之後、Wiki生成之前。除了確認網址，也要看標題、正文和來源是否齊全。這樣不用等到簡報完成，才回頭找整份內容的問題。</p><p>內容整理也保留2個例子：高美濕地不同頁面的面積口徑不一，所以教材不混用面積數字；彩虹村資料包含早期創作與後續共創，因此不把所有作品都歸給同一個人。</p></section><footer class="site-footer"><p>本頁是本次實作的記錄。建置程式可重現已整理資料的網站；如要更新內容，必須重新取得資料、核對Wiki並執行檢查。</p><div class="link-row"><a href="index.html">回Wiki</a><a href="slides.html">閱讀教學簡報</a><a href="README.md" download>下載使用說明</a></div></footer></main>'
    return page("製作流程與紀錄｜台中景點入門", content, "process")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag in ("a", "img", "script", "link"):
            url = attrs.get("href") if tag in ("a", "link") else attrs.get("src")
            if url:
                self.links.append(url)


def validate(article_list, source_data, slides, final=False):
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    sources = source_data["sources"]
    sids = [s["source_id"] for s in sources]
    wids = [a["wiki_id"] for a in article_list]
    check("主要來源數量", len(sources) >= 5 and len(sids) == len(set(sids)), str(len(sources)) + "篇主要來源，來源編號不重複。")
    required = ["title", "publisher", "canonical_url", "accessed_at", "summary", "evidence_location"]
    missing = [s["source_id"] + ":" + k for s in sources for k in required if not s.get(k)]
    no_body = [s["source_id"] for s in sources if not s.get("body_present")]
    check("正文與來源欄位", not missing and not no_body, "6篇都有正文確認、標題、網址、發布者、讀取日期與正文定位。" if not missing and not no_body else ";".join(missing + no_body))
    broken_sources = [(a["wiki_id"], sid) for a in article_list for sid in a["source_ids"] if sid not in sids]
    check("Wiki來源對應", len(article_list) == 8 and not broken_sources, str(len(article_list)) + "篇Wiki的來源編號均可在sources.json找到。")
    broken_related = [(a["wiki_id"], wid) for a in article_list for wid in a["related"] if wid not in wids]
    check("Wiki關聯頁面", not broken_related, "所有關聯Wiki頁面存在，沒有指向不存在的Wiki編號。" if not broken_related else str(broken_related))
    wrong_map = [(s["page"], wid) for s in slides for wid in s["wiki_ids"] if wid not in wids] + [(s["page"], sid) for s in slides for sid in s["source_ids"] if sid not in sids]
    check("簡報與Wiki對應", len(slides) == 12 and not wrong_map, str(len(slides)) + "頁簡報保留Wiki編號及來源；第1頁為自編學習引導。")
    facts_match = all(slides[i + 2]["points"] == article_list[i]["facts"] for i in range(6))
    check("景點簡報讀取Wiki", facts_match, "第3至8頁的重點直接取自對應Markdown的可回查的資料段落。")
    user_text = "\n".join([a["search_text"] for a in article_list] + ["\n".join(s["points"]) for s in slides])
    bad_quotes = sorted(set(re.findall(r"[「」『』“”‘’]", user_text)))
    bad_spacing = re.findall(r"[\u3400-\u9fff]\s+[A-Za-z0-9]|[A-Za-z0-9]\s+[\u3400-\u9fff]", user_text)
    check("文字與引號格式", not bad_quotes and not bad_spacing, "Wiki和簡報內容未出現上下引號、彎引號或中文與英文數字之間的空格。" if not bad_quotes and not bad_spacing else str(bad_quotes + bad_spacing))
    js_results = []
    node = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE", "node")
    for name in ("wiki.js", "slides.js"):
        try:
            result = subprocess.run([node, "--check", str(TEMPLATES / name)], capture_output=True, text=True, timeout=30)
            js_results.append((name, result.returncode == 0, result.stderr.strip()))
        except (OSError, subprocess.SubprocessError) as error:
            js_results.append((name, False, str(error)))
    check("JavaScript語法", all(x[1] for x in js_results), "Wiki搜尋與簡報互動腳本均通過Node語法檢查。" if all(x[1] for x in js_results) else str(js_results))
    link_errors, duplicate_ids = [], []
    outputs = ["index.html", "slides.html"] + (["process.html"] if final else [])
    for filename in outputs:
        parser = LinkParser()
        parser.feed((DIST / filename).read_text(encoding="utf-8"))
        duplicate_ids += [filename + ":" + x for x in set(parser.ids) if parser.ids.count(x) > 1]
        for url in parser.links:
            if url.startswith(("https://", "http://", "mailto:", "data:")) or url.startswith("#"):
                continue
            target = url.split("#")[0].split("?")[0]
            if target and not (DIST / target).exists():
                link_errors.append(filename + "→" + target)
    check("本地連結與HTML識別", not link_errors and not duplicate_ids, "本地檔案連結均有目標，HTML沒有重複id；外部網址僅檢查保留，未宣稱即時可用。" if not link_errors and not duplicate_ids else str(link_errors + duplicate_ids))
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    check("字型與黑字樣式", all(x in css for x in ('"Times New Roman"', '"標楷體"', '"DFKai-SB"', "text-align:justify", "color:#000")), "樣式指定Times New Roman、標楷體與黑字，段落左右對齊；實際字型顯示仍取決於裝置安裝字型。")
    return {"checked_at": NOW, "kind": "static_checks", "check_count": len(checks), "passed_count": sum(c["passed"] for c in checks), "all_passed": all(c["passed"] for c in checks), "checks": checks, "browser_qa": "由主執行者在瀏覽器完成後另存data/browser_checks.json；靜態檢查不代表瀏覽器操作已完成。"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Optional reviewed content directory for the initial import")
    args = parser.parse_args()
    if args.input:
        (ROOT / "data").mkdir(exist_ok=True)
        shutil.copy2(args.input / "wiki_sources.json", ROOT / "data/sources.json")
        shutil.copy2(args.input / "ingest_log.json", ROOT / "data/ingest.json")
        for path in sorted((args.input / "wiki").glob("*.md")):
            shutil.copy2(path, ROOT / "wiki" / path.name)
    source_data = read_json(ROOT / "data/sources.json")
    sources = source_data["sources"]
    source_index = {s["source_id"]: s for s in sources}
    article_list = [parse_wiki(path, source_index) for path in sorted((ROOT / "wiki").glob("W*.md"))]
    if len(article_list) != 8:
        raise ValueError("Expected8Wiki文章，實際為" + str(len(article_list)))
    ingest = read_json(ROOT / "data/ingest.json")
    browser_checks = read_json(ROOT / "data/browser_checks.json", {})
    DIST.mkdir(exist_ok=True)
    (DIST / "data").mkdir(exist_ok=True)
    (DIST / "wiki").mkdir(exist_ok=True)
    (DIST / "assets").mkdir(exist_ok=True)
    for path in (ROOT / "wiki").glob("*.md"):
        shutil.copy2(path, DIST / "wiki" / path.name)
    for path in (ROOT / "data").glob("*.json"):
        shutil.copy2(path, DIST / "data" / path.name)
    for name in ("AGENTS.md", "README.md"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, DIST / name)
    wiki_html = build_wiki(article_list, sources, source_data["accessed_date"])
    slides_html, slides = build_slides(article_list, sources)
    (DIST / "index.html").write_text(wiki_html, encoding="utf-8")
    (DIST / "slides.html").write_text(slides_html, encoding="utf-8")
    (DIST / "assets/workflow.svg").write_text(workflow_svg(), encoding="utf-8")
    maps = [{k: s[k] for k in ("page", "title", "wiki_ids", "wiki_files", "source_ids")} for s in slides]
    write_json(ROOT / "slide_map.json", maps)
    write_json(ROOT / "slides_data.json", slides)
    write_json(DIST / "data/slide_map.json", maps)
    write_json(DIST / "data/slides_data.json", slides)
    backlinks = {a["wiki_id"]: [b["wiki_id"] for b in article_list if a["wiki_id"] in b["related"]] for a in article_list}
    write_json(ROOT / "wiki/backlinks.json", backlinks)
    write_json(DIST / "wiki/backlinks.json", backlinks)
    write_json(DIST / "data/wiki_manifest.json", [{k: a[k] for k in ("wiki_id", "title", "filename", "source_ids", "raw_sha256", "related")} for a in article_list])
    # The process page and validation record are linked from the Wiki. Create
    # them before the final link check, then update with the measured results.
    (DIST / "validation.json").write_text("{}", encoding="utf-8")
    (DIST / "process.html").write_text("<!doctype html><html lang=\"zh-Hant\"><title>正在建置</title></html>", encoding="utf-8")
    validation = validate(article_list, source_data, slides)
    (DIST / "process.html").write_text(build_process(ingest, validation, browser_checks, source_data), encoding="utf-8")
    validation = validate(article_list, source_data, slides, final=True)
    write_json(DIST / "validation.json", validation)
    write_json(ROOT / "data/static_checks.json", validation)
    (DIST / "process.html").write_text(build_process(ingest, validation, browser_checks, source_data), encoding="utf-8")
    print(json.dumps({"built_at": NOW, "sources": len(sources), "wiki_pages": len(article_list), "slides": len(slides), "static_checks_passed": validation["passed_count"], "static_checks_total": validation["check_count"], "all_passed": validation["all_passed"], "output": str(DIST)}, ensure_ascii=False))
    if not validation["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
