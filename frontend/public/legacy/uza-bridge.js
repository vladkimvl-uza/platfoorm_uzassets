/* uza-bridge.js — Pack 7.69.4 bulk-extract.
 * has access to its UI ecosystem (glass-select widgets, drill modals, count-up
 * animation, design system injection, XLSX loader, edit menu).
 *
 * Source line ranges:
 */


function _editMenu(id,items){
var btns='';
for(var i=0;i<items.length;i++){
var it=items[i];
if(it[0]==='---'){btns+='<div class="sep"></div>';continue;}
btns+='<button class="'+(it[3]?'danger':'')+'" onclick="toggleEditMenu(\''+id+'\');'+it[2]+'">'+it[0]+' '+it[1]+'</button>';
}
return '<div class="edit-menu-wrap">'
+'<div class="edit-menu-btn" onclick="event.stopPropagation();toggleEditMenu(\''+id+'\')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg></div>'
+'<div class="edit-menu-dd" id="'+id+'">'+btns+'</div></div>';
}


async function _ensureXLSX(){
if(typeof XLSX!=='undefined')return;
if(window._xlsxLoadingPromise) return window._xlsxLoadingPromise;
window._xlsxLoadingPromise=new Promise(function(r,j){
var s=document.createElement('script');
s.src='https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js';
s.onload=function(){r();};
s.onerror=function(){window._xlsxLoadingPromise=null;j(new Error('SheetJS не загружен'));};
document.head.appendChild(s);
setTimeout(function(){if(typeof XLSX==='undefined'){window._xlsxLoadingPromise=null;j(new Error('timeout'));}},10000);
});
return window._xlsxLoadingPromise;
}


function _dlXlsx(wb,name){
var out=XLSX.write(wb,{bookType:'xlsx',type:'array'});
var blob=new Blob([out],{type:'application/octet-stream'});
var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();
setTimeout(function(){URL.revokeObjectURL(a.href);},5000);
}


function _uzFlagCss(size){
  var h = size==='thin' ? '1px' : (size==='medium' ? '2px' : '2.5px');
  return 'height:'+h+';background:linear-gradient(90deg,#0099B5 0%,#0099B5 33%,#CE1126 33%,#CE1126 33.5%,#FFFFFF 33.5%,#FFFFFF 66.5%,#CE1126 66.5%,#CE1126 67%,#1EB53A 67%,#1EB53A 100%);-webkit-print-color-adjust:exact !important;print-color-adjust:exact !important;';
}


function cpDrillCoYear(coName,year){
  if(typeof cpDrillOpen!=='function'||typeof cpCompute!=='function')return;
  var data=cpCompute();
  var loans=(data.loans||[]).filter(function(l){
    if(l.company!==coName)return false;
    var y=cpYearOf(l.dateDue);
    if(year==='gt2032')return y&&y>2032;
    return y===year;
  });
  var sumUsd=loans.reduce(function(a,l){return a+(l.debtUsd||0);},0);
  var coShort=String(coName).replace(/^АО\s*"?/,'').replace(/^"/,'').replace(/"$/,'');
  var yearLbl=year==='gt2032'?'после 2032':String(year)+' г.';
  var rateW=0,rateD=0;
  loans.forEach(function(l){if(l.rate>0&&l.rate<1){rateW+=l.rate*l.debtUsd;rateD+=l.debtUsd;}});
  var avgRate=rateD>0?rateW/rateD:0;
  var maxLoan=loans.slice().sort(function(a,b){return b.debtUsd-a.debtUsd;})[0];
  
  /* Группировка по типам кредитора */
  var byType={};
  loans.forEach(function(l){
    var t=l.lenderType||'other';
    if(!byType[t])byType[t]={amount:0,count:0};
    byType[t].amount+=l.debtUsd;byType[t].count++;
  });
  var typeRows=Object.keys(byType).map(function(t){
    var info=CP_LENDER_TYPES[t]||{label:t,color:'#888'};
    return {label:info.label,value:byType[t].amount,color:info.color,valueText:'$'+(byType[t].amount/1e6).toFixed(0)+'M · '+byType[t].count};
  }).sort(function(a,b){return b.value-a.value;});
  
  cpDrillOpen({
    title:coShort+' · '+yearLbl,
    subtitle:'Платежи компании в этот период',
    accent:year==='gt2032'?'#7F77DD':(year===2026?'#E24B4A':year===2027?'#EF9F27':'#378ADD'),
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    hero:cpDrillHeroHtml({
      value:(sumUsd/1e6).toFixed(0),unit:'млн $',cuDecimals:0,
      label:'К погашению в '+yearLbl,
      sub:loans.length+' кредит'+(loans.length===1?'':loans.length<5?'а':'ов')+(avgRate?' · средневзв. ставка '+(avgRate*100).toFixed(2)+'%':'')+(maxLoan?' · крупнейший $'+(maxLoan.debtUsd/1e6).toFixed(1)+'M':'')
    }),
    sections:[
      typeRows.length>1?{title:'По типу кредитора',count:typeRows.length,body:cpDrillBarsHtml(typeRows)}:null,
      {title:'Кредиты ('+loans.length+')',body:cpDrillLoansTableHtml(loans.slice().sort(function(a,b){return b.debtUsd-a.debtUsd;}),{limit:50})}
    ].filter(Boolean)
  });
}


function cpDrillCoYearAttr(el){
  if(!el)return;
  var co=el.getAttribute('data-co');
  var y=el.getAttribute('data-year');
  if(!co||!y)return;
  cpDrillCoYear(co,y==='gt2032'?'gt2032':parseInt(y,10));
}


function cpDrillCoYearBySlug(slug,year){
  if(!slug||typeof cpCompute!=='function')return;
  var data=cpCompute();
  var company=null;
  for(var i=0;i<(data.loans||[]).length;i++){
    if(cpCompanySlug(data.loans[i].company)===slug){company=data.loans[i].company;break;}
  }
  if(company)cpDrillCoYear(company,year);
}


function cpDrillYearAll(year){
  if(typeof cpDrillOpen!=='function'||typeof cpCompute!=='function')return;
  var data=cpCompute();
  var loans=(data.loans||[]).filter(function(l){
    var y=cpYearOf(l.dateDue);
    if(year==='gt2032')return y&&y>2032;
    return y===year;
  });
  var sumUsd=loans.reduce(function(a,l){return a+(l.debtUsd||0);},0);
  var rateW=0,rateD=0;
  loans.forEach(function(l){if(l.rate>0&&l.rate<1){rateW+=l.rate*l.debtUsd;rateD+=l.debtUsd;}});
  var avgRate=rateD>0?rateW/rateD:0;
  var yearLbl=year==='gt2032'?'после 2032':String(year)+' г.';
  
  /* Группировка по компаниям */
  var byCo={};
  loans.forEach(function(l){
    var co=l.company||'—';
    if(!byCo[co])byCo[co]={amount:0,count:0};
    byCo[co].amount+=l.debtUsd;byCo[co].count++;
  });
  var yearArg=typeof year==='string'?'\''+year+'\'':String(year);
  var coRows=Object.keys(byCo).map(function(co){
    var coShort=String(co).replace(/^АО\s*"?/,'').replace(/^"/,'').replace(/"$/,'');
    var slug=cpCompanySlug(co);
    return {
      label:coShort,
      value:byCo[co].amount,
      color:cpCompanySectorColor(co),
      valueText:'$'+(byCo[co].amount/1e6).toFixed(0)+'M · '+byCo[co].count,
      onClick:'cpDrillClose();setTimeout(function(){cpDrillCoYearBySlug(\''+slug+'\','+yearArg+');},260)'
    };
  }).sort(function(a,b){return b.value-a.value;});
  
  /* Группировка по валютам */
  var byCur={};
  loans.forEach(function(l){byCur[l.currency]=(byCur[l.currency]||0)+l.debtUsd;});
  var curRows=Object.keys(byCur).map(function(cur){
    return {label:cur,value:byCur[cur],color:cpCurrencyColor(cur),valueText:'$'+(byCur[cur]/1e6).toFixed(0)+'M'};
  }).sort(function(a,b){return b.value-a.value;});
  
  cpDrillOpen({
    title:'Все платежи · '+yearLbl,
    subtitle:'Распределение погашений по компаниям и валютам',
    accent:year==='gt2032'?'#7F77DD':(year===2026?'#E24B4A':year===2027?'#EF9F27':'#378ADD'),
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    hero:cpDrillHeroHtml({
      value:(sumUsd/1e6).toFixed(0),unit:'млн $',cuDecimals:0,
      label:'Σ погашений в '+yearLbl,
      sub:loans.length+' кредит'+(loans.length===1?'':loans.length<5?'а':'ов')+' · '+coRows.length+' компани'+(coRows.length===1?'я':coRows.length<5?'и':'й')+(avgRate?' · ставка '+(avgRate*100).toFixed(2)+'%':'')
    }),
    sections:[
      {title:'По компаниям (клик — детализация)',count:coRows.length,body:cpDrillBarsHtml(coRows)},
      curRows.length>1?{title:'По валютам',count:curRows.length,body:cpDrillBarsHtml(curRows)}:null,
      {title:'Топ-30 кредитов по объёму',body:cpDrillLoansTableHtml(loans.slice().sort(function(a,b){return b.debtUsd-a.debtUsd;}),{limit:30})}
    ].filter(Boolean)
  });
}


function cpDrillYearAllAttr(el){
  if(!el)return;
  var y=el.getAttribute('data-year');
  if(!y)return;
  cpDrillYearAll(y==='gt2032'?'gt2032':parseInt(y,10));
}


window.cpDrillOpen=function(opts){
opts=opts||{};
/* Закрываем предыдущий drill (но НЕ loan modal — он отдельный) */
var prev=document.getElementById('cp-drill-bg');
if(prev)prev.remove();

var bg=document.createElement('div');
bg.id='cp-drill-bg';
bg.className='cp-drill-bg';
bg.onclick=function(e){if(e.target===bg)cpDrillClose();};

var sizeCls='size-'+(opts.size||'lg');
var accent=opts.accent||'#7F77DD';
var accentBg=opts.accentBg||'rgba(127,119,221,.14)';
var icnHtml=opts.icon||'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>';

var heroHtml='';
if(opts.hero){
heroHtml='<div class="cp-drill-hero">'+opts.hero+'</div>';
}

var sectionsHtml='';
if(Array.isArray(opts.sections)){
sectionsHtml=opts.sections.map(function(sec,i){
var delay=(typeof sec.delay==='number'?sec.delay:i*80);
var cnt=sec.count?'<span class="cp-drill-sec-cnt">· '+sec.count+'</span>':'';
return '<div class="cp-drill-sec" style="--cd-d:'+delay+'ms">'
+(sec.title?'<div class="cp-drill-sec-h"><span>'+sec.title+'</span>'+cnt+'</div>':'')
+'<div>'+(sec.body||'')+'</div>'
+'</div>';
}).join('');
}

var footHtml='';
if(opts.footer){footHtml='<div class="cp-drill-foot">'+opts.footer+'</div>';}

var card=document.createElement('div');
card.className='cp-drill-card '+sizeCls;
card.style.cssText='--cd-accent:'+accent+';--cd-bg:'+accentBg;
card.innerHTML=
'<div class="cp-drill-h">'
+'<div class="cp-drill-icn">'+icnHtml+'</div>'
+'<div class="cp-drill-h-text">'
+'<div class="cp-drill-t">'+(opts.title||'')+'</div>'
+(opts.subtitle?'<div class="cp-drill-s">'+opts.subtitle+'</div>':'')
+'</div>'
+'<button class="cp-drill-x" onclick="cpDrillClose()" aria-label="Закрыть">×</button>'
+'</div>'
+'<div class="cp-drill-body">'
+heroHtml
+sectionsHtml
+'</div>'
+footHtml;

bg.appendChild(card);
document.body.appendChild(bg);

/* После DOM-вставки запускаем countups, чарты, и колбэк onMount */
setTimeout(function(){
if(typeof _countUpScan==='function')_countUpScan(card,80);
if(typeof opts.onMount==='function'){try{opts.onMount(card);}catch(e){console.warn('[cpDrillOpen] onMount error:',e);}}
},100);

/* Esc закрытие */
var escHandler=function(e){
if(e.key==='Escape'){cpDrillClose();document.removeEventListener('keydown',escHandler);}
};
document.addEventListener('keydown',escHandler);
window._cpDrillEscHandler=escHandler;
};


window.cpDrillClose=function(){
var bg=document.getElementById('cp-drill-bg');
if(!bg)return;
bg.classList.add('closing');
setTimeout(function(){bg.remove();},250);
if(window._cpDrillEscHandler){document.removeEventListener('keydown',window._cpDrillEscHandler);window._cpDrillEscHandler=null;}
};


window.cpDrillHeroHtml=function(opts){
var num=opts.value;
var unit=opts.unit||'';
var lbl=opts.label||'';
var sub=opts.sub||'';
var cuD=opts.cuDecimals==null?0:opts.cuDecimals;
return '<div class="cp-drill-hero-numwrap">'
+'<span class="cp-drill-hero-num" data-countup="'+num+'" data-cu-d="'+cuD+'">'+num+'</span>'
+(unit?'<span class="cp-drill-hero-unit">'+unit+'</span>':'')
+'</div>'
+'<div class="cp-drill-hero-meta">'
+(lbl?'<div class="cp-drill-hero-lbl">'+lbl+'</div>':'')
+(sub?'<div class="cp-drill-hero-sub">'+sub+'</div>':'')
+'</div>';
};


window.cpDrillStatGridHtml=function(items){
return '<div class="cp-drill-stat-grid">'+items.map(function(s){
var click=s.onClick?' class="cp-drill-stat clickable" onclick="'+s.onClick+'"':' class="cp-drill-stat"';
var color=s.color?' style="color:'+s.color+'"':'';
var cuD=s.cuDecimals==null?0:s.cuDecimals;
return '<div'+click+'>'
+'<div class="cp-drill-stat-l">'+s.label+'</div>'
+'<div class="cp-drill-stat-v"'+color+'>'+(typeof s.value==='number'?'<span data-countup="'+s.value+'" data-cu-d="'+cuD+'">'+s.value+'</span>':s.value)+(s.unit?'<span class="cp-drill-stat-u">'+s.unit+'</span>':'')+'</div>'
+(s.sub?'<div class="cp-drill-stat-s">'+s.sub+'</div>':'')
+'</div>';
}).join('')+'</div>';
};


window.cpDrillBarsHtml=function(items){
var maxVal=Math.max.apply(null,items.map(function(i){return i.value||0;}))||1;
return '<div class="cp-drill-bars">'+items.map(function(it,i){
var pct=(it.value/maxVal)*100;
var click=it.onClick?'onclick="'+it.onClick+'"':'';
var valTxt=it.valueText||(it.total?(it.value/it.total*100).toFixed(1)+'%':String(it.value));
return '<div class="cp-drill-bar-row" '+click+'>'
+'<div class="cp-drill-bar-l">'+it.label+'</div>'
+'<div class="cp-drill-bar-track"><div class="cp-drill-bar-fill" style="--w:'+pct.toFixed(2)+'%;--c:'+(it.color||'#7F77DD')+';--bd:'+(i*60)+'ms"></div></div>'
+'<div class="cp-drill-bar-v">'+valTxt+'</div>'
+'</div>';
}).join('')+'</div>';
};


function glassSelectToggle(id){
const el_=document.getElementById(id);if(!el_)return;
const isOpen=el_.classList.contains('open');
document.querySelectorAll('.glass-select.open').forEach(g=>g.classList.remove('open'));
if(!isOpen) el_.classList.add('open');
}


function glassSelectPick(id,val,onChangeSrc){
const el_=document.getElementById(id);if(!el_)return;
el_.classList.remove('open');
const fn=new Function('v',onChangeSrc);
fn(val);
}


function _countUpScan(container, baseDelay){
if(!container) return;
var reduced = (window._isReducedMotion && window._isReducedMotion());
container.querySelectorAll('[data-countup]').forEach(function(e,i){
var val=e.getAttribute('data-countup');
/* Stagger 80ms между соседними (было 35ms) — более выраженная волна. reduced-motion = 0 */
var stagger = reduced ? 0 : 80;
var dur = reduced ? 1 : 750;
_countUpEl(e, val, dur, (baseDelay||0)+i*stagger);
});
if(typeof _kpi2SetBarDelay==='function') _kpi2SetBarDelay(container);
}


(function _uzaInjectDesignSystem(){
  if(document.getElementById('uza-ds-css'))return;
  var s=document.createElement('style');s.id='uza-ds-css';
  s.textContent=[
    /* === Base card (наследует philosophy .kpi2) === */
    '.uza-card{background:rgba(255,255,255,.82);backdrop-filter:blur(16px) saturate(1.5);-webkit-backdrop-filter:blur(16px) saturate(1.5);border-radius:16px;padding:18px 20px;border:1px solid rgba(255,255,255,.70);box-shadow:0 2px 12px rgba(15,23,60,.07),0 1px 3px rgba(15,23,60,.04);position:relative;overflow:hidden;animation:uzaCardIn .55s cubic-bezier(.34,1.2,.64,1) var(--uza-d,0ms) both}',
    '.uza-card::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--uza-accent,#7F77DD);border-radius:16px 16px 0 0;animation:uzaDrawIn .8s cubic-bezier(.4,0,.2,1) var(--uza-d,0ms) both, uzaBreathe 2.8s ease-in-out calc(var(--uza-d,0ms) + 1s) infinite;transform-origin:left center}',
    '.uza-card::after{content:"";position:absolute;top:0;left:0;right:0;height:3px;border-radius:16px 16px 0 0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:uzaShimmer 6s ease-in-out calc(var(--uza-d,0ms) + 1.2s) infinite;transform:translateX(-120%);pointer-events:none}',
    '.uza-card.uza-clickable{cursor:pointer;transition:transform .25s cubic-bezier(.34,1.56,.64,1),box-shadow .25s,border-color .25s}',
    '.uza-card.uza-clickable:hover{transform:translateY(-3px) scale(1.005);box-shadow:0 12px 32px rgba(15,23,60,.12),0 4px 12px rgba(15,23,60,.06);border-color:rgba(127,119,221,.25)}',
    
    /* === Card title / section header === */
    '.uza-card-ttl{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;animation:uzaFadeUp .45s ease calc(var(--uza-d,0ms) + .15s) both}',
    '.uza-card-ttl-l{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}',
    '.uza-card-ttl-icon{width:28px;height:28px;border-radius:8px;background:color-mix(in srgb,var(--uza-accent,#7F77DD) 11%,transparent);color:var(--uza-accent,#7F77DD);display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:transform .3s cubic-bezier(.34,1.2,.64,1)}',
    '.uza-card.uza-clickable:hover .uza-card-ttl-icon{transform:scale(1.1) rotate(-4deg)}',
    '.uza-card-ttl-name{font-size:14px;font-weight:500;color:var(--t1);letter-spacing:-.01em}',
    '.uza-card-ttl-r{font-size:11px;color:var(--t3);letter-spacing:.04em;flex-shrink:0;margin-left:auto}',
    
    /* === Status pill (внутри title) === */
    '.uza-pill{font-size:10px;font-weight:500;padding:2px 10px;border-radius:11px;letter-spacing:.05em;text-transform:uppercase;line-height:1.5;white-space:nowrap}',
    '.uza-pill-teal{background:#E1F5EE;color:#0F6E56}',
    '.uza-pill-amber{background:#FAEEDA;color:#854F0B}',
    '.uza-pill-purple{background:#EEEDFE;color:#534AB7}',
    '.uza-pill-red{background:#FCEBEB;color:#A32D2D}',
    '.uza-pill-blue{background:#E6F1FB;color:#0C447C}',
    '.uza-pill-gray{background:#F1EFE8;color:#444441}',
    
    /* === Mini KPI inside card === */
    '.uza-mini-grid{display:grid;gap:10px}',
    '.uza-mini{background:rgba(255,255,255,.55);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.6);border-radius:10px;padding:12px 14px;animation:uzaFadeUp .4s ease calc(var(--uza-d,0ms) + var(--uza-md,0ms) + .25s) both;position:relative}',
    '.uza-mini-lbl{font-size:10px;font-weight:500;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}',
    '.uza-mini-val{font-size:22px;font-weight:400;letter-spacing:-.025em;line-height:1.05;color:var(--t1);font-feature-settings:"tnum"}',
    '.uza-mini-sub{font-size:10.5px;color:var(--t3);margin-top:3px;font-weight:400}',
    '.uza-mini-status-dot{position:absolute;top:14px;right:14px;width:7px;height:7px;border-radius:50%}',

    /* === DSCR card · clickable tiles + cells (премиум hover) === */
    '.fm-dscr-kpi-wrap{transition:transform .35s cubic-bezier(.34,1.2,.64,1),box-shadow .35s ease;border-radius:10px;position:relative}',
    '.fm-dscr-kpi-wrap:hover{transform:translateY(-2px) scale(1.012)}',
    '.fm-dscr-kpi-wrap:hover .uza-mini{background:rgba(255,255,255,.85);border-color:rgba(127,119,221,.35);box-shadow:0 8px 24px rgba(127,119,221,.14),0 2px 6px rgba(15,23,60,.06)}',
    '.fm-dscr-kpi-wrap:active{transform:translateY(0) scale(0.992);transition-duration:.12s}',
    '.fm-dscr-kpi-wrap::after{content:"";position:absolute;inset:0;border-radius:10px;background:radial-gradient(circle at var(--mx,50%) var(--my,50%),rgba(127,119,221,.10),transparent 60%);opacity:0;transition:opacity .25s ease;pointer-events:none}',
    '.fm-dscr-kpi-wrap:hover::after{opacity:1}',
    /* Pill clickable */
    '.fm-dscr-pill-clickable{transition:transform .25s cubic-bezier(.34,1.2,.64,1),box-shadow .25s ease}',
    '.fm-dscr-pill-clickable:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(226,75,74,.20)}',
    '.fm-dscr-pill-clickable:active{transform:translateY(0);transition-duration:.1s}',
    /* Table cells */
    '.fm-dscr-table tbody td.fm-dscr-cell{transition:background .15s ease,box-shadow .15s ease;position:relative}',
    '.fm-dscr-table tbody td.fm-dscr-cell:hover{background:rgba(127,119,221,.08);box-shadow:inset 0 0 0 1px rgba(127,119,221,.25)}',
    '.fm-dscr-table tbody td.fm-dscr-cell::after{content:"⌕";position:absolute;top:2px;right:3px;font-size:8px;color:#7F77DD;opacity:0;transition:opacity .15s ease}',
    '.fm-dscr-table tbody td.fm-dscr-cell:hover::after{opacity:.55}',

    
    /* === Modal === */
    '.uza-modal-ov{position:fixed;inset:0;background:rgba(15,18,40,.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;z-index:9990;padding:24px;animation:uzaOvIn .25s ease both}',
    '.uza-modal{background:#fff;border-radius:16px;width:min(960px,96vw);max-height:92vh;display:flex;flex-direction:column;overflow:hidden;animation:uzaModalIn .45s cubic-bezier(.34,1.2,.64,1) both;box-shadow:0 24px 64px rgba(15,23,60,.18),0 8px 24px rgba(15,23,60,.08)}',
    '.uza-modal-h{padding:18px 22px 16px;border-bottom:1px solid rgba(15,23,60,.06);display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-shrink:0;background:linear-gradient(180deg,rgba(127,119,221,.04),transparent)}',
    '.uza-modal-h-l{display:flex;flex-direction:column;gap:4px;min-width:0;flex:1}',
    '.uza-modal-h-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}',
    '.uza-modal-h-icon{width:30px;height:30px;border-radius:9px;background:color-mix(in srgb,var(--uza-accent,#7F77DD) 11%,transparent);color:var(--uza-accent,#7F77DD);display:flex;align-items:center;justify-content:center;flex-shrink:0}',
    '.uza-modal-h-ttl{font-size:15px;font-weight:500;color:var(--t1);letter-spacing:-.01em}',
    '.uza-modal-h-sub{font-size:11.5px;color:var(--t3);margin-left:40px;letter-spacing:.02em}',
    '.uza-modal-x{cursor:pointer;width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--t3);background:#F1F5F9;border:1px solid rgba(15,23,60,.04);transition:all .15s;flex-shrink:0}',
    '.uza-modal-x:hover{background:#E2E8F0;color:var(--t1)}',
    '.uza-modal-body{padding:20px 22px;overflow-y:auto;flex:1}',
    '.uza-modal-foot{padding:14px 22px;border-top:1px solid rgba(15,23,60,.06);display:flex;justify-content:flex-end;gap:8px;flex-shrink:0;background:#FAFAFC}',
    
    /* === Modal sections === */
    '.uza-sec{margin-bottom:22px;animation:uzaFadeUp .4s ease var(--uza-secd,0ms) both}',
    '.uza-sec:last-child{margin-bottom:0}',
    '.uza-sec-ttl{font-size:10px;font-weight:500;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}',
    '.uza-sec-desc{font-size:11.5px;color:var(--t2);margin-bottom:12px;line-height:1.65}',
    
    /* === Tables in modal === */
    '.uza-tbl{width:100%;border-collapse:collapse;font-size:11.5px;background:#fff;border-radius:10px;overflow:hidden;border:1px solid rgba(15,23,60,.06)}',
    '.uza-tbl thead{background:#FAFAFC}',
    '.uza-tbl th{font-size:9.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500;padding:9px 12px;text-align:right;border-bottom:1px solid rgba(15,23,60,.06);white-space:nowrap}',
    '.uza-tbl th:first-child{text-align:left}',
    '.uza-tbl td{padding:8px 12px;text-align:right;font-feature-settings:"tnum";color:var(--t1);border-bottom:0.5px solid rgba(15,23,60,.04)}',
    '.uza-tbl tbody tr:last-child td{border-bottom:none}',
    '.uza-tbl td:first-child{text-align:left;color:var(--t2);font-weight:400}',
    '.uza-tbl tr.strong td{font-weight:500;background:rgba(127,119,221,.04);color:var(--t1)}',
    '.uza-tbl tr.fc{background:#FAFAFC}',
    '.uza-tbl tr.highlight{background:rgba(127,119,221,.06)}',
    
    /* === Buttons === */
    '.uza-btn{padding:8px 16px;border-radius:8px;font-size:12px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .15s;border:1px solid transparent;display:inline-flex;align-items:center;gap:6px;letter-spacing:.01em}',
    '.uza-btn-primary{background:#7F77DD;color:#fff;border-color:#7F77DD}',
    '.uza-btn-primary:hover{background:#6459C7;border-color:#6459C7;transform:translateY(-1px);box-shadow:0 4px 12px rgba(127,119,221,.25)}',
    '.uza-btn-ghost{background:#fff;color:var(--t2);border-color:rgba(15,23,60,.1)}',
    '.uza-btn-ghost:hover{background:#F1F5F9;color:var(--t1);border-color:rgba(15,23,60,.18)}',
    
    /* === Inputs === */
    '.uza-input{width:100%;padding:8px 12px;border:1px solid rgba(15,23,60,.1);border-radius:8px;font-size:12.5px;font-family:inherit;font-feature-settings:"tnum";color:var(--t1);background:#fff;transition:border-color .15s,box-shadow .15s}',
    '.uza-input:focus{outline:none;border-color:#7F77DD;box-shadow:0 0 0 3px rgba(127,119,221,.12)}',
    
    /* === Alert/info box === */
    '.uza-alert{padding:12px 16px;border-radius:10px;border-left:3px solid;font-size:11.5px;line-height:1.65;background:#fff;border-top:1px solid rgba(15,23,60,.06);border-right:1px solid rgba(15,23,60,.06);border-bottom:1px solid rgba(15,23,60,.06);border-radius:0 10px 10px 0}',
    '.uza-alert-purple{border-left-color:#7F77DD;background:rgba(127,119,221,.03)}',
    '.uza-alert-teal{border-left-color:#1D9E75;background:rgba(29,158,117,.03)}',
    '.uza-alert-amber{border-left-color:#EF9F27;background:rgba(239,159,39,.04)}',
    '.uza-alert-red{border-left-color:#E24B4A;background:rgba(226,75,74,.03)}',
    '.uza-alert-ttl{font-size:12.5px;font-weight:500;color:var(--t1);margin-bottom:5px;display:flex;align-items:center;gap:6px}',
    
    /* === Animations === */
    '@keyframes uzaCardIn{from{opacity:0;transform:translateY(12px) scale(.985)}60%{opacity:1;transform:translateY(-2px) scale(1.002)}to{opacity:1;transform:translateY(0) scale(1)}}',
    '@keyframes uzaDrawIn{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0% 0 0)}}',
    '@keyframes uzaShimmer{0%,75%{transform:translateX(-120%)}85%{transform:translateX(120%)}100%{transform:translateX(120%)}}',
    '@keyframes uzaBreathe{0%,100%{opacity:1}50%{opacity:.4}}',
    '@keyframes uzaFadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}',
    '@keyframes uzaOvIn{from{opacity:0}to{opacity:1}}',
    '@keyframes uzaModalIn{from{opacity:0;transform:translateY(20px) scale(.96)}60%{opacity:1;transform:translateY(-3px) scale(1.005)}to{opacity:1;transform:translateY(0) scale(1)}}',
    '@keyframes uzaDrawLine{from{stroke-dashoffset:1000}to{stroke-dashoffset:0}}',
    '@keyframes uzaBarGrow{from{transform:scaleY(0);transform-origin:bottom}to{transform:scaleY(1)}}',
    '@keyframes uzaRowIn{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:translateX(0)}}',
    
    /* === Utility === */
    '.uza-num{font-feature-settings:"tnum";letter-spacing:-.02em}',
    '.uza-divider{height:1px;background:rgba(15,23,60,.06);margin:14px 0}',
    '.uza-divider-dashed{height:1px;background:repeating-linear-gradient(90deg,rgba(15,23,60,.1) 0 4px,transparent 4px 8px);margin:14px 0}',
    /* === Editor modal overrides (применяются ко всем editor-окнам с известными id) === */
    /* Чтобы все editor-модалы имели одинаковую гамму UZA, не переписывая каждый отдельно */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal {font-family:Geist,system-ui,sans-serif}',
    /* Заголовки 700 → 500 (не во всех bpd-modal — там уже норм) */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal h3,'+
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal .pe-h h3{font-weight:500;letter-spacing:-.005em;color:var(--t1)}',
    /* Inline overrides для всех modal-кнопок типа "Сохранить" с фиолетовым градиентом */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="Save"]:not([disabled]),'+
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="save"]:not([disabled]),'+
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="Apply"]{background:#7F77DD!important;background-image:none!important;border:1px solid #7F77DD!important;color:#fff!important;font-weight:500!important;border-radius:8px!important;padding:8px 16px!important;font-size:12px!important;letter-spacing:.01em;transition:all .15s}',
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="Save"]:not([disabled]):hover,'+
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="save"]:not([disabled]):hover,'+
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal button[onclick*="Apply"]:hover{background:#6459C7!important;border-color:#6459C7!important;transform:translateY(-1px);box-shadow:0 4px 12px rgba(127,119,221,.25)}',
    /* Радиусы карточек: 14px → 16px единообразно */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal > div:first-child{border-radius:16px!important}',
    /* font-weight 700 в шапках inline → 500 (мягкий override) */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal [style*="font-weight:700"]{font-weight:500!important}',
    /* Backdrop единообразный */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal{backdrop-filter:blur(8px)!important;-webkit-backdrop-filter:blur(8px)!important;background:rgba(15,18,40,.45)!important}',
    /* Тень 0 24px 64px */
    '#proc-data-edit-modal,#fin-data-edit-modal,#fin-edit-modal,#gov-data-edit-modal,#bp-edit-modal,#kpi-edit-modal,#pa-edit-modal,#fm-editor-modal,#bar-edit-modal,#ann-edit-modal,#fin-card-modal,#fin-upload-modal,#proc-upload-modal,#ifrs-upload-modal,#fin-data-upload,#cons-upload-modal,#cons-preview-overlay,#rating-modal-overlay,#openRatingModal,#esg-note-modal-ov,#esg-issue-modal-ov,#esg-modal-ov,#cm-edit-modal > div[style*="box-shadow"]{box-shadow:0 24px 64px rgba(15,23,60,.18),0 8px 24px rgba(15,23,60,.08)!important}',
    /* === Procurement editor (.pe-*) === */
    '.pe-card{border-radius:16px!important;box-shadow:0 24px 64px rgba(15,23,60,.18),0 8px 24px rgba(15,23,60,.08)!important;animation:uzaModalIn .45s cubic-bezier(.34,1.2,.64,1) both!important}',
    '.pe-bg{background:rgba(15,18,40,.45)!important;animation:uzaOvIn .25s ease both!important}',
    '.pe-h h3{font-weight:500!important;font-size:15px!important}',
    '.pe-co-name{font-weight:500!important}',
    '.pe-co-pct{font-weight:500!important}',
    '.pe-co-changed{font-weight:500!important;border-radius:11px!important;letter-spacing:.04em;text-transform:uppercase;font-size:9.5px!important}',
    /* === KPI editor === */
    '#kpi-edit-modal > div:first-child{border-radius:16px!important;animation:uzaModalIn .45s cubic-bezier(.34,1.2,.64,1) both!important}',
    /* === FM editor (Финмодель) === */
    '#fm-editor-modal > div:first-child{animation:uzaModalIn .45s cubic-bezier(.34,1.2,.64,1) both!important}'
  ].join('\n');
  document.head.appendChild(s);
})();



/* ═══════════════════════════════════════════════════════════════════════
 * Pack 7.69.4 — TRANSITIVE DEPS
 * Helpers that the original bridge functions call into.
 * ═══════════════════════════════════════════════════════════════════════ */


function toggleEditMenu(id){
var dd=document.getElementById(id);
var btn=dd?.previousElementSibling;
if(!dd)return;
var isOpen=dd.classList.contains('show');
document.querySelectorAll('.edit-menu-dd.show').forEach(function(d){d.classList.remove('show');d.previousElementSibling?.classList.remove('open');});
if(!isOpen){dd.classList.add('show');if(btn)btn.classList.add('open');}
}


function cpYearOf(s){
if(!s) return null;
var d=new Date(s);
return isNaN(d.getTime())?null:d.getFullYear();
}


function cpCurrencyColor(c){
return {USD:'#7F77DD',EUR:'#0A7B5E',CNY:'#EF9F27',JPY:'#E24B4A',SDR:'#9C8AC8',RUB:'#5B7FBC',UZS:'#888780'}[c]||'#888780';
}


function cpCompute(){
var db=cpGetDB();
var loans=db.loans||[];

/* Подтянем lenderType для записей где его нет (защита для импортированных данных) */
loans.forEach(function(l){
if(!l.lenderType) l.lenderType=cpClassifyLender(l.bank);
});

/* Фильтр по выбранной компании. window._cpSelectedCompany — это либо 'all'/'',
   либо slug (cpCompanySlug(loan.company)). Динамически собирается из данных. */
var selCo=window._cpSelectedCompany||'all';
if(selCo&&selCo!=='all'){
  loans=loans.filter(function(l){
    return cpCompanySlug(l&&l.company)===selCo;
  });
}

var totalUsd=0,totalLocal={USD:0,EUR:0,CNY:0,JPY:0,SDR:0,RUB:0,UZS:0};
var weightedRate=0,rateBase=0;
var byCurrency={},byBank={},byBucket={},byYear={},byLenderType={};
var rateByCurrency={};   /* {USD: {sum_w, sum_d}} */
var rateByTypeCurrency={};  /* {bond:{USD:{...}}, foreign:{...}, ...} */
var nearestPayment=null;
var guaranteedAmount=0,unguaranteedAmount=0;
var loanedTotal=0,repaidTotal=0;   /* Привлечено всего / Выплачено (в USD) */

loans.forEach(function(l){
totalUsd+=l.debtUsd;
totalLocal[l.currency]=(totalLocal[l.currency]||0)+l.debtCurrency;

/* Привлечено / Выплачено — конверсия sumTotal в USD через ratio из самих данных,
   с фолбэком на CP_RATES_FX для полностью погашенных кредитов (debtCurrency=0).
   Аномалия sumTotal=0 при debtUsd>0 (напр. L136) → берём минимум долг. */
var _sumT=l.sumTotal||0;
var _sumTUsd;
if(l.debtCurrency>0&&l.debtUsd>0){
  _sumTUsd=_sumT*(l.debtUsd/l.debtCurrency);
} else {
  var _fx=CP_RATES_FX[l.currency]||1, _fxUsd=CP_RATES_FX.USD||1;
  _sumTUsd=_sumT*_fx/_fxUsd;
}
if(_sumTUsd===0&&l.debtUsd>0) _sumTUsd=l.debtUsd;
loanedTotal+=_sumTUsd;
repaidTotal+=Math.max(0,_sumTUsd-l.debtUsd);

/* Средневзвешенная ставка по портфелю — учитываем только корректные ставки */
if(l.rate&&l.rate<1&&l.rate>0){
weightedRate+=l.rate*l.debtUsd;
rateBase+=l.debtUsd;

/* По валютам */
if(!rateByCurrency[l.currency]) rateByCurrency[l.currency]={w:0,d:0};
rateByCurrency[l.currency].w+=l.rate*l.debtUsd;
rateByCurrency[l.currency].d+=l.debtUsd;

/* По типам × валютам */
var t=l.lenderType;
if(!rateByTypeCurrency[t]) rateByTypeCurrency[t]={};
if(!rateByTypeCurrency[t][l.currency]) rateByTypeCurrency[t][l.currency]={w:0,d:0,count:0};
rateByTypeCurrency[t][l.currency].w+=l.rate*l.debtUsd;
rateByTypeCurrency[t][l.currency].d+=l.debtUsd;
rateByTypeCurrency[t][l.currency].count++;
}

byCurrency[l.currency]=(byCurrency[l.currency]||0)+l.debtUsd;
var bk=cpBankShortName(l.bank);
byBank[bk]=(byBank[bk]||0)+l.debtUsd;
var bucket=cpMatBucket(l.dateDue);
byBucket[bucket]=(byBucket[bucket]||0)+l.debtUsd;
var yr=cpYearOf(l.dateDue);
if(yr){
if(!byYear[yr]) byYear[yr]={amount:0,count:0};
byYear[yr].amount+=l.debtUsd;
byYear[yr].count++;
}

/* По типу кредитора */
var lt=l.lenderType;
if(!byLenderType[lt]) byLenderType[lt]={amount:0,count:0};
byLenderType[lt].amount+=l.debtUsd;
byLenderType[lt].count++;

/* Гарантии */
if(l.isGuaranteed) guaranteedAmount+=l.debtUsd;
else unguaranteedAmount+=l.debtUsd;

if(l.dateDue){
var days=cpDaysBetween(CP_AS_OF,l.dateDue);
if(days>=0&&(!nearestPayment||l.debtUsd>nearestPayment.debtUsd)){
if(days<=365) nearestPayment=l;
}
}
});

var avgRate=rateBase?weightedRate/rateBase:0;
var paymentNextYear=byBucket['<1 года']||0;
var overdue=byBucket['overdue']||0;
var topPaymentLoan=loans.filter(function(l){
return l.dateDue && cpDaysBetween(CP_AS_OF,l.dateDue)>=0 && cpDaysBetween(CP_AS_OF,l.dateDue)<=365;
}).sort(function(a,b){return b.debtUsd-a.debtUsd;})[0];

/* Финализируем средневзвешенные ставки */
var avgRateByCurrency={};
Object.keys(rateByCurrency).forEach(function(cur){
var r=rateByCurrency[cur];
avgRateByCurrency[cur]=r.d?r.w/r.d:0;
});
var avgRateByTypeCurrency={};
Object.keys(rateByTypeCurrency).forEach(function(t){
avgRateByTypeCurrency[t]={};
Object.keys(rateByTypeCurrency[t]).forEach(function(cur){
var r=rateByTypeCurrency[t][cur];
avgRateByTypeCurrency[t][cur]={rate:r.d?r.w/r.d:0,debt:r.d,count:r.count};
});
});

return {
loans:loans,
totalUsd:totalUsd,
totalLocal:totalLocal,
avgRate:avgRate,
loansCount:loans.length,
banksCount:Object.keys(byBank).length,
byCurrency:byCurrency,
byBank:byBank,
byBucket:byBucket,
byYear:byYear,
byLenderType:byLenderType,
avgRateByCurrency:avgRateByCurrency,
avgRateByTypeCurrency:avgRateByTypeCurrency,
guaranteedAmount:guaranteedAmount,
unguaranteedAmount:unguaranteedAmount,
paymentNextYear:paymentNextYear,
payment2026:(byYear[2026]&&byYear[2026].amount)||0,
payment2027:(byYear[2027]&&byYear[2027].amount)||0,
overdue:overdue,
topPaymentLoan:topPaymentLoan,
nearestPayment:nearestPayment,
loanedTotal:loanedTotal,
repaidTotal:repaidTotal,
repaidPct:loanedTotal>0?repaidTotal/loanedTotal:0
};
}


function cpCompanySlug(name){
  if(!name)return '';
  var s=String(name).trim();
  /* Все кавычки и пунктуация → в пробелы */
  s=s.replace(/[«»"'`''.,()\/\\\-]/g,' ');
  /* Транслитерация русской + узбекской кириллицы */
  var map={'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya','қ':'q','ў':'u','ҳ':'h','ғ':'g'};
  s=s.toLowerCase().split('').map(function(ch){return map[ch]!==undefined?map[ch]:ch;}).join('');
  /* Удаляем префиксы юр.формы (теперь они на латинице — \b работает корректно) */
  s=s.replace(/\b(ao|ooo|azh|oao|zao|gup|too|akb|atb|odazh|emchzh|mchzh|oqzh|ekha|aob|jsc|llc|ltd|llp|pjsc)\b/g,' ');
  /* Только a-z 0-9, всё остальное удаляем */
  s=s.replace(/[^a-z0-9]/g,'');
  return s||'unknown';
}


function _countUpEl(e, target, duration, delay){
if(!e) return;
var raw=parseFloat(String(target).replace(/[\s,\u2212]/g,'').replace('−','-'))||0;
var dec=parseInt(e.getAttribute('data-cu-d'))||0;
var sep=e.hasAttribute('data-cu-sep');
/* SUFFIX PRESERVATION — извлекаем HTML после числа, сохраняем дочерние элементы
   (' <span>/ 1200</span>', '<span>%</span>', ' лет', etc.). Без этого textContent= стирал
   все вложенные spans и анимация выглядела просто как замена текста.
   FIX: если innerHTML — это просто em-dash placeholder ('—', '\u2014', whitespace) —
   очищаем перед извлечением suffix. Иначе regex захватит '—' как suffix и финальный
   результат будет '52 057—'. Та же логика для одиночных '%' / 'н/д' / '...' плейсхолдеров. */
var orig = e.innerHTML;
var stripped = orig.replace(/<[^>]+>/g,'').trim();
if (stripped === '\u2014' || stripped === '—' || stripped === '-' || stripped === 'н/д' || stripped === '\u2026' || stripped === '...') {
  orig = '';
  e.innerHTML = '';
}
var m = orig.match(/^(\s*[\u2212\-]?[\d.,\s\u00A0]*)([\s\S]*)$/);
var suffix = m ? m[2] : '';
/* Дополнительная защита: если в найденном suffix остался em-dash (от предыдущего рендера),
   это всегда артефакт — em-dash после числа в финансовом контексте бессмысленен. Чистим. */
if (suffix && /[\u2014—]/.test(suffix)) {
  suffix = suffix.replace(/[\u2014—]/g,'').trim();
  if (suffix && !suffix.match(/^[\s%a-zа-яё/]/i)) suffix = ' ' + suffix;
}
/* CRITICAL: на первый вызов всегда стартуем с 0 (KPI рендерятся с уже готовым числом
   в HTML, поэтому prev=target и без этого фикса анимация 850→850 = ничего не видно).
   На повторный вызов (year-switch, filter change) — morph from current visible value.
   ENHANCEMENT: если у элемента есть data-cu-key — используем глобальный store
   window._cuPrevVals для morph между re-render'ами (пересозданными узлами). */
if(!window._cuPrevVals)window._cuPrevVals={};
var cuKey = e.getAttribute('data-cu-key');
var isFirstAnim = !e.hasAttribute('data-cu-done');
var fromVal;
if (cuKey && window._cuPrevVals[cuKey] != null) {
  /* Morph from previously stored value for this logical key (works across re-renders) */
  fromVal = window._cuPrevVals[cuKey];
  e.setAttribute('data-cu-done', '1');
} else if (isFirstAnim) {
  fromVal = 0;
  /* Сразу скрываем target в DOM чтобы избежать flash of final value до старта анимации */
  e.innerHTML = '0' + suffix;
  e.setAttribute('data-cu-done', '1');
} else {
  var prevTxt = (e.textContent||'').trim();
  var prevRaw = parseFloat(prevTxt.replace(/[\s,\u2212]/g,'').replace('−','-'));
  fromVal = (!isNaN(prevRaw) && prevTxt !== '') ? prevRaw : 0;
}
/* Сохраняем target в store для следующего вызова с тем же ключом */
if (cuKey) window._cuPrevVals[cuKey] = raw;
var neg=raw<0, abs=Math.abs(raw);
var startTime=performance.now()+(delay||0);
/* Если reduced motion — сразу финальное значение */
if (window._isReducedMotion && window._isReducedMotion()) {
  var s0 = dec>0 ? raw.toFixed(dec) : Math.round(raw).toString();
  if (sep) { var p0 = s0.split('.'); p0[0] = p0[0].replace(/\B(?=(\d{3})+(?!\d))/g,' '); s0 = p0.join('.'); }
  e.innerHTML = (neg?'\u2212':'') + s0.replace('-','') + suffix;
  return;
}
var _raf=requestAnimationFrame.bind(window);
function _fmt(v, isNeg){
var a = Math.abs(v);
var s=dec>0?a.toFixed(dec):Math.round(a).toString();
if(sep){var p=s.split('.');p[0]=p[0].replace(/\B(?=(\d{3})+(?!\d))/g,' ');s=p.join('.');}
return(isNeg?'\u2212':'')+s;
}
function frame(now){
if(now<startTime){_raf(frame);return;}
var t=Math.min((now-startTime)/(duration||700),1);
var eased=_ease(t);
/* Linear interpolation from fromVal to target (signed) */
var cur = fromVal + (raw - fromVal) * eased;
e.innerHTML=_fmt(cur, cur < 0) + suffix;
if(t<1)_raf(frame);
}
_raf(frame);
}


function _kpi2SetBarDelay(container){
if(!container) return;
container.querySelectorAll('.kpi2').forEach(function(e,i){
e.style.setProperty('--kpi2-d', (i*100)+'ms');
});
}

