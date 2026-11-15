(()=>{
  'use strict';
  const data=JSON.parse(document.getElementById('wiki-data').textContent);
  const entries=data.articles;
  const sourceIndex=Object.fromEntries(data.sources.map(s=>[s.source_id,s]));
  const $=s=>document.querySelector(s);
  const home=$('#wiki-home');const article=$('#wiki-reader');
  let markdownUrl=null;
  const search=$('#wiki-search');const status=$('#search-status');
  const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function showHome(){home.hidden=false;article.hidden=true;document.title='台中景點入門LLM Wiki';}
  function showArticle(id){
    const a=entries.find(x=>x.wiki_id===id);if(!a){showHome();return;}
    home.hidden=true;article.hidden=false;
    $('#article-title').textContent=a.title;
    $('#article-meta').textContent=a.wiki_id+'｜'+a.theme+'｜來源'+a.source_ids.join('、')+'｜整理日期'+data.date;
    $('#article-content').innerHTML=a.html;
    $('#article-sources').innerHTML=a.source_ids.map(sid=>{const s=sourceIndex[sid];return '<li><a href="'+escapeHtml(s.canonical_url)+'" target="_blank" rel="noopener noreferrer">'+escapeHtml(sid+s.title)+'</a>。'+escapeHtml(s.publisher)+'；查閱日期'+escapeHtml(s.accessed_at.slice(0,10))+'。</li>';}).join('');
    $('#article-related').innerHTML=a.related.map(r=>{const b=entries.find(x=>x.wiki_id===r);return b?'<a href="#'+b.wiki_id+'">'+escapeHtml(b.title)+'</a>':'';}).join('');
    if(markdownUrl)URL.revokeObjectURL(markdownUrl);
    markdownUrl=URL.createObjectURL(new Blob([a.markdown],{type:'text/markdown;charset=utf-8'}));
    $('#article-markdown').href=markdownUrl;
    $('#article-markdown').download=a.filename;
    document.querySelectorAll('.wiki-nav a[data-wiki]').forEach(x=>x.setAttribute('aria-current',String(x.dataset.wiki===id)));
    document.title=a.title+'｜台中景點入門LLM Wiki';
  }
  function route(){const id=decodeURIComponent(location.hash.slice(1));if(/^W\d{2}$/.test(id)){showArticle(id);}else{showHome();}}
  function filter(){
    const q=search.value.trim().toLocaleLowerCase();let count=0;
    document.querySelectorAll('.article-link').forEach(card=>{const a=entries.find(x=>x.wiki_id===card.dataset.wiki);const match=!q||(a.title+a.theme+a.search_text).toLocaleLowerCase().includes(q);card.hidden=!match;if(match)count++;});
    status.textContent='找到'+count+'篇Wiki內容';$('#empty-result').hidden=count!==0;
  }
  search.addEventListener('input',filter);
  window.addEventListener('hashchange',()=>{route();window.scrollTo({top:0,behavior:'instant'});});
  route();filter();
})();
