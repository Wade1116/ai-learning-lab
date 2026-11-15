(()=>{
  'use strict';
  const slides=[...document.querySelectorAll('.slide')];
  const menu=document.getElementById('slide-select');
  const current=document.getElementById('current-page');
  const progress=document.getElementById('progress-fill');
  const prev=document.getElementById('previous');const next=document.getElementById('next');
  let index=0;
  function pageFromHash(){const value=Number(location.hash.replace('#slide-',''));return Number.isInteger(value)&&value>=1&&value<=slides.length?value-1:0;}
  function show(n,changeHash=true){
    index=Math.max(0,Math.min(slides.length-1,n));
    slides.forEach((slide,i)=>{slide.classList.toggle('active',i===index);slide.setAttribute('aria-hidden',i===index?'false':'true');});
    current.textContent=(index+1)+'/'+slides.length;
    progress.style.width=((index+1)/slides.length*100)+'%';
    menu.value=String(index);prev.disabled=index===0;next.disabled=index===slides.length-1;
    document.title=(index+1)+'/'+slides.length+' '+slides[index].dataset.title+'｜台中景點入門';
    if(changeHash&&location.hash!=='#slide-'+(index+1)){history.replaceState(null,'','#slide-'+(index+1));}
    window.scrollTo({top:0,behavior:'instant'});
  }
  prev.addEventListener('click',()=>show(index-1));next.addEventListener('click',()=>show(index+1));
  menu.addEventListener('change',()=>show(Number(menu.value)));
  document.getElementById('print-deck').addEventListener('click',()=>window.print());
  document.addEventListener('keydown',e=>{
    if(e.altKey||e.ctrlKey||e.metaKey||['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;
    if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();show(index+1);}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();show(index-1);}
    else if(e.key==='Home'){e.preventDefault();show(0);}
    else if(e.key==='End'){e.preventDefault();show(slides.length-1);}
  });
  window.addEventListener('hashchange',()=>show(pageFromHash(),false));
  document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',()=>{
    const output=document.getElementById(button.dataset.scenario);const open=output.hidden;
    output.hidden=!open;button.setAttribute('aria-expanded',String(open));button.textContent=open?'收起比較理由':'查看比較理由';
  }));
  const chosen={};
  document.querySelectorAll('.quiz-options button').forEach(button=>button.addEventListener('click',()=>{
    const card=button.closest('.quiz-card');const qid=card.dataset.question;
    const correct=button.dataset.correct==='true';chosen[qid]=correct;
    card.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    card.querySelector('.quiz-feedback').textContent=(correct?'答對了。':'再想一下。')+button.dataset.feedback;
    const answered=Object.keys(chosen).length;const score=Object.values(chosen).filter(Boolean).length;
    document.getElementById('quiz-total').textContent='已作答'+answered+'/3題，目前答對'+score+'題。可以重新選擇，依回饋回到Wiki複習。';
  }));
  show(pageFromHash(),false);
})();
