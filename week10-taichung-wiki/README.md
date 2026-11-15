# 台中景點入門LLM Wiki與教學HTML簡報

本專案把6篇官方景點資料整理成8篇互相連結的Wiki，再由Wiki內容建立12頁教學HTML簡報。閱讀對象是原本不熟悉台中景點的學習者。

## 本週成果

- Wiki首頁：index.html。
- 教學簡報：slides.html。
- 需求整理、流程與實際紀錄：process.html。

這是ai-learning-lab裡的獨立第十週作業，放在week10-taichung-wiki/。舊網站的首頁、文章、共用CSS和Pages發布設定不因這份教材而改寫。

## 直接開啟與操作

下載此資料夾後，用瀏覽器開啟index.html或slides.html即可。HTML已內嵌必要的資料、樣式與程式，不需要API金鑰、CDN或後端服務。

簡報可使用上一頁、下一頁、左右方向鍵、Home、End及頁面選單。第9頁可展開比較理由，第11頁有3題測驗與回饋；列印按鈕套用全部12頁的列印樣式。

官方來源連結需要網路。中文字型指定標楷體，英文與數字指定Times New Roman；裝置沒有安裝時由瀏覽器使用替代字型。

## 檔案結構

|位置|用途|
|---|---|
|index.html、slides.html、process.html|本週實際發布的3個入口|
|wiki/|8份原始Markdown及反向連結|
|data/sources.json|6篇來源、摘要、正文定位及資料限制|
|data/ingest.json|本次資料讀取的實際紀錄|
|data/browser_checks.json|瀏覽器驗收紀錄，只有完成的項目才記為通過|
|data/pages_export_checks.json|GitHub子目錄匯出與Markdown原文一致檢查|
|templates/|黑白版面、Wiki搜尋及簡報互動程式|
|scripts/build_core.py|從Wiki建立HTML並執行10項靜態檢查|
|scripts/build.py|呼叫核心建置，再匯出適合既有Pages子目錄的版本|
|slide_map.json、slides_data.json|簡報與Wiki、來源的對應及文字|
|AGENTS.md|後續資料與教材的維護規則|

## 重建

需要Python3.9以上與Node.js。Python只用標準庫，Node.js僅用於檢查JavaScript語法。

```bash
python scripts/build.py
```

程式先讀取本資料夾的wiki/、data/與templates/，產生dist/，再把發布內容同步到本資料夾根目錄。GitHub提交保留根目錄發布檔與原始資料，dist/是可重建的中間輸出，不需要另外提交一份。

這個程式不會重新呼叫LLM或自動抓取網站。本次Markdown是由AI閱讀官方來源後協作整理的內容；資料更新必須重新取得來源並核對，再執行建置。

## Markdown原始檔如何保留

既有Pages使用Jekyll發布根目錄，含frontmatter的Markdown可能被轉成網頁。因此Wiki把8份原始Markdown完整嵌入HTML，下載時由瀏覽器建立Blob，保留原本的.md檔名與內容，不依賴伺服器上的.md網址。AGENTS.md與本README也採相同方式提供下載。

原始Markdown仍保留在GitHub的wiki/，可直接用GitHub的Raw功能查看。data/pages_export_checks.json確認內嵌文字與原始檔位元組一致；這項檢查不等於已完成瀏覽器下載驗收。

Jekyll處理規則參考：https://jekyllrb.com/docs/front-matter/。

## 發布方式

本週資料夾新增到Wade1116/ai-learning-lab的main分支後，沿用既有的GitHub Pages建置與部署，不新增或修改repo根目錄工作流程、.nojekyll或_config.yml。

發布是否成功應以對應commit的Pages工作流程結果，以及實際開啟本週index.html、slides.html和process.html為準。程式碼已提交不代表網頁已經部署完成。

## 資料與AI協作

資料讀取日期為2026-11-15。來源由國家公園署、交通部觀光署與臺中市政府觀光旅遊局提供；完整網址與正文定位見data/sources.json。

本次使用ChatGPT的GPT-6AstraPro協助閱讀來源、整理Wiki、製作HTML和檢查結果。教材僅介紹景點特色、空間用途與來源判讀，不提供即時天氣、潮汐、票價、營業時間、交通時間或一日遊動線。主題分類與情境問題是教學整理，不是官方排名。
