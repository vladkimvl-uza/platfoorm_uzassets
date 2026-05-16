/* ── Data model ─────────────────────────────────────────────────────────────
   _db.finModel[co][scenario] = {
     horizon: {startYear, endYear, factYears, forecastYears},
     macro: {inflation[y], usInflation[y], fx[y]},
     drivers: {
       volumes: [{id, name, unit, values{y:v}}],
       tariffs: [{id, name, unit, values{y:v}, volumeRef}],
       costs: [{id, name, type:'fixed|variable|semi-var', values{y:v}, unitDriver, unitCost}],
       capex: [{id, name, values{y:v}}],
       wc: {dso, dio, dpo, dap}  // turnover days
     },
     outputs: {
       pnl: {revenue{y}, cogs{y}, grossProfit{y}, opex{y}, opProfit{y}, finIncome{y}, finCost{y}, pbt{y}, tax{y}, netIncome{y}, ebitda{y}},
       cf:  {ocf{y}, icf{y}, fcf{y}, fcff{y}, fcfe{y}},
       bs:  {ppe{y}, nwc{y}, totalAssets{y}, equity{y}, debt{y}},
       ratios: {grossMargin, ebitdaMargin, netMargin, netDebtEbitda, roe, dscr, dsoActual, dioActual, dpoActual}
     },
     assumptions: {taxRate, wacc, dividendPayout}
   } */
function _fmInit(){
  if(!_db.finModel) _db.finModel={};
  return _db.finModel;
}
function _fmGetOrCreate(co, scenario){
  var fm=_fmInit();
  if(!fm[co]) fm[co]={};
  scenario=scenario||'base';
  if(!fm[co][scenario]){
    fm[co][scenario]=_fmDefaultModel();
  }
  return fm[co][scenario];
}
function _fmDefaultModel(){
  var curY=new Date().getFullYear();
  var factStart=curY-3, factEnd=curY, fcStart=curY+1, fcEnd=curY+6;
  var factYears=[], forecastYears=[];
  for(var y=factStart;y<=factEnd;y++) factYears.push(y);
  for(var y=fcStart;y<=fcEnd;y++) forecastYears.push(y);
  return {
    horizon:{startYear:factStart,endYear:fcEnd,factYears:factYears,forecastYears:forecastYears},
    macro:{inflation:{}, usInflation:{}, fx:{}},
    drivers:{
      volumes:[],
      tariffs:[],
      costs:[],
      capex:[],
      wc:{dso:30, dio:20, dpo:40, dap:15},
      /* Графики погашения долга по годам (абсолютные значения остатка) */
      debt:{ltDebt:{}, stDebt:{}, interestRate:0.09},
      /* Уставный капитал (абсолютное значение) */
      equity:{shareCapital:{}, openingCash:0, openingRE:0}
    },
    outputs:{pnl:{}, cf:{}, bs:{}, ratios:{}},
    assumptions:{taxRate:0.15, wacc:0.12, dividendPayout:0.30, terminalGrowth:0.03, riskFreeRate:0.14, beta:1.1, marketRiskPremium:0.06, countryAdjustment:-0.058, effectiveCostOfDebt:0.09}
  };
}

/* ── Autofill из кредитного портфеля (пока только Uzbekistan Airports) ────
   Извлекает график LT/ST из _db.creditPortfolio.loans, средневзвешенную
   ставку по типу кредитора, записывает в model.drivers.debt.* в UZSm. */
function _fmAutofillFromLoansUAP(model){
  if(!model) return {ok:false, reason:'нет модели'};
  var loans=(_db.creditPortfolio&&_db.creditPortfolio.loans)||[];
  var uap=loans.filter(function(l){
    return l&&l.company&&String(l.company).indexOf('Uzbekistan Airports')>=0;
  });
  if(!uap.length) return {ok:false, reason:'кредиты UzAirports не найдены в _db.creditPortfolio.loans'};

  var fx=(_db.creditPortfolio&&_db.creditPortfolio.fxRates)||(typeof CP_RATES_FX!=='undefined'?CP_RATES_FX:{USD:12078.47,EUR:14234.48,JPY:76,UZS:1});
  var asOfStr=(_db.creditPortfolio&&_db.creditPortfolio.asOf)||'2026-01-01';
  var asOf=new Date(asOfStr+'T00:00:00');

  /* Типовые ставки по кредитору — fallback, т.к. в Excel колонка % пуста */
  function estimateRate(loan){
    var b=String(loan.bank||'').toLowerCase();
    var c=loan.currency;
    if(b.indexOf('jica')>=0) return 0.010;
    if(b.indexOf('kfw')>=0) return 0.025;
    if(b.indexOf('helaba')>=0) return 0.060;
    if(b.indexOf('минфин')>=0||b.indexOf('minfin')>=0) return 0.000;
    if(b.indexOf('нбу')>=0)  return c==='UZS'?0.165:c==='EUR'?0.065:0.085;
    if(b.indexOf('хамкор')>=0) return c==='USD'?0.115:c==='UZS'?0.220:0.090;
    if(b.indexOf('кдб')>=0)  return c==='UZS'?0.180:0.085;
    if(b.indexOf('ipoteka')>=0) return c==='UZS'?0.220:0.090;
    return 0.10;
  }

  /* Линейная амортизация остатка от asOf до dateDue */
  function balanceAt(loan, atDate){
    var d0=parseFloat(loan.debtCurrency)||0;
    if(d0<=0) return 0;
    var dueStr=loan.dateDue, due;
    if(!dueStr){
      var dgStr=loan.dateGet;
      if(!dgStr) return 0;
      var dg=new Date(dgStr+'T00:00:00');
      due=new Date(dg); due.setFullYear(due.getFullYear()+8); /* fallback: 8 лет от dateGet */
    }else{
      due=new Date(dueStr+'T00:00:00');
    }
    if(atDate>=due) return 0;
    if(asOf>=due) return 0;
    var totalMs=due-asOf, remMs=due-atDate;
    if(remMs<=0) return 0;
    return d0*remMs/totalMs;
  }

  function toUZS(amt, cur){
    var rate=fx[cur]; if(rate==null) return 0;
    return amt*rate;
  }

  var horizon=model.horizon||{};
  var years=(horizon.forecastYears||[]).slice();
  if(!years.length){
    var curY=new Date().getFullYear();
    for(var y=curY;y<=curY+6;y++) years.push(y);
    horizon.forecastYears=years;
    model.horizon=horizon;
  }

  model.drivers=model.drivers||{};
  model.drivers.debt=model.drivers.debt||{ltDebt:{},stDebt:{},interestRate:0.09};
  model.drivers.debt.ltDebt=model.drivers.debt.ltDebt||{};
  model.drivers.debt.stDebt=model.drivers.debt.stDebt||{};

  years.forEach(function(y){
    var endY=new Date(y, 11, 31);
    var endNextY=new Date(y+1, 11, 31);
    var totalNow=0, totalNext=0;
    uap.forEach(function(loan){
      var balNow=balanceAt(loan, endY);
      var balNext=balanceAt(loan, endNextY);
      totalNow+=toUZS(balNow, loan.currency);
      totalNext+=toUZS(balNext, loan.currency);
    });
    var totalUZSm=totalNow/1e6;
    var ltUZSm=totalNext/1e6;
    var stUZSm=Math.max(0, totalUZSm-ltUZSm);
    model.drivers.debt.ltDebt[y]=Math.round(ltUZSm);
    model.drivers.debt.stDebt[y]=Math.round(stUZSm);
  });

  /* Средневзвешенная ставка по USD-остатку */
  var totalUsd=0, weightedRate=0;
  uap.forEach(function(loan){
    var debtUsd=parseFloat(loan.debtUsd)||0;
    if(debtUsd<=0) return;
    totalUsd+=debtUsd;
    weightedRate+=estimateRate(loan)*debtUsd;
  });
  if(totalUsd>0){
    model.drivers.debt.interestRate=Math.round(weightedRate/totalUsd*10000)/10000;
  }

  return {
    ok:true,
    loanCount:uap.length,
    yearCount:years.length,
    interestRate:model.drivers.debt.interestRate,
    totalDebt2026UZSm:Math.round((model.drivers.debt.ltDebt[years[0]]||0)+(model.drivers.debt.stDebt[years[0]]||0))
  };
}
window._fmAutofillFromLoansUAP=_fmAutofillFromLoansUAP;

function _fmAutofillBtnHandler(){
  var s=window._fmEditor;
  if(!s){alert('Редактор не активен');return;}
  if(s.co!=='Uzbekistan Airports'){
    alert('Автозаполнение из кредитов пока доступно только для Uzbekistan Airports');return;
  }
  var loans=(_db.creditPortfolio&&_db.creditPortfolio.loans)||[];
  var uap=loans.filter(function(l){return l&&l.company&&String(l.company).indexOf('Uzbekistan Airports')>=0;});
  if(!uap.length){alert('Кредиты UzAirports не найдены в _db.creditPortfolio.loans');return;}
  var d=s.model.drivers&&s.model.drivers.debt||{};
  var existing=Object.keys(d.ltDebt||{}).length+Object.keys(d.stDebt||{}).length;
  var msg='Заполнить долговой график для UzAirports из '+uap.length+' кредитов?';
  if(existing>0) msg+='\n\nСуществующие '+existing+' значений LT/ST будут перезаписаны.';
  msg+='\n\nБудут заполнены: ltDebt, stDebt, interestRate (UZSm) для прогнозных лет.\nИзменения нужно будет сохранить кнопкой «Сохранить».';
  if(!confirm(msg))return;

  var result=_fmAutofillFromLoansUAP(s.model);
  if(!result.ok){alert('Ошибка: '+result.reason);return;}

  window._fmEditorDirty=true;
  /* Recreate modal to refresh inputs and re-attach listeners */
  var m=document.getElementById('fm-editor-modal');
  if(m) m.remove();
  if(typeof _fmShowEditor==='function') _fmShowEditor();
  setTimeout(function(){
    var totalBln=(result.totalDebt2026UZSm/1000).toFixed(0);
    alert('✓ Заполнено '+result.yearCount+' лет ('+result.loanCount+' кредитов)\n\nДолг 2026: '+totalBln+' млрд UZS\nСтавка WACD: '+(result.interestRate*100).toFixed(2)+'%\n\nНе забудьте сохранить.');
  },150);
}
window._fmAutofillBtnHandler=_fmAutofillBtnHandler;

/* ── Core computation: drivers → P&L → CF → BS → ratios ───────────────────
   Полный EY/PwC-style driver-based computation.
   Все цифры в UZSm (миллионы сум). */
function _fmRecompute(model){
  if(!model||!model.horizon)return;
  var years=[].concat(model.horizon.factYears||[], model.horizon.forecastYears||[]);
  var out={pnl:{}, cf:{}, bs:{}, ratios:{}};
  var drv=model.drivers||{};
  var asm=model.assumptions||{taxRate:0.15, dividendPayout:0.3};
  var debtCfg=drv.debt||{ltDebt:{}, stDebt:{}, interestRate:0.09};
  var eqCfg=drv.equity||{shareCapital:{}, openingCash:0, openingRE:0};

  /* ─── 1. REVENUE ─── */
  years.forEach(function(y){
    var revenue=null;
    if(model.revenueDirect&&model.revenueDirect[y]!=null){
      revenue=model.revenueDirect[y];
    }else{
      revenue=0;
      (drv.tariffs||[]).forEach(function(t){
        var tariff=t.values&&t.values[y];
        if(tariff==null)return;
        var vol=null;
        if(t.volumeRef){
          var volObj=(drv.volumes||[]).find(function(v){return v.id===t.volumeRef;});
          if(volObj) vol=volObj.values&&volObj.values[y];
        }
        if(vol==null){
          var mainVol=(drv.volumes||[]).find(function(v){return !v.isSub;});
          if(mainVol) vol=mainVol.values&&mainVol.values[y];
        }
        if(vol!=null) revenue += vol*tariff;
      });
    }
    out.pnl.revenue=out.pnl.revenue||{};
    out.pnl.revenue[y]=revenue;
  });

  /* ─── 2. COSTS (делим на operating COGS, SG&A, и D&A отдельно) ─── */
  years.forEach(function(y){
    var opCost=0, sgaCost=0, depreciation=0;
    (drv.costs||[]).forEach(function(c){
      var val=c.values&&c.values[y];
      if(val==null&&c.unitDriver&&c.unitCost){
        var driverObj=(drv.volumes||[]).find(function(v){return v.id===c.unitDriver;});
        if(driverObj){
          var drvVal=driverObj.values&&driverObj.values[y];
          if(drvVal!=null) val=drvVal*(c.unitCost[y]||0);
        }
      }
      if(val!=null){
        var abs=Math.abs(val);
        if(c.isDA) depreciation += abs;
        else if(c.category==='sga') sgaCost += abs;
        else opCost += abs;
      }
    });
    out.pnl.cogs=out.pnl.cogs||{};
    out.pnl.cogs[y]=opCost;
    out.pnl.sga=out.pnl.sga||{};
    out.pnl.sga[y]=sgaCost;
    out.pnl.depreciation=out.pnl.depreciation||{};
    out.pnl.depreciation[y]=depreciation;
  });

  /* ─── 3. BALANCE SHEET: Debt, Cash, PPE ─── */
  /* 3a. Долг */
  years.forEach(function(y){
    var ltD=(debtCfg.ltDebt&&debtCfg.ltDebt[y]!=null)?debtCfg.ltDebt[y]:0;
    var stD=(debtCfg.stDebt&&debtCfg.stDebt[y]!=null)?debtCfg.stDebt[y]:0;
    out.bs.ltDebt=out.bs.ltDebt||{};
    out.bs.stDebt=out.bs.stDebt||{};
    out.bs.totalDebt=out.bs.totalDebt||{};
    out.bs.ltDebt[y]=ltD;
    out.bs.stDebt[y]=stD;
    out.bs.totalDebt[y]=ltD+stD;
  });
  /* 3b. PPE roll-forward: Beginning + CAPEX − D&A = Ending */
  var prevPPE=0;
  years.forEach(function(y){
    var capex=0;
    (drv.capex||[]).forEach(function(c){
      if(c.id==='capex_total'){
        var v=c.values&&c.values[y];
        if(v!=null){capex=Math.abs(v);return;}
      }
    });
    if(capex===0){
      (drv.capex||[]).forEach(function(c){
        if(c.id==='capex_total')return;
        var v=c.values&&c.values[y];
        if(v!=null) capex += Math.abs(v);
      });
    }
    var da=out.pnl.depreciation[y]||0;
    var endPPE=prevPPE+capex-da;
    out.bs.ppe=out.bs.ppe||{};
    out.bs.ppe[y]=endPPE;
    out.bs.capex=out.bs.capex||{};
    out.bs.capex[y]=capex;
    prevPPE=endPPE;
  });

  /* ─── 4. P&L с учётом finance costs ─── */
  years.forEach(function(y){
    var rev=out.pnl.revenue[y]||0;
    var cost=out.pnl.cogs[y]||0;
    var sga=out.pnl.sga[y]||0;
    var da=out.pnl.depreciation[y]||0;
    var totalDebt=out.bs.totalDebt[y]||0;
    out.pnl.grossProfit=out.pnl.grossProfit||{};
    out.pnl.grossProfit[y]=rev-cost;
    out.pnl.opProfit=out.pnl.opProfit||{};
    out.pnl.opProfit[y]=out.pnl.grossProfit[y]-sga;
    /* Finance cost = rate × среднее долга за период */
    var rate=(debtCfg.interestRate!=null)?debtCfg.interestRate:0.09;
    out.pnl.finCost=out.pnl.finCost||{};
    out.pnl.finCost[y]=totalDebt*rate;
    out.pnl.finIncome=out.pnl.finIncome||{};
    out.pnl.finIncome[y]=0;
    out.pnl.pbt=out.pnl.pbt||{};
    out.pnl.pbt[y]=out.pnl.opProfit[y]-out.pnl.finCost[y]+out.pnl.finIncome[y];
    out.pnl.tax=out.pnl.tax||{};
    out.pnl.tax[y]=-(out.pnl.pbt[y]>0?out.pnl.pbt[y]*asm.taxRate:0);
    out.pnl.netIncome=out.pnl.netIncome||{};
    out.pnl.netIncome[y]=out.pnl.pbt[y]+out.pnl.tax[y];
    out.pnl.ebitda=out.pnl.ebitda||{};
    out.pnl.ebitda[y]=out.pnl.opProfit[y]+da;
  });

  /* ─── 5. CASH FLOW + Cash roll-forward ─── */
  var prevNwc=0, prevCash=(eqCfg.openingCash||0);
  var prevDebt=0;
  years.forEach(function(y, idx){
    var rev=out.pnl.revenue[y]||0;
    var cost=out.pnl.cogs[y]||0;
    var nwc=(drv.wc?((drv.wc.dso/365)*rev+(drv.wc.dio/365)*cost-(drv.wc.dpo/365)*cost-(drv.wc.dap/365)*rev):0);
    var dNwc=nwc-prevNwc;
    prevNwc=nwc;
    var capex=out.bs.capex[y]||0;
    var totalDebt=out.bs.totalDebt[y]||0;
    var dDebt=totalDebt-prevDebt;
    prevDebt=totalDebt;
    /* CFO = NI + D&A − ΔNWC */
    out.cf.cfo=out.cf.cfo||{};
    out.cf.cfo[y]=(out.pnl.netIncome[y]||0)+(out.pnl.depreciation[y]||0)-dNwc;
    /* CFI = −CAPEX */
    out.cf.cfi=out.cf.cfi||{};
    out.cf.cfi[y]=-capex;
    /* CFF = ΔDebt − Dividends */
    var netIncome=out.pnl.netIncome[y]||0;
    var dividends=(netIncome>0)?(-netIncome*asm.dividendPayout):0;
    out.cf.dividends=out.cf.dividends||{};
    out.cf.dividends[y]=dividends;
    out.cf.cff=out.cf.cff||{};
    out.cf.cff[y]=dDebt+dividends;
    /* FCF к акционеру (FCFE): CFO + CFI + ΔDebt */
    out.cf.fcf=out.cf.fcf||{};
    out.cf.fcf[y]=out.cf.cfo[y]+out.cf.cfi[y];
    out.cf.fcfe=out.cf.fcfe||{};
    out.cf.fcfe[y]=out.cf.cfo[y]+out.cf.cfi[y]+dDebt;
    /* FCFF: EBIT(1-t) + D&A - CAPEX - ΔNWC (налог на чистую оп.прибыль) */
    out.cf.fcff=out.cf.fcff||{};
    out.cf.fcff[y]=(out.pnl.opProfit[y]||0)*(1-asm.taxRate)+(out.pnl.depreciation[y]||0)-capex-dNwc;
    /* Cash roll-forward */
    var netCashChange=out.cf.cfo[y]+out.cf.cfi[y]+out.cf.cff[y];
    var endCash=prevCash+netCashChange;
    out.bs.cash=out.bs.cash||{};
    out.bs.cash[y]=endCash;
    out.cf.netCashChange=out.cf.netCashChange||{};
    out.cf.netCashChange[y]=netCashChange;
    prevCash=endCash;
    /* NWC */
    out.bs.nwc=out.bs.nwc||{};
    out.bs.nwc[y]=nwc;
  });

  /* ─── 6. Equity (Share + Retained earnings) + Net Debt ─── */
  var prevRE=(eqCfg.openingRE||0);
  years.forEach(function(y){
    var shareCap=(eqCfg.shareCapital&&eqCfg.shareCapital[y]!=null)?eqCfg.shareCapital[y]:0;
    var ni=out.pnl.netIncome[y]||0;
    var div=out.cf.dividends[y]||0; /* отрицательное */
    var re=prevRE+ni+div; /* div отрицательный, значит вычитаем */
    prevRE=re;
    out.bs.shareCapital=out.bs.shareCapital||{};
    out.bs.shareCapital[y]=shareCap;
    out.bs.retainedEarnings=out.bs.retainedEarnings||{};
    out.bs.retainedEarnings[y]=re;
    out.bs.equity=out.bs.equity||{};
    out.bs.equity[y]=shareCap+re;
    out.bs.netDebt=out.bs.netDebt||{};
    out.bs.netDebt[y]=(out.bs.totalDebt[y]||0)-(out.bs.cash[y]||0);
  });

  /* ─── 7. TOTAL ASSETS / LIABILITIES (упрощённая формула) ─── */
  years.forEach(function(y){
    out.bs.totalAssets=out.bs.totalAssets||{};
    out.bs.totalAssets[y]=(out.bs.ppe[y]||0)+(out.bs.cash[y]||0)+(out.bs.nwc[y]>0?out.bs.nwc[y]:0);
    out.bs.totalLiabilities=out.bs.totalLiabilities||{};
    out.bs.totalLiabilities[y]=(out.bs.totalDebt[y]||0)+(out.bs.nwc[y]<0?-out.bs.nwc[y]:0);
  });

  /* ─── 8. RATIOS ─── */
  years.forEach(function(y){
    var rev=out.pnl.revenue[y]||0;
    var eb=out.pnl.ebitda[y]||0;
    var ni=out.pnl.netIncome[y]||0;
    var eq=out.bs.equity[y]||0;
    var nd=out.bs.netDebt[y]||0;
    out.ratios.grossMargin=out.ratios.grossMargin||{};
    out.ratios.grossMargin[y]=rev?out.pnl.grossProfit[y]/rev:null;
    out.ratios.ebitdaMargin=out.ratios.ebitdaMargin||{};
    out.ratios.ebitdaMargin[y]=rev?eb/rev:null;
    out.ratios.netMargin=out.ratios.netMargin||{};
    out.ratios.netMargin[y]=rev?ni/rev:null;
    out.ratios.netDebtEbitda=out.ratios.netDebtEbitda||{};
    out.ratios.netDebtEbitda[y]=eb?nd/eb:null;
    out.ratios.roe=out.ratios.roe||{};
    out.ratios.roe[y]=eq?ni/eq:null;
  });

  /* ─── 8b. DEBT COVERAGE: CFADS, DSCR, LLCR, PLCR (IFI стандарт) ───
     CFADS = EBITDA − Tax − ΔWC − CAPEX (project finance стандарт)
     DSCR  = CFADS / (Interest + Principal repayment) — критично для IFC/EBRD/ADB covenants
     LLCR  = NPV(CFADS, WACD) over loan life / Outstanding debt at start of forecast
     PLCR  = NPV(CFADS, WACD) over project life / Outstanding debt at start of forecast */
  var prevNwcCov=0, prevTotalDebtCov=null;
  out.cf.cfads=out.cf.cfads||{};
  out.cf.principalRepayment=out.cf.principalRepayment||{};
  out.cf.debtService=out.cf.debtService||{};
  out.ratios.dscrByYear=out.ratios.dscrByYear||{};
  years.forEach(function(y){
    var ebitdaCov=out.pnl.ebitda[y]||0;
    var taxCov=out.pnl.tax[y]||0;
    var capexCov=out.bs.capex[y]||0;
    var nwcCov=out.bs.nwc[y]||0;
    var dNwcCov=nwcCov-prevNwcCov;
    prevNwcCov=nwcCov;
    var cfadsY=ebitdaCov-taxCov-dNwcCov-capexCov;
    out.cf.cfads[y]=cfadsY;

    var totalDebtCov=out.bs.totalDebt[y]||0;
    var principal=(prevTotalDebtCov!=null)?Math.max(0, prevTotalDebtCov-totalDebtCov):0;
    prevTotalDebtCov=totalDebtCov;
    out.cf.principalRepayment[y]=principal;

    var interestCov=out.pnl.finCost[y]||0;
    var debtServiceY=interestCov+principal;
    out.cf.debtService[y]=debtServiceY;

    var dscrY=(debtServiceY>0)?(cfadsY/debtServiceY):null;
    out.ratios.dscrByYear[y]=(dscrY!=null&&isFinite(dscrY))?dscrY:null;
  });
  /* DSCR Min/Avg — только по прогнозным годам (forward-looking метрика) */
  var fcDscrs=[];
  (model.horizon.forecastYears||[]).forEach(function(y){
    var v=out.ratios.dscrByYear[y];
    if(v!=null&&isFinite(v)) fcDscrs.push(v);
  });
  out.ratios.dscrMin=fcDscrs.length?Math.min.apply(null, fcDscrs):null;
  out.ratios.dscrAvg=fcDscrs.length?(fcDscrs.reduce(function(a,b){return a+b;},0)/fcDscrs.length):null;

  /* LLCR — discount CFADS только по годам, где остаётся непогашенный долг */
  var wacdCov=(drv.debt&&drv.debt.interestRate)||0.09;
  var fcYearsCov=(model.horizon.forecastYears||[]);
  var loanEndIdx=-1;
  for(var iCov=fcYearsCov.length-1; iCov>=0; iCov--){
    if((out.bs.totalDebt[fcYearsCov[iCov]]||0)>0){loanEndIdx=iCov; break;}
  }
  out.ratios.llcr=null;
  if(loanEndIdx>=0){
    var npvLL=0;
    for(var jCov=0; jCov<=loanEndIdx; jCov++){
      var cfLL=out.cf.cfads[fcYearsCov[jCov]]||0;
      npvLL += cfLL/Math.pow(1+wacdCov, jCov+1);
    }
    var debtStartLL=out.bs.totalDebt[fcYearsCov[0]]||0;
    if(debtStartLL>0) out.ratios.llcr=npvLL/debtStartLL;
  }
  /* PLCR — по всему прогнозному горизонту */
  out.ratios.plcr=null;
  var npvPL=0;
  fcYearsCov.forEach(function(y, idx){
    npvPL += (out.cf.cfads[y]||0)/Math.pow(1+wacdCov, idx+1);
  });
  var debtStartPL=fcYearsCov.length?(out.bs.totalDebt[fcYearsCov[0]]||0):0;
  if(debtStartPL>0) out.ratios.plcr=npvPL/debtStartPL;

  /* ─── 9. ENTERPRISE VALUE + EQUITY VALUE ─── */
  var wacc=asm.wacc||0.12;
  var g=asm.terminalGrowth||0.03;
  var pvSum=0, lastFc=(model.horizon.forecastYears||[]).slice(-1)[0];
  (model.horizon.forecastYears||[]).forEach(function(y,i){
    var fcff=out.cf.fcff&&out.cf.fcff[y];
    if(fcff!=null) pvSum += fcff/Math.pow(1+wacc, i+1);
  });
  var ev=null;
  if(lastFc&&out.cf.fcff&&out.cf.fcff[lastFc]!=null&&wacc>g){
    var tv=out.cf.fcff[lastFc]*(1+g)/(wacc-g);
    var n=(model.horizon.forecastYears||[]).length;
    var pvTV=tv/Math.pow(1+wacc, n);
    ev=pvSum+pvTV;
  }
  out.ratios.enterpriseValue=ev;
  out.ratios.npv=pvSum;
  /* Equity value = EV − Net debt (на последний год) */
  if(ev!=null&&lastFc){
    var ndLast=out.bs.netDebt[lastFc]||0;
    out.ratios.equityValue=ev-ndLast;
  }

  model.outputs=out;
  return out;
}

/* ── Shell ──────────────────────────────────────────────────────────────── */
function showFinModelView(){
  if(typeof logTelemetry==='function') logTelemetry('nav','Финансовая модель',{view:'finmodel'});
  if(typeof S!=='undefined') S.view='finmodel';
  if(typeof killCharts==='function') killCharts();
  if(typeof renderSidebar==='function') renderSidebar();
  var _sb=document.getElementById('sidebar');
  if(_sb&&_sb.classList.contains('collapsed')&&typeof toggleSidebar==='function') toggleSidebar();
  document.querySelectorAll('#sidebar .sb-item, #sidebar .sb-sub-item').forEach(function(i){i.classList.remove('active');});
  var grp=document.getElementById('sb-finance-group');
  var sub=document.getElementById('sb-finance-submenu');
  if(grp){grp.classList.add('open');}
  if(sub){sub.style.display='flex';}
  document.getElementById('finance-nav-btn')?.classList.add('active');
  document.getElementById('finmodel-nav-btn')?.classList.add('active');
  _fmInit();
  /* Cleanup: удаляем некорректные ключи (undefined, null, пустая строка) — legacy bug fix */
  if(_db.finModel&&typeof _db.finModel==='object'){
    ['undefined','null',''].forEach(function(badKey){
      if(_db.finModel[badKey]){
        console.warn('[FM] Удаляю некорректный ключ финмодели:',badKey);
        delete _db.finModel[badKey];
        if(typeof fetch==='function'&&typeof FB_URL==='function'){
          var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
          fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(_db.finModel)}).catch(function(){});
        }
      }
    });
  }
  window._fmScenario=window._fmScenario||'base';
  window._fmHorizon=window._fmHorizon||7;
  /* По умолчанию: первая компания у которой есть модель; если моделей нет — null (empty state) */
  if(!window._fmSelCo){
    var cosWithModel=_db.finModel?Object.keys(_db.finModel).filter(function(k){
      return k&&k!=='undefined'&&k!=='null'&&_db.finModel[k]&&typeof _db.finModel[k]==='object';
    }):[];
    window._fmSelCo=cosWithModel.length?cosWithModel[0]:null;
  }
  /* Diagnostics */
  console.log('[FM] showFinModelView · _db.finModel:',
    _db.finModel?'exists ('+Object.keys(_db.finModel).length+' companies)':'MISSING');
  if(_db.finModel){
    Object.keys(_db.finModel).forEach(function(co){
      var scens=Object.keys(_db.finModel[co]||{});
      console.log('[FM]   ·',co,'→ scenarios:',scens.join(','));
      scens.forEach(function(sc){
        var m=_db.finModel[co][sc];
        var vcount=(m&&m.drivers&&m.drivers.volumes||[]).length;
        var ccount=(m&&m.drivers&&m.drivers.costs||[]).length;
        console.log('[FM]     ·',sc,'→ volumes:',vcount,'costs:',ccount);
      });
    });
  }
  var mc=document.getElementById('main-content');
  if(!mc)return;
  mc.innerHTML=_fmRenderShell();
  /* Force reload from Firebase if finModel is empty (handles case где data не успело загрузиться) */
  if(!_db.finModel||Object.keys(_db.finModel).length===0){
    console.log('[FM] _db.finModel пустой — делаем принудительный GET...');
    var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
    fetch(url).then(function(r){return r.ok?r.json():null;}).then(function(data){
      console.log('[FM] Firebase вернул:',data?('данные есть, '+Object.keys(data).length+' компаний'):'null');
      if(data&&typeof data==='object'){
        /* Очищаем некорректные ключи */
        ['undefined','null',''].forEach(function(bk){if(data[bk])delete data[bk];});
        _db.finModel=data;
        /* Если компании не выбрано — берём первую */
        if(!window._fmSelCo){
          var keys=Object.keys(data);
          if(keys.length) window._fmSelCo=keys[0];
        }
        /* Регенерируем shell потому что dropdown теперь должен содержать загруженные компании */
        if(mc) mc.innerHTML=_fmRenderShell();
        _fmRepaint();
      }else{
        _fmRepaint();
      }
    }).catch(function(e){
      console.error('[FM] force GET failed:',e);
      _fmRepaint();
    });
  }else{
    _fmRepaint();
  }
}
window.showFinModelView=showFinModelView;

function _fmRenderShell(){
  var h='<style>'
    + '.fm-scroll{background:#F4F3F9;min-height:100%;padding:0}'
    + '.fm-body{padding:20px 22px}'
    + '@keyframes fmCardIn{0%{opacity:0;transform:translateY(10px) scale(.98)}60%{opacity:1;transform:translateY(-2px) scale(1)}100%{opacity:1;transform:translateY(0) scale(1)}}'
    + '@keyframes fmNumIn{0%{opacity:0;transform:translateY(6px)}100%{opacity:1;transform:translateY(0)}}'
    + '@keyframes fmBarFill{0%{width:0}100%{width:var(--w,100%)}}'
    + '@keyframes fmStripeIn{0%{transform:scaleX(0)}100%{transform:scaleX(1)}}'
    + '.fm-kpi-row{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-bottom:16px;align-items:stretch}'
    + '@media(max-width:1300px){.fm-kpi-row{grid-template-columns:repeat(4,1fr)}}'
    + '@media(max-width:900px){.fm-kpi-row{grid-template-columns:repeat(3,1fr)}}'
    + '@media(max-width:600px){.fm-kpi-row{grid-template-columns:repeat(2,1fr)}}'
    + '.fm-row{display:grid;gap:14px;margin-bottom:14px}'
    + '.fm-card{background:#fff;border-radius:12px;border:1px solid rgba(0,0,0,.05);padding:16px 18px;animation:fmCardIn .55s cubic-bezier(.34,1.2,.64,1) var(--d,0ms) both;position:relative;overflow:hidden}'
    + '.fm-card-ttl{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;animation:fmNumIn .45s ease var(--d,0ms) both}'
    + '.fm-card-ttl-l{font-size:12px;font-weight:700;color:var(--t1);text-transform:uppercase;letter-spacing:.06em}'
    + '.fm-card-ttl-r{font-size:10.5px;color:var(--t3)}'
    /* Portfolio roadmap */
    + '.fm-road{display:flex;flex-direction:column;gap:4px}'
    + '.fm-road-hd{display:grid;grid-template-columns:180px 1fr;gap:10px;padding:4px 0;border-bottom:1px solid rgba(0,0,0,.05);margin-bottom:6px}'
    + '.fm-road-years{display:flex;gap:2px}'
    + '.fm-road-year{flex:1;text-align:center;font-size:9.5px;font-weight:600;color:var(--t3);letter-spacing:.04em}'
    + '.fm-road-year.fact{color:var(--t2)}.fm-road-year.fc{color:#EF9F27}'
    + '.fm-road-row{display:grid;grid-template-columns:180px 1fr;gap:10px;align-items:center;padding:4px 0;border-bottom:0.5px solid rgba(0,0,0,.03);animation:fmNumIn .3s ease calc(var(--d,0ms) + var(--rd,0ms)) both;transition:background .15s;cursor:pointer;border-radius:6px}'
    + '.fm-road-row:hover{background:rgba(127,119,221,.04)}'
    + '.fm-road-co{display:flex;align-items:center;gap:8px;min-width:0;padding-left:4px}'
    + '.fm-road-co-strip{width:3px;height:14px;border-radius:2px;flex-shrink:0}'
    + '.fm-road-co-name{font-size:12px;font-weight:500;color:var(--t1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}'
    + '.fm-road-co-tag{font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(127,119,221,.08);color:#6459C7;font-weight:600;letter-spacing:.04em;flex-shrink:0}'
    + '.fm-road-co-tag.fc{background:rgba(239,159,39,.15);color:#A36500}'
    + '.fm-road-bars{display:flex;gap:2px;align-items:stretch;height:32px}'
    + '.fm-road-bar{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;position:relative}'
    + '.fm-road-bar-fill{width:100%;border-radius:3px 3px 0 0;transition:height .3s ease;cursor:pointer;min-height:2px}'
    + '.fm-road-bar-fill.fact{background:var(--bc,#7F77DD)}.fm-road-bar-fill.fc{background:var(--bc,#7F77DD);opacity:.6;background-image:linear-gradient(45deg,transparent 40%,rgba(255,255,255,.25) 50%,transparent 60%)}'
    /* Scenarios */
    + '.fm-scn-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}'
    + '.fm-scn{background:#fff;border-radius:10px;border:1px solid rgba(0,0,0,.06);padding:12px 14px;cursor:pointer;transition:all .18s}'
    + '.fm-scn:hover{border-color:rgba(127,119,221,.25);box-shadow:0 3px 14px rgba(15,23,60,.06)}'
    + '.fm-scn.active{border-color:#7F77DD;box-shadow:0 0 0 1px #7F77DD,0 3px 14px rgba(127,119,221,.12)}'
    + '.fm-scn-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}'
    + '.fm-scn-ttl{font-size:11px;font-weight:700;color:var(--t1);text-transform:uppercase;letter-spacing:.06em}'
    + '.fm-scn-tag{font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;letter-spacing:.04em}'
    + '.fm-scn.s-base .fm-scn-tag{background:rgba(55,138,221,.12);color:#1D5A8F}'
    + '.fm-scn.s-opt .fm-scn-tag{background:rgba(29,158,117,.12);color:#0F6E56}'
    + '.fm-scn.s-str .fm-scn-tag{background:rgba(226,75,74,.12);color:#933632}'
    + '.fm-scn-metric{display:flex;justify-content:space-between;font-size:11px;padding:4px 0;border-bottom:0.5px dashed rgba(0,0,0,.05)}'
    + '.fm-scn-metric:last-child{border-bottom:none}'
    + '.fm-scn-metric span:first-child{color:var(--t3)}'
    + '.fm-scn-metric span:last-child{color:var(--t1);font-weight:600;font-feature-settings:"tnum"}'
    /* Insights */
    + '.fm-insight{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:8px;margin-bottom:6px;background:rgba(255,255,255,.6);animation:fmNumIn .3s ease calc(var(--d,0ms) + var(--rd,0ms)) both}'
    + '.fm-insight.up{background:rgba(29,158,117,.07);border-left:3px solid #1D9E75}'
    + '.fm-insight.down{background:rgba(226,75,74,.07);border-left:3px solid #E24B4A}'
    + '.fm-insight-ico{flex-shrink:0;margin-top:1px}'
    + '.fm-insight-body{flex:1;min-width:0}'
    + '.fm-insight-ttl{font-size:11.5px;font-weight:600;color:var(--t1);margin-bottom:2px}'
    + '.fm-insight-desc{font-size:10.5px;color:var(--t2);line-height:1.45}'
    /* P&L table */
    + '.fm-pnl{width:100%;border-collapse:collapse;font-size:11.5px}'
    + '.fm-pnl th{text-align:right;padding:6px 10px;font-size:9.5px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid rgba(0,0,0,.06);white-space:nowrap}'
    + '.fm-pnl th:first-child{text-align:left;padding-left:0}'
    + '.fm-pnl th.fact{color:var(--t2)}.fm-pnl th.fc{color:#EF9F27}'
    + '.fm-pnl td{padding:5px 10px;text-align:right;color:var(--t1);font-feature-settings:"tnum";border-bottom:0.5px solid rgba(0,0,0,.03)}'
    + '.fm-pnl td:first-child{text-align:left;padding-left:0;color:var(--t2);font-weight:500}'
    + '.fm-pnl tr.strong td{font-weight:700;color:var(--t1);background:rgba(127,119,221,.04)}'
    + '.fm-pnl tr.subtotal td{font-weight:600;border-top:1px solid rgba(0,0,0,.06)}'
    + '.fm-pnl td.neg{color:#933632}'
    + '.fm-pnl td.fc-cell{background:rgba(239,159,39,.04)}'
    + '.fm-empty{padding:40px 20px;text-align:center;color:var(--t3);font-size:12.5px;line-height:1.6}'
    + '.fm-empty-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;margin-top:12px;border:1px solid #7F77DD;border-radius:8px;background:rgba(127,119,221,.08);color:#6459C7;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .15s}'
    + '.fm-empty-btn:hover{background:rgba(127,119,221,.14)}'
    + '</style>';

  h += '<div class="fm-scroll">';

  /* ═══ Topbar (dash-topbar Finance-style, центрированный hero) ═══ */
  var scenarios=[{id:'base',l:'Базовый'},{id:'opt',l:'Оптимистичный'},{id:'str',l:'Стрессовый'}];
  var co=window._fmSelCo; /* может быть null если нет моделей */
  var scn=window._fmScenario;
  /* Список компаний: модель OR фин.данные (НСБУ/IFRS) — чтобы можно было создать модель
     прямо из dropdown для компаний с заполненными НСБУ данными */
  var cos=[];
  var coSet={};
  var hasModelSet={};
  if(_db.finModel&&typeof _db.finModel==='object'){
    Object.keys(_db.finModel).forEach(function(k){
      if(k&&k!=='undefined'&&k!=='null'&&_db.finModel[k]&&typeof _db.finModel[k]==='object'){
        if(!coSet[k]){cos.push(k); coSet[k]=true;}
        hasModelSet[k]=true;
      }
    });
  }
  if(_db.financials&&typeof _db.financials==='object'){
    Object.keys(_db.financials).forEach(function(k){
      if(!k||k==='_meta')return;
      /* Снимаем префикс __nsbu_ если есть */
      var name = k.indexOf('__nsbu_')===0 ? k.slice(7) : k;
      if(!name||name==='undefined'||name==='null')return;
      var fd = _db.financials[k];
      /* Проверяем что есть хотя бы годы с данными */
      if(fd && Array.isArray(fd.years) && fd.years.length>0){
        if(!coSet[name]){cos.push(name); coSet[name]=true;}
      }
    });
  }
  /* Сортировка: те что есть в COMPANIES — первыми, в порядке COMPANIES; затем кастомные */
  var coOrder={};COMPANIES.forEach(function(c,i){coOrder[c.name]=i;});
  cos.sort(function(a,b){
    var ai=coOrder[a]!=null?coOrder[a]:999;
    var bi=coOrder[b]!=null?coOrder[b]:999;
    if(ai!==bi) return ai-bi;
    return a.localeCompare(b);
  });
  var curCo=co?COMPANIES.find(function(c){return c.name===co;}):null;
  var curSec=curCo?(SECTOR_SOLID[curCo.sector]||'#888'):'#7F77DD';
  var btnLabel=co||'Выберите компанию';
  h += '<div class="dash-topbar">';
  h += '<div class="dash-tb-l" style="gap:10px">';
  h += sbToggleBtnHtml();
  h += '<div class="glass-select" id="gs-fm-co">';
  h += '<button class="glass-select-btn" onclick="event.stopPropagation();glassSelectToggle(\x27gs-fm-co\x27)" type="button" style="padding:5px 10px 5px 11px;gap:8px;min-width:180px;max-width:260px">';
  h += '<span style="width:7px;height:7px;border-radius:50%;background:'+curSec+';flex-shrink:0;box-shadow:0 0 0 2px rgba(255,255,255,.08);'+(co?'':'opacity:.4')+'"></span>';
  h += '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left;'+(co?'':'opacity:.55;font-weight:500')+'">'+esc(btnLabel)+'</span>';
  h += '<svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;opacity:.6"><path d="M2 4.5l4 4 4-4"/></svg>';
  h += '</button>';
  h += '<div class="glass-select-menu" style="min-width:260px;max-height:420px;overflow-y:auto">';
  if(cos.length===0){
    h += '<div style="padding:16px 14px;text-align:center;color:var(--t3);font-size:11.5px;line-height:1.5">Моделей пока нет.<br><span style="font-size:10.5px">Нажмите «Импорт шаблона Excel»<br>или «Редактор драйверов»</span></div>';
  }else{
    cos.forEach(function(n){
      var ci=COMPANIES.find(function(c){return c.name===n;});
      var sc=ci?(SECTOR_SOLID[ci.sector]||'#888'):'#7F77DD';
      var act=n===co;
      var noModel = !hasModelSet[n];
      var noModelTag = noModel ? '<span style="font-size:8.5px;padding:1px 5px;background:rgba(148,163,184,.14);color:#64748B;border-radius:3px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;margin-left:6px">НСБУ</span>' : '';
      h += '<button class="glass-select-item'+(act?' active':'')+'" onclick="event.stopPropagation();glassSelectPick(\x27gs-fm-co\x27,\x27'+esc(n).replace(/'/g,"\\x27")+'\x27,\x27_fmSetCo(v)\x27)" style="display:flex;align-items:center;gap:9px;padding:8px 12px;text-align:left"><span style="width:7px;height:7px;border-radius:50%;background:'+sc+';flex-shrink:0'+(noModel?';opacity:.6':'')+'"></span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(n)+'</span>'+noModelTag+'</button>';
    });
  }
  h += '</div></div></div>';
  /* Центральный hero */
  var titleText=co?('Финансовая модель · '+co):'Финансовая модель';
  var subText=co?'горизонт 7 лет · прогноз + факт':'Загрузите Excel-шаблон или создайте модель вручную';
  h += '<div class="dash-tb-c" style="flex-direction:column;gap:2px">';
  h += '<div id="fm-header-title" style="font-size:14px;font-weight:600;color:#fff;letter-spacing:.01em;line-height:1.2">'+esc(titleText)+'</div>';
  h += '<div id="fm-header-sub" style="font-size:10px;font-weight:500;color:rgba(255,255,255,.55);letter-spacing:.08em;text-transform:uppercase;font-feature-settings:\'tnum\'">'+esc(subText)+'</div>';
  h += '</div>';
  /* Правая: меню */
  h += '<div class="dash-tb-r" style="gap:6px">';
  h += _editMenu('fm-edit', [
    ['↓', 'Импорт шаблона Excel', '_fmShowImport()'],
    ['↑', 'Экспорт Excel (Big 4 / IFI)', '_fmExportExcel()'],
    ['', 'Редактор драйверов', '_fmShowEditor()'],
    ['', 'Анализ чувствительности', '_fmShowSensitivity()'],
    ['---'],
    ['↺', 'Восстановить из черновика', '_fmShowRecoveryUI()'],
    ['↓', 'Экспорт PDF для НС', '_fmExportPDF()'],
    ['---'],
    ['×', 'Сбросить модель', '_fmReset()', 1]
  ]);
  h += '</div></div>';

  /* ═══ Body ═══ */
  h += '<div class="fm-body">';
  h += '<div id="fm-kpi-row" class="fm-kpi-row"></div>';
  h += '<div class="fm-row" style="grid-template-columns:2fr 1fr">';
  h += '<div class="fm-card" style="--d:200ms"><div class="fm-card-ttl"><div class="fm-card-ttl-l">Портфельная дорожная карта EBITDA</div><div class="fm-card-ttl-r" id="fm-road-hint">Факт → прогноз · млрд сум</div></div><div id="fm-road-body"></div></div>';
  h += '<div class="fm-card" style="--d:250ms"><div class="fm-card-ttl"><div class="fm-card-ttl-l">Ключевые инсайты</div></div><div id="fm-insights-body"></div></div>';
  h += '</div>';
  h += '<div class="fm-row" style="grid-template-columns:1fr 1fr">';
  h += '<div class="fm-card" style="--d:280ms"><div class="fm-card-ttl"><div class="fm-card-ttl-l">Ключевые драйверы</div><div class="fm-card-ttl-r">loading factor · capacity</div></div><div id="fm-drivers-body"></div></div>';
  h += '<div class="fm-card" style="--d:320ms"><div class="fm-card-ttl"><div class="fm-card-ttl-l">Оборотный капитал</div><div class="fm-card-ttl-r">дней оборачиваемости</div></div><div id="fm-turnover-body"></div></div>';
  h += '</div>';
  h += '<div class="fm-row" style="grid-template-columns:1fr">';
  h += '<div class="fm-card" style="--d:380ms"><div class="fm-card-ttl"><div class="fm-card-ttl-l">P&L · '+esc(co)+'</div><div class="fm-card-ttl-r">млрд сум</div></div><div id="fm-pnl-body" style="overflow-x:auto"></div></div>';
  h += '</div>';
  /* ═══ НОВЫЕ БЛОКИ: ROIC / Debt+CAPEX / WACC — UZA stylе ═══ */
  h += '<div class="fm-row" style="grid-template-columns:1fr">';
  h += '<div class="uza-card uza-clickable" style="--uza-accent:#1D9E75;--uza-d:430ms" onclick="_fmOpenROICDrill()" title="Детализация ROIC и расчёт NOPAT">';
  h += '<div class="uza-card-ttl"><div class="uza-card-ttl-l"><div class="uza-card-ttl-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10l3-3 2 2 4-5"/><path d="M9 4h3v3"/></svg></div><div class="uza-card-ttl-name">ROIC vs WACC</div><span class="uza-pill uza-pill-teal">value creation</span></div><div class="uza-card-ttl-r">return on invested capital</div></div>';
  h += '<div id="fm-roic-body"></div></div>';
  h += '</div>';
  h += '<div class="fm-row" style="grid-template-columns:1.4fr 1fr">';
  h += '<div class="uza-card uza-clickable" style="--uza-accent:#7F77DD;--uza-d:480ms" onclick="_fmOpenDebtDrill()" title="Детализация долговой нагрузки и графика погашения">';
  h += '<div class="uza-card-ttl"><div class="uza-card-ttl-l"><div class="uza-card-ttl-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="10" height="7" rx="1"/><path d="M5 4V3a2 2 0 1 1 4 0v1"/></svg></div><div class="uza-card-ttl-name">Долговая нагрузка</div><span class="uza-pill uza-pill-gray" id="fm-debt-cov-tag">—</span></div><div class="uza-card-ttl-r">профиль погашения</div></div>';
  h += '<div id="fm-debt-body"></div></div>';
  h += '<div class="uza-card uza-clickable" style="--uza-accent:#EF9F27;--uza-d:530ms" onclick="_fmOpenCapexDrill()" title="Детализация CAPEX программы">';
  h += '<div class="uza-card-ttl"><div class="uza-card-ttl-l"><div class="uza-card-ttl-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11.5h10M3.5 11.5V7l3-3 3 3v4.5"/></svg></div><div class="uza-card-ttl-name">CAPEX программа</div></div><div class="uza-card-ttl-r">млрд сум · maintenance + growth</div></div>';
  h += '<div id="fm-capex-body"></div></div>';
  h += '</div>';
  h += '<div class="fm-row" style="grid-template-columns:1fr">';
  h += '<div class="uza-card" style="--uza-accent:#378ADD;--uza-d:555ms">';
  h += '<div class="uza-card-ttl"><div class="uza-card-ttl-l"><div class="uza-card-ttl-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11h10M3 11V7l2-2 2 2v4M9 11V5l2-2v8"/><circle cx="7" cy="2.5" r=".8" fill="currentColor"/></svg></div><div class="uza-card-ttl-name">Покрытие долга — DSCR / LLCR / PLCR</div><span class="uza-pill uza-pill-blue" id="fm-dscr-tag">—</span></div><div class="uza-card-ttl-r">IFI standard · CFADS / debt service</div></div>';
  h += '<div id="fm-dscr-body"></div></div>';
  h += '</div>';
  h += '<div class="fm-row" style="grid-template-columns:1fr">';
  h += '<div class="uza-card uza-clickable" style="--uza-accent:#7F77DD;--uza-d:580ms" onclick="_fmOpenWACCDrill()" title="Изменить компоненты WACC и пересчитать EV">';
  h += '<div class="uza-card-ttl"><div class="uza-card-ttl-l"><div class="uza-card-ttl-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="2"/><path d="M7 1v2M7 11v2M1 7h2M11 7h2"/></svg></div><div class="uza-card-ttl-name">WACC и его компоненты</div><span class="uza-pill uza-pill-purple" id="fm-wacc-tag">—</span></div><div class="uza-card-ttl-r">cost of capital decomposition</div></div>';
  h += '<div id="fm-wacc-body"></div></div>';
  h += '</div>';
  h += '</div></div>';
  return h;
}

function _fmSetCo(v){
  if(window._fmSelCo===v)return;
  window._fmSelCo=v;
  var btn=document.querySelector('#gs-fm-co .glass-select-btn');
  if(btn){
    var ci=COMPANIES.find(function(c){return c.name===v;});
    var sc=ci?(SECTOR_SOLID[ci.sector]||'#888'):'#888';
    var dot=btn.querySelector('span:first-child');
    var lbl=btn.querySelector('span:nth-child(2)');
    if(dot)dot.style.background=sc;
    if(lbl)lbl.textContent=v;
  }
  document.querySelectorAll('#gs-fm-co .glass-select-item').forEach(function(it){
    var lbl=it.querySelector('span:last-child');
    it.classList.toggle('active', lbl && lbl.textContent===v);
  });
  _fmRepaint();
}
window._fmSetCo=_fmSetCo;

function _fmSetScenario(s){
  if(window._fmScenario===s)return;
  window._fmScenario=s;
  document.querySelectorAll('#fm-scn-seg button[data-scn]').forEach(function(btn){
    var act=btn.getAttribute('data-scn')===s;
    if(act){btn.style.background='rgba(255,255,255,.2)';btn.style.color='#fff';btn.style.boxShadow='0 1px 3px rgba(0,0,0,.15)';}
    else{btn.style.background='transparent';btn.style.color='rgba(255,255,255,.4)';btn.style.boxShadow='none';}
  });
  _fmRepaint();
}
window._fmSetScenario=_fmSetScenario;

/* ── Repaint ────────────────────────────────────────────────────────────── */
function _fmRepaint(){
  var co=window._fmSelCo;
  var scn=window._fmScenario||'base';
  var scnLabels={base:'Базовый',opt:'Оптимистичный',str:'Стрессовый'};
  var hTitle=document.getElementById('fm-header-title');
  var hSub=document.getElementById('fm-header-sub');
  if(!co){
    if(hTitle) hTitle.textContent='Финансовая модель';
    if(hSub) hSub.textContent='Загрузите Excel-шаблон или создайте модель вручную';
    _fmRenderEmpty(null);
    return;
  }
  if(hTitle) hTitle.textContent='Финансовая модель · '+co;
  if(hSub) hSub.textContent='горизонт 7 лет · прогноз + факт';

  var model=(_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn])||null;
  if(!model){
    _fmRenderEmpty(co);
    return;
  }
  _fmEnsureAssumptions(model);
  _fmRecompute(model);
  _fmRenderKPIRow(model);
  _fmRenderRoadmap();
  _fmRenderPnL(model);
  _fmRenderInsights(model);
  _fmRenderDrivers(model);
  _fmRenderTurnover(model);
  _fmRenderROIC(model);
  _fmRenderDebt(model);
  _fmRenderDSCR(model);
  _fmRenderCapex(model);
  _fmRenderWACC(model);
}

function _fmRenderEmpty(co){
  var msg=co
    ? 'Модель для <strong>'+esc(co)+'</strong> ещё не создана'
    : 'Финансовая модель ещё не настроена';
  var hint=co
    ? 'Создайте модель вручную через редактор драйверов или загрузите готовый Excel-шаблон (формат EY/PwC: Volume × Tariffs = Revenue, Fixed/Variable OPEX, CAPEX schedule).'
    : 'Нажмите «Импорт шаблона Excel» или «Создать модель» — система спросит для какой компании создать финансовую модель.';
  var emptyHtml='<div class="fm-empty"><svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#CBD5E1" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:12px"><rect x="6" y="10" width="36" height="30" rx="3"/><path d="M6 18h36M14 26l4 4 4-6 6 6M14 34h20"/></svg>';
  emptyHtml+='<div style="font-size:14px;font-weight:600;color:var(--t1);margin-bottom:6px">'+msg+'</div>';
  emptyHtml+='<div style="max-width:460px;margin:0 auto">'+hint+'</div>';
  emptyHtml+='<div style="margin-top:16px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">';
  emptyHtml+='<button class="fm-empty-btn" onclick="_fmShowEditor()"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 2.5l2 2-8 8H3.5v-2l8-8z"/></svg>Создать модель</button>';
  emptyHtml+='<button class="fm-empty-btn" onclick="_fmShowImport()"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v9M4.5 7.5L8 11l3.5-3.5M3 13.5h10"/></svg>Импорт Excel</button>';
  emptyHtml+='</div></div>';
  ['fm-kpi-row','fm-road-body','fm-insights-body','fm-pnl-body','fm-scn-body'].forEach(function(id){
    var el=document.getElementById(id);if(el)el.innerHTML='';
  });
  var kpiRow=document.getElementById('fm-kpi-row');
  if(kpiRow){kpiRow.style.display='none';}
  var pnlCard=document.getElementById('fm-pnl-body');
  if(pnlCard){
    pnlCard.closest('.fm-card').parentElement.style.display='none';
    pnlCard.closest('.fm-card').parentElement.previousElementSibling.style.display='none';
    pnlCard.closest('.fm-card').parentElement.nextElementSibling.style.display='none';
  }
  var body=document.querySelector('.fm-body');
  if(body){
    /* Реструктурируем body для empty state */
    body.innerHTML='<div class="fm-card" style="--d:100ms">'+emptyHtml+'</div>';
  }
}

function _fmRenderKPIRow(model){
  var row=document.getElementById('fm-kpi-row');if(!row)return;
  row.style.display='grid';
  var o=model.outputs||{};
  var horizon=model.horizon||{};
  var lastFact=(horizon.factYears||[]).slice(-1)[0];
  var firstFc=(horizon.forecastYears||[])[0];
  var lastFc=(horizon.forecastYears||[]).slice(-1)[0];
  var wacc=(model.assumptions&&model.assumptions.wacc)||0.12;
  var growth=(model.assumptions&&model.assumptions.terminalGrowth)||0.03;
  /* NPV — дисконтированные FCFF */
  var npv=0, pvSum=0;
  (horizon.forecastYears||[]).forEach(function(y,i){
    var fcff=o.cf&&o.cf.fcff&&o.cf.fcff[y];
    if(fcff!=null){
      var df=Math.pow(1+wacc, i+1);
      npv += fcff/df;
      pvSum += fcff/df;
    }
  });
  /* Enterprise Value = Σ PV(FCFF) + PV(Terminal Value)
     TV = FCFF_lastFc × (1+g) / (WACC - g) */
  var ev=null;
  if(lastFc){
    var fcffLast=o.cf&&o.cf.fcff&&o.cf.fcff[lastFc];
    if(fcffLast!=null&&wacc>growth){
      var tv=fcffLast*(1+growth)/(wacc-growth);
      var n=(horizon.forecastYears||[]).length;
      var pvTV=tv/Math.pow(1+wacc, n);
      ev=pvSum+pvTV;
    }
  }
  /* EBITDA CAGR */
  var eFact=o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFact];
  var eFc=o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc];
  var yrsDiff=(lastFc&&lastFact)?(lastFc-lastFact):0;
  var cagr=(eFact&&eFc&&yrsDiff>0)?(Math.pow(Math.abs(eFc/eFact), 1/yrsDiff)-1):null;
  /* Free Cash Flow суммарный (прогноз) + на последний год */
  var fcfTotal=0, fcfLast=null;
  (horizon.forecastYears||[]).forEach(function(y){
    var v=o.cf&&o.cf.fcf&&o.cf.fcf[y];
    if(v!=null){fcfTotal+=v;if(y===lastFc)fcfLast=v;}
  });
  /* Revenue */
  var revLast=o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFc];
  /* EBITDA margin */
  var ebMargin=o.ratios&&o.ratios.ebitdaMargin&&o.ratios.ebitdaMargin[lastFc];
  /* Net Debt + Equity Value */
  var netDebtLast=o.bs&&o.bs.netDebt&&o.bs.netDebt[lastFc];
  var equityVal=o.ratios&&o.ratios.equityValue;
  var nETtoEB=null;
  if(netDebtLast!=null&&o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc]){
    nETtoEB=netDebtLast/o.pnl.ebitda[lastFc];
  }

  /* fmt → HTML с data-countup для счётчика. Возвращает span + суффикс где нужно. */
  function fmt(v,dec){
    if(v==null||isNaN(v))return '<span style="color:var(--t3)">—</span>';
    var a=Math.abs(v);
    if(a>=1000000){
      /* Триллионы */
      var val=v/1000;
      var d=val>=100?0:(val>=10?1:2);
      return '<span data-countup="'+val+'" data-cu-d="'+d+'"></span><span style="font-size:.58em;color:var(--t3);font-weight:500;margin-left:3px">трлн</span>';
    }
    if(a>=1000){
      return '<span data-countup="'+v+'" data-cu-d="0" data-cu-sep></span>';
    }
    if(a>=1){
      return '<span data-countup="'+v+'" data-cu-d="'+(dec||0)+'"></span>';
    }
    return '<span data-countup="'+v+'" data-cu-d="'+(dec||1)+'"></span>';
  }
  /* fmtPct — для процентов (EBITDA margin и пр.) */
  function fmtPct(v,dec){
    if(v==null||isNaN(v))return '<span style="color:var(--t3)">—</span>';
    var val=v*100;
    return '<span data-countup="'+val+'" data-cu-d="'+(dec||1)+'"></span><span style="font-size:.65em;color:var(--t3);font-weight:500;margin-left:2px">%</span>';
  }
  function spark(seriesKey, color, section){
    var src;
    if(section==='cf') src=(o.cf||{});
    else if(section==='bs') src=(o.bs||{});
    else src=(o.pnl||{});
    var vals=src[seriesKey]||{};
    var allY=[].concat(horizon.factYears||[], horizon.forecastYears||[]);
    var pts=allY.map(function(y){return vals[y];}).filter(function(v){return v!=null;});
    if(pts.length<2)return '';
    var max=Math.max.apply(null,pts), min=Math.min.apply(null,pts);
    var range=max-min||1;
    var w=110, h=24;
    var step=pts.length>1?w/(pts.length-1):w;
    var d='M';
    pts.forEach(function(v,i){
      var x=i*step;
      var y=h-((v-min)/range)*(h-4)-2;
      d += (i?' L':'')+x.toFixed(1)+','+y.toFixed(1);
    });
    var lastX=(pts.length-1)*step, lastY=h-((pts[pts.length-1]-min)/range)*(h-4)-2;
    var gid='fmspk_'+section+'_'+seriesKey+'_'+Math.floor(Math.random()*1000);
    return '<svg class="kpi2-spark" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" style="height:24px;margin-top:6px;opacity:.85;width:100%"><defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="'+color+'" stop-opacity=".28"/><stop offset="100%" stop-color="'+color+'" stop-opacity="0"/></linearGradient></defs><path d="'+d+' L'+w+','+h+' L0,'+h+' Z" fill="url(#'+gid+')"/><path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="'+lastX.toFixed(1)+'" cy="'+lastY.toFixed(1)+'" r="2" fill="'+color+'"/></svg>';
  }

  var cards=[
    {kind:'ev',         accent:'#7F77DD',d:0,  l:'Стоимость компании (EV)', v:fmt(ev), s:'DCF @ WACC '+(wacc*100).toFixed(0)+'% + TV', spk:spark('revenue','#7F77DD','pnl')},
    {kind:'equity',     accent:'#6B8EDE',d:60, l:'Equity Value',            v:fmt(equityVal), s:'EV − Net Debt (на '+(lastFc||'—')+')', spk:spark('netIncome','#6B8EDE','pnl')},
    {kind:'npv',        accent:'#1D9E75',d:120,l:'NPV прогноза',            v:fmt(npv),s:'дисконт. FCFF · млрд сум',             spk:spark('fcff','#1D9E75','cf')},
    {kind:'fcf',        accent:'#378ADD',d:180,l:'FCF '+(lastFc||''),       v:fmt(fcfLast),s:'свободный денежный поток',          spk:spark('fcf','#378ADD','cf')},
    {kind:'netdebt',    accent:netDebtLast!=null&&netDebtLast>0?'#E24B4A':'#1D9E75',d:240,l:'Net Debt '+(lastFc||''), v:fmt(netDebtLast), s:nETtoEB!=null?'Net Debt/EBITDA '+nETtoEB.toFixed(1)+'×':'чистый долг', spk:spark('totalDebt','#E24B4A','bs')},
    {kind:'revenue',    accent:'#EF9F27',d:300,l:'Выручка '+(lastFc||''),   v:fmt(revLast),s:'прогноз · млрд сум',                spk:spark('revenue','#EF9F27','pnl')},
    {kind:'ebitdaMargin',accent:'#9F6BDD',d:360,l:'EBITDA margin '+(lastFc||''), v:fmtPct(ebMargin,1), s:cagr!=null?('CAGR '+(cagr>=0?'+':'')+(cagr*100).toFixed(1)+'%'):'маржинальность', spk:spark('ebitda','#9F6BDD','pnl')}
  ];
  var html='';
  cards.forEach(function(k){
    html += '<div class="kpi2 fin-shimmer" onclick="_fmKpiDrill(\''+k.kind+'\')" style="--kpi2-accent:'+k.accent+';--kpi2-d:'+k.d+'ms;animation:kpiCardIn .5s cubic-bezier(.34,1.2,.64,1) '+k.d+'ms both;cursor:pointer" title="Подробнее">';
    html += '<div>';
    html += '<div class="kpi2-lbl">'+k.l+'</div>';
    html += '<div class="kpi2-val" style="color:var(--t1)">'+k.v+'</div>';
    html += '<div class="kpi2-sub">'+k.s+'</div>';
    html += '</div>';
    html += k.spk;
    html += '</div>';
  });
  row.innerHTML=html;
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(row, 100);}, 50);
}

function _fmRenderRoadmap(){
  var box=document.getElementById('fm-road-body');if(!box)return;
  var scn=window._fmScenario||'base';
  /* Собираем EBITDA всех компаний по годам */
  var allYears=[], comps=[];
  COMPANIES.forEach(function(co){
    var m=_db.finModel&&_db.finModel[co.name]&&_db.finModel[co.name][scn];
    if(!m||!m.outputs||!m.outputs.pnl||!m.outputs.pnl.ebitda)return;
    var years=[].concat(m.horizon.factYears||[], m.horizon.forecastYears||[]);
    years.forEach(function(y){if(allYears.indexOf(y)<0)allYears.push(y);});
    comps.push({co:co,years:years,ebitda:m.outputs.pnl.ebitda,factYears:m.horizon.factYears||[]});
  });
  if(!comps.length){
    box.innerHTML='<div style="padding:28px 12px;text-align:center;color:var(--t3);font-size:12px">Нет моделей. Создайте первую, чтобы увидеть портфельную панораму.</div>';
    return;
  }
  allYears.sort(function(a,b){return a-b;});
  /* Max EBITDA для нормализации высоты */
  var maxEb=0;
  comps.forEach(function(c){c.years.forEach(function(y){var v=c.ebitda[y]||0;if(Math.abs(v)>maxEb)maxEb=Math.abs(v);});});
  if(!maxEb)maxEb=1;
  /* Header */
  var html='<div class="fm-road-hd"><div style="font-size:9.5px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.05em">Компания</div><div class="fm-road-years">';
  allYears.forEach(function(y,i){
    var isFact=comps[0].factYears.indexOf(y)>=0;
    html += '<div class="fm-road-year '+(isFact?'fact':'fc')+'">'+y+(isFact?'':' П')+'</div>';
  });
  html += '</div></div>';
  /* Rows */
  comps.forEach(function(c,ci){
    var secColor=SECTOR_SOLID[c.co.sector]||'#7F77DD';
    html += '<div class="fm-road-row" style="--rd:'+(ci*40)+'ms" onclick="_fmSetCo(\x27'+esc(c.co.name).replace(/'/g,"\\x27")+'\x27)">';
    html += '<div class="fm-road-co"><div class="fm-road-co-strip" style="background:'+secColor+'"></div><div class="fm-road-co-name">'+esc(c.co.name)+'</div></div>';
    html += '<div class="fm-road-bars">';
    allYears.forEach(function(y){
      var v=c.ebitda[y]||0;
      var isFact=c.factYears.indexOf(y)>=0;
      var hPct=Math.min(100, Math.abs(v)/maxEb*100);
      var ttl=y+(isFact?' (факт)':' (прогноз)')+': '+(v==null?'—':(v>=0?'+':'')+v.toFixed(1)+' млрд сум');
      html += '<div class="fm-road-bar" title="'+esc(ttl)+'"><div class="fm-road-bar-fill '+(isFact?'fact':'fc')+'" style="height:'+hPct+'%;--bc:'+secColor+'"></div></div>';
    });
    html += '</div></div>';
  });
  box.innerHTML=html;
}

function _fmRenderPnL(model){
  var box=document.getElementById('fm-pnl-body');if(!box)return;
  var o=model.outputs||{pnl:{}};
  var horizon=model.horizon||{};
  var years=[].concat(horizon.factYears||[], horizon.forecastYears||[]);
  var factYears=horizon.factYears||[];
  function fmt(v){if(v==null||isNaN(v))return '—';return v.toLocaleString('ru-RU',{maximumFractionDigits:0});}
  function cellCls(y){return factYears.indexOf(y)>=0?'':'fc-cell';}
  var rows=[
    {l:'Выручка',k:'revenue',strong:true},
    {l:'Себестоимость',k:'cogs',neg:true},
    {l:'Валовая прибыль',k:'grossProfit',subtotal:true},
    {l:'Операционная прибыль',k:'opProfit',subtotal:true},
    {l:'Чистая прибыль',k:'netIncome',strong:true},
    {l:'EBITDA',k:'ebitda',strong:true}
  ];
  var html='<table class="fm-pnl"><thead><tr><th>Показатель</th>';
  years.forEach(function(y){
    var isF=factYears.indexOf(y)>=0;
    html += '<th class="'+(isF?'fact':'fc')+'">'+y+(isF?'':' П')+'</th>';
  });
  html += '</tr></thead><tbody>';
  rows.forEach(function(r){
    var cls=(r.strong?'strong ':'')+(r.subtotal?'subtotal ':'');
    html += '<tr class="'+cls+'"><td>'+r.l+'</td>';
    years.forEach(function(y){
      var v=o.pnl&&o.pnl[r.k]&&o.pnl[r.k][y];
      var tdCls=cellCls(y);
      if(r.neg&&v!=null&&v<0)tdCls+=' neg';
      html += '<td class="'+tdCls+'">'+fmt(v)+'</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  box.innerHTML=html;
}

function _fmRenderInsights(model){
  var box=document.getElementById('fm-insights-body');if(!box)return;
  var o=model.outputs||{};var horizon=model.horizon||{};
  var insights=[];
  var lastFc=(horizon.forecastYears||[]).slice(-1)[0];
  var firstFc=(horizon.forecastYears||[])[0];
  var lastFact=(horizon.factYears||[]).slice(-1)[0];
  /* Insight: рост выручки */
  if(o.pnl&&o.pnl.revenue){
    var rLast=o.pnl.revenue[lastFc];
    var rFact=o.pnl.revenue[lastFact];
    if(rLast&&rFact){
      var delta=(rLast-rFact)/Math.abs(rFact);
      if(delta>=0.15) insights.push({t:'up',title:'Рост выручки '+Math.round(delta*100)+'% к '+lastFc,desc:'с '+Math.round(rFact).toLocaleString('ru-RU')+' до '+Math.round(rLast).toLocaleString('ru-RU')+' млрд сум'});
      else if(delta<=-0.05) insights.push({t:'down',title:'Снижение выручки '+Math.round(delta*100)+'%',desc:'к концу горизонта с '+Math.round(rFact).toLocaleString('ru-RU')+' до '+Math.round(rLast).toLocaleString('ru-RU')+' млрд сум'});
    }
  }
  /* Insight: margin compression / expansion */
  if(o.ratios&&o.ratios.ebitdaMargin){
    var mFact=o.ratios.ebitdaMargin[lastFact];
    var mFc=o.ratios.ebitdaMargin[lastFc];
    if(mFact!=null&&mFc!=null){
      var mDelta=mFc-mFact;
      if(Math.abs(mDelta)>=0.03){
        insights.push({t:mDelta>=0?'up':'down',title:(mDelta>=0?'Расширение маржи EBITDA ':'Сжатие маржи EBITDA ')+(mDelta>=0?'+':'')+(mDelta*100).toFixed(1)+' п.п.',desc:'с '+(mFact*100).toFixed(1)+'% до '+(mFc*100).toFixed(1)+'% к '+lastFc});
      }
    }
  }
  /* Insight: CAPEX burden */
  var totalCapex=0;
  (model.drivers&&model.drivers.capex||[]).forEach(function(c){
    (horizon.forecastYears||[]).forEach(function(y){var v=c.values&&c.values[y];if(v!=null)totalCapex+=v;});
  });
  var totalRev=0;
  (horizon.forecastYears||[]).forEach(function(y){var v=o.pnl&&o.pnl.revenue&&o.pnl.revenue[y];if(v!=null)totalRev+=v;});
  if(totalCapex>0&&totalRev>0){
    var capexIntensity=totalCapex/totalRev;
    if(capexIntensity>=0.15) insights.push({t:'down',title:'Высокая CAPEX-интенсивность '+Math.round(capexIntensity*100)+'%',desc:'общий CAPEX '+Math.round(totalCapex).toLocaleString('ru-RU')+' млрд сум за период прогноза'});
  }
  /* Insight: FCF breakeven */
  var fcfFirst=o.cf&&o.cf.fcf&&o.cf.fcf[firstFc];
  var fcfLast=o.cf&&o.cf.fcf&&o.cf.fcf[lastFc];
  if(fcfFirst!=null&&fcfFirst<0&&fcfLast!=null&&fcfLast>0){
    insights.push({t:'up',title:'Выход на положительный FCF',desc:'с '+Math.round(fcfFirst).toLocaleString('ru-RU')+' в '+firstFc+' до '+Math.round(fcfLast).toLocaleString('ru-RU')+' в '+lastFc});
  }else if(fcfLast!=null&&fcfLast<0){
    insights.push({t:'down',title:'Отрицательный FCF '+lastFc,desc:Math.round(fcfLast).toLocaleString('ru-RU')+' млрд сум · требуется финансирование'});
  }
  if(!insights.length){
    box.innerHTML='<div style="padding:20px 8px;text-align:center;color:var(--t3);font-size:11.5px">Инсайты появятся после заполнения драйверов модели.</div>';
    return;
  }
  var html='';
  insights.slice(0,5).forEach(function(ins,i){
    var ico=ins.t==='up'
      ? '<svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3v8M3.5 6L7 2.5L10.5 6"/></svg>'
      : '<svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#E24B4A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3v8M3.5 8L7 11.5L10.5 8"/></svg>';
    html += '<div class="fm-insight '+ins.t+'" style="--rd:'+(i*50)+'ms"><div class="fm-insight-ico">'+ico+'</div><div class="fm-insight-body"><div class="fm-insight-ttl">'+esc(ins.title)+'</div><div class="fm-insight-desc">'+esc(ins.desc)+'</div></div></div>';
  });
  box.innerHTML=html;
}

/* ── Ключевые драйверы (Key drivers) — company-specific ───────────────── */
function _fmRenderDrivers(model){
  var box=document.getElementById('fm-drivers-body');if(!box)return;
  var co=window._fmSelCo;
  var horizon=model.horizon||{};
  var lastFact=(horizon.factYears||[]).slice(-1)[0];

  /* Uzbekistan Airports — специфика: загрузка аэропортов по локациям */
  if(co==='Uzbekistan Airports'&&Array.isArray(model.airportLoad)&&model.airportLoad.length){
    /* Валидация: load должен быть коэффициентом 0-1.2 (0-120%).
       Если все значения вне диапазона (placeholders, null, >1.2) — показываем empty state.
       Частый кейс: Excel содержит "7" как placeholder → 700% = артефакт, не реальные данные. */
    var validLoads = model.airportLoad.filter(function(a){
      return typeof a.load==='number' && !isNaN(a.load) && a.load>0 && a.load<=1.2;
    });
    if(validLoads.length===0){
      /* Нет валидных данных — показываем приглашение */
      box.innerHTML='<div style="padding:24px 12px;text-align:center;color:var(--t3);font-size:11.5px;line-height:1.6">'+
        '<div style="margin-bottom:6px;font-weight:600;color:var(--t2)">Загрузка аэропортов не заполнена</div>'+
        '<div style="font-size:10.5px">Значения коэффициентов загрузки должны быть в диапазоне 0…1<br>(например, 0,72 = 72% загрузки).</div>'+
        '<div style="font-size:10px;margin-top:6px;color:#94A3B8">Заполните лист <em>«Control - dashboard»</em> и переимпортируйте Excel</div>'+
      '</div>';
      return;
    }
    
    var html='<div style="display:grid;gap:6px">';
    /* Header */
    html += '<div style="display:grid;grid-template-columns:1fr 60px 80px;gap:10px;padding:4px 0 6px;border-bottom:0.5px solid rgba(0,0,0,.05)">';
    html += '<div style="font-size:9.5px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.05em">Аэропорт</div>';
    html += '<div style="font-size:9.5px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.05em;text-align:right">Загрузка</div>';
    html += '<div style="font-size:9.5px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.05em;text-align:right">Индекс</div>';
    html += '</div>';
    model.airportLoad.forEach(function(a, i){
      var isValid = typeof a.load==='number' && !isNaN(a.load) && a.load>0 && a.load<=1.2;
      var pct = isValid ? a.load : null;
      var pctStr = pct!=null ? ((pct*100).toFixed(0)+'%') : '—';
      var barW = pct!=null ? Math.min(100, pct*100) : 0;
      var barColor = pct==null ? '#CBD5E1' : (barW>=70?'#1D9E75':(barW>=40?'#EF9F27':'#E24B4A'));
      var textColor = pct==null ? 'var(--t3)' : barColor;
      html += '<div style="display:grid;grid-template-columns:1fr 60px 80px;gap:10px;align-items:center;padding:3px 0;animation:fmNumIn .3s ease '+(i*35)+'ms both">';
      html += '<div style="font-size:11.5px;color:var(--t1);font-weight:500">'+esc(a.name)+'</div>';
      html += '<div style="font-size:11.5px;color:'+textColor+';font-weight:700;text-align:right;font-feature-settings:\'tnum\'">'+pctStr+'</div>';
      html += '<div style="height:6px;background:rgba(0,0,0,.04);border-radius:3px;overflow:hidden">'+(pct!=null?'<div style="height:100%;width:'+barW+'%;background:'+barColor+';border-radius:3px;animation:fmBarFill .6s cubic-bezier(.22,.61,.36,1) '+(i*35+100)+'ms both"></div>':'')+'</div>';
      html += '</div>';
    });
    html += '</div>';
    box.innerHTML=html;
    return;
  }

  /* Generic — показываем top-3 объёма по модели */
  var vols=(model.drivers&&model.drivers.volumes||[]).filter(function(v){return !v.isSub;});
  if(!vols.length){
    box.innerHTML='<div style="padding:20px 8px;text-align:center;color:var(--t3);font-size:11.5px">Драйверы модели не определены.<br><span style="font-size:10.5px">Добавьте объёмы через редактор драйверов.</span></div>';
    return;
  }
  var html='<div style="display:grid;gap:8px">';
  vols.slice(0,4).forEach(function(v, i){
    var last=v.values&&v.values[lastFact];
    var fcY=(horizon.forecastYears||[]).slice(-1)[0];
    var future=v.values&&v.values[fcY];
    var growth=(last&&future&&last!==0)?((future/last-1)*100):null;
    html += '<div style="padding:8px 10px;background:rgba(127,119,221,.04);border-left:3px solid #7F77DD;border-radius:6px;animation:fmNumIn .3s ease '+(i*40)+'ms both">';
    html += '<div style="font-size:11px;color:var(--t1);font-weight:600;margin-bottom:3px">'+esc(v.name)+'</div>';
    html += '<div style="display:flex;justify-content:space-between;align-items:baseline">';
    html += '<div style="font-size:10.5px;color:var(--t3)">'+esc(v.unit||'')+(lastFact?' · '+lastFact:'')+'</div>';
    html += '<div style="font-size:13px;font-weight:700;color:var(--t1);font-feature-settings:\'tnum\'">'+(last!=null?last.toLocaleString('ru-RU',{maximumFractionDigits:0}):'—')+(growth!=null?' <span style="font-size:10.5px;color:'+(growth>=0?'#1D9E75':'#E24B4A')+';font-weight:600">'+(growth>=0?'+':'')+growth.toFixed(0)+'%</span>':'')+'</div>';
    html += '</div>';
    html += '</div>';
  });
  html += '</div>';
  box.innerHTML=html;
}

/* ── Оборотный капитал (Turnover days) ──────────────────────────────────── */
function _fmRenderTurnover(model){
  var box=document.getElementById('fm-turnover-body');if(!box)return;
  var wc=(model.drivers&&model.drivers.wc)||{};
  var kr=model.keyRatios||{};
  var o=model.outputs||{};
  var horizon=model.horizon||{};
  var lastFact=(horizon.factYears||[]).slice(-1)[0];
  var rev=o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFact];
  var cost=o.pnl&&o.pnl.cogs&&o.pnl.cogs[lastFact];

  /* Если есть keyRatios из Control dashboard — используем их (точнее) */
  var items=[
    {l:'Оборачиваемость дебиторской',k:'dso',altKey:'receivableTurnover',sub:'DSO · дебиторская',color:'#7F77DD',base:rev,unit:'выручки'},
    {l:'Оборачиваемость запасов',k:'dio',altKey:'inventoryTurnover',sub:'DIO · запасы',color:'#1D9E75',base:cost,unit:'себестоимости'},
    {l:'Оборачиваемость кредиторской',k:'dpo',altKey:'payablesTurnover',sub:'DPO · кредиторская',color:'#EF9F27',base:cost,unit:'себестоимости'},
    {l:'Оборачиваемость авансов',k:'dap',altKey:null,sub:'DAP · авансы полученные',color:'#378ADD',base:rev,unit:'выручки'}
  ];
  var html='<div style="display:grid;gap:9px">';
  items.forEach(function(it,i){
    var days=(it.altKey&&kr[it.altKey]!=null)?kr[it.altKey]:wc[it.k];
    var amount=(days!=null&&it.base)?(it.base*days/365):null;
    var daysStr=(days!=null?days.toFixed(days<20?2:0)+' дн':'—');
    html += '<div onclick="_fmTurnoverDrill(\''+it.k+'\')" style="padding:9px 11px;background:#fff;border:1px solid rgba(0,0,0,.04);border-radius:8px;animation:fmNumIn .3s ease '+(i*40)+'ms both;border-left:3px solid '+it.color+';cursor:pointer;transition:all .2s" onmouseover="this.style.transform=\'translateX(2px)\';this.style.boxShadow=\'0 4px 12px rgba(15,23,60,.06)\'" onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'" title="Подробнее">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">';
    html += '<div style="font-size:11px;color:var(--t1);font-weight:500">'+esc(it.l)+'</div>';
    html += '<div style="font-size:14px;font-weight:500;color:var(--t1);font-feature-settings:\'tnum\';letter-spacing:-.01em">'+daysStr+'</div>';
    html += '</div>';
    html += '<div style="display:flex;justify-content:space-between;align-items:baseline">';
    html += '<div style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500">'+esc(it.sub)+'</div>';
    html += '<div style="font-size:10.5px;color:var(--t3);font-feature-settings:\'tnum\'">≈ '+(amount!=null?amount.toLocaleString('ru-RU',{maximumFractionDigits:0}):'—')+' (от '+it.unit+')</div>';
    html += '</div>';
    html += '</div>';
  });
  html += '</div>';
  box.innerHTML=html;
}

/* ═══════════════════════════════════════════════════════════════════════════
   UZA DESIGN SYSTEM · Единый стиль модалов и карточек на базе .kpi2 / Финансов
   ═══════════════════════════════════════════════════════════════════════════ */
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

/* ═══════════════════════════════════════════════════════════════════════════
   UZA helpers
   ═══════════════════════════════════════════════════════════════════════════ */

/* Универсальный modal frame в новом стиле */
function _uzaOpenModal(opts){
  /* opts: {id, title, subtitle, accent, icon (svg), bodyHtml, footHtml} */
  var existing=document.getElementById(opts.id||'uza-modal-instance');
  if(existing){
    existing.style.animation='uzaOvIn .2s ease reverse forwards';
    setTimeout(function(){if(existing.parentNode)existing.parentNode.removeChild(existing);},200);
  }
  var ov=document.createElement('div');
  ov.id=opts.id||'uza-modal-instance';
  ov.className='uza-modal-ov';
  ov.style.setProperty('--uza-accent', opts.accent||'#7F77DD');
  ov.onclick=function(e){if(e.target===ov)_uzaCloseModal(ov.id);};
  var modal=document.createElement('div');
  modal.className='uza-modal';
  var iconHtml=opts.icon||'';
  var subHtml=opts.subtitle?'<div class="uza-modal-h-sub">'+esc(opts.subtitle)+'</div>':'';
  modal.innerHTML=
    '<div class="uza-modal-h">'+
      '<div class="uza-modal-h-l">'+
        '<div class="uza-modal-h-row">'+
          (iconHtml?'<div class="uza-modal-h-icon">'+iconHtml+'</div>':'')+
          '<div class="uza-modal-h-ttl">'+esc(opts.title||'')+'</div>'+
          (opts.pill?'<span class="uza-pill '+(opts.pillClass||'uza-pill-purple')+'">'+esc(opts.pill)+'</span>':'')+
        '</div>'+
        subHtml+
      '</div>'+
      '<button class="uza-modal-x" onclick="_uzaCloseModal(\''+ov.id+'\')" title="Закрыть"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"/></svg></button>'+
    '</div>'+
    '<div class="uza-modal-body">'+(opts.bodyHtml||'')+'</div>'+
    (opts.footHtml?'<div class="uza-modal-foot">'+opts.footHtml+'</div>':'');
  ov.appendChild(modal);
  document.body.appendChild(ov);
  /* ESC handler */
  var escH=function(e){if(e.key==='Escape'){_uzaCloseModal(ov.id);document.removeEventListener('keydown',escH);}};
  document.addEventListener('keydown',escH);
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(modal,80);},150);
  return modal;
}
window._uzaOpenModal=_uzaOpenModal;

function _uzaCloseModal(id){
  var ov=document.getElementById(id||'uza-modal-instance');
  if(!ov)return;
  ov.style.animation='uzaOvIn .2s ease reverse forwards';
  var modal=ov.querySelector('.uza-modal');
  if(modal) modal.style.animation='uzaModalIn .25s ease reverse forwards';
  setTimeout(function(){if(ov&&ov.parentNode)ov.parentNode.removeChild(ov);},220);
}
window._uzaCloseModal=_uzaCloseModal;

/* Helper: мини-KPI карточка */
function _uzaMiniKpi(opts){
  /* opts: {label, value, sub, dotColor, delay} */
  var dot=opts.dotColor?'<div class="uza-mini-status-dot" style="background:'+opts.dotColor+'"></div>':'';
  return '<div class="uza-mini" style="--uza-md:'+(opts.delay||0)+'ms">'+dot+
    '<div class="uza-mini-lbl">'+(opts.label||'')+'</div>'+
    '<div class="uza-mini-val">'+(opts.value||'—')+'</div>'+
    (opts.sub?'<div class="uza-mini-sub">'+opts.sub+'</div>':'')+
  '</div>';
}
window._uzaMiniKpi=_uzaMiniKpi;

/* Number formatting (locale ru-RU) */
function _uzaFmtNum(v,dec){
  if(v==null||isNaN(v))return '<span style="color:var(--t3)">—</span>';
  var a=Math.abs(v);
  if(a>=1000000) return (v/1000).toLocaleString('ru-RU',{maximumFractionDigits:1})+' трлн';
  if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
  return v.toLocaleString('ru-RU',{maximumFractionDigits:dec||0});
}
window._uzaFmtNum=_uzaFmtNum;


/* ═══════════════════════════════════════════════════════════════════════════
   ФИНМОДЕЛЬ: ROIC, Долговая нагрузка, CAPEX, WACC — расчёт + рендер + drill
   ═══════════════════════════════════════════════════════════════════════════ */

/* Дефолты для компонентов WACC. Применяются если в model.assumptions их нет. */
var _FM_WACC_DEFAULTS={riskFreeRate:0.14,beta:1.1,marketRiskPremium:0.06,countryAdjustment:-0.058,effectiveCostOfDebt:0.09};

/* Гарантирует наличие новых assumption-полей в модели. */
function _fmEnsureAssumptions(model){
  if(!model)return;
  model.assumptions=model.assumptions||{};
  Object.keys(_FM_WACC_DEFAULTS).forEach(function(k){
    if(model.assumptions[k]==null) model.assumptions[k]=_FM_WACC_DEFAULTS[k];
  });
  if(model.assumptions.taxRate==null) model.assumptions.taxRate=0.15;
  if(model.assumptions.wacc==null) model.assumptions.wacc=0.12;
  if(model.assumptions.terminalGrowth==null) model.assumptions.terminalGrowth=0.03;
}
window._fmEnsureAssumptions=_fmEnsureAssumptions;

/* Числовое форматирование: возвращает строку без HTML (для модалов и tooltip).
   Для inline в карточках используются data-countup span'ы. */
function _fmFmtNum(v,dec){
  if(v==null||isNaN(v))return '—';
  var a=Math.abs(v);
  if(a>=1000000) return (v/1000).toLocaleString('ru-RU',{maximumFractionDigits:a>=10000000?0:1})+' трлн';
  if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
  if(a>=1) return v.toLocaleString('ru-RU',{maximumFractionDigits:dec||0});
  return v.toLocaleString('ru-RU',{maximumFractionDigits:dec||1});
}
function _fmFmtPct(v,dec){
  if(v==null||isNaN(v))return '—';
  return (v*100).toFixed(dec==null?1:dec)+'%';
}

/* ───────────────── ROIC ───────────────── */
function _fmComputeROIC(model){
  var o=model.outputs||{},h=model.horizon||{};
  var taxRate=(model.assumptions&&model.assumptions.taxRate)||0.15;
  var wacc=(model.assumptions&&model.assumptions.wacc)||0.12;
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var byYear={},nopatBy={},icBy={};
  allY.forEach(function(y){
    var op=o.pnl&&o.pnl.opProfit&&o.pnl.opProfit[y];
    var debt=o.bs&&o.bs.totalDebt&&o.bs.totalDebt[y];
    var eq=o.bs&&o.bs.equity&&o.bs.equity[y];
    var cash=o.bs&&o.bs.cash&&o.bs.cash[y];
    if(op==null||eq==null)return;
    var nopat=op*(1-taxRate);
    var ic=(eq||0)+(debt||0)-(cash||0);
    nopatBy[y]=nopat;
    icBy[y]=ic;
    byYear[y]=ic>0?nopat/ic:null;
  });
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var roicLast=lastFc&&byYear[lastFc]!=null?byYear[lastFc]:null;
  var ic_last=lastFc&&icBy[lastFc]||null;
  var nopat_last=lastFc&&nopatBy[lastFc]||null;
  var spread=roicLast!=null?roicLast-wacc:null;
  var eva=spread!=null&&ic_last!=null?spread*ic_last:null;
  return{byYear:byYear,nopatBy:nopatBy,icBy:icBy,roicLast:roicLast,nopatLast:nopat_last,icLast:ic_last,wacc:wacc,spread:spread,eva:eva,lastFc:lastFc};
}
window._fmComputeROIC=_fmComputeROIC;

/* ───────────────── DEBT ───────────────── */
function _fmComputeDebt(model){
  var o=model.outputs||{},h=model.horizon||{};
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var debt=lastFc?(o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]):null;
  var eb=lastFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc]):null;
  var nd=lastFc?(o.bs&&o.bs.netDebt&&o.bs.netDebt[lastFc]):null;
  /* Процентные расходы могут лежать в finCost (out.pnl.finCost) или interest */
  var int=lastFc?((o.pnl&&o.pnl.finCost&&o.pnl.finCost[lastFc])||(o.pnl&&o.pnl.interest&&o.pnl.interest[lastFc])):null;
  var eq=lastFc?(o.bs&&o.bs.equity&&o.bs.equity[lastFc]):null;
  var ndE=eb&&eb!==0?(nd!=null?nd/eb:null):null;
  var intCov=int&&int!==0?(eb!=null?eb/Math.abs(int):null):null;
  var totCap=(debt||0)+(eq||0);
  var debtEq=totCap>0?debt/totCap:null;
  /* YoY deltas */
  var prevFc=(h.forecastYears||[]).slice(-2)[0]||(h.factYears||[]).slice(-1)[0];
  var prevNd=prevFc?(o.bs&&o.bs.netDebt&&o.bs.netDebt[prevFc]):null;
  var prevEb=prevFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[prevFc]):null;
  var prevInt=prevFc?((o.pnl&&o.pnl.finCost&&o.pnl.finCost[prevFc])||(o.pnl&&o.pnl.interest&&o.pnl.interest[prevFc])):null;
  var prevNdE=prevEb&&prevEb!==0?(prevNd!=null?prevNd/prevEb:null):null;
  var prevIntCov=prevInt&&prevInt!==0?(prevEb!=null?prevEb/Math.abs(prevInt):null):null;
  var deltaNdE=ndE!=null&&prevNdE!=null?ndE-prevNdE:null;
  var deltaIntCov=intCov!=null&&prevIntCov!=null?intCov-prevIntCov:null;
  /* Schedule по годам */
  var schedule=allY.map(function(y){
    var lt=(o.bs&&o.bs.ltDebt&&o.bs.ltDebt[y])||0;
    var st=(o.bs&&o.bs.stDebt&&o.bs.stDebt[y])||0;
    var total=lt+st;
    if(!total){
      var td=(o.bs&&o.bs.totalDebt&&o.bs.totalDebt[y])||0;
      lt=td*0.7;st=td*0.3;total=td;
    }
    return{y:y,lt:lt,st:st,total:total,isFc:!factSet[y]};
  });
  return{ndE:ndE,intCov:intCov,debtEq:debtEq,schedule:schedule,covNdE:3.0,covIntCov:2.5,deltaNdE:deltaNdE,deltaIntCov:deltaIntCov,covOk:(ndE==null||ndE<=3.0)&&(intCov==null||intCov>=2.5)};
}
window._fmComputeDebt=_fmComputeDebt;

/* ───────────────── CAPEX ───────────────── */
function _fmComputeCapex(model){
  var o=model.outputs||{},h=model.horizon||{};
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  var totalCapex=0,totalGrowth=0,totalMaint=0,totalRev=0;
  var byYear=allY.map(function(y){
    /* CAPEX в этой модели лежит в out.bs.capex (накопительный годовой капекс) */
    var capex=Math.abs((o.bs&&o.bs.capex&&o.bs.capex[y])||0);
    /* Fallback: cf.cfi (отрицательный) или cf.capex */
    if(!capex){
      capex=Math.abs((o.cf&&o.cf.capex&&o.cf.capex[y])||(o.cf&&o.cf.cfi&&o.cf.cfi[y])||0);
    }
    var da=Math.abs((o.pnl&&o.pnl.depreciation&&o.pnl.depreciation[y])||0);
    var maint=Math.min(capex,da);
    var growth=Math.max(0,capex-da);
    totalCapex+=capex;
    totalGrowth+=growth;
    totalMaint+=maint;
    var rev=(o.pnl&&o.pnl.revenue&&o.pnl.revenue[y])||0;
    totalRev+=rev;
    return{y:y,capex:capex,maint:maint,growth:growth,isFc:!factSet[y]};
  });
  var capexIntensity=totalRev>0?totalCapex/totalRev:null;
  /* Payback по EBITDA-инкременту */
  var firstFc=(h.forecastYears||[])[0];
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var firstEb=firstFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[firstFc]):null;
  var lastEb=lastFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc]):null;
  var ebInc=firstEb!=null&&lastEb!=null?lastEb-firstEb:null;
  var payback=ebInc&&ebInc>0&&totalGrowth>0?totalGrowth/ebInc:null;
  return{totalCapex:totalCapex,capexIntensity:capexIntensity,payback:payback,byYear:byYear,totalGrowth:totalGrowth,totalMaint:totalMaint};
}
window._fmComputeCapex=_fmComputeCapex;

/* ───────────────── WACC ───────────────── */
function _fmComputeWACC(model){
  _fmEnsureAssumptions(model);
  var a=model.assumptions;
  var o=model.outputs||{},h=model.horizon||{};
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var debt=lastFc?(o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]):0;
  var eq=lastFc?(o.bs&&o.bs.equity&&o.bs.equity[lastFc]):0;
  var totCap=(debt||0)+(eq||0);
  var wD=totCap>0?debt/totCap:0;
  var wE=totCap>0?eq/totCap:1;
  var costEq=a.riskFreeRate+a.beta*a.marketRiskPremium+a.countryAdjustment;
  var costDebtAfter=a.effectiveCostOfDebt*(1-a.taxRate);
  var wacc=wE*costEq+wD*costDebtAfter;
  /* Sensitivity ±2пп к WACC: пересчитываем EV (NPV(FCFF) + TV) */
  var fcY=h.forecastYears||[];
  var sens=[];
  var deltas=[-0.02,-0.01,0,0.01,0.02];
  var oldEv=o.ratios&&o.ratios.enterpriseValue;
  deltas.forEach(function(dw){
    var w=wacc+dw;
    var pv=0;
    fcY.forEach(function(y,i){var f=o.cf&&o.cf.fcff&&o.cf.fcff[y];if(f!=null)pv+=f/Math.pow(1+w,i+1);});
    var fcffLast=fcY.length?(o.cf&&o.cf.fcff&&o.cf.fcff[fcY[fcY.length-1]]):null;
    var ev=null;
    if(fcffLast!=null&&w>(a.terminalGrowth||0.03)){
      var tv=fcffLast*(1+(a.terminalGrowth||0.03))/(w-(a.terminalGrowth||0.03));
      var pvTV=tv/Math.pow(1+w,fcY.length);
      ev=pv+pvTV;
    }
    var delta=ev!=null&&oldEv?(ev-oldEv)/oldEv:null;
    sens.push({wacc:w,ev:ev,delta:delta});
  });
  return{wacc:wacc,costEq:costEq,costDebtAfter:costDebtAfter,costDebtPre:a.effectiveCostOfDebt,wE:wE,wD:wD,sens:sens,rf:a.riskFreeRate,beta:a.beta,mrp:a.marketRiskPremium,ca:a.countryAdjustment,taxRate:a.taxRate};
}
window._fmComputeWACC=_fmComputeWACC;

/* ═══════════════════════════════════════════════════════════════════════════
   FIN-MODEL: ROIC / Debt / CAPEX / WACC — RESTYLED to UZA design system
   ═══════════════════════════════════════════════════════════════════════════ */

function _fmRenderROIC(model){
  var box=document.getElementById('fm-roic-body');if(!box)return;
  var d=_fmComputeROIC(model);
  var h=model.horizon||{};
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  /* Палитра — единая (ROIC всегда фиолетовый, WACC всегда серый), цвет даётся через бейдж/spread */
  var roicCol='#7F77DD';
  var roicColLight='rgba(127,119,221,.10)';
  var spreadPos=d.spread!=null&&d.spread>=0;
  var spreadCol=spreadPos?'#0F6E56':d.spread!=null?'#A32D2D':'var(--t3)';
  /* Канва уникальный id, на случай если повторно перерисовываем */
  var cid='fm-roic-canvas-'+Date.now();
  var html='<div style="display:grid;grid-template-columns:240px 1fr;gap:24px;align-items:center;margin-bottom:14px">';
  /* Left summary */
  html+='<div>';
  html+='<div style="font-size:11px;color:var(--t3);letter-spacing:.06em;text-transform:uppercase;font-weight:500;margin-bottom:6px">ROIC '+(d.lastFc||'—')+'П</div>';
  html+='<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:14px">';
  html+='<span style="font-size:36px;font-weight:400;color:var(--t1);letter-spacing:-.04em;line-height:1" data-countup="'+(d.roicLast!=null?(d.roicLast*100):0)+'" data-cu-d="1"></span>';
  html+='<span style="font-size:14px;font-weight:500;color:var(--t3)">%</span>';
  html+='</div>';
  if(d.spread!=null){
    var sign=spreadPos?'+':'';
    var msg=spreadPos?'Компания создаёт стоимость':'Компания разрушает стоимость';
    var alertCls=spreadPos?'uza-alert-teal':'uza-alert-red';
    html+='<div class="uza-alert '+alertCls+'" style="font-size:11px;line-height:1.5;padding:10px 12px">';
    html+='<div style="font-size:13px;font-weight:500;color:'+spreadCol+';margin-bottom:2px">'+sign+(d.spread*100).toFixed(1)+' п.п.</div>';
    html+='<div style="color:var(--t2)">'+msg+' выше стоимости капитала · WACC '+_fmFmtPct(d.wacc,1)+'</div>';
    html+='</div>';
  }
  html+='</div>';
  /* Right: Chart.js canvas — стиль showCompanyFinCard line chart */
  html+='<div style="position:relative;height:160px"><canvas id="'+cid+'"></canvas></div>';
  html+='</div>';
  /* mini KPIs */
  html+='<div class="uza-divider-dashed"></div>';
  html+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
  html+=_uzaMiniKpi({label:'NOPAT '+(d.lastFc||'—')+'П',value:'<span data-countup="'+(d.nopatLast||0)+'" data-cu-d="0" data-cu-sep></span>',sub:'млрд сум',delay:0});
  html+=_uzaMiniKpi({label:'Invested capital',value:'<span data-countup="'+(d.icLast||0)+'" data-cu-d="0" data-cu-sep></span>',sub:'млрд сум',delay:60});
  html+=_uzaMiniKpi({label:'Спред ROIC−WACC',value:'<span style="color:'+spreadCol+'">'+(d.spread!=null?(spreadPos?'+':'')+(d.spread*100).toFixed(1)+' п.п.':'—')+'</span>',sub:spreadPos?'value creation':d.spread!=null?'value destruction':'—',delay:120});
  html+=_uzaMiniKpi({label:'EVA '+(d.lastFc||'—')+'П',value:'<span style="color:'+spreadCol+'" data-countup="'+(d.eva||0)+'" data-cu-d="0" data-cu-sep></span>',sub:'economic value added',delay:180});
  html+='</div>';
  box.innerHTML=html;
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(box,80);},50);
  /* Render Chart.js — единый стиль с показCompanyFinCard */
  setTimeout(function(){
    if(typeof Chart==='undefined') return;
    var canvas=document.getElementById(cid); if(!canvas) return;
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var roicData=allY.map(function(y){var v=d.byYear[y];return v!=null?+(v*100).toFixed(2):null;});
    var waccData=allY.map(function(){return +(d.wacc*100).toFixed(2);});
    /* Per-point styling: fact = filled, forecast = hollow ring */
    var pointBg=allY.map(function(y){return factSet[y]?roicCol:'#FFFFFF';});
    var pointBorder=allY.map(function(){return roicCol;});
    /* Find idx где факт переходит в прогноз — для разделительной dashed зоны (опционально, легко) */
    new Chart(canvas,{
      type:'line',
      data:{
        labels:labels,
        datasets:[
          {
            label:'ROIC',
            data:roicData,
            borderColor:roicCol,
            backgroundColor:roicColLight,
            borderWidth:2,
            tension:.3,
            pointRadius:3.5,
            pointHoverRadius:5,
            pointBackgroundColor:pointBg,
            pointBorderColor:pointBorder,
            pointBorderWidth:2,
            fill:true,
            spanGaps:true
          },
          {
            label:'WACC',
            data:waccData,
            borderColor:'#94A3B8',
            backgroundColor:'transparent',
            borderWidth:1.5,
            borderDash:[5,4],
            tension:0,
            pointRadius:0,
            pointHoverRadius:0,
            fill:false
          }
        ]
      },
      options:{
        responsive:true,
        maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{
            position:'bottom',
            align:'start',
            labels:{
              boxWidth:8,
              boxHeight:8,
              font:{size:10,family:'inherit'},
              padding:8,
              usePointStyle:true,
              color:'#5F5E5A'
            }
          },
          tooltip:{
            backgroundColor:'rgba(15,23,60,.92)',
            titleFont:{size:11,family:'inherit',weight:'500'},
            bodyFont:{size:11,family:'inherit'},
            padding:10,
            cornerRadius:8,
            displayColors:true,
            boxPadding:4,
            callbacks:{
              label:function(ctx){return ctx.dataset.label+': '+ctx.parsed.y.toFixed(1)+'%';}
            }
          }
        },
        scales:{
          x:{
            grid:{display:false},
            ticks:{font:{size:10,family:'inherit'},color:'#94A3B8'},
            border:{color:'rgba(15,23,60,.08)'}
          },
          y:{
            grid:{color:'rgba(15,23,60,.04)',drawTicks:false},
            ticks:{
              font:{size:10,family:'inherit'},
              color:'#94A3B8',
              padding:6,
              callback:function(v){return v.toFixed(0)+'%';}
            },
            border:{display:false}
          }
        },
        animation:{duration:700,easing:'easeOutCubic'}
      }
    });
  },80);
}
window._fmRenderROIC=_fmRenderROIC;

function _fmRenderDebt(model){
  var box=document.getElementById('fm-debt-body');if(!box)return;
  var d=_fmComputeDebt(model);
  var tag=document.getElementById('fm-debt-cov-tag');
  if(tag){
    if(d.ndE!=null){
      tag.textContent=d.ndE.toFixed(1)+'×';
      tag.className='uza-pill '+(d.ndE<=d.covNdE*0.7?'uza-pill-teal':d.ndE<=d.covNdE?'uza-pill-amber':'uza-pill-red');
    } else { tag.textContent='—'; tag.className='uza-pill uza-pill-gray'; }
  }
  function arr(delta,inverse){
    if(delta==null||Math.abs(delta)<0.05) return '<span style="font-size:10px;color:#94A3B8;margin-left:4px">→</span>';
    var good=inverse?delta<0:delta>0;
    var col=good?'#1D9E75':'#A32D2D';
    var sym=delta>=0?'↑':'↓';
    return '<span style="font-size:10.5px;color:'+col+';margin-left:6px;font-weight:500">'+sym+(delta>=0?'+':'')+delta.toFixed(1)+'</span>';
  }
  var ndCol=d.ndE!=null?(d.ndE<=d.covNdE*0.7?'#1D9E75':d.ndE<=d.covNdE?'#EF9F27':'#E24B4A'):'#94A3B8';
  var icCol=d.intCov!=null?(d.intCov>=d.covIntCov*1.5?'#1D9E75':d.intCov>=d.covIntCov?'#EF9F27':'#E24B4A'):'#94A3B8';
  var html='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:18px">';
  html+=_uzaMiniKpi({label:'Net Debt / EBITDA',value:'<span style="color:'+ndCol+'" data-countup="'+(d.ndE||0)+'" data-cu-d="1"></span><span style="color:'+ndCol+';font-size:14px">×</span>'+arr(d.deltaNdE,true),sub:'covenant ≤ '+d.covNdE.toFixed(1)+'×',dotColor:ndCol,delay:0});
  html+=_uzaMiniKpi({label:'Interest coverage',value:'<span style="color:'+icCol+'" data-countup="'+(d.intCov||0)+'" data-cu-d="1"></span><span style="color:'+icCol+';font-size:14px">×</span>'+arr(d.deltaIntCov,false),sub:'covenant ≥ '+d.covIntCov.toFixed(1)+'×',dotColor:icCol,delay:60});
  html+=_uzaMiniKpi({label:'Debt / (D+E)',value:'<span data-countup="'+((d.debtEq||0)*100)+'" data-cu-d="0"></span><span style="font-size:14px;color:var(--t3)">%</span>',sub:'структура капитала',dotColor:'#7F77DD',delay:120});
  html+='</div>';
  /* Schedule chart — Chart.js stacked bar (стиль Финансов) */
  var cid='fm-debt-chart-'+Date.now();
  html+='<div style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500;margin-bottom:8px">График погашения · '+(typeof finUL==='function'?finUL():'млрд сум')+'</div>';
  html+='<div style="position:relative;height:180px"><canvas id="'+cid+'"></canvas></div>';
  box.innerHTML=html;
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(box,80);},50);
  /* Render Chart.js — единый стиль с showCompanyFinCard */
  setTimeout(function(){
    if(typeof Chart==='undefined') return;
    var canvas=document.getElementById(cid); if(!canvas) return;
    var labels=d.schedule.map(function(s){return s.y+(s.isFc?'П':'');});
    var ltData=d.schedule.map(function(s){return s.lt||null;});
    var stData=d.schedule.map(function(s){return s.st||null;});
    /* Финансы format: convert to млрд если >1000 */
    function fmt(v){
      if(v==null) return '—';
      if(typeof finFmt==='function'){
        try{ return finFmt(v, d.schedule[0]&&d.schedule[0].y); }catch(e){}
      }
      var a=Math.abs(v);
      if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
      return v.toLocaleString('ru-RU',{maximumFractionDigits:1});
    }
    new Chart(canvas,{
      type:'bar',
      data:{
        labels:labels,
        datasets:[
          {
            label:'Долгосрочный',
            data:ltData,
            backgroundColor:'#7F77DD',
            borderColor:'#7F77DD',
            borderWidth:0,
            borderRadius:3,
            stack:'debt'
          },
          {
            label:'Краткосрочный',
            data:stData,
            backgroundColor:'rgba(127,119,221,.45)',
            borderColor:'rgba(127,119,221,.45)',
            borderWidth:0,
            borderRadius:3,
            stack:'debt'
          }
        ]
      },
      options:{
        responsive:true,
        maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{
            position:'bottom',
            align:'start',
            labels:{
              boxWidth:8,
              boxHeight:8,
              font:{size:10,family:'inherit'},
              padding:8,
              usePointStyle:true,
              color:'#5F5E5A'
            }
          },
          tooltip:{
            backgroundColor:'rgba(15,23,60,.92)',
            titleFont:{size:11,family:'inherit',weight:'500'},
            bodyFont:{size:11,family:'inherit'},
            padding:10,
            cornerRadius:8,
            displayColors:true,
            boxPadding:4,
            callbacks:{
              label:function(ctx){return ctx.dataset.label+': '+fmt(ctx.parsed.y);},
              footer:function(items){
                var sum=items.reduce(function(s,i){return s+(i.parsed.y||0);},0);
                return 'Всего: '+fmt(sum);
              }
            }
          }
        },
        scales:{
          x:{
            stacked:true,
            grid:{display:false},
            ticks:{font:{size:10,family:'inherit'},color:'#94A3B8'},
            border:{color:'rgba(15,23,60,.08)'}
          },
          y:{
            stacked:true,
            grid:{color:'rgba(15,23,60,.04)',drawTicks:false},
            ticks:{
              font:{size:10,family:'inherit'},
              color:'#94A3B8',
              padding:6,
              callback:function(v){return fmt(v);}
            },
            border:{display:false}
          }
        },
        animation:{duration:700,easing:'easeOutCubic'}
      }
    });
  },80);
}
window._fmRenderDebt=_fmRenderDebt;

/* ── DSCR / LLCR / PLCR — IFI debt coverage analysis ─────────────────────── */
function _fmRenderDSCR(model){
  var box=document.getElementById('fm-dscr-body');if(!box)return;
  var tag=document.getElementById('fm-dscr-tag');
  if(!model||!model.outputs){box.innerHTML='';return;}
  var out=model.outputs;
  var ratios=out.ratios||{};
  var fcYears=(model.horizon&&model.horizon.forecastYears)||[];

  /* Empty state — нет долга или нет CFADS */
  var anyDscr=false;
  fcYears.forEach(function(y){if(ratios.dscrByYear&&ratios.dscrByYear[y]!=null) anyDscr=true;});
  if(!anyDscr){
    if(tag){tag.textContent='нет данных';tag.className='uza-pill uza-pill-gray';}
    box.innerHTML='<div style="padding:24px 12px;text-align:center;color:var(--t3);font-size:11.5px;line-height:1.6">'+
      '<div style="margin-bottom:6px;font-weight:600;color:var(--t2)">Нет данных для расчёта DSCR</div>'+
      '<div style="font-size:10.5px">Заполните график долга (LT/ST по годам) и операционные драйверы<br>(EBITDA, CAPEX, оборотный капитал) — расчёт произойдёт автоматически.</div>'+
    '</div>';
    return;
  }

  /* Цветовая шкала DSCR (стандартные IFI пороги) */
  function dscrColor(v){
    if(v==null) return '#94A3B8';
    if(v>=1.30) return '#1D9E75';
    if(v>=1.10) return '#EF9F27';
    if(v>=1.00) return '#E24B4A';
    return '#933632';
  }
  function dscrLabel(v){
    if(v==null) return '—';
    if(v>=1.30) return 'комфорт';
    if(v>=1.10) return 'covenant';
    if(v>=1.00) return 'тонко';
    return 'breach';
  }

  /* Tag в заголовке карточки — по DSCR Min · clickable */
  var dMin=ratios.dscrMin, dAvg=ratios.dscrAvg;
  if(tag){
    if(dMin!=null){
      tag.textContent='min '+dMin.toFixed(2)+'×';
      var pillCol=dMin>=1.30?'teal':dMin>=1.10?'amber':'red';
      tag.className='uza-pill uza-pill-'+pillCol+' fm-dscr-pill-clickable';
      tag.style.cursor='pointer';
      tag.onclick=function(){_fmDscrClick('min');};
      tag.title='Декомпозиция DSCR минимум';
    } else { tag.textContent='—'; tag.className='uza-pill uza-pill-gray'; tag.onclick=null; tag.style.cursor=''; }
  }

  /* 4 mini-KPI: DSCR Min, DSCR Avg, LLCR, PLCR — все clickable */
  var minCol=dscrColor(dMin), avgCol=dscrColor(dAvg);
  var llcrCol=ratios.llcr!=null?(ratios.llcr>=1.30?'#1D9E75':ratios.llcr>=1.10?'#EF9F27':'#E24B4A'):'#94A3B8';
  var html='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:18px">';
  html+='<div class="fm-dscr-kpi-wrap" data-fm-act="min" onclick="_fmDscrClick(\'min\')" style="cursor:pointer">'+_uzaMiniKpi({
    label:'DSCR минимум',
    value:'<span style="color:'+minCol+'" data-countup="'+(dMin!=null?dMin:0)+'" data-cu-d="2"></span><span style="color:'+minCol+';font-size:14px">×</span>',
    sub:'covenant ≥ 1.20× · '+dscrLabel(dMin),
    dotColor:minCol,delay:0
  })+'</div>';
  html+='<div class="fm-dscr-kpi-wrap" data-fm-act="avg" onclick="_fmDscrClick(\'avg\')" style="cursor:pointer">'+_uzaMiniKpi({
    label:'DSCR среднее',
    value:'<span style="color:'+avgCol+'" data-countup="'+(dAvg!=null?dAvg:0)+'" data-cu-d="2"></span><span style="color:'+avgCol+';font-size:14px">×</span>',
    sub:'по прогнозным годам',
    dotColor:avgCol,delay:60
  })+'</div>';
  html+='<div class="fm-dscr-kpi-wrap" data-fm-act="llcr" onclick="_fmDscrClick(\'llcr\')" style="cursor:pointer">'+_uzaMiniKpi({
    label:'LLCR',
    value:ratios.llcr!=null?'<span style="color:'+llcrCol+'" data-countup="'+ratios.llcr+'" data-cu-d="2"></span><span style="color:'+llcrCol+';font-size:14px">×</span>':'<span style="color:#94A3B8">—</span>',
    sub:'NPV(CFADS) / Debt · loan life',
    dotColor:llcrCol,delay:120
  })+'</div>';
  html+='<div class="fm-dscr-kpi-wrap" data-fm-act="plcr" onclick="_fmDscrClick(\'plcr\')" style="cursor:pointer">'+_uzaMiniKpi({
    label:'PLCR',
    value:ratios.plcr!=null?'<span data-countup="'+ratios.plcr+'" data-cu-d="2"></span><span style="font-size:14px;color:var(--t3)">×</span>':'<span style="color:#94A3B8">—</span>',
    sub:'NPV(CFADS) / Debt · project life',
    dotColor:'#7F77DD',delay:180
  })+'</div>';
  html+='</div>';

  /* Year-by-year таблица: CFADS / Debt Service / DSCR с цветным индикатором */
  function fmtBn(v){
    if(v==null||!isFinite(v)) return '—';
    var bn=v/1000; /* UZSm → млрд UZS */
    if(Math.abs(bn)>=1000) return (bn/1000).toFixed(1)+' трлн';
    if(Math.abs(bn)>=10) return Math.round(bn).toLocaleString('ru-RU');
    return bn.toLocaleString('ru-RU',{maximumFractionDigits:1});
  }
  html+='<div style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500;margin-bottom:8px">График покрытия по годам · млрд сум · DSCR в кратности · клик — детализация</div>';
  html+='<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.05);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px" class="fm-dscr-table">';
  html+='<thead><tr style="background:rgba(0,0,0,.02)">';
  html+='<th style="padding:8px 12px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600;width:160px">Метрика</th>';
  fcYears.forEach(function(y){
    html+='<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:#A36500;font-weight:600">'+y+' П</th>';
  });
  html+='</tr></thead><tbody>';
  /* Строка CFADS — clickable cells */
  html+='<tr style="border-top:0.5px solid rgba(0,0,0,.04)"><td style="padding:7px 12px;color:var(--t1);font-weight:500"><div style="font-size:11.5px">CFADS</div><div style="font-size:10px;color:var(--t3);margin-top:1px">EBITDA − Tax − ΔWC − CAPEX</div></td>';
  fcYears.forEach(function(y){
    var v=out.cf&&out.cf.cfads&&out.cf.cfads[y];
    html+='<td class="fm-dscr-cell" onclick="_fmDscrClick(\'cell-cfads\','+y+')" title="Декомпозиция CFADS '+y+'" style="padding:7px 6px;text-align:right;font-feature-settings:\x27tnum\x27;color:'+(v!=null&&v<0?'#E24B4A':'var(--t1)')+';cursor:pointer">'+fmtBn(v)+'</td>';
  });
  html+='</tr>';
  /* Строка Debt Service — clickable cells */
  html+='<tr style="border-top:0.5px solid rgba(0,0,0,.04)"><td style="padding:7px 12px;color:var(--t1);font-weight:500"><div style="font-size:11.5px">Обслуживание долга</div><div style="font-size:10px;color:var(--t3);margin-top:1px">Interest + Principal</div></td>';
  fcYears.forEach(function(y){
    var v=out.cf&&out.cf.debtService&&out.cf.debtService[y];
    html+='<td class="fm-dscr-cell" onclick="_fmDscrClick(\'cell-dsvc\','+y+')" title="Состав Debt Service '+y+'" style="padding:7px 6px;text-align:right;font-feature-settings:\x27tnum\x27;color:var(--t2);cursor:pointer">'+fmtBn(v)+'</td>';
  });
  html+='</tr>';
  /* Строка DSCR — clickable cells */
  html+='<tr style="border-top:0.5px solid rgba(0,0,0,.04);background:rgba(55,138,221,.025)"><td style="padding:7px 12px;color:var(--t1);font-weight:600"><div style="font-size:11.5px">DSCR</div><div style="font-size:10px;color:var(--t3);margin-top:1px">CFADS / debt service</div></td>';
  fcYears.forEach(function(y){
    var v=ratios.dscrByYear&&ratios.dscrByYear[y];
    var c=dscrColor(v);
    var disp=(v!=null&&isFinite(v))?(v.toFixed(2)+'×'):'—';
    html+='<td class="fm-dscr-cell" onclick="_fmDscrClick(\'cell-dscr\','+y+')" title="Декомпозиция DSCR '+y+'" style="padding:7px 6px;text-align:right;font-feature-settings:\x27tnum\x27;font-weight:700;color:'+c+';cursor:pointer"><span style="display:inline-flex;align-items:center;gap:4px;justify-content:flex-end"><span style="width:5px;height:5px;border-radius:50%;background:'+c+';display:inline-block"></span>'+disp+'</span></td>';
  });
  html+='</tr>';
  html+='</tbody></table></div>';

  /* Footnote с порогами */
  html+='<div style="margin-top:10px;display:flex;gap:14px;flex-wrap:wrap;font-size:10px;color:var(--t3);align-items:center">';
  html+='<div style="display:flex;align-items:center;gap:5px"><span style="width:7px;height:7px;border-radius:50%;background:#1D9E75"></span>≥ 1.30× — комфорт</div>';
  html+='<div style="display:flex;align-items:center;gap:5px"><span style="width:7px;height:7px;border-radius:50%;background:#EF9F27"></span>1.10–1.30× — зона covenant</div>';
  html+='<div style="display:flex;align-items:center;gap:5px"><span style="width:7px;height:7px;border-radius:50%;background:#E24B4A"></span>1.00–1.10× — тонко</div>';
  html+='<div style="display:flex;align-items:center;gap:5px"><span style="width:7px;height:7px;border-radius:50%;background:#933632"></span>&lt; 1.00× — covenant breach</div>';
  html+='</div>';

  box.innerHTML=html;
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(box,80);},50);
}
window._fmRenderDSCR=_fmRenderDSCR;

/* ══ DSCR / LLCR / PLCR drill-down modals (premium clickable) ══════════════ */
/* ════════════════════════════════════════════════════════════════════════════
   DSCR / LLCR / PLCR — DRILL-DOWN MODAL SYSTEM
   ────────────────────────────────────────────────────────────────────────────
   Архитектура:
   - _fmDscrComputeStats(model) — единый снапшот всех derived stats
   - _fmDscrFmtBn / _fmDscrFmtRatio / _fmDscrColorFor — форматтеры
   - _fmDscrWaterfallHtml(items,total) — waterfall-bars helper
   - 7 модалок: KPI tiles (4) + table cells (3)
   ──────────────────────────────────────────────────────────────────────────── */

/* Снапшот всех stats — один проход по модели */
function _fmDscrComputeStats(model){
  if(!model||!model.outputs)return null;
  var out=model.outputs;
  var ratios=out.ratios||{};
  var fcYears=(model.horizon&&model.horizon.forecastYears)||[];
  var minYear=null,minVal=Infinity,maxYear=null,maxVal=-Infinity;
  fcYears.forEach(function(y){
    var v=ratios.dscrByYear&&ratios.dscrByYear[y];
    if(v==null||!isFinite(v))return;
    if(v<minVal){minVal=v;minYear=y;}
    if(v>maxVal){maxVal=v;maxYear=y;}
  });
  if(minVal===Infinity)minVal=null;
  if(maxVal===-Infinity)maxVal=null;
  var zones={comfort:[],covenant:[],tight:[],breach:[]};
  fcYears.forEach(function(y){
    var v=ratios.dscrByYear&&ratios.dscrByYear[y];
    if(v==null||!isFinite(v))return;
    if(v>=1.30) zones.comfort.push(y);
    else if(v>=1.10) zones.covenant.push(y);
    else if(v>=1.00) zones.tight.push(y);
    else zones.breach.push(y);
  });
  /* Loan life — последний год с непогашенным долгом */
  var loanEndYr=null;
  for(var i=fcYears.length-1;i>=0;i--){
    if(((out.bs&&out.bs.totalDebt&&out.bs.totalDebt[fcYears[i]])||0)>0){loanEndYr=fcYears[i];break;}
  }
  /* PV per year for LLCR (cfads discounted) */
  var wacd=(model.drivers&&model.drivers.debt&&model.drivers.debt.interestRate)||0.09;
  var pvByYear={};
  fcYears.forEach(function(y,idx){
    var cf=(out.cf&&out.cf.cfads&&out.cf.cfads[y])||0;
    pvByYear[y]=cf/Math.pow(1+wacd,idx+1);
  });
  return {
    fcYears:fcYears, minYear:minYear, minVal:minVal, maxYear:maxYear, maxVal:maxVal,
    zones:zones, loanEndYr:loanEndYr, wacd:wacd, pvByYear:pvByYear,
    dscrByYear:ratios.dscrByYear||{},
    cfads:(out.cf&&out.cf.cfads)||{},
    debtService:(out.cf&&out.cf.debtService)||{},
    principal:(out.cf&&out.cf.principalRepayment)||{},
    interest:(out.pnl&&out.pnl.finCost)||{},
    ebitda:(out.pnl&&out.pnl.ebitda)||{},
    tax:(out.pnl&&out.pnl.tax)||{},
    capex:(out.bs&&out.bs.capex)||{},
    nwc:(out.bs&&out.bs.nwc)||{},
    totalDebt:(out.bs&&out.bs.totalDebt)||{},
    dscrMin:ratios.dscrMin,
    dscrAvg:ratios.dscrAvg,
    llcr:ratios.llcr,
    plcr:ratios.plcr
  };
}
window._fmDscrComputeStats=_fmDscrComputeStats;

/* Format helpers */
function _fmDscrFmtBn(v){
  if(v==null||!isFinite(v))return '—';
  var bn=v/1000;
  if(Math.abs(bn)>=1000)return (bn/1000).toFixed(2)+' трлн';
  if(Math.abs(bn)>=10)return Math.round(bn).toLocaleString('ru-RU')+' млрд';
  return bn.toLocaleString('ru-RU',{maximumFractionDigits:1})+' млрд';
}
function _fmDscrFmtSigned(v){
  if(v==null||!isFinite(v))return '—';
  return (v>=0?'+':'−')+_fmDscrFmtBn(Math.abs(v));
}
function _fmDscrColorFor(v){
  if(v==null||!isFinite(v))return '#94A3B8';
  if(v>=1.30)return '#1D9E75';
  if(v>=1.10)return '#EF9F27';
  if(v>=1.00)return '#E24B4A';
  return '#933632';
}
function _fmDscrZoneLabel(v){
  if(v==null||!isFinite(v))return '—';
  if(v>=1.30)return 'комфорт';
  if(v>=1.10)return 'зона covenant';
  if(v>=1.00)return 'тонко';
  return 'covenant breach';
}

/* Waterfall HTML — для CFADS декомпозиции */
function _fmDscrWaterfallHtml(items, totalLabel, totalValue){
  var maxAbs=Math.max.apply(null, items.map(function(i){return Math.abs(i.value||0);}).concat([Math.abs(totalValue||0)||1]));
  if(maxAbs<=0)maxAbs=1;
  var html='<div class="cp-drill-bars" style="padding:14px 16px">';
  items.forEach(function(it,i){
    var pct=(Math.abs(it.value)/maxAbs)*100;
    var sign=it.value>=0?'+':'−';
    var color=it.color||(it.value>=0?'#1D9E75':'#E24B4A');
    html+='<div class="cp-drill-bar-row">'+
      '<div class="cp-drill-bar-l" style="color:var(--t2)">'+it.label+'</div>'+
      '<div class="cp-drill-bar-track"><div class="cp-drill-bar-fill" style="--w:'+pct.toFixed(2)+'%;--c:'+color+';--bd:'+(i*60)+'ms"></div></div>'+
      '<div class="cp-drill-bar-v" style="color:'+color+';font-weight:600">'+sign+_fmDscrFmtBn(Math.abs(it.value))+'</div>'+
    '</div>';
  });
  /* Total row — выделенная */
  var totPct=(Math.abs(totalValue)/maxAbs)*100;
  html+='<div class="cp-drill-bar-row" style="border-top:1px solid rgba(0,0,0,.08);margin-top:8px;padding-top:10px">'+
    '<div class="cp-drill-bar-l" style="font-weight:700;color:#1E2A4A;text-transform:uppercase;letter-spacing:.04em;font-size:11px">= '+totalLabel+'</div>'+
    '<div class="cp-drill-bar-track"><div class="cp-drill-bar-fill" style="--w:'+totPct.toFixed(2)+'%;--c:#1E2A4A;--bd:'+(items.length*60+80)+'ms"></div></div>'+
    '<div class="cp-drill-bar-v" style="font-weight:700;color:#1E2A4A;font-size:13px">'+_fmDscrFmtBn(totalValue)+'</div>'+
  '</div>';
  html+='</div>';
  return html;
}

/* Year-bars block для DSCR / CFADS / Debt Service по всем прогнозным годам */
function _fmDscrYearBarsHtml(s, valuesMap, formatter, colorFn, clickFn){
  var items=s.fcYears.map(function(y){
    var v=valuesMap[y];
    var col=colorFn?colorFn(v,y):'#7F77DD';
    return {
      label:String(y)+' П',
      value:Math.abs(v||0),
      valueText:formatter?formatter(v):String(v),
      color:col,
      onClick:clickFn?clickFn(y):null
    };
  });
  return cpDrillBarsHtml(items);
}

/* ──────────────────────────────────────────────────────────────────────────
   ROUTER — точка входа клика
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrClick(action, year){
  var co=window._fmSelCo;
  if(!co)return;
  var scn=window._fmScenario||'base';
  var model=_db&&_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model||!model.outputs){
    if(typeof toast==='function')toast('Модель не рассчитана');
    return;
  }
  switch(action){
    case 'min':     return _fmDscrModalMin(model);
    case 'avg':     return _fmDscrModalAvg(model);
    case 'llcr':    return _fmDscrModalLLCR(model);
    case 'plcr':    return _fmDscrModalPLCR(model);
    case 'cell-dscr':   return _fmDscrModalCellDSCR(model, year);
    case 'cell-cfads':  return _fmDscrModalCellCFADS(model, year);
    case 'cell-dsvc':   return _fmDscrModalCellDebtSvc(model, year);
  }
}
window._fmDscrClick=_fmDscrClick;

/* ──────────────────────────────────────────────────────────────────────────
   MODAL A — DSCR минимум
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalMin(model){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var dMin=s.dscrMin, yr=s.minYear;
  var color=_fmDscrColorFor(dMin);
  var sub='covenant ≥ 1.20× · '+_fmDscrZoneLabel(dMin)+(yr?(' · худший год: '+yr):'');

  /* Worst year decomposition */
  var sections=[];
  if(yr){
    var ebY=s.ebitda[yr]||0, txY=s.tax[yr]||0, cxY=s.capex[yr]||0, nwcY=s.nwc[yr]||0;
    /* Compute prev NWC for ΔWC */
    var fcIdx=s.fcYears.indexOf(yr);
    var prevNwc=fcIdx>0?(s.nwc[s.fcYears[fcIdx-1]]||0):0;
    var dNwc=nwcY-prevNwc;
    var cfadsY=s.cfads[yr]||0;
    var dsvcY=s.debtService[yr]||0;
    var intY=s.interest[yr]||0, prnY=s.principal[yr]||0;

    sections.push({
      title:'Год '+yr+' · Snapshot',
      body:cpDrillStatGridHtml([
        {label:'CFADS',        value:_fmDscrFmtBn(cfadsY).replace(/ млрд| трлн/,''), unit:cfadsY!=null&&Math.abs(cfadsY)>=1000000?'трлн':'млрд', sub:'операционный денежный поток', color:'#378ADD', cuDecimals:cfadsY!=null&&Math.abs(cfadsY)>=10000?0:1},
        {label:'Debt service', value:_fmDscrFmtBn(dsvcY).replace(/ млрд| трлн/,''),  unit:dsvcY!=null&&Math.abs(dsvcY)>=1000000?'трлн':'млрд', sub:'Interest + Principal', color:'#EF9F27', cuDecimals:dsvcY!=null&&Math.abs(dsvcY)>=10000?0:1},
        {label:'DSCR',         value:dMin!=null?dMin.toFixed(2):'—', unit:'×', cuDecimals:2, color:color, sub:_fmDscrZoneLabel(dMin)},
        {label:'Дефицит/запас',value:_fmDscrFmtSigned(cfadsY-dsvcY).replace(/[+−]/g,'').replace(/ млрд| трлн/,''), unit:Math.abs(cfadsY-dsvcY)>=1000000?'трлн':'млрд', color:cfadsY>=dsvcY?'#1D9E75':'#E24B4A', sub:cfadsY>=dsvcY?'CFADS покрывает':'недостаточно', cuDecimals:Math.abs(cfadsY-dsvcY)>=10000?0:1}
      ])
    });

    sections.push({
      title:'CFADS '+yr+' · декомпозиция',
      body:_fmDscrWaterfallHtml([
        {label:'EBITDA',       value:ebY,    color:'#1D9E75'},
        {label:'− Tax',        value:-txY,   color:'#E24B4A'},
        {label:'− ΔNWC',       value:-dNwc,  color:'#EF9F27'},
        {label:'− CAPEX',      value:-cxY,   color:'#378ADD'}
      ],'CFADS '+yr,cfadsY)
    });

    sections.push({
      title:'Debt service '+yr+' · состав',
      body:_fmDscrWaterfallHtml([
        {label:'Interest',     value:intY,   color:'#7F77DD'},
        {label:'Principal',    value:prnY,   color:'#A36500'}
      ],'Debt service '+yr,dsvcY)
    });
  }

  /* Все годы DSCR — clickable */
  sections.push({
    title:'DSCR по всем прогнозным годам · клик — детализация',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(y){
      var v=s.dscrByYear[y];
      return {
        label:String(y)+(y===s.minYear?' П · MIN':' П'),
        value:Math.max(0.001,v||0),
        valueText:(v!=null&&isFinite(v))?(v.toFixed(2)+'×'):'—',
        color:_fmDscrColorFor(v),
        onClick:'_fmDscrClick(\'cell-dscr\','+y+')'
      };
    }))
  });

  cpDrillOpen({
    title:'DSCR минимум',
    subtitle:yr?('Худший год · '+yr+' · '+_fmDscrZoneLabel(dMin)):_fmDscrZoneLabel(dMin),
    accent:color,
    accentBg:color==='#1D9E75'?'rgba(29,158,117,.12)':color==='#EF9F27'?'rgba(239,159,39,.12)':color==='#E24B4A'?'rgba(226,75,74,.12)':'rgba(147,54,50,.12)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><path d="M3 12a9 9 0 1018 0 9 9 0 00-18 0z"/></svg>',
    hero:cpDrillHeroHtml({value:dMin!=null?dMin.toFixed(2):'—',unit:'×',cuDecimals:2,label:'DSCR минимум по прогнозу',sub:'covenant ≥ 1.20× · IFI стандарт'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>Источник: <strong>Долг</strong> (LT/ST · WACD) + <strong>Драйверы EBITDA</strong> + <strong>CAPEX</strong> + <strong>WC</strong></span><a onclick="cpDrillClose();_fmShowEditor()" style="color:#7F77DD;cursor:pointer;font-weight:600">Открыть редактор →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL B — DSCR среднее
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalAvg(model){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var dAvg=s.dscrAvg;
  var color=_fmDscrColorFor(dAvg);
  var sections=[];

  /* Распределение по зонам covenant */
  var zoneRows=[
    {label:'Комфорт ≥ 1.30×',     value:s.zones.comfort.length,  color:'#1D9E75', valueText:s.zones.comfort.length+(s.zones.comfort.length?' · '+s.zones.comfort.join(', '):'')},
    {label:'Covenant 1.10–1.30×', value:s.zones.covenant.length, color:'#EF9F27', valueText:s.zones.covenant.length+(s.zones.covenant.length?' · '+s.zones.covenant.join(', '):'')},
    {label:'Тонко 1.00–1.10×',    value:s.zones.tight.length,    color:'#E24B4A', valueText:s.zones.tight.length+(s.zones.tight.length?' · '+s.zones.tight.join(', '):'')},
    {label:'Breach < 1.00×',       value:s.zones.breach.length,   color:'#933632', valueText:s.zones.breach.length+(s.zones.breach.length?' · '+s.zones.breach.join(', '):'')}
  ].filter(function(r){return r.value>0;});

  sections.push({
    title:'Сводка по covenant-зонам',
    count:s.fcYears.length+' лет',
    body:cpDrillStatGridHtml([
      {label:'Min DSCR', value:s.dscrMin!=null?s.dscrMin.toFixed(2):'—', unit:'×', cuDecimals:2, color:_fmDscrColorFor(s.dscrMin), sub:s.minYear?('в '+s.minYear+' г.'):''},
      {label:'Avg DSCR', value:dAvg!=null?dAvg.toFixed(2):'—', unit:'×', cuDecimals:2, color:color, sub:'по прогнозу'},
      {label:'Max DSCR', value:s.maxVal!=null?s.maxVal.toFixed(2):'—', unit:'×', cuDecimals:2, color:_fmDscrColorFor(s.maxVal), sub:s.maxYear?('в '+s.maxYear+' г.'):''},
      {label:'Forecast лет', value:s.fcYears.length, unit:'', color:'#7F77DD', sub:'в расчёте'}
    ])
  });

  sections.push({
    title:'DSCR по всем прогнозным годам · клик — детализация',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(y){
      var v=s.dscrByYear[y];
      return {
        label:String(y)+' П',
        value:Math.max(0.001,v||0),
        valueText:(v!=null&&isFinite(v))?(v.toFixed(2)+'×'):'—',
        color:_fmDscrColorFor(v),
        onClick:'_fmDscrClick(\'cell-dscr\','+y+')'
      };
    }))
  });

  if(zoneRows.length){
    sections.push({
      title:'Распределение лет по зонам covenant',
      body:cpDrillBarsHtml(zoneRows)
    });
  }

  sections.push({
    title:'Метод расчёта',
    body:'<div style="padding:14px 16px;color:var(--t2);font-size:11.5px;line-height:1.7">'+
      '<div style="font-family:monospace;background:rgba(0,0,0,.03);padding:8px 12px;border-radius:6px;margin-bottom:8px;font-size:11px">DSCR_avg = Σ DSCR[y] / N · по годам где Debt service > 0</div>'+
      'Среднее берётся <strong>только по прогнозным годам</strong> с непогашенным долгом — это IFI-стандарт. Years с DSCR=∞ (Debt service = 0) исключаются.'+
    '</div>'
  });

  cpDrillOpen({
    title:'DSCR среднее',
    subtitle:s.fcYears.length+' прогнозных лет · '+_fmDscrZoneLabel(dAvg),
    accent:color,
    accentBg:color==='#1D9E75'?'rgba(29,158,117,.12)':color==='#EF9F27'?'rgba(239,159,39,.12)':'rgba(226,75,74,.12)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-9 4 18 3-9h4"/></svg>',
    hero:cpDrillHeroHtml({value:dAvg!=null?dAvg.toFixed(2):'—',unit:'×',cuDecimals:2,label:'DSCR среднее по прогнозу',sub:'AVG(DSCR[y]) для всех y где Debt Service > 0'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>Среднее DSCR не заменяет Min — covenants проверяются по worst year</span><a onclick="cpDrillClose();_fmDscrClick(\'min\')" style="color:#7F77DD;cursor:pointer;font-weight:600">Перейти к DSCR Min →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL C — LLCR
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalLLCR(model){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var llcr=s.llcr;
  var color=llcr==null?'#94A3B8':(llcr>=1.30?'#1D9E75':llcr>=1.10?'#EF9F27':'#E24B4A');
  var sections=[];
  /* Loan life period */
  var loanYrs=s.fcYears.filter(function(y){return ((s.totalDebt[y]||0)>0);});
  var loanLifeStart=loanYrs.length?loanYrs[0]:null;
  var loanLifeEnd=loanYrs.length?loanYrs[loanYrs.length-1]:null;
  var debtStart=loanLifeStart?(s.totalDebt[loanLifeStart]||0):0;
  var npvSum=0;
  loanYrs.forEach(function(y){npvSum+=s.pvByYear[y]||0;});

  sections.push({
    title:'Параметры расчёта',
    body:cpDrillStatGridHtml([
      {label:'Discount rate (WACD)', value:(s.wacd*100).toFixed(2), unit:'%', cuDecimals:2, color:'#378ADD', sub:'эффективная ставка по портфелю'},
      {label:'Срок займа',           value:loanLifeStart&&loanLifeEnd?(loanLifeStart+'–'+loanLifeEnd):'—', unit:'', sub:loanYrs.length+' лет в LLCR'},
      {label:'Начальный долг',       value:_fmDscrFmtBn(debtStart).replace(/ млрд| трлн/,''), unit:Math.abs(debtStart)>=1000000?'трлн':'млрд', color:'#EF9F27', sub:'долг в '+(loanLifeStart||'—')+' г.', cuDecimals:debtStart>=10000?0:1},
      {label:'NPV(CFADS)',           value:_fmDscrFmtBn(npvSum).replace(/ млрд| трлн/,''), unit:Math.abs(npvSum)>=1000000?'трлн':'млрд', color:'#7F77DD', sub:'дисконтировано WACD', cuDecimals:Math.abs(npvSum)>=10000?0:1}
    ])
  });

  /* PV by year — bars */
  if(loanYrs.length){
    sections.push({
      title:'PV(CFADS) по годам жизни займа · вклад в NPV',
      count:loanYrs.length,
      body:cpDrillBarsHtml(loanYrs.map(function(y,idx){
        var pv=s.pvByYear[y]||0;
        return {
          label:String(y)+' · ('+(idx+1)+' г.)',
          value:Math.abs(pv),
          valueText:_fmDscrFmtSigned(pv),
          color:pv>=0?'#1D9E75':'#E24B4A',
          onClick:'_fmDscrClick(\'cell-cfads\','+y+')'
        };
      }))
    });
  }

  sections.push({
    title:'LLCR vs DSCR Avg · какая метрика что показывает',
    body:cpDrillStatGridHtml([
      {label:'LLCR',     value:llcr!=null?llcr.toFixed(2):'—', unit:'×', cuDecimals:2, color:color, sub:'NPV(CFADS) / Debt'},
      {label:'DSCR Avg', value:s.dscrAvg!=null?s.dscrAvg.toFixed(2):'—', unit:'×', cuDecimals:2, color:_fmDscrColorFor(s.dscrAvg), sub:'среднее за период'}
    ])+
    '<div style="padding:10px 16px;color:var(--t2);font-size:11px;line-height:1.7">'+
      '<strong style="color:#1E2A4A">LLCR</strong> — forward-looking агрегат: один показатель для всей жизни займа. <strong style="color:#1E2A4A">DSCR</strong> — period-by-period: показывает риск конкретного года.<br>'+
      'IFC/EBRD используют <strong>оба</strong>: LLCR ≥ 1.30× для loan-level одобрения, DSCR ≥ 1.20× как ежегодный covenant.'+
    '</div>'
  });

  sections.push({
    title:'Формула',
    body:'<div style="padding:14px 16px;color:var(--t2);font-size:11.5px;line-height:1.7">'+
      '<div style="font-family:monospace;background:rgba(0,0,0,.03);padding:10px 12px;border-radius:6px;margin-bottom:6px;font-size:11px">LLCR = Σ [CFADS<sub>y</sub> / (1+WACD)<sup>y</sup>] / Outstanding debt<sub>start</sub></div>'+
      'Числитель — приведённая стоимость всех CFADS за оставшийся срок займа. Знаменатель — непогашенный долг на начало периода.'+
    '</div>'
  });

  cpDrillOpen({
    title:'LLCR — Loan Life Coverage Ratio',
    subtitle:loanYrs.length?(loanYrs.length+' лет жизни займа · IFI ≥ 1.30×'):'IFI standard ≥ 1.30×',
    accent:color,
    accentBg:'rgba(29,158,117,.12)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/></svg>',
    hero:cpDrillHeroHtml({value:llcr!=null?llcr.toFixed(2):'—',unit:'×',cuDecimals:2,label:'LLCR · forward-looking aggregate',sub:'NPV(CFADS, WACD) / Outstanding debt'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>WACD меняется в редакторе → График долга → Эффективная ставка</span><a onclick="cpDrillClose();_fmShowEditor()" style="color:#7F77DD;cursor:pointer;font-weight:600">Открыть редактор →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL D — PLCR
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalPLCR(model){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var plcr=s.plcr;
  var color=plcr==null?'#94A3B8':(plcr>=1.30?'#1D9E75':plcr>=1.10?'#EF9F27':'#E24B4A');
  var sections=[];

  var npvSum=0;
  s.fcYears.forEach(function(y){npvSum+=s.pvByYear[y]||0;});
  var debtStart=s.fcYears.length?(s.totalDebt[s.fcYears[0]]||0):0;

  /* Tail PV (после loan life) — для понимания насколько project life добавляет */
  var loanYrs=s.fcYears.filter(function(y){return ((s.totalDebt[y]||0)>0);});
  var tailYrs=s.fcYears.filter(function(y){return ((s.totalDebt[y]||0)<=0);});
  var tailNpv=0;
  tailYrs.forEach(function(y){tailNpv+=s.pvByYear[y]||0;});

  sections.push({
    title:'Параметры расчёта',
    body:cpDrillStatGridHtml([
      {label:'Discount rate (WACD)', value:(s.wacd*100).toFixed(2), unit:'%', cuDecimals:2, color:'#378ADD'},
      {label:'Project life',         value:s.fcYears.length?(s.fcYears[0]+'–'+s.fcYears[s.fcYears.length-1]):'—', unit:'', sub:s.fcYears.length+' лет горизонт'},
      {label:'NPV(CFADS) total',     value:_fmDscrFmtBn(npvSum).replace(/ млрд| трлн/,''), unit:Math.abs(npvSum)>=1000000?'трлн':'млрд', color:'#7F77DD', cuDecimals:Math.abs(npvSum)>=10000?0:1},
      {label:'Начальный долг',       value:_fmDscrFmtBn(debtStart).replace(/ млрд| трлн/,''), unit:Math.abs(debtStart)>=1000000?'трлн':'млрд', color:'#EF9F27', cuDecimals:debtStart>=10000?0:1}
    ])
  });

  sections.push({
    title:'PV(CFADS) по всем прогнозным годам',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(y,idx){
      var pv=s.pvByYear[y]||0;
      var hasDebt=((s.totalDebt[y]||0)>0);
      return {
        label:String(y)+(hasDebt?' · в LLCR':' · только PLCR'),
        value:Math.abs(pv),
        valueText:_fmDscrFmtSigned(pv),
        color:pv>=0?(hasDebt?'#1D9E75':'#7F77DD'):'#E24B4A',
        onClick:'_fmDscrClick(\'cell-cfads\','+y+')'
      };
    }))
  });

  sections.push({
    title:'PLCR vs LLCR — отличие',
    body:cpDrillStatGridHtml([
      {label:'LLCR', value:s.llcr!=null?s.llcr.toFixed(2):'—', unit:'×', cuDecimals:2, color:_fmDscrColorFor(s.llcr), sub:loanYrs.length+' лет жизни займа'},
      {label:'PLCR', value:plcr!=null?plcr.toFixed(2):'—', unit:'×', cuDecimals:2, color:color, sub:s.fcYears.length+' лет project life'},
      {label:'PV tail (после займа)', value:_fmDscrFmtBn(tailNpv).replace(/ млрд| трлн/,''), unit:Math.abs(tailNpv)>=1000000?'трлн':'млрд', sub:tailYrs.length+' лет хвоста', color:tailNpv>=0?'#1D9E75':'#E24B4A', cuDecimals:Math.abs(tailNpv)>=10000?0:1},
      {label:'Δ PLCR − LLCR', value:(s.llcr!=null&&plcr!=null)?(plcr-s.llcr).toFixed(2):'—', unit:'×', cuDecimals:2, sub:'вклад post-loan лет', color:(s.llcr!=null&&plcr!=null&&plcr>=s.llcr)?'#1D9E75':'#E24B4A'}
    ])+
    '<div style="padding:10px 16px;color:var(--t2);font-size:11px;line-height:1.7">'+
      'PLCR ≥ LLCR обычно. Превышение показывает, что после погашения долга проект продолжает генерировать CFADS — это даёт дополнительный buffer для рефинансирования.'+
    '</div>'
  });

  cpDrillOpen({
    title:'PLCR — Project Life Coverage Ratio',
    subtitle:s.fcYears.length+' лет project life · WACD '+(s.wacd*100).toFixed(2)+'%',
    accent:color,
    accentBg:'rgba(127,119,221,.14)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-5"/></svg>',
    hero:cpDrillHeroHtml({value:plcr!=null?plcr.toFixed(2):'—',unit:'×',cuDecimals:2,label:'PLCR · вся жизнь проекта',sub:'NPV(CFADS) включая годы после погашения долга'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>PLCR строже LLCR — учитывает все будущие CF, не только до погашения</span><a onclick="cpDrillClose();_fmDscrClick(\'llcr\')" style="color:#7F77DD;cursor:pointer;font-weight:600">Перейти к LLCR →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL E — DSCR cell (year)
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalCellDSCR(model, year){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var v=s.dscrByYear[year];
  var color=_fmDscrColorFor(v);
  var ebY=s.ebitda[year]||0, txY=s.tax[year]||0, cxY=s.capex[year]||0, nwcY=s.nwc[year]||0;
  var fcIdx=s.fcYears.indexOf(year);
  var prevNwc=fcIdx>0?(s.nwc[s.fcYears[fcIdx-1]]||0):0;
  var dNwc=nwcY-prevNwc;
  var cfadsY=s.cfads[year]||0;
  var dsvcY=s.debtService[year]||0;
  var intY=s.interest[year]||0, prnY=s.principal[year]||0;
  var sections=[];

  sections.push({
    title:'Snapshot '+year,
    body:cpDrillStatGridHtml([
      {label:'CFADS '+year,        value:_fmDscrFmtBn(cfadsY).replace(/ млрд| трлн/,''), unit:Math.abs(cfadsY)>=1000000?'трлн':'млрд', color:'#378ADD', cuDecimals:Math.abs(cfadsY)>=10000?0:1, onClick:'_fmDscrClick(\'cell-cfads\','+year+')'},
      {label:'Debt service '+year, value:_fmDscrFmtBn(dsvcY).replace(/ млрд| трлн/,''),  unit:Math.abs(dsvcY)>=1000000?'трлн':'млрд', color:'#EF9F27', cuDecimals:Math.abs(dsvcY)>=10000?0:1, onClick:'_fmDscrClick(\'cell-dsvc\','+year+')'},
      {label:'DSCR',               value:v!=null?v.toFixed(2):'—', unit:'×', cuDecimals:2, color:color, sub:_fmDscrZoneLabel(v)},
      {label:'Запас',              value:_fmDscrFmtBn(cfadsY-dsvcY).replace(/ млрд| трлн/,''), unit:Math.abs(cfadsY-dsvcY)>=1000000?'трлн':'млрд', color:cfadsY>=dsvcY?'#1D9E75':'#E24B4A', cuDecimals:Math.abs(cfadsY-dsvcY)>=10000?0:1, sub:cfadsY>=dsvcY?'покрывает':'дефицит'}
    ])
  });

  sections.push({
    title:'CFADS '+year+' · декомпозиция',
    body:_fmDscrWaterfallHtml([
      {label:'EBITDA',  value:ebY,   color:'#1D9E75'},
      {label:'− Tax',   value:-txY,  color:'#E24B4A'},
      {label:'− ΔNWC',  value:-dNwc, color:'#EF9F27'},
      {label:'− CAPEX', value:-cxY,  color:'#378ADD'}
    ],'CFADS '+year,cfadsY)
  });

  sections.push({
    title:'Debt service '+year+' · состав',
    body:_fmDscrWaterfallHtml([
      {label:'Interest',  value:intY, color:'#7F77DD'},
      {label:'Principal', value:prnY, color:'#A36500'}
    ],'Debt service '+year,dsvcY)
  });

  sections.push({
    title:'DSCR в контексте всех годов · клик — переход',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(yy){
      var vv=s.dscrByYear[yy];
      return {
        label:String(yy)+(yy===year?' П · текущий':' П'),
        value:Math.max(0.001,vv||0),
        valueText:(vv!=null&&isFinite(vv))?(vv.toFixed(2)+'×'):'—',
        color:_fmDscrColorFor(vv),
        onClick:yy!==year?('_fmDscrClick(\'cell-dscr\','+yy+')'):null
      };
    }))
  });

  cpDrillOpen({
    title:'DSCR '+year,
    subtitle:_fmDscrZoneLabel(v)+' · детализация года',
    accent:color,
    accentBg:color==='#1D9E75'?'rgba(29,158,117,.12)':color==='#EF9F27'?'rgba(239,159,39,.12)':color==='#E24B4A'?'rgba(226,75,74,.12)':color==='#933632'?'rgba(147,54,50,.12)':'rgba(148,163,184,.14)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M2 12h20"/></svg>',
    hero:cpDrillHeroHtml({value:v!=null?v.toFixed(2):'—',unit:'×',cuDecimals:2,label:'DSCR за '+year+' год',sub:'CFADS / Debt Service · IFI covenant ≥ 1.20×'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>Изменить EBITDA / CAPEX / WC / Долг → редактор</span><a onclick="cpDrillClose();_fmShowEditor()" style="color:#7F77DD;cursor:pointer;font-weight:600">Открыть редактор →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL F — CFADS cell (year)
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalCellCFADS(model, year){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var ebY=s.ebitda[year]||0, txY=s.tax[year]||0, cxY=s.capex[year]||0, nwcY=s.nwc[year]||0;
  var fcIdx=s.fcYears.indexOf(year);
  var prevNwc=fcIdx>0?(s.nwc[s.fcYears[fcIdx-1]]||0):0;
  var dNwc=nwcY-prevNwc;
  var cfadsY=s.cfads[year]||0;
  /* PV для этого года в LLCR */
  var pv=s.pvByYear[year]||0;
  var sections=[];

  sections.push({
    title:'Декомпозиция · waterfall',
    body:_fmDscrWaterfallHtml([
      {label:'EBITDA',         value:ebY,   color:'#1D9E75'},
      {label:'− Tax',          value:-txY,  color:'#E24B4A'},
      {label:'− ΔNWC',         value:-dNwc, color:'#EF9F27'},
      {label:'− CAPEX',        value:-cxY,  color:'#378ADD'}
    ],'CFADS '+year,cfadsY)
  });

  /* Year-over-year */
  var prevYr=fcIdx>0?s.fcYears[fcIdx-1]:null;
  var nextYr=fcIdx<s.fcYears.length-1?s.fcYears[fcIdx+1]:null;
  var prevCf=prevYr?(s.cfads[prevYr]||0):null;
  var nextCf=nextYr?(s.cfads[nextYr]||0):null;
  var yoyItems=[
    {label:'CFADS · '+year, value:cfadsY!=null?_fmDscrFmtBn(cfadsY).replace(/ млрд| трлн/,''):'—', unit:Math.abs(cfadsY)>=1000000?'трлн':'млрд', color:'#378ADD', cuDecimals:Math.abs(cfadsY)>=10000?0:1, sub:'текущий год'}
  ];
  if(prevCf!=null){yoyItems.push({label:'YoY изменение', value:(((cfadsY-prevCf)/Math.abs(prevCf||1))*100).toFixed(1), unit:'%', cuDecimals:1, color:cfadsY>=prevCf?'#1D9E75':'#E24B4A', sub:'vs '+prevYr+' г.'});}
  yoyItems.push({label:'PV(CFADS) для LLCR', value:_fmDscrFmtBn(pv).replace(/ млрд| трлн/,''), unit:Math.abs(pv)>=1000000?'трлн':'млрд', color:'#7F77DD', cuDecimals:Math.abs(pv)>=10000?0:1, sub:'дисконт WACD '+(s.wacd*100).toFixed(1)+'%'});
  yoyItems.push({label:'Дисконт-фактор', value:(1/Math.pow(1+s.wacd, fcIdx+1)).toFixed(3), unit:'', cuDecimals:3, color:'#94A3B8', sub:'1/(1+WACD)^'+(fcIdx+1)});

  sections.push({title:'Контекст · YoY и PV', body:cpDrillStatGridHtml(yoyItems)});

  /* CFADS все годы */
  sections.push({
    title:'CFADS по всем годам · клик — детализация',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(yy){
      var cf=s.cfads[yy];
      return {
        label:String(yy)+(yy===year?' П · текущий':' П'),
        value:Math.abs(cf||0),
        valueText:_fmDscrFmtSigned(cf),
        color:cf>=0?'#378ADD':'#E24B4A',
        onClick:yy!==year?('_fmDscrClick(\'cell-cfads\','+yy+')'):null
      };
    }))
  });

  sections.push({
    title:'Формула · project finance стандарт',
    body:'<div style="padding:14px 16px;color:var(--t2);font-size:11.5px;line-height:1.7">'+
      '<div style="font-family:monospace;background:rgba(0,0,0,.03);padding:10px 12px;border-radius:6px;margin-bottom:8px;font-size:11px">CFADS = EBITDA − Tax − ΔNWC − CAPEX</div>'+
      '<strong>Cash Flow Available for Debt Service</strong> — операционный денежный поток до обслуживания долга. Используется в DSCR (числитель), LLCR/PLCR (numerator NPV).<br>'+
      'ΔNWC = NWC<sub>'+year+'</sub> − NWC<sub>'+(prevYr||'opening')+'</sub> · отток оборотного капитала (если NWC растёт).'+
    '</div>'
  });

  cpDrillOpen({
    title:'CFADS '+year,
    subtitle:'операционный денежный поток для покрытия долга',
    accent:'#378ADD',
    accentBg:'rgba(55,138,221,.12)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-9 4 18 3-9h4"/></svg>',
    hero:cpDrillHeroHtml({value:_fmDscrFmtBn(cfadsY).replace(/ млрд| трлн/,''),unit:Math.abs(cfadsY)>=1000000?'трлн':'млрд',cuDecimals:Math.abs(cfadsY)>=10000?0:1,label:'CFADS за '+year+' год',sub:'EBITDA − Tax − ΔNWC − CAPEX · project finance стандарт'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>Источник: P&L (EBITDA/Tax) + CAPEX + WC drivers</span><a onclick="cpDrillClose();_fmShowEditor()" style="color:#7F77DD;cursor:pointer;font-weight:600">Открыть редактор →</a></div>'
  });
}

/* ──────────────────────────────────────────────────────────────────────────
   MODAL G — Debt Service cell (year)
   ────────────────────────────────────────────────────────────────────────── */
function _fmDscrModalCellDebtSvc(model, year){
  var s=_fmDscrComputeStats(model);if(!s)return;
  var dsvcY=s.debtService[year]||0;
  var intY=s.interest[year]||0;
  var prnY=s.principal[year]||0;
  var totalDebtY=s.totalDebt[year]||0;
  var fcIdx=s.fcYears.indexOf(year);
  var prevYr=fcIdx>0?s.fcYears[fcIdx-1]:null;
  var prevDebt=prevYr?(s.totalDebt[prevYr]||0):null;
  var sections=[];

  sections.push({
    title:'Состав платежа '+year,
    body:_fmDscrWaterfallHtml([
      {label:'Interest',  value:intY,  color:'#7F77DD'},
      {label:'Principal', value:prnY,  color:'#A36500'}
    ],'Debt service '+year, dsvcY)
  });

  /* Контекст */
  var ctxItems=[
    {label:'Долг на конец '+year, value:_fmDscrFmtBn(totalDebtY).replace(/ млрд| трлн/,''), unit:Math.abs(totalDebtY)>=1000000?'трлн':'млрд', color:'#EF9F27', cuDecimals:totalDebtY>=10000?0:1},
    {label:'WACD',                value:(s.wacd*100).toFixed(2), unit:'%', cuDecimals:2, color:'#7F77DD', sub:'эфф. ставка'}
  ];
  if(prevDebt!=null){
    var dDebt=prevDebt-totalDebtY;
    ctxItems.push({label:'Долг '+(prevYr||''), value:_fmDscrFmtBn(prevDebt).replace(/ млрд| трлн/,''), unit:Math.abs(prevDebt)>=1000000?'трлн':'млрд', color:'#94A3B8', cuDecimals:prevDebt>=10000?0:1, sub:'на конец '+prevYr});
    ctxItems.push({label:'Δ Долг (Principal)', value:_fmDscrFmtBn(Math.abs(dDebt)).replace(/ млрд| трлн/,''), unit:Math.abs(dDebt)>=1000000?'трлн':'млрд', color:dDebt>=0?'#1D9E75':'#E24B4A', cuDecimals:Math.abs(dDebt)>=10000?0:1, sub:dDebt>=0?'погашение':'наращивание'});
  }
  sections.push({title:'Контекст долгового графика', body:cpDrillStatGridHtml(ctxItems)});

  /* График долга по всем годам */
  sections.push({
    title:'Кривая остатка долга по годам',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(yy){
      var d=s.totalDebt[yy]||0;
      return {
        label:String(yy)+(yy===year?' П · текущий':' П'),
        value:Math.max(0.001,d),
        valueText:_fmDscrFmtBn(d),
        color:'#EF9F27'
      };
    }))
  });

  /* Все debt service */
  sections.push({
    title:'Debt service по годам · клик — детализация',
    count:s.fcYears.length,
    body:cpDrillBarsHtml(s.fcYears.map(function(yy){
      var ds=s.debtService[yy]||0;
      return {
        label:String(yy)+(yy===year?' П · текущий':' П'),
        value:Math.max(0.001,ds),
        valueText:_fmDscrFmtBn(ds),
        color:'#A36500',
        onClick:yy!==year?('_fmDscrClick(\'cell-dsvc\','+yy+')'):null
      };
    }))
  });

  cpDrillOpen({
    title:'Debt service '+year,
    subtitle:'обслуживание долга — Interest + Principal',
    accent:'#EF9F27',
    accentBg:'rgba(239,159,39,.14)',
    icon:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h2"/></svg>',
    hero:cpDrillHeroHtml({value:_fmDscrFmtBn(dsvcY).replace(/ млрд| трлн/,''),unit:Math.abs(dsvcY)>=1000000?'трлн':'млрд',cuDecimals:Math.abs(dsvcY)>=10000?0:1,label:'Debt service за '+year+' год',sub:'Знаменатель DSCR · float-rate WACD '+(s.wacd*100).toFixed(1)+'%'}),
    sections:sections,
    footer:'<div style="display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--t3)"><span>Изменить график долга → редактор → Драйверы → Долг (LT/ST по годам)</span><a onclick="cpDrillClose();_fmShowEditor()" style="color:#7F77DD;cursor:pointer;font-weight:600">Открыть редактор →</a></div>'
  });
}




function _fmRenderCapex(model){
  var box=document.getElementById('fm-capex-body');if(!box)return;
  var d=_fmComputeCapex(model);
  var html='<div class="uza-mini-grid" style="grid-template-columns:1fr 1fr;margin-bottom:16px">';
  html+=_uzaMiniKpi({label:'CAPEX 7 лет',value:'<span data-countup="'+d.totalCapex+'" data-cu-d="0" data-cu-sep></span>',sub:(d.capexIntensity!=null?(d.capexIntensity*100).toFixed(0)+'% от выручки':'млрд сум'),dotColor:'#EF9F27',delay:0});
  html+=_uzaMiniKpi({label:'Payback growth',value:(d.payback!=null?d.payback.toFixed(1)+' лет':'—'),sub:'по EBITDA-инкременту',dotColor:'#7F77DD',delay:60});
  html+='</div>';
  /* CAPEX chart — Chart.js stacked bar */
  var cid='fm-capex-chart-'+Date.now();
  html+='<div style="position:relative;height:160px"><canvas id="'+cid+'"></canvas></div>';
  box.innerHTML=html;
  if(typeof _countUpScan==='function') setTimeout(function(){_countUpScan(box,80);},50);
  setTimeout(function(){
    if(typeof Chart==='undefined') return;
    var canvas=document.getElementById(cid); if(!canvas) return;
    var labels=d.byYear.map(function(s){return String(s.y).slice(2)+(s.isFc?'П':'');});
    var maintData=d.byYear.map(function(s){return s.maint||null;});
    var growthData=d.byYear.map(function(s){return s.growth||null;});
    function fmt(v){
      if(v==null) return '—';
      if(typeof finFmt==='function'){
        try{ return finFmt(v, d.byYear[0]&&d.byYear[0].y); }catch(e){}
      }
      var a=Math.abs(v);
      if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
      return v.toLocaleString('ru-RU',{maximumFractionDigits:1});
    }
    new Chart(canvas,{
      type:'bar',
      data:{
        labels:labels,
        datasets:[
          {
            label:'Поддержание',
            data:maintData,
            backgroundColor:'rgba(136,135,128,.55)',
            borderWidth:0,
            borderRadius:2,
            stack:'capex'
          },
          {
            label:'Развитие',
            data:growthData,
            backgroundColor:'#EF9F27',
            borderWidth:0,
            borderRadius:2,
            stack:'capex'
          }
        ]
      },
      options:{
        responsive:true,
        maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{
            position:'bottom',
            align:'start',
            labels:{
              boxWidth:8,
              boxHeight:8,
              font:{size:10,family:'inherit'},
              padding:8,
              usePointStyle:true,
              color:'#5F5E5A'
            }
          },
          tooltip:{
            backgroundColor:'rgba(15,23,60,.92)',
            titleFont:{size:11,family:'inherit',weight:'500'},
            bodyFont:{size:11,family:'inherit'},
            padding:10,
            cornerRadius:8,
            displayColors:true,
            boxPadding:4,
            callbacks:{
              label:function(ctx){return ctx.dataset.label+': '+fmt(ctx.parsed.y);}
            }
          }
        },
        scales:{
          x:{
            stacked:true,
            grid:{display:false},
            ticks:{font:{size:10,family:'inherit'},color:'#94A3B8'},
            border:{color:'rgba(15,23,60,.08)'}
          },
          y:{
            stacked:true,
            grid:{color:'rgba(15,23,60,.04)',drawTicks:false},
            ticks:{
              font:{size:10,family:'inherit'},
              color:'#94A3B8',
              padding:6,
              callback:function(v){return fmt(v);}
            },
            border:{display:false}
          }
        },
        animation:{duration:700,easing:'easeOutCubic'}
      }
    });
  },80);
}
window._fmRenderCapex=_fmRenderCapex;

function _fmRenderWACC(model){
  var box=document.getElementById('fm-wacc-body');if(!box)return;
  var d=_fmComputeWACC(model);
  var tag=document.getElementById('fm-wacc-tag');
  if(tag){tag.textContent=(d.wacc*100).toFixed(2)+'%';tag.className='uza-pill uza-pill-purple';}
  var html='<div style="display:grid;grid-template-columns:1.3fr 1fr;gap:22px">';
  /* LEFT */
  html+='<div>';
  html+='<div style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500;margin-bottom:8px">Структура капитала</div>';
  var wEPct=(d.wE*100).toFixed(0);var wDPct=(d.wD*100).toFixed(0);
  html+='<div style="display:flex;height:24px;border-radius:6px;overflow:hidden;margin-bottom:14px;background:rgba(15,23,60,.04)">';
  html+='<div style="width:0;background:#7F77DD;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:500;animation:uzaBarW1 .8s cubic-bezier(.34,1.0,.64,1) 100ms forwards;--w:'+wEPct+'%">Equity '+wEPct+'%</div>';
  if(d.wD>0) html+='<div style="width:0;background:#1D9E75;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:500;animation:uzaBarW2 .8s cubic-bezier(.34,1.0,.64,1) 250ms forwards;--w:'+wDPct+'%">Debt '+wDPct+'%</div>';
  html+='</div>';
  /* Add inline keyframes for bar widths */
  if(!document.getElementById('uza-wacc-bar-css')){
    var sb=document.createElement('style');sb.id='uza-wacc-bar-css';
    sb.textContent='@keyframes uzaBarW1{to{width:var(--w)}}@keyframes uzaBarW2{to{width:var(--w)}}';
    document.head.appendChild(sb);
  }
  html+='<table class="uza-tbl" style="font-size:11.5px">';
  html+='<tr><td>Cost of equity (CAPM)</td><td style="font-weight:500;color:#534AB7">'+(d.costEq*100).toFixed(2)+'%</td></tr>';
  html+='<tr><td style="padding-left:24px;color:var(--t3);font-size:10.5px">Risk-free rate (10Y ОВГЗ)</td><td style="color:var(--t2);font-size:10.5px">'+(d.rf*100).toFixed(1)+'%</td></tr>';
  html+='<tr><td style="padding-left:24px;color:var(--t3);font-size:10.5px">+ β × Risk premium ('+d.beta.toFixed(1)+' × '+(d.mrp*100).toFixed(0)+'%)</td><td style="color:var(--t2);font-size:10.5px">'+(d.beta*d.mrp*100).toFixed(1)+'%</td></tr>';
  html+='<tr><td style="padding-left:24px;color:var(--t3);font-size:10.5px">'+(d.ca>=0?'+':'')+' Country adjustment</td><td style="color:var(--t2);font-size:10.5px">'+(d.ca>=0?'+':'')+(d.ca*100).toFixed(1)+'%</td></tr>';
  html+='<tr><td>Cost of debt после налога</td><td style="font-weight:500;color:#0F6E56">'+(d.costDebtAfter*100).toFixed(2)+'%</td></tr>';
  html+='<tr><td style="padding-left:24px;color:var(--t3);font-size:10.5px">Effective rate</td><td style="color:var(--t2);font-size:10.5px">'+(d.costDebtPre*100).toFixed(1)+'%</td></tr>';
  html+='<tr><td style="padding-left:24px;color:var(--t3);font-size:10.5px">× (1 − tax '+(d.taxRate*100).toFixed(0)+'%)</td><td style="color:var(--t2);font-size:10.5px">×'+((1-d.taxRate)).toFixed(2)+'</td></tr>';
  html+='<tr class="strong"><td>WACC = '+d.wE.toFixed(2)+'×'+(d.costEq*100).toFixed(1)+'% + '+d.wD.toFixed(2)+'×'+(d.costDebtAfter*100).toFixed(1)+'%</td><td style="color:#534AB7;font-size:14px">'+(d.wacc*100).toFixed(1)+'%</td></tr>';
  html+='</table>';
  html+='</div>';
  /* RIGHT — sensitivity */
  html+='<div>';
  html+='<div style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:500;margin-bottom:8px">Чувствительность EV к WACC</div>';
  if(d.sens.length){
    html+='<table class="uza-tbl" style="font-size:11px">';
    html+='<thead><tr><th>WACC</th><th>EV</th><th>Δ к базе</th></tr></thead><tbody>';
    d.sens.forEach(function(s,i){
      var isBase=i===2;
      var deltaCol=s.delta!=null?(s.delta>=0?'#1D9E75':'#A32D2D'):'var(--t2)';
      var rowCls=isBase?'highlight':'';
      html+='<tr class="'+rowCls+'" style="animation:uzaRowIn .4s ease '+(i*50)+'ms both">';
      html+='<td style="'+(isBase?'color:#534AB7;font-weight:500':'color:var(--t2)')+'">'+(s.wacc*100).toFixed(1)+'%</td>';
      html+='<td style="'+(isBase?'font-weight:500;color:#534AB7':'')+'">'+_uzaFmtNum(s.ev,0)+'</td>';
      html+='<td style="'+(isBase?'color:#534AB7;font-weight:500':'color:'+deltaCol)+'">'+(isBase?'база':(s.delta!=null?(s.delta>=0?'+':'')+(s.delta*100).toFixed(0)+'%':'—'))+'</td>';
      html+='</tr>';
    });
    html+='</tbody></table>';
    var s_plus1=d.sens[3];
    if(s_plus1&&s_plus1.delta!=null){
      var msg='+1 п.п. к WACC '+(s_plus1.delta>=0?'повышает':'снижает')+' EV на '+Math.abs(s_plus1.delta*100).toFixed(0)+'%. ';
      msg+=Math.abs(s_plus1.delta)>=0.1?'Чувствительность высокая.':'Чувствительность умеренная.';
      html+='<div style="font-size:10.5px;color:var(--t3);margin-top:10px;line-height:1.55">'+msg+'</div>';
    }
  } else {
    html+='<div style="padding:20px 8px;text-align:center;color:var(--t3);font-size:11px">EV ещё не рассчитан.</div>';
  }
  html+='</div>';
  html+='</div>';
  box.innerHTML=html;
}
window._fmRenderWACC=_fmRenderWACC;

/* ═════════════ DRILL MODALS ═════════════ */

function _fmOpenROICDrill(){
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  var d=_fmComputeROIC(model);
  var h=model.horizon||{};var allY=[].concat(h.factYears||[],h.forecastYears||[]);var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  var taxRate=(model.assumptions&&model.assumptions.taxRate)||0.15;
  var bH='';
  bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Расчёт ROIC по годам</div>';
  bH+='<div class="uza-sec-desc">ROIC = NOPAT / Invested Capital. NOPAT = Операционная прибыль × (1 − ставка налога). Invested Capital = Equity + Total Debt − Cash.</div>';
  bH+='<div style="overflow-x:auto"><table class="uza-tbl" style="min-width:680px">';
  bH+='<thead><tr><th>Показатель</th>';
  allY.forEach(function(y){bH+='<th'+(factSet[y]?'':' style="color:#854F0B"')+'>'+y+(factSet[y]?'':' П')+'</th>';});
  bH+='</tr></thead><tbody>';
  bH+='<tr><td>Операционная прибыль</td>';
  allY.forEach(function(y){var v=model.outputs&&model.outputs.pnl&&model.outputs.pnl.opProfit&&model.outputs.pnl.opProfit[y];bH+='<td>'+_uzaFmtNum(v)+'</td>';});
  bH+='</tr>';
  bH+='<tr><td>× (1 − налог '+(taxRate*100).toFixed(0)+'%)</td>';
  allY.forEach(function(){bH+='<td style="color:var(--t3);font-size:10.5px">×'+((1-taxRate)).toFixed(2)+'</td>';});
  bH+='</tr>';
  bH+='<tr class="strong"><td>NOPAT</td>';
  allY.forEach(function(y){bH+='<td>'+_uzaFmtNum(d.nopatBy[y])+'</td>';});
  bH+='</tr>';
  bH+='<tr><td>Invested capital</td>';
  allY.forEach(function(y){bH+='<td>'+_uzaFmtNum(d.icBy[y])+'</td>';});
  bH+='</tr>';
  bH+='<tr class="strong"><td>ROIC</td>';
  allY.forEach(function(y){var v=d.byYear[y];bH+='<td style="color:'+(v!=null&&v>=d.wacc?'#0F6E56':v!=null?'#A32D2D':'var(--t3)')+';font-weight:500">'+(v!=null?(v*100).toFixed(1)+'%':'—')+'</td>';});
  bH+='</tr>';
  bH+='<tr><td>WACC (бенчмарк)</td>';
  allY.forEach(function(){bH+='<td style="color:var(--t3)">'+(d.wacc*100).toFixed(1)+'%</td>';});
  bH+='</tr>';
  bH+='</tbody></table></div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Что говорит ROIC</div>';
  bH+='<div class="uza-alert uza-alert-teal" style="margin-bottom:10px"><div class="uza-alert-ttl">ROIC выше WACC — value creation</div>Каждый рубль вложенного капитала зарабатывает больше, чем стоимость его привлечения. Каждый дополнительный сум инвестиций увеличивает стоимость акционера.</div>';
  bH+='<div class="uza-alert uza-alert-red" style="margin-bottom:10px"><div class="uza-alert-ttl">ROIC ниже WACC — value destruction</div>Компания «разрушает» стоимость, даже если показывает прибыль. Лучше вернуть капитал акционеру (дивиденды) или сократить активы.</div>';
  bH+='<div class="uza-alert uza-alert-purple"><div class="uza-alert-ttl">EVA = (ROIC − WACC) × Invested Capital</div>Экономическая добавленная стоимость в абсолюте. Текущее значение: <strong style="color:'+(d.eva!=null&&d.eva>=0?'#0F6E56':'#A32D2D')+';font-weight:500">'+_uzaFmtNum(d.eva)+' млрд сум</strong>.</div>';
  bH+='</div>';
  _uzaOpenModal({
    id:'uza-roic-drill',
    title:'Детализация ROIC · '+co,
    subtitle:'NOPAT / Invested Capital по годам',
    accent:'#1D9E75',
    pill:'value creation',
    pillClass:'uza-pill-teal',
    icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10l3-3 2 2 4-5"/><path d="M9 4h3v3"/></svg>',
    bodyHtml:bH
  });
}
window._fmOpenROICDrill=_fmOpenROICDrill;

function _fmOpenDebtDrill(){
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  var d=_fmComputeDebt(model);
  var bH='';
  var ndStatus=d.ndE!=null?(d.ndE<=d.covNdE*0.7?'safe':d.ndE<=d.covNdE?'warn':'breach'):'na';
  var icStatus=d.intCov!=null?(d.intCov>=d.covIntCov*1.5?'safe':d.intCov>=d.covIntCov?'warn':'breach'):'na';
  var stColor={safe:'#1D9E75',warn:'#EF9F27',breach:'#E24B4A',na:'#94A3B8'};
  var stLbl={safe:'В пределах ковенант',warn:'Близко к границе',breach:'НАРУШЕНИЕ ковенант',na:'нет данных'};
  bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Метрики долговой нагрузки</div>';
  bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr)">';
  bH+=_uzaMiniKpi({label:'Net Debt / EBITDA',value:'<span style="color:'+stColor[ndStatus]+'">'+(d.ndE!=null?d.ndE.toFixed(1)+'×':'—')+'</span>',sub:'covenant ≤ '+d.covNdE.toFixed(1)+'× · '+stLbl[ndStatus],dotColor:stColor[ndStatus],delay:0});
  bH+=_uzaMiniKpi({label:'Interest coverage',value:'<span style="color:'+stColor[icStatus]+'">'+(d.intCov!=null?d.intCov.toFixed(1)+'×':'—')+'</span>',sub:'covenant ≥ '+d.covIntCov.toFixed(1)+'× · '+stLbl[icStatus],dotColor:stColor[icStatus],delay:60});
  bH+=_uzaMiniKpi({label:'Debt / (D+E)',value:(d.debtEq!=null?(d.debtEq*100).toFixed(0)+'%':'—'),sub:'структура капитала',dotColor:'#7F77DD',delay:120});
  bH+='</div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">График погашения по годам</div>';
  bH+='<div style="overflow-x:auto"><table class="uza-tbl" style="min-width:600px">';
  bH+='<thead><tr><th>Год</th><th>Долгосроч. долг</th><th>Краткосроч. долг</th><th>Всего</th><th>EBITDA</th><th>Net Debt/EBITDA</th></tr></thead><tbody>';
  d.schedule.forEach(function(s,i){
    var eb=model.outputs&&model.outputs.pnl&&model.outputs.pnl.ebitda&&model.outputs.pnl.ebitda[s.y];
    var nd=model.outputs&&model.outputs.bs&&model.outputs.bs.netDebt&&model.outputs.bs.netDebt[s.y];
    var ratio=nd!=null&&eb?nd/eb:null;
    var ratioCol=ratio!=null?(ratio<=d.covNdE?'#0F6E56':'#A32D2D'):'var(--t3)';
    bH+='<tr class="'+(s.isFc?'fc':'')+'" style="animation:uzaRowIn .35s ease '+(i*30)+'ms both"><td'+(s.isFc?' style="color:#854F0B"':'')+'>'+s.y+(s.isFc?' П':'')+'</td><td>'+_uzaFmtNum(s.lt)+'</td><td>'+_uzaFmtNum(s.st)+'</td><td style="font-weight:500">'+_uzaFmtNum(s.total)+'</td><td>'+_uzaFmtNum(eb)+'</td><td style="color:'+ratioCol+';font-weight:500">'+(ratio!=null?ratio.toFixed(1)+'×':'—')+'</td></tr>';
  });
  bH+='</tbody></table></div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-sec-ttl">Что отслеживать</div>';
  bH+='<div class="uza-alert uza-alert-purple"><ul style="margin:0;padding-left:18px;line-height:1.7"><li><strong style="font-weight:500">Net Debt / EBITDA</strong> — главный ковенант. При превышении 3× банки могут потребовать досрочного погашения или повышения ставки.</li><li><strong style="font-weight:500">Interest coverage</strong> — способность обслуживать долг. Ниже 2,5× — риск технического дефолта.</li><li><strong style="font-weight:500">Профиль погашения</strong> — пиковые годы погашения требуют рефинансирования.</li><li><strong style="font-weight:500">Структура LT/ST</strong> — высокая доля краткосрочного долга — риск ликвидности.</li></ul></div>';
  bH+='</div>';
  var ovrPill=d.ndE!=null?(d.ndE<=d.covNdE*0.7?{l:'в норме',c:'uza-pill-teal'}:d.ndE<=d.covNdE?{l:'внимание',c:'uza-pill-amber'}:{l:'нарушение',c:'uza-pill-red'}):{l:'нет данных',c:'uza-pill-gray'};
  _uzaOpenModal({
    id:'uza-debt-drill',
    title:'Долговая нагрузка · '+co,
    subtitle:'covenants tracker и график погашения',
    accent:'#7F77DD',
    pill:ovrPill.l,
    pillClass:ovrPill.c,
    icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="10" height="7" rx="1"/><path d="M5 4V3a2 2 0 1 1 4 0v1"/></svg>',
    bodyHtml:bH
  });
}
window._fmOpenDebtDrill=_fmOpenDebtDrill;

function _fmOpenCapexDrill(){
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  var d=_fmComputeCapex(model);
  var bH='';
  bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Сводка инвестиционной программы</div>';
  bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
  bH+=_uzaMiniKpi({label:'CAPEX 7 лет',value:_uzaFmtNum(d.totalCapex),sub:'млрд сум',dotColor:'#EF9F27',delay:0});
  bH+=_uzaMiniKpi({label:'CAPEX intensity',value:(d.capexIntensity!=null?(d.capexIntensity*100).toFixed(0)+'%':'—'),sub:'от выручки',dotColor:'#7F77DD',delay:60});
  bH+=_uzaMiniKpi({label:'Поддержание',value:_uzaFmtNum(d.totalMaint),sub:(d.totalCapex>0?(d.totalMaint/d.totalCapex*100).toFixed(0)+'% доли':'—'),dotColor:'#888780',delay:120});
  bH+=_uzaMiniKpi({label:'Развитие',value:_uzaFmtNum(d.totalGrowth),sub:(d.totalCapex>0?(d.totalGrowth/d.totalCapex*100).toFixed(0)+'% доли':'—'),dotColor:'#EF9F27',delay:180});
  bH+='</div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:160ms"><div class="uza-sec-ttl">Разбивка CAPEX по годам</div>';
  bH+='<div style="overflow-x:auto"><table class="uza-tbl" style="min-width:600px">';
  bH+='<thead><tr><th>Год</th><th>CAPEX</th><th>Амортизация (D&A)</th><th>Поддержание</th><th>Развитие</th><th>Доля развития</th></tr></thead><tbody>';
  d.byYear.forEach(function(s,i){
    var da=model.outputs&&model.outputs.pnl&&model.outputs.pnl.depreciation&&model.outputs.pnl.depreciation[s.y];
    var growthShare=s.capex>0?(s.growth/s.capex*100):0;
    bH+='<tr class="'+(s.isFc?'fc':'')+'" style="animation:uzaRowIn .35s ease '+(i*30)+'ms both"><td'+(s.isFc?' style="color:#854F0B"':'')+'>'+s.y+(s.isFc?' П':'')+'</td><td style="font-weight:500">'+_uzaFmtNum(s.capex)+'</td><td>'+_uzaFmtNum(da)+'</td><td>'+_uzaFmtNum(s.maint)+'</td><td style="color:'+(s.growth>0?'#854F0B':'var(--t3)')+';font-weight:500">'+_uzaFmtNum(s.growth)+'</td><td>'+growthShare.toFixed(0)+'%</td></tr>';
  });
  bH+='</tbody></table></div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:300ms"><div class="uza-sec-ttl">Логика разделения</div>';
  bH+='<div class="uza-alert uza-alert-amber"><div style="line-height:1.7"><p style="margin:0 0 8px"><strong style="font-weight:500">Поддержание (maintenance CAPEX)</strong> = min(CAPEX, D&A). Инвестиции на сохранение текущей мощности — замена изношенного оборудования. По экономике это «затраты», не создающие новой стоимости.</p><p style="margin:0 0 8px"><strong style="font-weight:500">Развитие (growth CAPEX)</strong> = max(0, CAPEX − D&A). Инвестиции в новые мощности — генерируют будущий рост EBITDA. Окупаемость измеряется через NPV или IRR.</p><p style="margin:0"><strong style="font-weight:500">Payback growth ('+(d.payback!=null?d.payback.toFixed(1)+' лет':'—')+')</strong> — оценочный срок окупаемости развития.</p></div></div>';
  bH+='</div>';
  _uzaOpenModal({
    id:'uza-capex-drill',
    title:'CAPEX программа · '+co,
    subtitle:'maintenance + growth разбивка по годам',
    accent:'#EF9F27',
    icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11.5h10M3.5 11.5V7l3-3 3 3v4.5"/></svg>',
    bodyHtml:bH
  });
}
window._fmOpenCapexDrill=_fmOpenCapexDrill;

function _fmOpenWACCDrill(){
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  _fmEnsureAssumptions(model);
  var a=model.assumptions;
  var bH='';
  bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Параметры стоимости капитала</div>';
  bH+='<div class="uza-sec-desc">Изменяйте параметры — WACC и EV пересчитаются автоматически. Для сохранения нажмите «Применить и сохранить».</div>';
  bH+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">';
  bH+='<div><div style="font-size:10.5px;font-weight:500;color:#534AB7;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #EEEDFE">Cost of equity (CAPM)</div>';
  bH+=_uzaDrillField('Risk-free rate (10Y ОВГЗ)','rfPct',(a.riskFreeRate*100).toFixed(2),'%','0.1');
  bH+=_uzaDrillField('Beta (β)','betaVal',a.beta.toFixed(2),'','0.05');
  bH+=_uzaDrillField('Market risk premium','mrpPct',(a.marketRiskPremium*100).toFixed(2),'%','0.1');
  bH+=_uzaDrillField('Country adjustment','caPct',(a.countryAdjustment*100).toFixed(2),'%','0.1');
  bH+='</div>';
  bH+='<div><div style="font-size:10.5px;font-weight:500;color:#0F6E56;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #E1F5EE">Cost of debt</div>';
  bH+=_uzaDrillField('Effective rate','codPct',(a.effectiveCostOfDebt*100).toFixed(2),'%','0.1');
  bH+=_uzaDrillField('Tax rate','txPct',(a.taxRate*100).toFixed(2),'%','0.5');
  bH+=_uzaDrillField('Terminal growth','tgPct',((a.terminalGrowth||0.03)*100).toFixed(2),'%','0.1');
  bH+='</div></div></div>';
  bH+='<div class="uza-sec" style="--uza-secd:160ms"><div class="uza-sec-ttl">Live recalculation</div><div id="fm-wacc-live" style="background:rgba(127,119,221,.04);border:1px solid rgba(127,119,221,.12);border-radius:12px;padding:16px"></div></div>';
  var foot='<button class="uza-btn uza-btn-ghost" onclick="_uzaCloseModal(\'uza-wacc-drill\')">Отмена</button>'+
    '<button class="uza-btn uza-btn-primary" onclick="_fmWACCApply()">Применить и сохранить</button>';
  var modal=_uzaOpenModal({
    id:'uza-wacc-drill',
    title:'Компоненты WACC · '+co,
    subtitle:'live recalculation EV/NPV при изменении параметров',
    accent:'#7F77DD',
    icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="2"/><path d="M7 1v2M7 11v2M1 7h2M11 7h2"/></svg>',
    bodyHtml:bH,
    footHtml:foot
  });
  setTimeout(function(){
    ['rfPct','betaVal','mrpPct','caPct','codPct','txPct','tgPct'].forEach(function(id){
      var inp=modal.querySelector('[data-fm-fld="'+id+'"]');
      if(inp) inp.addEventListener('input',_fmWACCLiveUpdate);
    });
    _fmWACCLiveUpdate();
  },80);
}
window._fmOpenWACCDrill=_fmOpenWACCDrill;

function _uzaDrillField(label,id,val,suffix,step){
  return '<div style="margin-bottom:12px"><label style="font-size:11px;color:var(--t3);display:block;margin-bottom:5px;font-weight:500">'+esc(label)+'</label>'+
    '<div style="display:flex;align-items:center;gap:6px"><input type="number" step="'+step+'" data-fm-fld="'+id+'" value="'+val+'" class="uza-input" style="flex:1"/>'+
    (suffix?'<span style="font-size:11px;color:var(--t3);min-width:14px;font-weight:500">'+suffix+'</span>':'')+'</div></div>';
}
window._uzaDrillField=_uzaDrillField;

function _fmWACCLiveUpdate(){
  var modal=document.querySelector('#uza-wacc-drill .uza-modal');if(!modal)return;
  function gv(id){var el=modal.querySelector('[data-fm-fld="'+id+'"]');return el?parseFloat(el.value)||0:0;}
  var rf=gv('rfPct')/100,beta=gv('betaVal'),mrp=gv('mrpPct')/100,ca=gv('caPct')/100;
  var cod=gv('codPct')/100,tx=gv('txPct')/100,tg=gv('tgPct')/100;
  var costEq=rf+beta*mrp+ca;
  var costDebtAfter=cod*(1-tx);
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model)return;
  var o=model.outputs||{},h=model.horizon||{};
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var debt=lastFc?o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]:null;
  var eq=lastFc?o.bs&&o.bs.equity&&o.bs.equity[lastFc]:null;
  var totCap=(debt||0)+(eq||0);
  var wD=totCap>0?debt/totCap:0;var wE=totCap>0?eq/totCap:1;
  var wacc=wE*costEq+wD*costDebtAfter;
  var fcY=h.forecastYears||[];
  var pv=0;
  fcY.forEach(function(y,i){var f=o.cf&&o.cf.fcff&&o.cf.fcff[y];if(f!=null)pv+=f/Math.pow(1+wacc,i+1);});
  var fcffLast=fcY.length?o.cf&&o.cf.fcff&&o.cf.fcff[fcY[fcY.length-1]]:null;
  var newEv=null;
  if(fcffLast!=null&&wacc>tg){
    var tv=fcffLast*(1+tg)/(wacc-tg);
    var pvTV=tv/Math.pow(1+wacc,fcY.length);
    newEv=pv+pvTV;
  }
  var oldEv=o.ratios&&o.ratios.enterpriseValue;
  var deltaEv=newEv!=null&&oldEv?(newEv-oldEv)/oldEv:null;
  var live=document.getElementById('fm-wacc-live');
  if(!live)return;
  var html='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
  html+=_uzaMiniKpi({label:'Cost of equity',value:'<span style="color:#534AB7">'+(costEq*100).toFixed(2)+'%</span>',sub:'CAPM',dotColor:'#534AB7'});
  html+=_uzaMiniKpi({label:'Cost of debt (after tax)',value:'<span style="color:#0F6E56">'+(costDebtAfter*100).toFixed(2)+'%</span>',sub:'effective × (1−tax)',dotColor:'#0F6E56'});
  html+=_uzaMiniKpi({label:'Новый WACC',value:'<span style="color:#534AB7">'+(wacc*100).toFixed(2)+'%</span>',sub:wE.toFixed(2)+'×CoE + '+wD.toFixed(2)+'×CoD',dotColor:'#7F77DD'});
  var evCol=deltaEv!=null?(deltaEv>=0?'#1D9E75':'#A32D2D'):'var(--t1)';
  var evSub=deltaEv!=null?(deltaEv>=0?'+':'')+(deltaEv*100).toFixed(1)+'% к базе':'млрд сум';
  html+=_uzaMiniKpi({label:'Новый EV',value:'<span style="color:'+evCol+'">'+_uzaFmtNum(newEv)+'</span>',sub:evSub,dotColor:evCol});
  html+='</div>';
  live.innerHTML=html;
}
window._fmWACCLiveUpdate=_fmWACCLiveUpdate;

/* _fmWACCApply остаётся в старом виде, только в конце вызывает _uzaCloseModal */
function _fmWACCApply(){
  var modal=document.querySelector('#uza-wacc-drill .uza-modal');if(!modal)return;
  function gv(id){var el=modal.querySelector('[data-fm-fld="'+id+'"]');return el?parseFloat(el.value)||0:0;}
  var co=window._fmSelCo,scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model)return;
  _fmEnsureAssumptions(model);
  var rf=gv('rfPct')/100,beta=gv('betaVal'),mrp=gv('mrpPct')/100,ca=gv('caPct')/100;
  var cod=gv('codPct')/100,tx=gv('txPct')/100,tg=gv('tgPct')/100;
  var costEq=rf+beta*mrp+ca;
  var costDebtAfter=cod*(1-tx);
  var o=model.outputs||{},h=model.horizon||{};var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var debt=lastFc?o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]:0;
  var eq=lastFc?o.bs&&o.bs.equity&&o.bs.equity[lastFc]:1;
  var totCap=(debt||0)+(eq||0);
  var wD=totCap>0?debt/totCap:0;var wE=totCap>0?eq/totCap:1;
  var wacc=wE*costEq+wD*costDebtAfter;
  model.assumptions.riskFreeRate=rf;
  model.assumptions.beta=beta;
  model.assumptions.marketRiskPremium=mrp;
  model.assumptions.countryAdjustment=ca;
  model.assumptions.effectiveCostOfDebt=cod;
  model.assumptions.taxRate=tx;
  model.assumptions.terminalGrowth=tg;
  model.assumptions.wacc=wacc;
  if(typeof FB_URL==='function'){
    var url=FB_URL().replace(/\.json.*$/,'')+'/finModel/'+encodeURIComponent(co)+'/'+scn+'/assumptions.json';
    fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(model.assumptions)}).catch(function(e){console.warn('[FM] WACC save failed',e);});
  }
  if(typeof toast==='function') toast('WACC обновлён · '+(wacc*100).toFixed(2)+'%');
  _uzaCloseModal('uza-wacc-drill');
  _fmRepaint();
}
window._fmWACCApply=_fmWACCApply;

/* ═══════════════════════════════════════════════════════════════════════════
   FIN-MODEL · KPI ROW DRILL-DOWNS (7 cards) + WORKING CAPITAL DRILL-DOWNS (4)
   ═══════════════════════════════════════════════════════════════════════════ */

function _fmKpiDrill(kind){
  var co=window._fmSelCo, scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  var o=model.outputs||{};
  var h=model.horizon||{};
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  var lastFact=(h.factYears||[]).slice(-1)[0];
  var asm=model.assumptions||{};
  var wacc=asm.wacc||0.12;
  var growth=asm.terminalGrowth||0.03;
  var unitL=(typeof finUL==='function'?finUL():'млрд сум');
  
  /* Helpers */
  function fmtN(v,dec){
    /* UZSm scale → human-readable. v=1,124,532 → "1.12 трлн" (1.12 trillion sum) */
    if(v==null||isNaN(v))return '<span style="color:var(--t3)">—</span>';
    var a=Math.abs(v);
    if(a>=1e6) return (v/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})+' трлн';
    if(a>=1e3) return (v/1e3).toLocaleString('ru-RU',{maximumFractionDigits:1})+' млрд';
    return v.toLocaleString('ru-RU',{maximumFractionDigits:dec||0})+' млн';
  }
  function fmtPct(v,dec){if(v==null||isNaN(v))return '—';return (v*100).toFixed(dec==null?1:dec)+'%';}
  
  /* Универсальный line chart helper — Chart.js, premium UzAssets design system
     Дизайн-код:
     - тонкие линии (1.6px), нет агрессивной заливки для multi-series
     - tension .15 (минимум сглаживания, честные тренды)
     - palette: #7F77DD #1D9E75 #EF9F27 #378ADD #E24B4A #1E2A4A
     - grid: rgba(15,23,42,.04), без X-grid
     - cubic-bezier(.34,1.2,.64,1) easing
     - hex→rgba конверсия для альфы корректно */
  function lineChartHtml(opts){
    return '<div style="position:relative;height:'+(opts.height||180)+'px;padding:4px 0"><canvas id="'+opts.cid+'"></canvas></div>';
  }
  /* Hex/rgb/rgba → rgba(r,g,b,alpha) */
  function _uzaColorAlpha(c,a){
    if(!c)return 'rgba(127,119,221,'+a+')';
    if(c.charAt(0)==='#'){
      var hex=c.slice(1);
      if(hex.length===3)hex=hex.split('').map(function(x){return x+x;}).join('');
      var r=parseInt(hex.slice(0,2),16), g=parseInt(hex.slice(2,4),16), b=parseInt(hex.slice(4,6),16);
      return 'rgba('+r+','+g+','+b+','+a+')';
    }
    if(c.indexOf('rgba')===0)return c.replace(/,[^,)]+\)$/,','+a+')');
    if(c.indexOf('rgb')===0)return c.replace('rgb(','rgba(').replace(')',','+a+')');
    return c;
  }
  function renderLineChart(cid,labels,datasets,yFmt){
    setTimeout(function(){
      if(typeof Chart==='undefined') return;
      var canvas=document.getElementById(cid); if(!canvas) return;
      var multi=datasets.length>1;
      var ds=datasets.map(function(d,idx){
        /* Default fill: только single series. Для multi-series — clean lines */
        var doFill=(d.fill==null)?(!multi):d.fill;
        var bgCol=d.fillColor||_uzaColorAlpha(d.color, multi?0.04:0.10);
        return {
          label:d.label,
          data:d.data,
          borderColor:d.color,
          backgroundColor:bgCol,
          borderWidth:1.6,
          tension:0.15,
          pointRadius:3,
          pointHoverRadius:5,
          pointBackgroundColor:'#fff',
          pointBorderColor:d.color,
          pointBorderWidth:1.6,
          pointHoverBackgroundColor:d.color,
          pointHoverBorderColor:'#fff',
          pointHoverBorderWidth:2,
          fill:doFill,
          spanGaps:true,
          borderDash:d.dash||[],
          cubicInterpolationMode:'default',
          order:multi?(datasets.length-idx):0
        };
      });
      new Chart(canvas,{
        type:'line',
        data:{labels:labels,datasets:ds},
        options:{
          responsive:true,
          maintainAspectRatio:false,
          interaction:{mode:'index',intersect:false},
          layout:{padding:{top:8,bottom:0,left:2,right:8}},
          plugins:{
            legend:{position:'bottom',align:'start',labels:{boxWidth:6,boxHeight:6,font:{size:10.5,family:'inherit',weight:'500'},padding:12,usePointStyle:true,pointStyle:'circle',color:'#5F5E5A'}},
            tooltip:{
              backgroundColor:'rgba(30,42,74,.96)',
              titleColor:'#fff',
              bodyColor:'#E2E8F0',
              titleFont:{size:11,family:'inherit',weight:'600'},
              bodyFont:{size:11.5,family:'inherit'},
              padding:{x:12,y:10},
              cornerRadius:8,
              displayColors:true,
              boxPadding:6,
              boxWidth:6,
              boxHeight:6,
              usePointStyle:true,
              caretSize:0,
              caretPadding:8,
              borderColor:'rgba(255,255,255,.06)',
              borderWidth:1,
              callbacks:{label:function(ctx){return ' '+ctx.dataset.label+': '+(yFmt?yFmt(ctx.parsed.y):ctx.parsed.y);}}
            }
          },
          scales:{
            x:{
              grid:{display:false},
              ticks:{font:{size:10,family:'inherit'},color:'#94A3B8',padding:6},
              border:{color:'rgba(15,23,42,.06)'}
            },
            y:{
              grid:{color:'rgba(15,23,42,.04)',drawTicks:false,lineWidth:1},
              ticks:{font:{size:10,family:'inherit'},color:'#94A3B8',padding:8,maxTicksLimit:5,callback:function(v){return yFmt?yFmt(v):v;}},
              border:{display:false}
            }
          },
          animation:{duration:700,easing:'easeOutCubic'},
          transitions:{active:{animation:{duration:200}}}
        }
      });
    },80);
  }
  
  var meta=null;
  
  if(kind==='ev'){
    /* Enterprise Value drill: PV(FCFF) + PV(TV) breakdown */
    var fcY=h.forecastYears||[];
    var pvSum=0,pvDetails=[];
    fcY.forEach(function(y,i){
      var fcff=o.cf&&o.cf.fcff&&o.cf.fcff[y];
      if(fcff!=null){
        var df=Math.pow(1+wacc,i+1);
        var pv=fcff/df;
        pvSum+=pv;
        pvDetails.push({y:y,fcff:fcff,df:df,pv:pv});
      }
    });
    var fcffLast=fcY.length?(o.cf&&o.cf.fcff&&o.cf.fcff[fcY[fcY.length-1]]):null;
    var tv=null,pvTV=null,ev=null;
    if(fcffLast!=null&&wacc>growth){
      tv=fcffLast*(1+growth)/(wacc-growth);
      pvTV=tv/Math.pow(1+wacc,fcY.length);
      ev=pvSum+pvTV;
    }
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Компоненты Enterprise Value</div>';
    bH+='<div class="uza-sec-desc">EV = Σ PV(FCFF за прогнозный период) + PV(Terminal Value). Ставка дисконтирования — WACC '+(wacc*100).toFixed(2)+'%.</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr)">';
    bH+=_uzaMiniKpi({label:'PV прогноза',value:fmtN(pvSum),sub:fcY.length+' лет дисконт. FCFF',dotColor:'#1D9E75',delay:0});
    bH+=_uzaMiniKpi({label:'PV Terminal Value',value:fmtN(pvTV),sub:'g='+((growth*100).toFixed(1))+'% perpetuity',dotColor:'#7F77DD',delay:60});
    bH+=_uzaMiniKpi({label:'Enterprise Value',value:'<span style="color:#534AB7">'+fmtN(ev)+'</span>',sub:unitL,dotColor:'#534AB7',delay:120});
    bH+='</div></div>';
    /* DCF table */
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Дисконтированный поток FCFF</div>';
    bH+='<div style="overflow-x:auto"><table class="uza-tbl" style="min-width:580px"><thead><tr><th>Год</th><th>FCFF</th><th>Discount factor</th><th>PV(FCFF)</th></tr></thead><tbody>';
    pvDetails.forEach(function(p,i){
      bH+='<tr style="animation:uzaRowIn .35s ease '+(i*30)+'ms both"><td style="color:#854F0B">'+p.y+'</td><td>'+fmtN(p.fcff)+'</td><td style="color:var(--t3)">÷ '+p.df.toFixed(3)+'</td><td style="font-weight:500">'+fmtN(p.pv)+'</td></tr>';
    });
    bH+='<tr class="strong"><td colspan="3">Σ PV(FCFF) прогноза</td><td style="color:#0F6E56">'+fmtN(pvSum)+'</td></tr>';
    if(tv!=null){
      bH+='<tr><td>Terminal Value (на конец)</td><td>'+fmtN(tv)+'</td><td style="color:var(--t3)">÷ '+Math.pow(1+wacc,fcY.length).toFixed(3)+'</td><td style="font-weight:500">'+fmtN(pvTV)+'</td></tr>';
    }
    bH+='<tr class="strong"><td colspan="3">EV = Σ PV(FCFF) + PV(TV)</td><td style="color:#534AB7;font-size:14px">'+fmtN(ev)+'</td></tr>';
    bH+='</tbody></table></div></div>';
    /* Methodology */
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert uza-alert-purple"><div class="uza-alert-ttl">Методология DCF</div>Enterprise Value представляет рыночную стоимость операционных активов компании независимо от структуры финансирования. Прогнозный период — '+fcY.length+' лет, после чего применяется Gordon Growth Model для оценки terminal value с темпом роста '+(growth*100).toFixed(1)+'%. Чувствительность EV к WACC высокая — см. блок «WACC и его компоненты».</div></div>';
    meta={id:'uza-kpi-ev',title:'Enterprise Value · '+co,subtitle:'DCF разбивка с дисконтированными FCFF',accent:'#7F77DD',pill:fmtN(ev),pillClass:'uza-pill-purple',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1.5v11M3 5l4-3 4 3M3 9l4 3 4-3"/></svg>',
      bodyHtml:bH};
  }
  
  else if(kind==='equity'){
    var ev2=o.ratios&&o.ratios.enterpriseValue;
    var nd=lastFc?(o.bs&&o.bs.netDebt&&o.bs.netDebt[lastFc]):null;
    var debt=lastFc?(o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]):null;
    var cash=lastFc?(o.bs&&o.bs.cash&&o.bs.cash[lastFc]):null;
    var equityVal=o.ratios&&o.ratios.equityValue;
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Equity Value = EV − Net Debt</div>';
    bH+='<div class="uza-sec-desc">Equity Value — рыночная стоимость акционерного капитала. Получается из EV вычитанием чистого долга (Net Debt = Total Debt − Cash).</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
    bH+=_uzaMiniKpi({label:'Enterprise Value',value:fmtN(ev2),sub:'операционные активы',dotColor:'#7F77DD',delay:0});
    bH+=_uzaMiniKpi({label:'Total Debt '+(lastFc||''),value:fmtN(debt),sub:'долгосрочный + краткосрочный',dotColor:'#E24B4A',delay:60});
    bH+=_uzaMiniKpi({label:'Cash '+(lastFc||''),value:fmtN(cash),sub:'денежные средства',dotColor:'#1D9E75',delay:120});
    bH+=_uzaMiniKpi({label:'Equity Value',value:'<span style="color:#534AB7">'+fmtN(equityVal)+'</span>',sub:unitL,dotColor:'#534AB7',delay:180});
    bH+='</div></div>';
    /* Net Debt evolution */
    var ndLabels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var ndData=allY.map(function(y){var v=o.bs&&o.bs.netDebt&&o.bs.netDebt[y];return v!=null?+v.toFixed(0):null;});
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Чистый долг по годам</div>';
    bH+=lineChartHtml({cid:'uza-eq-chart',height:160});
    bH+='</div>';
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert uza-alert-purple"><div class="uza-alert-ttl">Что показывает Equity Value</div>Это «справедливая» стоимость акций при условии, что компания продолжит работу. Используется для расчёта P/E, P/B и других мультипликаторов. Если Equity Value > рыночной капитализации — акции недооценены.</div></div>';
    meta={id:'uza-kpi-equity',title:'Equity Value · '+co,subtitle:'EV − Net Debt разбивка',accent:'#6B8EDE',pill:fmtN(equityVal),pillClass:'uza-pill-blue',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="5.5"/><path d="M7 4v3l2 1.5"/></svg>',
      bodyHtml:bH,
      onMount:function(){renderLineChart('uza-eq-chart',ndLabels,[{label:'Net Debt',data:ndData,color:'#6B8EDE'}],function(v){return fmtN(v);});}};
  }
  
  else if(kind==='npv'){
    var fcY=h.forecastYears||[];
    var pvSum=0,pvDetails=[];
    fcY.forEach(function(y,i){
      var fcff=o.cf&&o.cf.fcff&&o.cf.fcff[y];
      if(fcff!=null){var df=Math.pow(1+wacc,i+1);var pv=fcff/df;pvSum+=pv;pvDetails.push({y:y,fcff:fcff,df:df,pv:pv});}
    });
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">NPV прогнозного периода</div>';
    bH+='<div class="uza-sec-desc">Net Present Value = Σ FCFF<sub>t</sub> / (1+WACC)<sup>t</sup>. Это сумма приведённых к сегодняшнему моменту денежных потоков прогнозного периода (без terminal value).</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr)">';
    bH+=_uzaMiniKpi({label:'NPV прогноза',value:'<span style="color:#0F6E56">'+fmtN(pvSum)+'</span>',sub:fcY.length+' лет дисконт. FCFF',dotColor:'#1D9E75',delay:0});
    bH+=_uzaMiniKpi({label:'WACC',value:(wacc*100).toFixed(2)+'%',sub:'ставка дисконтирования',dotColor:'#7F77DD',delay:60});
    bH+=_uzaMiniKpi({label:'Σ FCFF (без дисконта)',value:fmtN(fcY.reduce(function(s,y){var v=o.cf&&o.cf.fcff&&o.cf.fcff[y];return s+(v||0);},0)),sub:'операционный поток',dotColor:'#888780',delay:120});
    bH+='</div></div>';
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Дисконтирование по годам</div>';
    bH+='<div style="overflow-x:auto"><table class="uza-tbl" style="min-width:540px"><thead><tr><th>Год</th><th>FCFF</th><th>Discount factor</th><th>PV(FCFF)</th><th>Доля NPV</th></tr></thead><tbody>';
    pvDetails.forEach(function(p,i){
      var share=pvSum>0?(p.pv/pvSum*100):0;
      bH+='<tr style="animation:uzaRowIn .35s ease '+(i*30)+'ms both"><td style="color:#854F0B">'+p.y+'</td><td>'+fmtN(p.fcff)+'</td><td style="color:var(--t3)">'+(1/p.df).toFixed(3)+'</td><td style="font-weight:500">'+fmtN(p.pv)+'</td><td style="color:var(--t3)">'+share.toFixed(1)+'%</td></tr>';
    });
    bH+='<tr class="strong"><td colspan="3">Итого</td><td style="color:#0F6E56;font-size:14px">'+fmtN(pvSum)+'</td><td>100%</td></tr>';
    bH+='</tbody></table></div></div>';
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert uza-alert-teal"><div class="uza-alert-ttl">Trade-off "ближе vs дальше"</div>Денежные потоки в первые годы дают больше NPV из-за меньшего discount factor. Поэтому ускорение роста выручки и сокращение CAPEX в первые 1-2 года прогноза приносит больше стоимости акционеру, чем тот же эффект в год '+(fcY[fcY.length-1]||'')+'.</div></div>';
    meta={id:'uza-kpi-npv',title:'NPV прогноза · '+co,subtitle:'дисконтированные FCFF по годам',accent:'#1D9E75',pill:fmtN(pvSum),pillClass:'uza-pill-teal',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12V2M2 12h10M5 9V5M8 9V3M11 9V6"/></svg>',
      bodyHtml:bH};
  }
  
  else if(kind==='fcf'){
    var fcfLast=lastFc?(o.cf&&o.cf.fcf&&o.cf.fcf[lastFc]):null;
    var cfo=lastFc?(o.cf&&o.cf.cfo&&o.cf.cfo[lastFc]):null;
    var cfi=lastFc?(o.cf&&o.cf.cfi&&o.cf.cfi[lastFc]):null;
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Free Cash Flow '+(lastFc||'')+'</div>';
    bH+='<div class="uza-sec-desc">FCF = CFO + CFI = операционный поток − инвестиционный отток. Деньги, доступные акционерам и кредиторам после поддержания операций и инвестиций.</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr)">';
    bH+=_uzaMiniKpi({label:'CFO (операционный)',value:'<span style="color:#0F6E56">'+fmtN(cfo)+'</span>',sub:'денежный поток от операций',dotColor:'#1D9E75',delay:0});
    bH+=_uzaMiniKpi({label:'CFI (инвестиционный)',value:'<span style="color:#854F0B">'+fmtN(cfi)+'</span>',sub:'CAPEX и другие инвестиции',dotColor:'#EF9F27',delay:60});
    bH+=_uzaMiniKpi({label:'Free Cash Flow',value:'<span style="color:'+(fcfLast!=null&&fcfLast>=0?'#0F6E56':'#A32D2D')+'">'+fmtN(fcfLast)+'</span>',sub:unitL,dotColor:fcfLast!=null&&fcfLast>=0?'#1D9E75':'#A32D2D',delay:120});
    bH+='</div></div>';
    /* FCF trend chart */
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var fcfData=allY.map(function(y){var v=o.cf&&o.cf.fcf&&o.cf.fcf[y];return v!=null?+v.toFixed(0):null;});
    var cfoData=allY.map(function(y){var v=o.cf&&o.cf.cfo&&o.cf.cfo[y];return v!=null?+v.toFixed(0):null;});
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Динамика FCF и CFO</div>';
    bH+=lineChartHtml({cid:'uza-fcf-chart',height:180});
    bH+='</div>';
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert uza-alert-purple"><div class="uza-alert-ttl">Качество FCF</div>Если FCF растёт за счёт сокращения CAPEX — это «временный» рост, ведущий к деградации активов. Здоровый FCF — когда CFO растёт быстрее CFI. Сравните оба тренда на графике.</div></div>';
    meta={id:'uza-kpi-fcf',title:'Free Cash Flow · '+co,subtitle:'динамика операционного и инвестиционного потоков',accent:'#378ADD',pill:fmtN(fcfLast),pillClass:'uza-pill-blue',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11l4-4 2 2 4-5"/><path d="M8 4h4v4"/></svg>',
      bodyHtml:bH,
      onMount:function(){renderLineChart('uza-fcf-chart',labels,[
        {label:'CFO',data:cfoData,color:'#1D9E75'},
        {label:'FCF',data:fcfData,color:'#378ADD'}
      ],function(v){return fmtN(v);});}};
  }
  
  else if(kind==='netdebt'){
    var nd=lastFc?(o.bs&&o.bs.netDebt&&o.bs.netDebt[lastFc]):null;
    var debt=lastFc?(o.bs&&o.bs.totalDebt&&o.bs.totalDebt[lastFc]):null;
    var cash=lastFc?(o.bs&&o.bs.cash&&o.bs.cash[lastFc]):null;
    var lt=lastFc?(o.bs&&o.bs.ltDebt&&o.bs.ltDebt[lastFc]):null;
    var st=lastFc?(o.bs&&o.bs.stDebt&&o.bs.stDebt[lastFc]):null;
    var eb=lastFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc]):null;
    var ndE=eb&&eb!==0&&nd!=null?nd/eb:null;
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Net Debt '+(lastFc||'')+' = Total Debt − Cash</div>';
    bH+='<div class="uza-sec-desc">Чистый долг — главная метрика долговой нагрузки. Используется в Net Debt/EBITDA (covenant ≤ 3.0×) и при расчёте Equity Value.</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
    bH+=_uzaMiniKpi({label:'Долгосрочный долг',value:fmtN(lt),sub:'погашение > 12 мес',dotColor:'#534AB7',delay:0});
    bH+=_uzaMiniKpi({label:'Краткосрочный долг',value:fmtN(st),sub:'погашение ≤ 12 мес',dotColor:'#7F77DD',delay:60});
    bH+=_uzaMiniKpi({label:'Cash',value:'<span style="color:#0F6E56">'+fmtN(cash)+'</span>',sub:'денежные средства',dotColor:'#1D9E75',delay:120});
    bH+=_uzaMiniKpi({label:'Net Debt',value:'<span style="color:'+(nd!=null&&nd<=0?'#0F6E56':'#A32D2D')+'">'+fmtN(nd)+'</span>',sub:ndE!=null?'ND/EBITDA '+ndE.toFixed(1)+'×':unitL,dotColor:nd!=null&&nd<=0?'#1D9E75':'#E24B4A',delay:180});
    bH+='</div></div>';
    /* Net Debt evolution */
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var ndData=allY.map(function(y){var v=o.bs&&o.bs.netDebt&&o.bs.netDebt[y];return v!=null?+v.toFixed(0):null;});
    var debtData=allY.map(function(y){var v=o.bs&&o.bs.totalDebt&&o.bs.totalDebt[y];return v!=null?+v.toFixed(0):null;});
    var cashData=allY.map(function(y){var v=o.bs&&o.bs.cash&&o.bs.cash[y];return v!=null?+v.toFixed(0):null;});
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Динамика по годам</div>';
    bH+=lineChartHtml({cid:'uza-nd-chart',height:180});
    bH+='</div>';
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert '+(nd!=null&&nd<=0?'uza-alert-teal':'uza-alert-amber')+'"><div class="uza-alert-ttl">'+(nd!=null&&nd<=0?'Отрицательный Net Debt':'Положительный Net Debt')+'</div>'+(nd!=null&&nd<=0?'Cash превышает долг — компания финансово автономна. Может направить средства на дивиденды, M&A или buyback. Часто бывает у tech и стабильных дивидендных аристократов.':'Стандартная ситуация для капиталоёмкого бизнеса. Контролируйте Net Debt/EBITDA — выход за 3× открывает риски рефинансирования.')+'</div></div>';
    meta={id:'uza-kpi-netdebt',title:'Net Debt · '+co,subtitle:'структура долга и денежной позиции',accent:nd!=null&&nd<=0?'#1D9E75':'#E24B4A',pill:ndE!=null?ndE.toFixed(1)+'× к EBITDA':fmtN(nd),pillClass:nd!=null&&nd<=0?'uza-pill-teal':'uza-pill-red',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="10" height="7" rx="1"/><path d="M5 4V3a2 2 0 1 1 4 0v1"/></svg>',
      bodyHtml:bH,
      onMount:function(){renderLineChart('uza-nd-chart',labels,[
        {label:'Total Debt',data:debtData,color:'#534AB7'},
        {label:'Cash',data:cashData,color:'#1D9E75'},
        {label:'Net Debt',data:ndData,color:'#E24B4A'}
      ],function(v){return fmtN(v);});}};
  }
  
  else if(kind==='revenue'){
    var revLast=lastFc?(o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFc]):null;
    var revFact=lastFact?(o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFact]):null;
    var yrsDiff=(lastFc&&lastFact)?(lastFc-lastFact):0;
    var revCagr=(revFact&&revLast&&yrsDiff>0)?(Math.pow(Math.abs(revLast/revFact),1/yrsDiff)-1):null;
    var totalGrowth=(revFact&&revLast)?((revLast/revFact)-1):null;
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">Выручка '+(lastFc||'')+'</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
    bH+=_uzaMiniKpi({label:'Факт '+(lastFact||''),value:fmtN(revFact),sub:'базовый год',dotColor:'#888780',delay:0});
    bH+=_uzaMiniKpi({label:'Прогноз '+(lastFc||''),value:'<span style="color:#854F0B">'+fmtN(revLast)+'</span>',sub:unitL,dotColor:'#EF9F27',delay:60});
    bH+=_uzaMiniKpi({label:'Рост накопит.',value:totalGrowth!=null?(totalGrowth>=0?'+':'')+(totalGrowth*100).toFixed(0)+'%':'—',sub:'за '+yrsDiff+' лет',dotColor:'#7F77DD',delay:120});
    bH+=_uzaMiniKpi({label:'CAGR',value:revCagr!=null?'<span style="color:'+(revCagr>=0?'#0F6E56':'#A32D2D')+'">'+(revCagr>=0?'+':'')+(revCagr*100).toFixed(1)+'%</span>':'—',sub:'годовой темп',dotColor:revCagr!=null&&revCagr>=0?'#1D9E75':'#E24B4A',delay:180});
    bH+='</div></div>';
    /* Revenue chart */
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var revData=allY.map(function(y){var v=o.pnl&&o.pnl.revenue&&o.pnl.revenue[y];return v!=null?+v.toFixed(0):null;});
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Динамика выручки</div>';
    bH+=lineChartHtml({cid:'uza-rev-chart',height:180});
    bH+='</div>';
    /* Drivers context */
    var drv=model.drivers||{};
    var hasVol=drv.volumes&&drv.volumes.length;
    var hasTar=drv.tariffs&&drv.tariffs.length;
    if(hasVol||hasTar){
      bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-sec-ttl">Драйверы выручки</div>';
      bH+='<div class="uza-alert uza-alert-amber">Выручка декомпозируется через '+(hasVol?(drv.volumes.length+' объёмов'):'')+(hasVol&&hasTar?' × ':'')+(hasTar?(drv.tariffs.length+' тарифов'):'')+'. Изменения объёмов и тарифов формируют прогноз. Открыть редактор драйверов через меню «Изменить модель».</div>';
      bH+='</div>';
    }
    meta={id:'uza-kpi-revenue',title:'Выручка · '+co,subtitle:'факт + прогноз с CAGR',accent:'#EF9F27',pill:revCagr!=null?'CAGR '+(revCagr>=0?'+':'')+(revCagr*100).toFixed(1)+'%':'—',pillClass:'uza-pill-amber',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 13l4-4 3 3 5-7"/><path d="M9 5h4v4"/></svg>',
      bodyHtml:bH,
      onMount:function(){renderLineChart('uza-rev-chart',labels,[
        {label:'Выручка',data:revData,color:'#EF9F27'}
      ],function(v){return fmtN(v);});}};
  }
  
  else if(kind==='ebitdaMargin'){
    var ebMargin=lastFc?(o.ratios&&o.ratios.ebitdaMargin&&o.ratios.ebitdaMargin[lastFc]):null;
    var ebMarginFact=lastFact?(o.ratios&&o.ratios.ebitdaMargin&&o.ratios.ebitdaMargin[lastFact]):null;
    var deltaMargin=ebMargin!=null&&ebMarginFact!=null?ebMargin-ebMarginFact:null;
    var ebFact=lastFact?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFact]):null;
    var ebFc=lastFc?(o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc]):null;
    var yrsDiff=(lastFc&&lastFact)?(lastFc-lastFact):0;
    var ebCagr=(ebFact&&ebFc&&yrsDiff>0)?(Math.pow(Math.abs(ebFc/ebFact),1/yrsDiff)-1):null;
    var bH='';
    bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">EBITDA margin '+(lastFc||'')+'</div>';
    bH+='<div class="uza-sec-desc">EBITDA margin = EBITDA / Выручка. Главный индикатор операционной эффективности — показывает сколько с каждого рубля выручки остаётся до амортизации, налогов и процентов.</div>';
    bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(4,1fr)">';
    bH+=_uzaMiniKpi({label:'Margin '+(lastFact||''),value:fmtPct(ebMarginFact,1),sub:'факт базовый',dotColor:'#888780',delay:0});
    bH+=_uzaMiniKpi({label:'Margin '+(lastFc||''),value:'<span style="color:#534AB7">'+fmtPct(ebMargin,1)+'</span>',sub:'прогноз',dotColor:'#9F6BDD',delay:60});
    bH+=_uzaMiniKpi({label:'Изменение маржи',value:deltaMargin!=null?'<span style="color:'+(deltaMargin>=0?'#0F6E56':'#A32D2D')+'">'+(deltaMargin>=0?'+':'')+(deltaMargin*100).toFixed(1)+' п.п.</span>':'—',sub:'за '+yrsDiff+' лет',dotColor:deltaMargin!=null&&deltaMargin>=0?'#1D9E75':'#E24B4A',delay:120});
    bH+=_uzaMiniKpi({label:'EBITDA CAGR',value:ebCagr!=null?'<span style="color:'+(ebCagr>=0?'#0F6E56':'#A32D2D')+'">'+(ebCagr>=0?'+':'')+(ebCagr*100).toFixed(1)+'%</span>':'—',sub:'годовой темп',dotColor:ebCagr!=null&&ebCagr>=0?'#1D9E75':'#E24B4A',delay:180});
    bH+='</div></div>';
    /* Margin trend */
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var marginData=allY.map(function(y){var v=o.ratios&&o.ratios.ebitdaMargin&&o.ratios.ebitdaMargin[y];return v!=null?+(v*100).toFixed(2):null;});
    bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Динамика маржи</div>';
    bH+=lineChartHtml({cid:'uza-margin-chart',height:180});
    bH+='</div>';
    bH+='<div class="uza-sec" style="--uza-secd:240ms"><div class="uza-alert '+(deltaMargin!=null&&deltaMargin>=0?'uza-alert-teal':'uza-alert-red')+'"><div class="uza-alert-ttl">'+(deltaMargin!=null&&deltaMargin>=0?'Маржа растёт':'Сжатие маржи')+'</div>'+(deltaMargin!=null&&deltaMargin>=0?'Операционная эффективность улучшается — либо за счёт роста цен, либо снижения себестоимости, либо рычага масштаба. Проверьте драйверы тарифов и объёмов.':'Маржа сужается — выручка растёт быстрее EBITDA. Это означает что себестоимость и SG&A растут быстрее цен. Опасный тренд — проверьте структуру затрат и индексацию тарифов.')+'</div></div>';
    meta={id:'uza-kpi-ebmargin',title:'EBITDA margin · '+co,subtitle:'операционная эффективность',accent:'#9F6BDD',pill:fmtPct(ebMargin,1),pillClass:'uza-pill-purple',
      icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="5.5"/><path d="M4 9c1 1 2 1.5 3 1.5s2-.5 3-1.5"/><circle cx="5" cy="6" r=".5" fill="currentColor"/><circle cx="9" cy="6" r=".5" fill="currentColor"/></svg>',
      bodyHtml:bH,
      onMount:function(){renderLineChart('uza-margin-chart',labels,[
        {label:'EBITDA margin',data:marginData,color:'#9F6BDD'}
      ],function(v){return v.toFixed(1)+'%';});}};
  }
  
  if(meta){
    var modal=_uzaOpenModal(meta);
    if(meta.onMount){setTimeout(function(){try{meta.onMount(modal);}catch(e){console.warn(e);}},100);}
  }
}
window._fmKpiDrill=_fmKpiDrill;

/* Working Capital drill — DSO/DIO/DPO/DAP */
function _fmTurnoverDrill(metric){
  var co=window._fmSelCo, scn=window._fmScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn];
  if(!model){if(typeof toast==='function')toast('Модель не загружена');return;}
  var o=model.outputs||{};
  var h=model.horizon||{};
  var allY=[].concat(h.factYears||[],h.forecastYears||[]);
  var factSet={};(h.factYears||[]).forEach(function(y){factSet[y]=true;});
  var lastFact=(h.factYears||[]).slice(-1)[0];
  var wc=(model.drivers&&model.drivers.wc)||{};
  var kr=model.keyRatios||{};
  
  var meta=({
    'dso':{title:'DSO · Дебиторская задолженность',name:'Days Sales Outstanding',altKey:'receivableTurnover',color:'#7F77DD',accent:'#7F77DD',sub:'выручки',baseKey:'revenue',
      desc:'DSO показывает сколько дней в среднем компания ждёт оплаты от покупателей. Чем меньше DSO, тем быстрее оборачивается дебиторка и тем меньше потребность в финансировании оборотного капитала.',
      formula:'DSO = Дебиторская задолженность × 365 / Выручка',
      better:'lower',
      benchmark:'обычно 30-60 дней. >90 дней = риск неплатежей или слабая дисциплина расчётов.'},
    'dio':{title:'DIO · Оборачиваемость запасов',name:'Days Inventory Outstanding',altKey:'inventoryTurnover',color:'#1D9E75',accent:'#1D9E75',sub:'себестоимости',baseKey:'cogs',
      desc:'DIO показывает сколько дней запасы сидят на складе до продажи. Низкий DIO = эффективная логистика, высокий DIO = замороженный капитал в неликвидах.',
      formula:'DIO = Запасы × 365 / Себестоимость',
      better:'lower',
      benchmark:'для retail 30-60 дней, для производства до 120 дней. >180 дней = риск устаревания товара.'},
    'dpo':{title:'DPO · Кредиторская задолженность',name:'Days Payables Outstanding',altKey:'payablesTurnover',color:'#EF9F27',accent:'#EF9F27',sub:'себестоимости',baseKey:'cogs',
      desc:'DPO показывает сколько дней компания «удерживает» оплату поставщикам. Высокий DPO = бесплатное финансирование за счёт поставщиков, но риск ухудшения отношений и потери скидок.',
      formula:'DPO = Кредиторская задолженность × 365 / Себестоимость',
      better:'higher',
      benchmark:'обычно 30-60 дней. >90 дней может сигналить о проблемах с ликвидностью.'},
    'dap':{title:'DAP · Авансы полученные',name:'Days Advances Payable',altKey:null,color:'#378ADD',accent:'#378ADD',sub:'выручки',baseKey:'revenue',
      desc:'DAP показывает сколько дней авансовых платежей от покупателей удерживается компанией. Это «отрицательный» оборотный капитал — клиенты финансируют операции компании.',
      formula:'DAP = Авансы полученные × 365 / Выручка',
      better:'higher',
      benchmark:'характерно для подписочного бизнеса, девелопмента, авиаотрасли. Высокий DAP — признак сильной переговорной позиции.'}
  })[metric];
  if(!meta){if(typeof toast==='function')toast('Метрика не найдена');return;}
  
  function fmtN(v){if(v==null||isNaN(v))return '—';var a=Math.abs(v);if(a>=1e6) return (v/1e6).toLocaleString('ru-RU',{maximumFractionDigits:2})+' трлн';if(a>=1e3) return (v/1e3).toLocaleString('ru-RU',{maximumFractionDigits:1})+' млрд';return v.toLocaleString('ru-RU',{maximumFractionDigits:0})+' млн';}
  
  var days=(meta.altKey&&kr[meta.altKey]!=null)?kr[meta.altKey]:wc[metric];
  var rev=lastFact?(o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFact]):null;
  var cost=lastFact?(o.pnl&&o.pnl.cogs&&o.pnl.cogs[lastFact]):null;
  var base=meta.baseKey==='revenue'?rev:cost;
  var amount=(days!=null&&base)?(base*days/365):null;
  
  var bH='';
  /* Header KPI */
  bH+='<div class="uza-sec" style="--uza-secd:0ms"><div class="uza-sec-ttl">'+meta.name+' '+(lastFact||'')+'</div>';
  bH+='<div class="uza-sec-desc">'+meta.desc+'</div>';
  bH+='<div class="uza-mini-grid" style="grid-template-columns:repeat(3,1fr)">';
  bH+=_uzaMiniKpi({label:'Период оборачиваемости',value:'<span style="color:'+meta.color+'">'+(days!=null?days.toFixed(days<20?2:0):'—')+'</span><span style="font-size:14px;color:var(--t3);margin-left:3px">дн</span>',sub:meta.formula.split('=')[0]+'оборота',dotColor:meta.color,delay:0});
  bH+=_uzaMiniKpi({label:'Сумма '+(lastFact||''),value:fmtN(amount),sub:'≈ ' +(base!=null?(amount/base*100).toFixed(1):'—')+'% от '+meta.sub,dotColor:'#888780',delay:60});
  bH+=_uzaMiniKpi({label:'База расчёта',value:fmtN(base),sub:meta.baseKey==='revenue'?'выручка':'себестоимость',dotColor:'#7F77DD',delay:120});
  bH+='</div></div>';
  
  /* Formula */
  bH+='<div class="uza-sec" style="--uza-secd:120ms"><div class="uza-sec-ttl">Формула расчёта</div>';
  bH+='<div class="uza-alert uza-alert-purple" style="font-family:monospace;font-size:12px;line-height:1.7"><strong style="font-weight:500">'+meta.formula+'</strong>';
  if(days!=null&&amount!=null&&base){
    bH+='<div style="font-family:inherit;margin-top:8px;color:var(--t2);font-size:11.5px">Подстановка для '+(lastFact||'')+': '+fmtN(amount)+' × 365 / '+fmtN(base)+' = '+days.toFixed(2)+' дн</div>';
  }
  bH+='</div>';
  bH+='</div>';
  
  /* Benchmark */
  bH+='<div class="uza-sec" style="--uza-secd:200ms"><div class="uza-sec-ttl">Что считается нормой</div>';
  bH+='<div class="uza-alert uza-alert-'+(meta.better==='lower'?'teal':'amber')+'"><div class="uza-alert-ttl">'+(meta.better==='lower'?'Меньше = лучше':'Больше = лучше')+'</div>'+meta.benchmark+'</div>';
  bH+='</div>';
  
  /* Динамика по годам — берём из drivers или keyRatios */
  var driverYearly=(model.drivers&&model.drivers.wcYearly&&model.drivers.wcYearly[metric])||null;
  if(driverYearly||allY.length){
    var labels=allY.map(function(y){return y+(factSet[y]?'':'П');});
    var data=allY.map(function(y){
      if(driverYearly&&driverYearly[y]!=null)return +driverYearly[y].toFixed(1);
      return days!=null?+days.toFixed(1):null;
    });
    bH+='<div class="uza-sec" style="--uza-secd:280ms"><div class="uza-sec-ttl">Динамика по годам · дни</div>';
    bH+='<div style="position:relative;height:160px"><canvas id="uza-tov-chart"></canvas></div>';
    bH+='<div style="font-size:11px;color:var(--t3);margin-top:10px;line-height:1.55">Если значение неизменно по годам — это означает что в модели используется фиксированный коэффициент оборачиваемости. Для динамической оборачиваемости заполните годовые значения в редакторе драйверов.</div>';
    bH+='</div>';
    /* Render chart */
    setTimeout(function(){
      if(typeof Chart==='undefined') return;
      var canvas=document.getElementById('uza-tov-chart'); if(!canvas) return;
      new Chart(canvas,{
        type:'line',
        data:{labels:labels,datasets:[{label:meta.name,data:data,borderColor:meta.color,backgroundColor:meta.color.replace('#','rgba(').slice(0,-1)+',.10)',borderWidth:2,tension:.3,pointRadius:3.5,pointHoverRadius:5,pointBackgroundColor:meta.color,pointBorderColor:meta.color,pointBorderWidth:2,fill:true,spanGaps:true}]},
        options:{
          responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
          plugins:{
            legend:{display:false},
            tooltip:{backgroundColor:'rgba(15,23,60,.92)',titleFont:{size:11,family:'inherit',weight:'500'},bodyFont:{size:11,family:'inherit'},padding:10,cornerRadius:8,displayColors:true,boxPadding:4,callbacks:{label:function(ctx){return ctx.parsed.y.toFixed(1)+' дн';}}}
          },
          scales:{
            x:{grid:{display:false},ticks:{font:{size:10,family:'inherit'},color:'#94A3B8'},border:{color:'rgba(15,23,60,.08)'}},
            y:{grid:{color:'rgba(15,23,60,.04)',drawTicks:false},ticks:{font:{size:10,family:'inherit'},color:'#94A3B8',padding:6,callback:function(v){return v.toFixed(0)+' дн';}},border:{display:false}}
          },
          animation:{duration:700,easing:'easeOutCubic'}
        }
      });
    },120);
  }
  
  _uzaOpenModal({
    id:'uza-tov-'+metric,
    title:meta.title+' · '+co,
    subtitle:meta.name+' для '+(lastFact||'—')+' года',
    accent:meta.accent,
    pill:days!=null?days.toFixed(days<20?1:0)+' дн':'—',
    pillClass:meta.color==='#7F77DD'?'uza-pill-purple':meta.color==='#1D9E75'?'uza-pill-teal':meta.color==='#EF9F27'?'uza-pill-amber':'uza-pill-blue',
    icon:'<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="5.5"/><path d="M7 3.5v3.5l2.5 1.5"/></svg>',
    bodyHtml:bH
  });
}
window._fmTurnoverDrill=_fmTurnoverDrill;

/* ═══════════════════════════════════════════════════════════════════════════
   FM EDITOR · Stage 1 — Validation, Backup, Overview tab, Beforeunload
   ═══════════════════════════════════════════════════════════════════════════ */

/* Диапазоны валидации для разных типов полей. Используются на input
   для подсветки и при save. tabId.field или tabId/field/year. */
var _FM_VALIDATION={
  /* Допущения (assumptions) */
  taxRate:{min:0,max:0.5,unit:'%',decimals:1,name:'Ставка налога',hint:'Обычно 0–50%'},
  wacc:{min:0.03,max:0.30,unit:'%',decimals:1,name:'WACC',hint:'Разумно 3–30%'},
  dividendPayout:{min:0,max:1,unit:'%',decimals:0,name:'Payout',hint:'0–100%'},
  terminalGrowth:{min:-0.05,max:0.10,unit:'%',decimals:1,name:'g',hint:'Обычно 2–5%'},
  /* WC */
  dso:{min:0,max:365,unit:'дн',decimals:0,name:'DSO',hint:'Реалистично 0–120'},
  dio:{min:0,max:365,unit:'дн',decimals:0,name:'DIO',hint:'Реалистично 0–120'},
  dpo:{min:0,max:365,unit:'дн',decimals:0,name:'DPO',hint:'Реалистично 0–120'},
  dap:{min:0,max:365,unit:'дн',decimals:0,name:'DAP',hint:'Реалистично 0–120'},
  /* Debt */
  interestRate:{min:0,max:0.5,unit:'%',decimals:1,name:'Ставка',hint:'0–50%'},
  /* Цифры по годам — ≥0 для большинства */
  ltDebt:{min:0,max:1e10,unit:'',decimals:0,name:'LT долг',hint:'≥0 в млн сум'},
  stDebt:{min:0,max:1e10,unit:'',decimals:0,name:'ST долг',hint:'≥0 в млн сум'},
  shareCapital:{min:0,max:1e10,unit:'',decimals:0,name:'Уставный',hint:'≥0'},
  openingCash:{min:0,max:1e10,unit:'',decimals:0,name:'Cash на начало',hint:'≥0'},
  openingRE:{min:-1e10,max:1e10,unit:'',decimals:0,name:'RE на начало',hint:''},
  revenueDirect:{min:0,max:1e10,unit:'',decimals:0,name:'Выручка',hint:'≥0 в млн сум'},
  /* По умолчанию для драйверов volumes/tariffs/costs/capex по годам */
  _genericVal:{min:-1e10,max:1e10,unit:'',decimals:2,name:'Значение',hint:''},
  _genericPositive:{min:0,max:1e10,unit:'',decimals:2,name:'Значение',hint:'≥0'}
};
window._FM_VALIDATION=_FM_VALIDATION;

/* Получить правило для поля. Понимает контекст (assumptions, wc, debt, equity, value по годам). */
function _fmGetRule(tabId,field,row){
  var r=_FM_VALIDATION[field];
  if(r) return r;
  /* Yearly value */
  if(tabId==='capex') return _FM_VALIDATION._genericPositive;
  if(tabId==='volumes') return _FM_VALIDATION._genericPositive;
  if(tabId==='tariffs') return _FM_VALIDATION._genericPositive;
  if(tabId==='costs') return _FM_VALIDATION._genericPositive;
  return _FM_VALIDATION._genericVal;
}
window._fmGetRule=_fmGetRule;

/* Validate single input. Returns null if ok, else error message. */
function _fmValidateInput(inp){
  var v=inp.value;
  if(v===''||v==null) return null; /* empty allowed */
  var n=parseFloat(v);
  if(isNaN(n)) return 'не число';
  var tabId=inp.getAttribute('data-fm');
  var field=inp.getAttribute('data-f');
  var year=inp.getAttribute('data-y');
  var r;
  if(tabId==='asm'){
    /* Assumptions: input в процентах, но правила в долях */
    var rr=_FM_VALIDATION[field];
    if(rr){
      var pct=n/100;
      if(pct<rr.min||pct>rr.max) return rr.name+' вне диапазона '+(rr.min*100).toFixed(0)+'–'+(rr.max*100).toFixed(0)+'%';
    }
    return null;
  }
  if(tabId==='wc'){
    var rw=_FM_VALIDATION[field];
    if(rw&&(n<rw.min||n>rw.max)) return rw.name+' вне диапазона '+rw.min+'–'+rw.max;
    return null;
  }
  if(tabId==='debt'&&field==='interestRate'){
    var ri=_FM_VALIDATION.interestRate;
    var pct2=n/100;
    if(pct2<ri.min||pct2>ri.max) return 'Ставка вне 0–50%';
    return null;
  }
  if(tabId==='debt'){
    var rd=_FM_VALIDATION[field];
    if(rd&&(n<rd.min||n>rd.max)) return rd.name+' вне диапазона';
    return null;
  }
  if(tabId==='equity'){
    var re=_FM_VALIDATION[field];
    if(re&&(n<re.min||n>re.max)) return re.name+' вне диапазона';
    return null;
  }
  if(tabId==='revenueDirect'){
    if(n<0) return 'Выручка не может быть отрицательной';
    return null;
  }
  /* Generic yearly values */
  if(year){
    var rg=_fmGetRule(tabId,field);
    if(rg&&(n<rg.min||n>rg.max)) return 'значение вне диапазона';
  }
  return null;
}
window._fmValidateInput=_fmValidateInput;

/* Подсветить инпут красным при ошибке + tooltip. */
function _fmApplyValidationStyle(inp,err){
  if(err){
    inp.style.borderColor='#E24B4A';
    inp.style.background='rgba(226,75,74,.05)';
    inp.title=err;
    inp.setAttribute('data-fm-err','1');
  } else {
    inp.style.borderColor='';
    /* Восстанавливаем исходный фон в зависимости от data-y и factSet */
    var year=inp.getAttribute('data-y');
    var s=window._fmEditor;
    var isF=year&&s&&s.factSet[year];
    inp.style.background=year?(isF?'#fff':'#FFFBF4'):'';
    inp.removeAttribute('title');
    inp.removeAttribute('data-fm-err');
  }
}
window._fmApplyValidationStyle=_fmApplyValidationStyle;

/* Прогон всех инпутов модала, возвращает массив ошибок. */
function _fmValidateAll(){
  var errs=[];
  var modal=document.getElementById('fm-editor-modal');
  if(!modal) return errs;
  modal.querySelectorAll('input[data-fm]').forEach(function(inp){
    if(inp.type==='checkbox') return;
    var e=_fmValidateInput(inp);
    _fmApplyValidationStyle(inp,e);
    if(e){
      var lblNode=inp.closest('tr');
      var rowName='';
      if(lblNode){
        var nameInp=lblNode.querySelector('input[data-f="name"]');
        if(nameInp) rowName=nameInp.value;
      }
      var year=inp.getAttribute('data-y');
      errs.push({tab:inp.getAttribute('data-fm'),field:inp.getAttribute('data-f'),year:year,row:rowName,msg:e});
    }
  });
  return errs;
}
window._fmValidateAll=_fmValidateAll;

/* ── Backup в localStorage ── */
function _fmBackupKey(co,scn){return 'uz_fm_backup_'+(co||'').replace(/\s+/g,'_')+'_'+(scn||'base');}

function _fmBackupSave(){
  var s=window._fmEditor;
  if(!s||!s.co)return;
  try{
    var snapshot={
      co:s.co,scn:s.scn,
      model:s.model,
      tab:window._fmEditorTab,
      ts:Date.now()
    };
    localStorage.setItem(_fmBackupKey(s.co,s.scn),JSON.stringify(snapshot));
  }catch(e){console.warn('[FM backup] save failed',e);}
}
window._fmBackupSave=_fmBackupSave;

function _fmBackupClear(co,scn){
  try{localStorage.removeItem(_fmBackupKey(co,scn));}catch(e){}
}
window._fmBackupClear=_fmBackupClear;

function _fmBackupGet(co,scn){
  try{
    var raw=localStorage.getItem(_fmBackupKey(co,scn));
    if(!raw)return null;
    return JSON.parse(raw);
  }catch(e){return null;}
}
window._fmBackupGet=_fmBackupGet;

/* Очистка старых backup-ов (>7 дней) */
function _fmBackupCleanup(){
  try{
    var now=Date.now();
    var maxAge=7*24*3600*1000;
    var keysToRemove=[];
    for(var i=0;i<localStorage.length;i++){
      var k=localStorage.key(i);
      if(k&&k.indexOf('uz_fm_backup_')===0){
        try{
          var v=JSON.parse(localStorage.getItem(k));
          if(v&&v.ts&&(now-v.ts)>maxAge) keysToRemove.push(k);
        }catch(e){keysToRemove.push(k);}
      }
    }
    keysToRemove.forEach(function(k){localStorage.removeItem(k);});
    if(keysToRemove.length) console.log('[FM backup] cleaned',keysToRemove.length,'old backups');
  }catch(e){}
}
window._fmBackupCleanup=_fmBackupCleanup;

/* Restore из backup. Вызывается из Overview tab. */
function _fmBackupRestore(){
  var s=window._fmEditor;
  if(!s)return;
  var b=_fmBackupGet(s.co,s.scn);
  if(!b||!b.model){
    if(typeof toast==='function') toast('Резервная копия не найдена');
    return;
  }
  if(!confirm('Восстановить модель из резервной копии от '+new Date(b.ts).toLocaleString('ru-RU')+'?\nТекущие несохранённые правки будут потеряны.'))return;
  s.model=b.model;
  _db.finModel=_db.finModel||{};
  _db.finModel[s.co]=_db.finModel[s.co]||{};
  _db.finModel[s.co][s.scn]=b.model;
  /* Закрыть и открыть заново */
  document.getElementById('fm-editor-modal').remove();
  _fmShowEditor();
  if(typeof toast==='function') toast('Восстановлено из резервной копии');
}
window._fmBackupRestore=_fmBackupRestore;

/* ── Beforeunload защита ── */
function _fmBeforeUnloadHandler(e){
  if(window._fmEditorDirty){
    e.preventDefault();
    e.returnValue='Есть несохранённые изменения в финансовой модели. Закрыть страницу?';
    return e.returnValue;
  }
}
window._fmBeforeUnloadHandler=_fmBeforeUnloadHandler;

function _fmAttachBeforeUnload(){
  window.removeEventListener('beforeunload',_fmBeforeUnloadHandler);
  window.addEventListener('beforeunload',_fmBeforeUnloadHandler);
}

function _fmDetachBeforeUnload(){
  window.removeEventListener('beforeunload',_fmBeforeUnloadHandler);
  window._fmEditorDirty=false;
}
window._fmDetachBeforeUnload=_fmDetachBeforeUnload;

/* Помечает модель грязной + бэкап + валидация + индикатор */
function _fmEdMarkDirty(inp){
  window._fmEditorDirty=true;
  _fmAttachBeforeUnload();
  /* Валидация конкретного поля */
  if(inp){
    var e=_fmValidateInput(inp);
    _fmApplyValidationStyle(inp,e);
  }
  /* Дебаунсный backup */
  clearTimeout(window._fmBackupTimer);
  window._fmBackupTimer=setTimeout(function(){
    _fmEdReadInputsToModel(); /* собрать значения в model */
    _fmBackupSave();
    _fmUpdateDirtyBadge();
  },500);
  _fmUpdateDirtyBadge();
  /* Live preview обновление */
  if(typeof _fmScheduleLivePreview==='function') _fmScheduleLivePreview();
  if(typeof _fmRefreshTariffLinkage==='function') _fmRefreshTariffLinkage();
}
window._fmEdMarkDirty=_fmEdMarkDirty;

/* Индикатор непросохранённых изменений в шапке модала */
function _fmUpdateDirtyBadge(){
  var b=document.getElementById('fm-ed-dirty-badge');
  if(!b)return;
  if(window._fmEditorDirty){
    b.style.display='inline-flex';
    var errs=_fmValidateAll();
    if(errs.length){
      b.style.background='#FCEBEB';
      b.style.color='#A32D2D';
      b.innerHTML='<span style="width:6px;height:6px;border-radius:50%;background:#E24B4A;display:inline-block"></span>'+errs.length+' предупреждени'+(errs.length===1?'е':errs.length<5?'я':'й');
    } else {
      b.style.background='#FAEEDA';
      b.style.color='#854F0B';
      b.innerHTML='<span style="width:6px;height:6px;border-radius:50%;background:#EF9F27;display:inline-block"></span>несохранённые правки';
    }
  } else {
    b.style.display='none';
  }
}
window._fmUpdateDirtyBadge=_fmUpdateDirtyBadge;

/* ── Чтение DOM → model (без сохранения в Firebase, для backup) ── */
function _fmEdReadInputsToModel(){
  var s=window._fmEditor;
  if(!s)return;
  var m=s.model;
  document.querySelectorAll('#fm-editor-modal input[data-fm], #fm-editor-modal select[data-fm]').forEach(function(inp){
    var tabId=inp.getAttribute('data-fm');
    var idx=inp.getAttribute('data-i');
    var field=inp.getAttribute('data-f');
    var yr=inp.getAttribute('data-y');
    var val=inp.value;
    var isChk=inp.type==='checkbox';
    if(tabId==='wc'){
      if(!m.drivers.wc)m.drivers.wc={};
      m.drivers.wc[field]=parseFloat(val)||0;
    }else if(tabId==='asm'){
      if(!m.assumptions)m.assumptions={};
      m.assumptions[field]=(parseFloat(val)||0)/100;
    }else if(tabId==='revenueDirect'){
      if(!m.revenueDirect)m.revenueDirect={};
      if(val==='')delete m.revenueDirect[yr];
      else m.revenueDirect[yr]=parseFloat(val)||0;
    }else if(tabId==='debt'){
      if(!m.drivers.debt)m.drivers.debt={ltDebt:{},stDebt:{}};
      if(field==='interestRate'){m.drivers.debt.interestRate=(parseFloat(val)||0)/100;}
      else if(field==='ltDebt'||field==='stDebt'){
        if(!m.drivers.debt[field])m.drivers.debt[field]={};
        if(val==='')delete m.drivers.debt[field][yr];
        else m.drivers.debt[field][yr]=parseFloat(val)||0;
      }
    }else if(tabId==='equity'){
      if(!m.drivers.equity)m.drivers.equity={shareCapital:{}};
      if(field==='openingCash'||field==='openingRE'){
        m.drivers.equity[field]=parseFloat(val)||0;
      }else if(field==='shareCapital'){
        if(!m.drivers.equity.shareCapital)m.drivers.equity.shareCapital={};
        if(val==='')delete m.drivers.equity.shareCapital[yr];
        else m.drivers.equity.shareCapital[yr]=parseFloat(val)||0;
      }
    }else if(idx!==null){
      var list=m.drivers[tabId]; if(!list)return;
      var row=list[parseInt(idx)]; if(!row)return;
      if(yr){
        if(!row.values)row.values={};
        if(val==='')delete row.values[yr];
        else row.values[yr]=parseFloat(val)||0;
      }else if(field){
        if(isChk) row[field]=inp.checked;
        else row[field]=val;
      }
    }
  });
}
window._fmEdReadInputsToModel=_fmEdReadInputsToModel;

/* ── Health checks для Overview tab ── */
function _fmHealthCheck(model){
  var checks=[];
  var fcY=(model.horizon&&model.horizon.forecastYears)||[];
  var factY=(model.horizon&&model.horizon.factYears)||[];
  var d=model.drivers||{};
  /* 1. Выручка */
  var hasRevDirect=model.revenueDirect&&Object.keys(model.revenueDirect).length>0;
  var hasVols=(d.volumes||[]).filter(function(v){return v.values&&Object.keys(v.values).length;}).length>0;
  var hasTariffs=(d.tariffs||[]).filter(function(t){return t.values&&Object.keys(t.values).length;}).length>0;
  if(hasRevDirect){
    checks.push({s:'ok',c:'revenue',t:'Выручка указана напрямую',d:Object.keys(model.revenueDirect).length+' лет заполнено'});
  } else if(hasVols&&hasTariffs){
    var unlinked=(d.tariffs||[]).filter(function(t){return !t.volumeRef;}).length;
    if(unlinked>0){
      checks.push({s:'warn',c:'revenue',t:'Не все тарифы привязаны к объёмам',d:unlinked+' тариф'+(unlinked===1?'':'а')+' без volume reference — выручка не будет считаться'});
    } else {
      checks.push({s:'ok',c:'revenue',t:'Объёмы × Тарифы настроены',d:(d.volumes||[]).length+' объём'+((d.volumes||[]).length===1?'':'ов')+' и '+(d.tariffs||[]).length+' тариф'+((d.tariffs||[]).length===1?'':'ов')});
    }
  } else {
    checks.push({s:'err',c:'revenue',t:'Выручка не настроена',d:'Заполните таб «Выручка» напрямую или настройте Объёмы + Тарифы'});
  }
  /* 2. Затраты */
  var costs=d.costs||[];
  var opCosts=costs.filter(function(c){return c.category==='operating';}).length;
  var sgaCosts=costs.filter(function(c){return c.category==='sga';}).length;
  var daCosts=costs.filter(function(c){return c.isDA;}).length;
  if(costs.length===0){
    checks.push({s:'err',c:'costs',t:'Затраты не указаны',d:'Без затрат EBITDA = Выручка, что нереалистично'});
  } else if(daCosts===0&&((d.capex||[]).length>0)){
    checks.push({s:'warn',c:'costs',t:'Нет амортизации (D&A)',d:'CAPEX есть, но не задана амортизация — PPE будет накапливаться без списания'});
  } else {
    checks.push({s:'ok',c:'costs',t:'Затраты заданы',d:opCosts+' Operating, '+sgaCosts+' SG&A'+(daCosts?', '+daCosts+' D&A':'')});
  }
  /* 3. CAPEX */
  var capex=d.capex||[];
  var capexFilled=capex.filter(function(c){return c.values&&Object.values(c.values).some(function(v){return v>0;});}).length;
  if(capex.length===0){
    checks.push({s:'warn',c:'capex',t:'CAPEX не задан',d:'Без CAPEX компания не растёт — приемлемо только для зрелого бизнеса'});
  } else if(capexFilled===0){
    checks.push({s:'warn',c:'capex',t:'CAPEX строки пустые',d:'Заполните значения по годам'});
  } else {
    checks.push({s:'ok',c:'capex',t:'CAPEX программа задана',d:capex.length+' категори'+(capex.length===1?'я':'й')});
  }
  /* 4. Долг */
  var debt=d.debt||{};
  var ltKeys=Object.keys(debt.ltDebt||{}).length;
  var stKeys=Object.keys(debt.stDebt||{}).length;
  if(ltKeys===0&&stKeys===0){
    checks.push({s:'info',c:'debt',t:'Долга нет',d:'Если у компании есть кредиты, заполните таб «Долг»'});
  } else {
    checks.push({s:'ok',c:'debt',t:'Долг задан',d:ltKeys+' лет LT, '+stKeys+' лет ST · ставка '+((debt.interestRate||0.09)*100).toFixed(1)+'%'});
  }
  /* 5. Equity */
  var eq=d.equity||{};
  var shKeys=Object.keys(eq.shareCapital||{}).length;
  if(shKeys===0){
    checks.push({s:'err',c:'equity',t:'Уставный капитал не задан',d:'Без shareCapital модель посчитает Equity = 0, BS не сойдётся'});
  } else {
    checks.push({s:'ok',c:'equity',t:'Уставный капитал задан',d:shKeys+' лет · openingCash='+(eq.openingCash||0)+' · openingRE='+(eq.openingRE||0)});
  }
  /* 6. WC */
  var wc=d.wc||{};
  if(!wc.dso&&!wc.dio&&!wc.dpo){
    checks.push({s:'warn',c:'wc',t:'Оборотный капитал не задан',d:'Изменение NWC не учтётся в денежном потоке'});
  } else {
    checks.push({s:'ok',c:'wc',t:'Оборачиваемость задана',d:'DSO='+(wc.dso||0)+', DIO='+(wc.dio||0)+', DPO='+(wc.dpo||0)});
  }
  /* 7. Допущения */
  var a=model.assumptions||{};
  if(!a.taxRate||!a.wacc){
    checks.push({s:'warn',c:'assumptions',t:'Допущения не полные',d:'Заполните taxRate и WACC в табе «Допущения»'});
  } else {
    checks.push({s:'ok',c:'assumptions',t:'Допущения заданы',d:'Tax='+(a.taxRate*100).toFixed(0)+'% · WACC='+(a.wacc*100).toFixed(1)+'% · Payout='+((a.dividendPayout||0)*100).toFixed(0)+'%'});
  }
  /* Health score: ok=2, warn=1, info=2, err=0 */
  var maxScore=checks.length*2;
  var score=checks.reduce(function(a,c){return a+(c.s==='ok'||c.s==='info'?2:c.s==='warn'?1:0);},0);
  var pct=Math.round(score/maxScore*100);
  return{checks:checks,score:pct};
}
window._fmHealthCheck=_fmHealthCheck;

/* Render Overview tab */
function _fmEdOverview(m){
  var hc=_fmHealthCheck(m);
  var s=window._fmEditor;
  var backup=_fmBackupGet(s.co,s.scn);
  var hasBackup=backup&&backup.ts;
  var scoreCol=hc.score>=80?'#1D9E75':hc.score>=50?'#EF9F27':'#E24B4A';
  var scoreBg=hc.score>=80?'#E1F5EE':hc.score>=50?'#FAEEDA':'#FCEBEB';
  var h='<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px">';
  /* Health score card */
  h+='<div style="padding:16px 18px;background:'+scoreBg+';border-radius:10px;border-left:3px solid '+scoreCol+'">';
  h+='<div style="font-size:9.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-bottom:4px">Готовность модели</div>';
  h+='<div style="display:flex;align-items:baseline;gap:10px"><span style="font-size:32px;font-weight:500;color:'+scoreCol+';letter-spacing:-.02em">'+hc.score+'</span><span style="font-size:14px;font-weight:500;color:'+scoreCol+'">%</span></div>';
  h+='<div style="font-size:11px;color:var(--t2);margin-top:4px">'+hc.checks.filter(function(c){return c.s==='ok';}).length+' из '+hc.checks.length+' блоков заполнены корректно</div>';
  h+='</div>';
  /* Backup card */
  h+='<div style="padding:16px 18px;background:#F1EFE8;border-radius:10px;border-left:3px solid #888780">';
  h+='<div style="font-size:9.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-bottom:4px">Резервная копия</div>';
  if(hasBackup){
    var ago=Math.round((Date.now()-backup.ts)/60000);
    var agoTxt=ago<1?'только что':ago<60?ago+' мин назад':Math.round(ago/60)+' ч назад';
    h+='<div style="font-size:13px;color:var(--t1);font-weight:500">Сохранена '+agoTxt+'</div>';
    h+='<div style="font-size:11px;color:var(--t2);margin-top:4px">Авто-backup в браузере при каждом изменении</div>';
    h+='<button onclick="_fmBackupRestore()" style="margin-top:10px;padding:5px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:#fff;color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600">↺ Восстановить</button>';
  } else {
    h+='<div style="font-size:13px;color:var(--t2)">Ещё не сохранялась</div>';
    h+='<div style="font-size:11px;color:var(--t3);margin-top:4px">Авто-backup появится при первом изменении</div>';
  }
  h+='</div>';
  h+='</div>';
  /* Checks list */
  h+='<div style="font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-bottom:8px">Проверки целостности</div>';
  h+='<div style="border:1px solid rgba(0,0,0,.06);border-radius:10px;overflow:hidden">';
  hc.checks.forEach(function(c,i){
    var icoCol=c.s==='ok'?'#1D9E75':c.s==='warn'?'#EF9F27':c.s==='err'?'#E24B4A':'#888780';
    var icoBg=c.s==='ok'?'#E1F5EE':c.s==='warn'?'#FAEEDA':c.s==='err'?'#FCEBEB':'#F1EFE8';
    var ico=c.s==='ok'?'<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="'+icoCol+'" stroke-width="2" stroke-linecap="round"><path d="M2.5 6.5L5 9l4.5-5"/></svg>'
      :c.s==='warn'?'<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="'+icoCol+'" stroke-width="2" stroke-linecap="round"><path d="M6 2v5M6 9v.5"/></svg>'
      :c.s==='err'?'<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="'+icoCol+'" stroke-width="2" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg>'
      :'<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="'+icoCol+'" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="6" r="4"/><path d="M6 6v3"/></svg>';
    h+='<div style="display:flex;align-items:flex-start;gap:11px;padding:11px 14px;border-bottom:'+(i<hc.checks.length-1?'0.5px solid rgba(0,0,0,.05)':'none')+';cursor:pointer;transition:background .12s" onclick="window._fmEditorTab=\''+c.c+'\';document.getElementById(\'fm-editor-modal\').remove();_fmShowEditor()" onmouseover="this.style.background=\'rgba(0,0,0,.02)\'" onmouseout="this.style.background=\'\'">';
    h+='<div style="width:22px;height:22px;background:'+icoBg+';border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px">'+ico+'</div>';
    h+='<div style="flex:1;min-width:0">';
    h+='<div style="font-size:12px;color:var(--t1);font-weight:500">'+esc(c.t)+'</div>';
    h+='<div style="font-size:10.5px;color:var(--t3);margin-top:2px;line-height:1.45">'+esc(c.d)+'</div>';
    h+='</div>';
    h+='<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--t3)" stroke-width="1.5" stroke-linecap="round" style="margin-top:4px;opacity:.5"><path d="M5 3l4 4-4 4"/></svg>';
    h+='</div>';
  });
  h+='</div>';
  /* Quick info */
  h+='<div style="margin-top:20px;padding:14px;background:rgba(127,119,221,.04);border-radius:10px;font-size:11px;color:var(--t2);line-height:1.6">';
  h+='<strong style="color:var(--t1)">Как пользоваться:</strong> ';
  h+='Каждый таб отвечает за одну часть модели. Поля автоматически валидируются — некорректные значения подсвечиваются красным. ';
  h+='Изменения сохраняются в локальной копии при каждом редактировании. Чтобы записать в основную базу — нажмите «Сохранить».';
  h+='</div>';
  return h;
}
window._fmEdOverview=_fmEdOverview;


/* ═══════════════════════════════════════════════════════════════════════════
   FM EDITOR · Stage 2 — Inline add/delete, Auto-fill helpers, Toolbar
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Inline add row — без полного перерендера модала ── */
function _fmEdRowAddInline(tabId){
  var s=window._fmEditor; if(!s) return;
  var m=s.model;
  if(!Array.isArray(m.drivers[tabId])) m.drivers[tabId]=[];
  var newId='d'+Date.now()+'_'+Math.floor(Math.random()*1000);
  var newRow={id:newId,name:'',values:{}};
  /* Defaults для специфичных табов */
  if(tabId==='tariffs'){newRow.unit='';newRow.volumeRef='';}
  if(tabId==='volumes'){newRow.unit='';}
  if(tabId==='costs'){newRow.category='operating';newRow.type='Variable';newRow.isDA=false;}
  if(tabId==='capex'){/* nothing extra */}
  m.drivers[tabId].push(newRow);
  /* Найти tbody и вставить новую строку */
  var modal=document.getElementById('fm-editor-modal');
  if(!modal) return;
  var idx=m.drivers[tabId].length-1;
  var rowHtml=_fmEdRenderRow(tabId,newRow,idx,s.years,s.factSet,m);
  /* Если есть placeholder "Строк нет" — убрать */
  var emptyTr=modal.querySelector('tbody tr td[colspan]');
  if(emptyTr) emptyTr.parentElement.remove();
  var tbody=modal.querySelector('table tbody');
  if(tbody){
    tbody.insertAdjacentHTML('beforeend',rowHtml);
    /* Bind input/change на новые поля */
    var newTr=tbody.lastElementChild;
    if(newTr){
      newTr.querySelectorAll('input[data-fm], select[data-fm]').forEach(function(inp){
        var ev=inp.tagName==='SELECT'||inp.type==='checkbox'?'change':'input';
        inp.addEventListener(ev,function(){_fmEdMarkDirty(inp);});
      });
      /* Анимация появления */
      newTr.style.animation='fmdRowIn .3s ease both';
      /* Фокус на name */
      var nameInp=newTr.querySelector('input[data-f="name"]');
      if(nameInp) setTimeout(function(){nameInp.focus();},100);
    }
  }
  window._fmEditorDirty=true;
  _fmAttachBeforeUnload();
  _fmUpdateDirtyBadge();
  if(typeof _fmScheduleLivePreview==='function') _fmScheduleLivePreview();
  if(typeof _fmRefreshTariffLinkage==='function') _fmRefreshTariffLinkage();
}
window._fmEdRowAddInline=_fmEdRowAddInline;

/* ── Inline delete row + reindex ── */
function _fmEdRowDelInline(tabId,idx,btn){
  var s=window._fmEditor; if(!s) return;
  var m=s.model;
  var list=m.drivers[tabId];
  if(!Array.isArray(list)) return;
  var rowName=(list[idx]&&list[idx].name)||'строку';
  if(!confirm('Удалить «'+rowName+'»?')) return;
  list.splice(idx,1);
  /* Удалить tr и переиндексировать */
  var tr=btn.closest('tr');
  if(!tr) return;
  tr.style.animation='fmdRowOut .25s ease both';
  setTimeout(function(){
    if(tr.parentNode) tr.parentNode.removeChild(tr);
    /* reindex data-i во всех оставшихся */
    var modal=document.getElementById('fm-editor-modal');
    if(!modal) return;
    var trs=modal.querySelectorAll('tbody tr[data-fm-row]');
    trs.forEach(function(t,newIdx){
      t.setAttribute('data-fm-row',newIdx);
      t.querySelectorAll('[data-i]').forEach(function(el){el.setAttribute('data-i',newIdx);});
      var delBtn=t.querySelector('button[data-fm-del]');
      if(delBtn) delBtn.setAttribute('onclick','_fmEdRowDelInline(\''+tabId+'\','+newIdx+',this)');
      var afBtns=t.querySelectorAll('button[data-fm-af]');
      afBtns.forEach(function(b){
        var op=b.getAttribute('data-fm-af');
        b.setAttribute('onclick','_fmEdAutoFill(\''+tabId+'\','+newIdx+',\''+op+'\')');
      });
    });
    /* Если список пуст — показать placeholder */
    if(list.length===0){
      var tbody=modal.querySelector('table tbody');
      if(tbody){
        var colsCount=tbody.previousElementSibling.querySelectorAll('th').length;
        tbody.innerHTML='<tr><td colspan="'+colsCount+'" style="padding:24px;text-align:center;color:var(--t3);font-size:11.5px">Строк нет. Нажмите «+ Строка» чтобы добавить.</td></tr>';
      }
    }
  },240);
  window._fmEditorDirty=true;
  _fmAttachBeforeUnload();
  _fmUpdateDirtyBadge();
}
window._fmEdRowDelInline=_fmEdRowDelInline;

/* ── Render одной строки (используется и при initial render, и при inline add) ── */
function _fmEdRenderRow(tabId,d,i,years,factSet,m){
  var h='<tr data-fm-row="'+i+'" style="border-top:0.5px solid rgba(0,0,0,.04)">';
  /* Имя */
  h += '<td style="padding:4px 8px"><input data-fm="'+tabId+'" data-i="'+i+'" data-f="name" value="'+esc(d.name||'')+'" style="width:100%;min-width:140px;padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11.5px;font-family:inherit;outline:none" placeholder="Название"></td>';
  /* Специфичные поля по tabId */
  if(tabId==='tariffs'){
    var vols=(m.drivers.volumes||[]).filter(function(v){return !v.isSub;});
    h += '<td style="padding:4px 8px"><input data-fm="tariffs" data-i="'+i+'" data-f="unit" value="'+esc(d.unit||'')+'" style="width:95px;padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none" placeholder="UZS/unit"></td>';
    h += '<td style="padding:4px 8px"><select data-fm="tariffs" data-i="'+i+'" data-f="volumeRef" style="width:150px;padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none;background:#fff">';
    h += '<option value="">— не привязан —</option>';
    vols.forEach(function(v){var sel=d.volumeRef===v.id?' selected':'';h += '<option value="'+esc(v.id)+'"'+sel+'>'+esc(v.name||'(без имени)')+'</option>';});
    h += '</select></td>';
  } else if(tabId==='volumes'){
    h += '<td style="padding:4px 8px"><input data-fm="volumes" data-i="'+i+'" data-f="unit" value="'+esc(d.unit||'')+'" style="width:120px;padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none" placeholder="Ед. измерения"></td>';
  } else if(tabId==='costs'){
    h += '<td style="padding:4px 8px"><select data-fm="costs" data-i="'+i+'" data-f="category" style="padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none;background:#fff">';
    ['operating','sga'].forEach(function(c){var sel=d.category===c?' selected':'';h += '<option value="'+c+'"'+sel+'>'+(c==='operating'?'Operating':'SG&A')+'</option>';});
    h += '</select></td>';
    h += '<td style="padding:4px 8px"><select data-fm="costs" data-i="'+i+'" data-f="type" style="padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none;background:#fff">';
    ['Fixed','Variable','Semi-variable'].forEach(function(t){var sel=d.type===t?' selected':'';h += '<option value="'+t+'"'+sel+'>'+t+'</option>';});
    h += '</select></td>';
    h += '<td style="padding:4px 8px;text-align:center"><input type="checkbox" data-fm="costs" data-i="'+i+'" data-f="isDA"'+(d.isDA?' checked':'')+' style="cursor:pointer"></td>';
  } else if(tabId==='capex'){
    h += '<td style="padding:4px 8px"><input data-fm="capex" data-i="'+i+'" data-f="unit" value="'+esc(d.unit||'')+'" style="width:120px;padding:4px 7px;border:1px solid rgba(0,0,0,.08);border-radius:5px;font-size:11px;font-family:inherit;outline:none" placeholder="Категория (опц.)"></td>';
  }
  /* Year cells */
  years.forEach(function(y){
    var isF=factSet[y];
    var v=d.values&&d.values[y]!=null?d.values[y]:'';
    h += '<td style="padding:2px 3px"><input type="number" step="any" data-fm="'+tabId+'" data-i="'+i+'" data-y="'+y+'" value="'+v+'" style="width:82px;padding:4px 5px;border:1px solid rgba(0,0,0,.06);border-radius:4px;font-size:11px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\';background:'+(isF?'#fff':'#FFFBF4')+';color:'+(isF?'var(--t1)':'#7A4A00')+'"></td>';
  });
  /* Auto-fill toolbar + delete */
  h += '<td style="padding:4px 6px;white-space:nowrap;display:flex;gap:3px;align-items:center">';
  h += '<button data-fm-af="forward" onclick="_fmEdAutoFill(\''+tabId+'\','+i+',\'forward\')" title="Forward-fill: последний факт во все прогнозы" style="width:24px;height:24px;border:1px solid rgba(0,0,0,.08);background:#fff;border-radius:5px;cursor:pointer;color:#534AB7;display:flex;align-items:center;justify-content:center;font-family:inherit;transition:background .12s" onmouseover="this.style.background=\'rgba(127,119,221,.1)\'" onmouseout="this.style.background=\'#fff\'"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h7M6.5 3l3 3-3 3"/></svg></button>';
  h += '<button data-fm-af="growth" onclick="_fmEdAutoFill(\''+tabId+'\','+i+',\'growth\')" title="Применить рост (% год к году)" style="width:24px;height:24px;border:1px solid rgba(0,0,0,.08);background:#fff;border-radius:5px;cursor:pointer;color:#534AB7;display:flex;align-items:center;justify-content:center;font-family:inherit;font-size:11px;font-weight:700" onmouseover="this.style.background=\'rgba(127,119,221,.1)\'" onmouseout="this.style.background=\'#fff\'">%</button>';
  h += '<button data-fm-af="interpolate" onclick="_fmEdAutoFill(\''+tabId+'\','+i+',\'interpolate\')" title="Линейная интерполяция между первым и последним заполненным" style="width:24px;height:24px;border:1px solid rgba(0,0,0,.08);background:#fff;border-radius:5px;cursor:pointer;color:#534AB7;display:flex;align-items:center;justify-content:center;font-family:inherit;font-size:13px;font-weight:600" onmouseover="this.style.background=\'rgba(127,119,221,.1)\'" onmouseout="this.style.background=\'#fff\'">~</button>';
  h += '<button data-fm-del="1" onclick="_fmEdRowDelInline(\''+tabId+'\','+i+',this)" title="Удалить строку" style="width:24px;height:24px;border:none;background:rgba(226,75,74,.08);border-radius:5px;cursor:pointer;color:#933632;display:flex;align-items:center;justify-content:center;font-family:inherit;margin-left:4px"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg></button>';
  h += '</td></tr>';
  return h;
}
window._fmEdRenderRow=_fmEdRenderRow;

/* ── Auto-fill operations ── */
function _fmEdAutoFill(tabId,idx,op){
  var s=window._fmEditor; if(!s) return;
  var m=s.model;
  var row=m.drivers[tabId]&&m.drivers[tabId][idx];
  if(!row) return;
  var years=s.years, factSet=s.factSet;
  /* Сначала прочитать текущие значения из DOM в row.values */
  var modal=document.getElementById('fm-editor-modal');
  if(!modal) return;
  if(!row.values) row.values={};
  modal.querySelectorAll('input[data-fm="'+tabId+'"][data-i="'+idx+'"][data-y]').forEach(function(inp){
    var y=inp.getAttribute('data-y');
    var v=inp.value;
    if(v==='') delete row.values[y];
    else row.values[y]=parseFloat(v)||0;
  });
  /* Найти последний факт год с значением */
  var factYears=years.filter(function(y){return factSet[y];});
  var fcYears=years.filter(function(y){return !factSet[y];});
  if(op==='forward'){
    /* Найти последний non-null год (любой) */
    var lastY=null;
    for(var i=years.length-1;i>=0;i--){
      if(row.values[years[i]]!=null){lastY=years[i];break;}
    }
    if(lastY==null){
      if(typeof toast==='function') toast('Заполните хотя бы один год чтобы применить forward-fill');
      return;
    }
    var lastV=row.values[lastY];
    /* Заполнить только пустые годы ПОСЛЕ lastY */
    var startIdx=years.indexOf(lastY);
    for(var j=startIdx+1;j<years.length;j++){
      if(row.values[years[j]]==null) row.values[years[j]]=lastV;
    }
  } else if(op==='growth'){
    var pct=prompt('Темп роста год к году, %:','5');
    if(pct==null) return;
    var rate=parseFloat(pct.replace(',','.'))/100;
    if(isNaN(rate)){if(typeof toast==='function') toast('Введите число');return;}
    /* От последнего заполненного года, идти вперёд: каждый следующий = предыдущий × (1+rate) */
    var lastFilled=null;
    for(var k=years.length-1;k>=0;k--){
      if(row.values[years[k]]!=null){lastFilled=k;break;}
    }
    if(lastFilled==null){if(typeof toast==='function') toast('Заполните хотя бы один год');return;}
    var prev=row.values[years[lastFilled]];
    for(var j2=lastFilled+1;j2<years.length;j2++){
      prev=prev*(1+rate);
      row.values[years[j2]]=Math.round(prev*100)/100;
    }
  } else if(op==='interpolate'){
    /* Найти первый и последний заполненный, между ними линейно */
    var firstY=null,firstIdx=-1,lastY2=null,lastIdx=-1;
    for(var i2=0;i2<years.length;i2++){
      if(row.values[years[i2]]!=null){
        if(firstY==null){firstY=years[i2];firstIdx=i2;}
        lastY2=years[i2];lastIdx=i2;
      }
    }
    if(firstIdx<0||lastIdx<=firstIdx){if(typeof toast==='function') toast('Заполните минимум 2 разных года для интерполяции');return;}
    var v1=row.values[firstY], v2=row.values[lastY2];
    var span=lastIdx-firstIdx;
    for(var j3=firstIdx+1;j3<lastIdx;j3++){
      var t=(j3-firstIdx)/span;
      row.values[years[j3]]=Math.round((v1+(v2-v1)*t)*100)/100;
    }
  }
  /* Обновить DOM cells этой строки */
  modal.querySelectorAll('input[data-fm="'+tabId+'"][data-i="'+idx+'"][data-y]').forEach(function(inp){
    var y=inp.getAttribute('data-y');
    var v=row.values[y];
    inp.value=v!=null?v:'';
    /* Анимация заливки */
    inp.style.transition='background .4s ease';
    inp.style.background='rgba(127,119,221,.18)';
    setTimeout(function(){
      inp.style.background=factSet[y]?'#fff':'#FFFBF4';
    },350);
  });
  window._fmEditorDirty=true;
  _fmAttachBeforeUnload();
  _fmUpdateDirtyBadge();
  if(typeof toast==='function') toast(op==='forward'?'Forward-fill применён':op==='growth'?'Темп роста применён':'Интерполяция применена');
}
window._fmEdAutoFill=_fmEdAutoFill;

/* ── Bulk forward-fill all rows ── */
function _fmEdBulkForwardFill(tabId){
  var s=window._fmEditor; if(!s) return;
  var m=s.model;
  var list=m.drivers[tabId];
  if(!Array.isArray(list)||!list.length){if(typeof toast==='function') toast('Нет строк');return;}
  if(!confirm('Применить forward-fill для всех '+list.length+' строк? Последнее заполненное значение каждой строки будет дублировано во все пустые прогнозные годы.'))return;
  list.forEach(function(row,idx){_fmEdAutoFill(tabId,idx,'forward');});
}
window._fmEdBulkForwardFill=_fmEdBulkForwardFill;

/* keyframe для удаления + add row animation */
(function(){
  if(document.getElementById('fm-row-anim-css')) return;
  var s=document.createElement('style');s.id='fm-row-anim-css';
  s.textContent='@keyframes fmdRowOut{0%{opacity:1;transform:translateX(0)}100%{opacity:0;transform:translateX(20px);height:0;padding:0;border:0}}';
  document.head.appendChild(s);
})();


/* ═══════════════════════════════════════════════════════════════════════════
   FM EDITOR · Stage 3 — Live preview, Tariffs↔Volumes linkage
   ═══════════════════════════════════════════════════════════════════════════ */

/* Live preview panel — пересчитывает model "as-you-type" с дебаунсом
   и показывает изменения в EBITDA / Revenue / FCF / NetDebt */
function _fmLivePreviewSnapshot(model){
  /* Возвращает {revenue, ebitda, ebMargin, fcf, netDebt, ndEb} для последнего прогноза */
  var o=model.outputs||{};var h=model.horizon||{};
  var lastFc=(h.forecastYears||[]).slice(-1)[0];
  if(!lastFc) return null;
  var rev=o.pnl&&o.pnl.revenue&&o.pnl.revenue[lastFc];
  var eb=o.pnl&&o.pnl.ebitda&&o.pnl.ebitda[lastFc];
  var ebM=o.ratios&&o.ratios.ebitdaMargin&&o.ratios.ebitdaMargin[lastFc];
  var fcf=o.cf&&o.cf.fcf&&o.cf.fcf[lastFc];
  var nd=o.bs&&o.bs.netDebt&&o.bs.netDebt[lastFc];
  var ndEb=nd!=null&&eb?nd/eb:null;
  var ev=o.ratios&&o.ratios.enterpriseValue;
  return{rev:rev,eb:eb,ebM:ebM,fcf:fcf,nd:nd,ndEb:ndEb,ev:ev,year:lastFc};
}
window._fmLivePreviewSnapshot=_fmLivePreviewSnapshot;

/* Снимок ДО любых правок — для сравнения */
function _fmStashBaselineSnapshot(){
  var s=window._fmEditor; if(!s) return;
  s.baseline=_fmLivePreviewSnapshot(s.model);
}
window._fmStashBaselineSnapshot=_fmStashBaselineSnapshot;

function _fmRenderLivePreview(){
  var s=window._fmEditor; if(!s) return;
  /* Прочитать DOM в model, recompute, snapshot */
  _fmEdReadInputsToModel();
  _fmEnsureAssumptions(s.model);
  try{_fmRecompute(s.model);}catch(e){console.warn('[FM live preview] recompute error',e);}
  var cur=_fmLivePreviewSnapshot(s.model);
  var b=s.baseline||cur;
  var box=document.getElementById('fm-ed-livepreview');
  if(!box) return;
  if(!cur||!cur.year){
    box.innerHTML='<div style="font-size:11px;color:var(--t3);text-align:center;padding:8px">Заполните прогнозные годы для предпросмотра</div>';
    return;
  }
  function diff(curV,baseV){
    if(curV==null||baseV==null||baseV===0) return null;
    return (curV-baseV)/Math.abs(baseV);
  }
  function fmtN(v){
    if(v==null||isNaN(v)) return '—';
    var a=Math.abs(v);
    if(a>=1000000) return (v/1000).toFixed(1)+' трлн';
    if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
    return v.toFixed(0);
  }
  function pct(v){return v==null?'—':((v>0?'+':'')+(v*100).toFixed(1)+'%');}
  function deltaSpan(d){
    if(d==null||Math.abs(d)<0.005) return '<span style="font-size:10px;color:var(--t3)"> →</span>';
    var col=d>0?'#1D9E75':'#A32D2D';
    return '<span style="font-size:10px;color:'+col+';margin-left:4px">'+(d>0?'↑':'↓')+' '+pct(d).replace(/^[+-]/,'')+'</span>';
  }
  var items=[
    {l:'Выручка '+cur.year,v:cur.rev,d:diff(cur.rev,b.rev),accent:'#7F77DD'},
    {l:'EBITDA',v:cur.eb,d:diff(cur.eb,b.eb),accent:'#1D9E75'},
    {l:'EBITDA margin',v:cur.ebM!=null?cur.ebM*100:null,d:diff(cur.ebM,b.ebM),accent:'#1D9E75',pct:true},
    {l:'FCF',v:cur.fcf,d:diff(cur.fcf,b.fcf),accent:'#378ADD'},
    {l:'Net Debt/EBITDA',v:cur.ndEb,d:diff(cur.ndEb,b.ndEb),accent:'#EF9F27',ratio:true,inverseGood:true},
    {l:'EV',v:cur.ev,d:diff(cur.ev,b.ev),accent:'#534AB7'}
  ];
  var html='<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px">';
  items.forEach(function(it){
    var valStr;
    if(it.pct) valStr=it.v!=null?it.v.toFixed(1)+'%':'—';
    else if(it.ratio) valStr=it.v!=null?it.v.toFixed(1)+'×':'—';
    else valStr=fmtN(it.v);
    /* Если inverseGood — стрелка вниз = good */
    var dShow=it.d;
    var dHtml=deltaSpan(dShow);
    if(it.inverseGood&&dShow!=null&&Math.abs(dShow)>=0.005){
      var col=dShow<0?'#1D9E75':'#A32D2D';
      dHtml='<span style="font-size:10px;color:'+col+';margin-left:4px">'+(dShow<0?'↓':'↑')+' '+pct(dShow).replace(/^[+-]/,'')+'</span>';
    }
    html+='<div style="background:#fff;border:1px solid rgba(0,0,0,.06);border-left:3px solid '+it.accent+';border-radius:6px;padding:8px 10px;border-radius:0 6px 6px 0">';
    html+='<div style="font-size:9.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.04em;font-weight:600;margin-bottom:3px">'+it.l+'</div>';
    html+='<div style="font-size:13px;font-weight:600;color:var(--t1);font-feature-settings:\'tnum\'">'+valStr+dHtml+'</div>';
    html+='</div>';
  });
  html+='</div>';
  box.innerHTML=html;
}
window._fmRenderLivePreview=_fmRenderLivePreview;

/* Дебаунсный wrapper — вызывается из _fmEdMarkDirty в Stage 1 после backup */
function _fmScheduleLivePreview(){
  clearTimeout(window._fmLivePreviewTimer);
  window._fmLivePreviewTimer=setTimeout(_fmRenderLivePreview,400);
}
window._fmScheduleLivePreview=_fmScheduleLivePreview;

/* ── Tariffs↔Volumes linkage indicator ──────────────────────
   В табе "Тарифы" — значки рядом с volumeRef select показывают:
   ✓ привязан к существующему объёму
   ! не привязан
   ✗ привязан к удалённому/несуществующему объёму
*/
function _fmRefreshTariffLinkage(){
  var s=window._fmEditor; if(!s||window._fmEditorTab!=='tariffs') return;
  var vols=(s.model.drivers.volumes||[]).map(function(v){return v.id;});
  var modal=document.getElementById('fm-editor-modal');
  if(!modal) return;
  modal.querySelectorAll('select[data-fm="tariffs"][data-f="volumeRef"]').forEach(function(sel){
    var ref=sel.value;
    var indicator=sel.parentElement.querySelector('.fm-link-ind');
    if(!indicator){
      indicator=document.createElement('span');
      indicator.className='fm-link-ind';
      indicator.style.cssText='display:inline-block;width:14px;height:14px;border-radius:50%;margin-left:6px;font-size:9px;font-weight:700;text-align:center;line-height:14px;flex-shrink:0;cursor:help';
      sel.parentElement.style.display='inline-flex';
      sel.parentElement.style.alignItems='center';
      sel.parentElement.appendChild(indicator);
    }
    if(!ref){
      indicator.style.background='#FAEEDA';
      indicator.style.color='#854F0B';
      indicator.textContent='!';
      indicator.title='Тариф не привязан к объёму — выручка не будет считаться';
    } else if(vols.indexOf(ref)<0){
      indicator.style.background='#FCEBEB';
      indicator.style.color='#A32D2D';
      indicator.textContent='✗';
      indicator.title='Привязан к удалённому объёму — исправьте ссылку';
    } else {
      indicator.style.background='#E1F5EE';
      indicator.style.color='#0F6E56';
      indicator.textContent='✓';
      indicator.title='Привязка корректна';
    }
  });
}
window._fmRefreshTariffLinkage=_fmRefreshTariffLinkage;


/* ═══════════════════════════════════════════════════════════════════════════
   FM EDITOR · Stage 4 — Auto-D&A, WACC link, Recovery UI
   ═══════════════════════════════════════════════════════════════════════════ */

/* Auto-D&A: если в costs нет ни одной строки с isDA=true, но есть CAPEX —
   добавить виртуальную строку D&A=сумма CAPEX/10 (straight-line) */
function _fmAutoEnsureDA(model){
  if(!model||!model.drivers) return false;
  var costs=model.drivers.costs||[];
  var hasDA=costs.some(function(c){return c.isDA;});
  if(hasDA) return false;
  var capex=model.drivers.capex||[];
  if(!capex.length) return false;
  var hasCapexValues=capex.some(function(c){return c.values&&Object.values(c.values).some(function(v){return v>0;});});
  if(!hasCapexValues) return false;
  /* Добавить авто-строку */
  var years=[].concat(model.horizon.factYears||[],model.horizon.forecastYears||[]);
  var values={};
  /* Накопительный CAPEX / 10 — простой straight-line. Каждый год добавляет 1/10 от capex предыдущих лет */
  var cumCapex=0;
  years.forEach(function(y){
    var yearCapex=0;
    capex.forEach(function(c){
      if(c.id==='capex_total') return; /* избегаем double-counting */
      var v=c.values&&c.values[y];
      if(v!=null) yearCapex+=Math.abs(v);
    });
    /* Если capex_total есть — берём его */
    var ct=capex.find(function(c){return c.id==='capex_total';});
    if(ct){
      var v=ct.values&&ct.values[y];
      if(v!=null) yearCapex=Math.abs(v);
    }
    cumCapex+=yearCapex;
    values[y]=Math.round(cumCapex/10*100)/100;
  });
  costs.push({
    id:'auto_da',
    name:'Амортизация (авто)',
    category:'operating',
    type:'Fixed',
    isDA:true,
    isAuto:true,
    values:values
  });
  model.drivers.costs=costs;
  return true;
}
window._fmAutoEnsureDA=_fmAutoEnsureDA;

/* Recovery UI — показывает все доступные backup-ы (по компаниям/сценариям).
   Запускается из меню FM или при детектировании orphan backup при init */
function _fmShowRecoveryUI(){
  var keys=[];
  for(var i=0;i<localStorage.length;i++){
    var k=localStorage.key(i);
    if(k&&k.indexOf('uz_fm_backup_')===0) keys.push(k);
  }
  if(!keys.length){
    if(typeof toast==='function') toast('Резервных копий нет');
    return;
  }
  var backups=keys.map(function(k){
    try{
      var v=JSON.parse(localStorage.getItem(k));
      return v?{key:k,co:v.co,scn:v.scn,ts:v.ts,model:v.model}:null;
    }catch(e){return null;}
  }).filter(Boolean).sort(function(a,b){return b.ts-a.ts;});
  /* Modal */
  var ov=document.createElement('div');
  ov.id='fm-recovery-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,18,40,.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:10100;display:flex;align-items:center;justify-content:center;animation:fadeIn .15s';
  ov.onclick=function(e){if(e.target===ov)ov.remove();};
  var box=document.createElement('div');
  box.style.cssText='background:#fff;border-radius:14px;width:min(620px,95vw);max-height:85vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.20);animation:fmCardIn .25s cubic-bezier(.34,1.2,.64,1)';
  var h='<div style="padding:16px 20px;border-bottom:1px solid rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:center">';
  h+='<div><div style="font-size:14px;font-weight:700;color:var(--t1)">Восстановление из резервных копий</div><div style="font-size:11px;color:var(--t3);margin-top:2px">'+backups.length+' резервных копи'+(backups.length===1?'я':'й')+' в локальном хранилище</div></div>';
  h+='<button onclick="document.getElementById(\'fm-recovery-modal\').remove()" style="width:30px;height:30px;border:none;background:rgba(0,0,0,.04);border-radius:8px;cursor:pointer"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"/></svg></button>';
  h+='</div>';
  h+='<div style="flex:1;overflow-y:auto;padding:12px 20px">';
  if(!backups.length){
    h+='<div style="padding:24px;text-align:center;color:var(--t3)">Резервных копий не найдено</div>';
  } else {
    backups.forEach(function(b,idx){
      var ago=Math.round((Date.now()-b.ts)/60000);
      var agoTxt=ago<1?'только что':ago<60?ago+' мин назад':ago<1440?Math.round(ago/60)+' ч назад':Math.round(ago/1440)+' дн назад';
      var scnLabel=b.scn==='base'?'Базовый':b.scn==='opt'?'Оптимистичный':b.scn==='str'?'Стрессовый':b.scn;
      h+='<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;border:1px solid rgba(0,0,0,.06);border-radius:8px;margin-bottom:8px;background:#fff">';
      h+='<div style="flex:1;min-width:0">';
      h+='<div style="font-size:13px;color:var(--t1);font-weight:600">'+esc(b.co||'(без имени)')+' · '+esc(scnLabel)+'</div>';
      h+='<div style="font-size:10.5px;color:var(--t3);margin-top:2px">'+agoTxt+' · '+new Date(b.ts).toLocaleString('ru-RU')+'</div>';
      h+='</div>';
      h+='<button onclick="_fmRecoveryRestore(\''+b.key+'\')" style="padding:6px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:rgba(127,119,221,.08);color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600">↺ Восстановить</button>';
      h+='<button onclick="_fmRecoveryDelete(\''+b.key+'\')" title="Удалить копию" style="width:28px;height:28px;border:none;background:rgba(226,75,74,.08);color:#933632;border-radius:6px;cursor:pointer;font-family:inherit"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg></button>';
      h+='</div>';
    });
  }
  h+='</div>';
  h+='<div style="padding:10px 20px;border-top:1px solid rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:center">';
  h+='<div style="font-size:10.5px;color:var(--t3)">Старые копии (>7 дней) удаляются автоматически</div>';
  h+='<button onclick="if(confirm(\'Удалить все резервные копии?\')){var ks=[];for(var i=0;i&lt;localStorage.length;i++){var k=localStorage.key(i);if(k&amp;&amp;k.indexOf(\'uz_fm_backup_\')===0)ks.push(k);}ks.forEach(function(k){localStorage.removeItem(k);});document.getElementById(\'fm-recovery-modal\').remove();if(typeof toast===\'function\')toast(\'Все копии удалены\');}" style="padding:6px 12px;font-size:11px;border:1px solid rgba(226,75,74,.3);border-radius:6px;background:rgba(226,75,74,.06);color:#933632;cursor:pointer;font-family:inherit">Очистить всё</button>';
  h+='</div>';
  box.innerHTML=h;
  ov.appendChild(box);
  document.body.appendChild(ov);
}
window._fmShowRecoveryUI=_fmShowRecoveryUI;

function _fmRecoveryRestore(key){
  try{
    var b=JSON.parse(localStorage.getItem(key));
    if(!b||!b.model){if(typeof toast==='function')toast('Копия повреждена');return;}
    if(!confirm('Восстановить модель «'+b.co+' · '+b.scn+'» от '+new Date(b.ts).toLocaleString('ru-RU')+'?\nТекущая модель будет перезаписана.'))return;
    _db.finModel=_db.finModel||{};
    _db.finModel[b.co]=_db.finModel[b.co]||{};
    _db.finModel[b.co][b.scn]=b.model;
    /* Persist to firebase */
    if(typeof FB_URL==='function'){
      var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
      fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(_db.finModel)}).catch(function(){});
    }
    var rm=document.getElementById('fm-recovery-modal');if(rm)rm.remove();
    window._fmSelCo=b.co;
    window._fmScenario=b.scn;
    if(typeof _fmRepaint==='function') _fmRepaint();
    if(typeof toast==='function') toast('Восстановлено: '+b.co);
  }catch(e){
    console.error('[FM recovery]',e);
    if(typeof toast==='function') toast('Ошибка восстановления');
  }
}
window._fmRecoveryRestore=_fmRecoveryRestore;

function _fmRecoveryDelete(key){
  if(!confirm('Удалить эту резервную копию?'))return;
  try{localStorage.removeItem(key);}catch(e){}
  document.getElementById('fm-recovery-modal').remove();
  _fmShowRecoveryUI();
}
window._fmRecoveryDelete=_fmRecoveryDelete;

/* ── WACC button в табе Допущения — открывает _fmOpenWACCDrill ── */
function _fmEdRenderWACCLink(){
  /* Эта функция возвращает HTML для блока в табе Assumptions, рекомендующего перейти к WACC editor */
  return '<div style="margin-top:18px;padding:14px 16px;background:rgba(127,119,221,.04);border-left:3px solid #7F77DD;border-radius:0 8px 8px 0;display:flex;align-items:flex-start;gap:12px">'+
    '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#7F77DD" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:1px"><circle cx="10" cy="10" r="7"/><path d="M10 6v4l2.5 1.5"/></svg>'+
    '<div style="flex:1;min-width:0">'+
    '<div style="font-size:12.5px;color:var(--t1);font-weight:600;margin-bottom:3px">WACC рассчитывается из компонентов</div>'+
    '<div style="font-size:10.5px;color:var(--t2);line-height:1.5;margin-bottom:8px">Значение «WACC» выше используется только для прямого override. Для детального расчёта через CAPM (Risk-free rate, β, Market risk premium, Country adjustment, Cost of debt) откройте отдельный редактор WACC.</div>'+
    '<button onclick="_fmEdAttemptClose();setTimeout(function(){_fmOpenWACCDrill();},150)" style="padding:6px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:#fff;color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600">Открыть редактор WACC →</button>'+
    '</div>'+
    '</div>';
}
window._fmEdRenderWACCLink=_fmEdRenderWACCLink;


function _fmReset(){
  if(!window._fmSelCo){
    if(typeof toast==='function') toast('Выберите компанию');
    return;
  }
  if(!confirm('Удалить все данные модели для '+window._fmSelCo+'? Операция необратима.'))return;
  if(_db.finModel&&_db.finModel[window._fmSelCo]){
    delete _db.finModel[window._fmSelCo];
    /* Прямой PUT — гарантированная запись */
    if(typeof fetch==='function'&&typeof FB_URL==='function'){
      var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
      fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(_db.finModel||{})}).catch(function(){});
    }
    window._fmSelCo=null;
    var remaining=Object.keys(_db.finModel||{}).filter(function(k){return k&&k!=='undefined'&&k!=='null';});
    if(remaining.length) window._fmSelCo=remaining[0];
  }
  if(typeof toast==='function') toast('Модель удалена');
  var mc=document.getElementById('main-content');
  if(mc) mc.innerHTML=_fmRenderShell();
  _fmRepaint();
}
window._fmReset=_fmReset;

/* ═══════════════════════════════════════════════════════════════════════════
   ═══  АНАЛИЗ ЧУВСТВИТЕЛЬНОСТИ (Sensitivity Analysis)
   ═══  Tornado chart — показывает как ключевые метрики (NPV, EV, Equity Value)
   ═══  реагируют на ±10%, ±20% изменение ключевых драйверов.
   ═══════════════════════════════════════════════════════════════════════════ */

function _fmShowSensitivity(){
  if(!window._fmSelCo){
    _fmShowCompanyPicker(function(co){
      window._fmSelCo=co;
      setTimeout(_fmShowSensitivity, 100);
    });
    return;
  }
  var co=window._fmSelCo;
  var scenario=window._fmSelScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scenario];
  if(!model||!model.outputs){
    if(typeof toast==='function') toast('Сначала создайте модель');
    return;
  }
  /* Базовая расчёт */
  var baseModel=JSON.parse(JSON.stringify(model));
  _fmRecompute(baseModel);
  var baseNPV=baseModel.outputs.ratios.npv;
  var baseEV=baseModel.outputs.ratios.enterpriseValue;
  var baseEQ=baseModel.outputs.ratios.equityValue;
  
  /* Построим список драйверов для чувствительности */
  window._fmSens={
    baseline: {npv:baseNPV, ev:baseEV, eq:baseEQ},
    target: 'npv', /* что анализируем: npv | ev | eq */
    shocks: [-20,-10,10,20], /* % изменения */
    results: [] /* массив {driver, label, values:[shockResults]} */
  };
  
  _fmSensCompute();
  
  var ov=document.createElement('div');
  ov.id='fm-sens-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,18,40,.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:10002;display:flex;align-items:center;justify-content:center;padding:20px';
  ov.onclick=function(e){if(e.target===ov) ov.remove();};
  var box=document.createElement('div');
  box.id='fm-sens-box';
  box.style.cssText='background:#fff;border-radius:14px;width:min(980px,97vw);max-height:92vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.25);animation:fmCardIn .28s cubic-bezier(.34,1.2,.64,1)';
  box.innerHTML=_fmSensHtml();
  ov.appendChild(box);
  document.body.appendChild(ov);
  setTimeout(_fmSensRenderChart, 50);
}
window._fmShowSensitivity=_fmShowSensitivity;

/* Рассчитываем tornado для каждого драйвера */
function _fmSensCompute(){
  var co=window._fmSelCo;
  var scenario=window._fmSelScenario||'base';
  var model=_db.finModel[co][scenario];
  var shocks=window._fmSens.shocks;
  var drivers=[];
  
  /* Драйвер 1: WACC (ставка дисконтирования) */
  drivers.push({
    id:'wacc', label:'WACC (стоимость капитала)', type:'assumption',
    basePath:['assumptions','wacc'], baseVal:model.assumptions.wacc
  });
  
  /* Драйвер 2: Terminal growth */
  drivers.push({
    id:'tg', label:'Терминальный рост (g)', type:'assumption',
    basePath:['assumptions','terminalGrowth'], baseVal:model.assumptions.terminalGrowth
  });
  
  /* Драйвер 3: Tax rate */
  drivers.push({
    id:'tax', label:'Ставка налога на прибыль', type:'assumption',
    basePath:['assumptions','taxRate'], baseVal:model.assumptions.taxRate
  });
  
  /* Драйверы 4+: Объёмы (volumes) */
  (model.drivers.volumes||[]).filter(function(v){return !v.isSub;}).slice(0,3).forEach(function(v){
    drivers.push({
      id:'vol_'+v.id, label:'Объём: '+v.name, type:'volumes',
      driverId:v.id
    });
  });
  
  /* Драйверы: Тарифы (tariffs) */
  (model.drivers.tariffs||[]).slice(0,3).forEach(function(t){
    drivers.push({
      id:'tar_'+t.id, label:'Тариф: '+t.name, type:'tariffs',
      driverId:t.id
    });
  });
  
  /* Драйверы: Затраты (costs) */
  (model.drivers.costs||[]).slice(0,3).forEach(function(c){
    drivers.push({
      id:'cost_'+c.id, label:'Затраты: '+c.name, type:'costs',
      driverId:c.id
    });
  });
  
  /* CAPEX */
  if((model.drivers.capex||[]).length>0){
    drivers.push({
      id:'capex', label:'CAPEX', type:'capex'
    });
  }
  
  /* Для каждого драйвера считаем shocked values */
  var results=drivers.map(function(d){
    var values=shocks.map(function(shock){
      var cloned=JSON.parse(JSON.stringify(model));
      /* Применяем shock */
      if(d.type==='assumption'){
        cloned.assumptions[d.basePath[1]]=d.baseVal*(1+shock/100);
      } else if(d.type==='volumes'){
        var vol=cloned.drivers.volumes.find(function(x){return x.id===d.driverId;});
        if(vol && vol.values){
          (cloned.horizon.forecastYears||[]).forEach(function(y){
            if(vol.values[y]!=null) vol.values[y]*=(1+shock/100);
          });
        }
      } else if(d.type==='tariffs'){
        var tar=cloned.drivers.tariffs.find(function(x){return x.id===d.driverId;});
        if(tar && tar.values){
          (cloned.horizon.forecastYears||[]).forEach(function(y){
            if(tar.values[y]!=null) tar.values[y]*=(1+shock/100);
          });
        }
      } else if(d.type==='costs'){
        var cst=cloned.drivers.costs.find(function(x){return x.id===d.driverId;});
        if(cst && cst.values){
          (cloned.horizon.forecastYears||[]).forEach(function(y){
            if(cst.values[y]!=null) cst.values[y]*=(1+shock/100);
          });
        }
      } else if(d.type==='capex'){
        (cloned.drivers.capex||[]).forEach(function(cp){
          if(cp.values){
            (cloned.horizon.forecastYears||[]).forEach(function(y){
              if(cp.values[y]!=null) cp.values[y]*=(1+shock/100);
            });
          }
        });
      }
      /* Пересчитываем */
      _fmRecompute(cloned);
      return {
        shock: shock,
        npv: cloned.outputs.ratios.npv,
        ev: cloned.outputs.ratios.enterpriseValue,
        eq: cloned.outputs.ratios.equityValue
      };
    });
    /* Range = max - min по целевой метрике */
    var target=window._fmSens.target;
    var vs=values.map(function(v){return v[target];}).filter(function(x){return x!=null;});
    var range = vs.length ? Math.max.apply(null,vs) - Math.min.apply(null,vs) : 0;
    return {driver:d, values:values, range:range};
  });
  
  /* Сортируем по убыванию range (самые чувствительные сверху) */
  results.sort(function(a,b){return b.range-a.range;});
  window._fmSens.results=results;
}

function _fmSensHtml(){
  var s=window._fmSens;
  var co=window._fmSelCo;
  var tMap={npv:'NPV', ev:'Enterprise Value', eq:'Equity Value'};
  var bMap={npv:s.baseline.npv, ev:s.baseline.ev, eq:s.baseline.eq};
  var baseVal=bMap[s.target];
  var h='';
  /* Header */
  h+='<div style="padding:18px 24px;border-bottom:1px solid rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:flex-start;flex-shrink:0">';
  h+='<div><div style="font-size:15px;font-weight:700;color:var(--t1);display:flex;align-items:center;gap:8px"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#7F77DD" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h12M2 8h8M2 4h4"/><path d="M14 4l-2 2 2 2M10 8l-2 2 2 2M6 12l-2 2 2 2" opacity="0.5"/></svg>Анализ чувствительности</div>';
  h+='<div style="font-size:11.5px;color:var(--t3);margin-top:3px"><strong>'+esc(co)+'</strong> · Tornado analysis · Базовое '+tMap[s.target]+': <strong style="color:var(--t1)">'+_fmFmtBig(baseVal)+'</strong></div></div>';
  h+='<button onclick="document.getElementById(\'fm-sens-modal\').remove()" style="width:28px;height:28px;border-radius:8px;border:none;background:rgba(0,0,0,.04);cursor:pointer;color:var(--t3);display:flex;align-items:center;justify-content:center"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg></button>';
  h+='</div>';
  
  /* Target metric selector */
  h+='<div style="padding:10px 24px;border-bottom:1px solid rgba(0,0,0,.06);background:#FAFAFC;display:flex;gap:8px;align-items:center;flex-shrink:0">';
  h+='<span style="font-size:10.5px;color:var(--t3);letter-spacing:.04em;text-transform:uppercase;font-weight:600">Целевая метрика</span>';
  ['npv','ev','eq'].forEach(function(t){
    h+='<button onclick="_fmSensSetTarget(\''+t+'\')" style="padding:5px 14px;border-radius:6px;font-size:11.5px;border:1px solid '+(s.target===t?'#7F77DD':'rgba(0,0,0,.08)')+';background:'+(s.target===t?'#7F77DD':'#fff')+';color:'+(s.target===t?'#fff':'var(--t2)')+';cursor:pointer;font-weight:600;font-family:inherit;transition:all .15s">'+tMap[t]+'</button>';
  });
  h+='<div style="margin-left:auto;display:flex;gap:4px;align-items:center;font-size:10.5px;color:var(--t3)"><span>Шоки:</span>';
  [-20,-10,10,20].forEach(function(sh){
    var col=sh<0?'#E24B4A':'#1D9E75';
    h+='<span style="padding:2px 7px;background:rgba('+(sh<0?'226,75,74':'29,158,117')+',.1);color:'+col+';border-radius:3px;font-weight:600;font-feature-settings:\'tnum\'">'+(sh>0?'+':'')+sh+'%</span>';
  });
  h+='</div></div>';
  
  /* Body: tornado chart + table */
  h+='<div style="flex:1;overflow-y:auto;padding:14px 24px 18px">';
  h+='<div id="fm-sens-chart" style="margin-bottom:18px"></div>';
  h+='<div id="fm-sens-table"></div>';
  h+='</div>';
  
  /* Footer */
  h+='<div style="padding:12px 24px;border-top:1px solid rgba(0,0,0,.06);display:flex;justify-content:space-between;align-items:center;flex-shrink:0;background:#FAFAFC">';
  h+='<div style="font-size:10.5px;color:var(--t3);line-height:1.5">Метод: Shock ±10%/±20% к каждому драйверу с пересчётом модели. Сортировка по абсолютному влиянию.</div>';
  h+='<button onclick="document.getElementById(\'fm-sens-modal\').remove()" style="padding:7px 20px;border-radius:7px;font-size:12px;border:1px solid rgba(0,0,0,.1);background:#fff;color:var(--t2);cursor:pointer;font-weight:500;font-family:inherit">Закрыть</button>';
  h+='</div>';
  return h;
}

function _fmSensSetTarget(t){
  window._fmSens.target=t;
  /* Пересчитываем ranges для нового target */
  window._fmSens.results.forEach(function(r){
    var vs=r.values.map(function(v){return v[t];}).filter(function(x){return x!=null;});
    r.range = vs.length ? Math.max.apply(null,vs) - Math.min.apply(null,vs) : 0;
  });
  window._fmSens.results.sort(function(a,b){return b.range-a.range;});
  document.getElementById('fm-sens-box').innerHTML=_fmSensHtml();
  setTimeout(_fmSensRenderChart, 50);
}
window._fmSensSetTarget=_fmSensSetTarget;

function _fmSensRenderChart(){
  var wrap=document.getElementById('fm-sens-chart'); if(!wrap) return;
  var s=window._fmSens;
  var target=s.target;
  var base=s.baseline[target];
  if(base==null){
    wrap.innerHTML='<div style="padding:32px;text-align:center;color:var(--t3);font-size:12px">Для этой метрики нет базового значения</div>';
    return;
  }
  var results=s.results;
  if(!results.length){
    wrap.innerHTML='<div style="padding:32px;text-align:center;color:var(--t3);font-size:12px">Нет драйверов для анализа</div>';
    return;
  }
  
  /* Tornado: горизонтальные бары, -20 слева, +20 справа, base посередине */
  var minVal=Infinity, maxVal=-Infinity;
  results.forEach(function(r){
    r.values.forEach(function(v){
      var x=v[target];
      if(x!=null){
        if(x<minVal) minVal=x;
        if(x>maxVal) maxVal=x;
      }
    });
  });
  /* Extend with base */
  if(base<minVal) minVal=base;
  if(base>maxVal) maxVal=base;
  var range=maxVal-minVal;
  if(range===0) range=Math.abs(base)||1;
  /* Padding 5% */
  var pad=range*0.05;
  minVal-=pad; maxVal+=pad;
  range=maxVal-minVal;
  
  var W=640, labelW=200, barH=24, gap=8, paddingL=labelW+10, paddingR=60;
  var chartW=W-paddingL-paddingR;
  var H=results.length*(barH+gap)+50;
  
  function x2px(x){ return paddingL + (x-minVal)/range * chartW; }
  var baseX=x2px(base);
  
  var svg='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" style="display:block;margin:0 auto;background:#FAFAFC;border-radius:8px;padding:8px">';
  /* Background */
  svg+='<rect x="'+paddingL+'" y="20" width="'+chartW+'" height="'+(H-30)+'" fill="#fff" stroke="rgba(0,0,0,.04)"/>';
  /* Vertical base line */
  svg+='<line x1="'+baseX+'" y1="20" x2="'+baseX+'" y2="'+(H-10)+'" stroke="#1E2A4A" stroke-width="1.5" stroke-dasharray="4 3"/>';
  svg+='<text x="'+baseX+'" y="14" text-anchor="middle" font-size="9" font-weight="700" fill="#1E2A4A" font-family="var(--font)">Base</text>';
  
  /* Axis labels (min/max) */
  svg+='<text x="'+paddingL+'" y="'+(H-1)+'" font-size="9" fill="var(--t3)" font-family="var(--font)">'+_fmFmtBig(minVal)+'</text>';
  svg+='<text x="'+(W-paddingR)+'" y="'+(H-1)+'" text-anchor="end" font-size="9" fill="var(--t3)" font-family="var(--font)">'+_fmFmtBig(maxVal)+'</text>';
  
  /* Bars */
  results.forEach(function(r,i){
    var y=25+i*(barH+gap);
    var vs=r.values.map(function(v){return {shock:v.shock, x:v[target]};}).filter(function(v){return v.x!=null;});
    /* Найдём low и high значения */
    var sortedX=vs.map(function(v){return v.x;}).sort(function(a,b){return a-b;});
    var low=sortedX[0]||base, high=sortedX[sortedX.length-1]||base;
    /* Bar: [low .. high] */
    var x1=x2px(low), x2=x2px(high);
    var leftW=baseX-x1, rightW=x2-baseX;
    /* Label */
    svg+='<text x="'+(paddingL-8)+'" y="'+(y+barH/2+3)+'" text-anchor="end" font-size="10.5" fill="var(--t2)" font-family="var(--font)">'+esc(r.driver.label.slice(0,32))+'</text>';
    /* Left half (neg shock — downside) */
    if(leftW>0){
      svg+='<rect x="'+x1+'" y="'+y+'" width="'+leftW+'" height="'+barH+'" fill="#FEE2E2" stroke="#E24B4A" stroke-width="1" rx="3"/>';
      svg+='<text x="'+(x1+4)+'" y="'+(y+barH/2+3)+'" font-size="9" fill="#933632" font-weight="600" font-family="var(--font)">'+_fmFmtBig(low)+'</text>';
    }
    /* Right half (pos shock — upside) */
    if(rightW>0){
      svg+='<rect x="'+baseX+'" y="'+y+'" width="'+rightW+'" height="'+barH+'" fill="#D1FAE5" stroke="#1D9E75" stroke-width="1" rx="3"/>';
      svg+='<text x="'+(x2-4)+'" y="'+(y+barH/2+3)+'" text-anchor="end" font-size="9" fill="#0F6E56" font-weight="600" font-family="var(--font)">'+_fmFmtBig(high)+'</text>';
    }
    /* Range badge справа */
    svg+='<text x="'+(W-paddingR+5)+'" y="'+(y+barH/2+3)+'" font-size="9.5" fill="#7F77DD" font-weight="700" font-family="var(--font)">Δ'+_fmFmtBig(r.range)+'</text>';
  });
  svg+='</svg>';
  
  wrap.innerHTML=svg;
  _fmSensRenderTable();
}

function _fmSensRenderTable(){
  var wrap=document.getElementById('fm-sens-table'); if(!wrap) return;
  var s=window._fmSens;
  var target=s.target;
  var base=s.baseline[target];
  var h='<table style="width:100%;border-collapse:collapse;font-size:11px;font-feature-settings:\'tnum\'">';
  h+='<thead><tr style="border-bottom:1px solid rgba(0,0,0,.08);background:#FAFAFC">';
  h+='<th style="padding:8px 12px;text-align:left;font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.04em;font-weight:600">Драйвер</th>';
  s.shocks.forEach(function(sh){
    var col=sh<0?'#933632':'#0F6E56';
    h+='<th style="padding:8px 10px;text-align:right;font-size:10px;color:'+col+';text-transform:uppercase;letter-spacing:.04em;font-weight:600">'+(sh>0?'+':'')+sh+'%</th>';
  });
  h+='<th style="padding:8px 10px;text-align:right;font-size:10px;color:#7F77DD;text-transform:uppercase;letter-spacing:.04em;font-weight:600">Δ Range</th>';
  h+='</tr></thead><tbody>';
  s.results.forEach(function(r){
    h+='<tr style="border-bottom:0.5px solid rgba(0,0,0,.04)">';
    h+='<td style="padding:6px 12px;color:var(--t2)">'+esc(r.driver.label)+'</td>';
    r.values.forEach(function(v){
      var val=v[target];
      var delta=val!=null&&base!=null?((val-base)/base*100):null;
      var color=delta!=null?(delta>0?'#0F6E56':(delta<0?'#933632':'var(--t2)')):'var(--t3)';
      h+='<td style="padding:6px 10px;text-align:right;color:'+color+';font-weight:'+(Math.abs(delta||0)>5?'600':'400')+'">'+(val!=null?_fmFmtBig(val):'—')+(delta!=null?' <span style="font-size:9px;opacity:.7">('+(delta>0?'+':'')+delta.toFixed(1)+'%)</span>':'')+'</td>';
    });
    h+='<td style="padding:6px 10px;text-align:right;color:#7F77DD;font-weight:700">'+_fmFmtBig(r.range)+'</td>';
    h+='</tr>';
  });
  h+='</tbody></table>';
  wrap.innerHTML=h;
}

/* Helper: formatting больших чисел */
function _fmFmtBig(v){
  if(v==null||isNaN(v)) return '—';
  var a=Math.abs(v);
  if(a>=1e9) return (v/1e9).toFixed(2)+' млрд';
  if(a>=1e6) return (v/1e6).toFixed(2)+' млн';
  if(a>=1000) return Math.round(v).toLocaleString('ru-RU');
  if(a>=10) return v.toFixed(1);
  return v.toFixed(2);
}

/* ═══════════════════════════════════════════════════════════════════════════
   ═══  ЭКСПОРТ PDF ДЛЯ НС (Наблюдательного Совета)
   ═══  Генерирует ОТДЕЛЬНУЮ HTML страницу с данными и вызывает print dialog
   ═══  → пользователь сохраняет как PDF через "Save as PDF"
   ═══════════════════════════════════════════════════════════════════════════ */

function _fmExportPDF(){
  if(!window._fmSelCo){
    _fmShowCompanyPicker(function(co){
      window._fmSelCo=co;
      setTimeout(_fmExportPDF, 100);
    });
    return;
  }
  var co=window._fmSelCo;
  var scenario=window._fmSelScenario||'base';
  var model=_db.finModel&&_db.finModel[co]&&_db.finModel[co][scenario];
  if(!model||!model.outputs){
    if(typeof toast==='function') toast('Сначала создайте модель');
    return;
  }
  
  var win=window.open('','fm-pdf-export','width=900,height=1200');
  if(!win){
    if(typeof toast==='function') toast('Всплывающее окно заблокировано — разрешите popup');
    return;
  }
  
  var html=_fmBuildPdfHtml(co, model, scenario);
  win.document.open();
  win.document.write(html);
  win.document.close();
  /* Даём время на рендеринг SVG и чартов */
  setTimeout(function(){
    try {
      win.focus();
      win.print();
    } catch(e){ console.error(e); }
  }, 600);
}
window._fmExportPDF=_fmExportPDF;

function _fmBuildPdfHtml(co, model, scenario){
  var out=model.outputs;
  var years=[].concat(model.horizon.factYears||[], model.horizon.forecastYears||[]);
  var factYears=model.horizon.factYears||[];
  var lastFc=(model.horizon.forecastYears||[]).slice(-1)[0];
  var firstFc=(model.horizon.forecastYears||[])[0];
  
  function fmt(v,dec){
    if(v==null||isNaN(v)) return '—';
    dec=dec==null?0:dec;
    return v.toLocaleString('ru-RU',{minimumFractionDigits:dec,maximumFractionDigits:dec});
  }
  function pct(v){
    if(v==null||isNaN(v)) return '—';
    return (v*100).toFixed(1)+'%';
  }
  function delta(newVal,oldVal){
    if(newVal==null||oldVal==null||oldVal===0) return '—';
    return (((newVal-oldVal)/Math.abs(oldVal))*100).toFixed(1)+'%';
  }
  
  /* CAGR для выручки и EBITDA */
  function cagr(series,years){
    var vals=years.map(function(y){return series&&series[y];}).filter(function(x){return x!=null&&x>0;});
    if(vals.length<2) return null;
    var first=vals[0], last=vals[vals.length-1];
    var n=vals.length-1;
    return Math.pow(last/first, 1/n)-1;
  }
  var revenueCAGR=cagr(out.pnl.revenue, years);
  var ebitdaCAGR=cagr(out.pnl.ebitda, years);
  
  /* P&L chart SVG */
  function buildChartSVG(){
    var W=760, H=200, pL=45, pR=15, pT=15, pB=35;
    var chartW=W-pL-pR, chartH=H-pT-pB;
    var allRev=years.map(function(y){return out.pnl.revenue&&out.pnl.revenue[y];}).filter(function(x){return x!=null;});
    var allEB=years.map(function(y){return out.pnl.ebitda&&out.pnl.ebitda[y];}).filter(function(x){return x!=null;});
    var maxV=Math.max.apply(null, allRev.concat(allEB));
    var minV=Math.min.apply(null, allRev.concat(allEB).concat([0]));
    if(maxV===minV) maxV=minV+1;
    var barW=chartW/years.length/2.5;
    var s='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" style="display:block;margin:12px auto;font-family:\'Inter\',system-ui,sans-serif">';
    /* Axes */
    s+='<line x1="'+pL+'" y1="'+(H-pB)+'" x2="'+(W-pR)+'" y2="'+(H-pB)+'" stroke="#000" stroke-width="1"/>';
    s+='<line x1="'+pL+'" y1="'+pT+'" x2="'+pL+'" y2="'+(H-pB)+'" stroke="#000" stroke-width="1"/>';
    /* Grid */
    for(var i=0;i<=4;i++){
      var y=pT+chartH*i/4;
      var lbl=minV+(maxV-minV)*(1-i/4);
      s+='<line x1="'+pL+'" y1="'+y+'" x2="'+(W-pR)+'" y2="'+y+'" stroke="#E5E7EB" stroke-width="0.5"/>';
      s+='<text x="'+(pL-4)+'" y="'+(y+3)+'" text-anchor="end" font-size="8" fill="#64748B">'+fmt(lbl/1000,0)+' млрд</text>';
    }
    /* Bars */
    years.forEach(function(y,i){
      var cx=pL+chartW*(i+0.5)/years.length;
      var rev=out.pnl.revenue&&out.pnl.revenue[y];
      var eb=out.pnl.ebitda&&out.pnl.ebitda[y];
      var isFact=factYears.indexOf(y)>=0;
      if(rev!=null){
        var h=Math.max(0,(rev-minV)/(maxV-minV))*chartH;
        s+='<rect x="'+(cx-barW-1)+'" y="'+(pT+chartH-h)+'" width="'+barW+'" height="'+h+'" fill="'+(isFact?'#378ADD':'#93C5FD')+'" rx="2"/>';
      }
      if(eb!=null){
        var h2=Math.max(0,(eb-minV)/(maxV-minV))*chartH;
        s+='<rect x="'+(cx+1)+'" y="'+(pT+chartH-h2)+'" width="'+barW+'" height="'+h2+'" fill="'+(isFact?'#7F77DD':'#C4BFF0')+'" rx="2"/>';
      }
      s+='<text x="'+cx+'" y="'+(H-pB+14)+'" text-anchor="middle" font-size="9" fill="#1E293B"'+(isFact?' font-weight="600"':'')+'>'+y+(isFact?'':' (П)')+'</text>';
    });
    /* Legend */
    s+='<rect x="'+(W-pR-140)+'" y="'+(pT-2)+'" width="8" height="8" fill="#378ADD"/><text x="'+(W-pR-128)+'" y="'+(pT+5)+'" font-size="9" fill="#1E293B">Выручка</text>';
    s+='<rect x="'+(W-pR-70)+'" y="'+(pT-2)+'" width="8" height="8" fill="#7F77DD"/><text x="'+(W-pR-58)+'" y="'+(pT+5)+'" font-size="9" fill="#1E293B">EBITDA</text>';
    s+='</svg>';
    return s;
  }
  
  var today=new Date();
  var dateStr=today.toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'});
  
  var h=''+
  '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">'+
  '<title>Финансовая модель — '+co+' — Бриф для НС</title>'+
  '<style>'+
    '@page { size: A4; margin: 18mm 16mm; }'+
    '* { box-sizing: border-box; -webkit-print-color-adjust: exact !important; color-adjust: exact !important; print-color-adjust: exact !important; }'+
    'html, body { margin: 0; padding: 0; font-family: "Inter","Geist",system-ui,sans-serif; color:#1E293B; font-size: 10pt; line-height: 1.4; background: #fff; }'+
    'body { padding: 0; max-width: 100%; }'+
    'h1 { font-size: 20pt; font-weight: 700; margin: 0 0 4pt; letter-spacing: -0.02em; color: #0F172A; }'+
    'h2 { font-size: 13pt; font-weight: 700; margin: 18pt 0 8pt; color: #1E2A4A; border-bottom: 1.5px solid #7F77DD; padding-bottom: 4pt; }'+
    'h3 { font-size: 11pt; font-weight: 600; margin: 10pt 0 4pt; color: #1E2A4A; }'+
    '.cover { padding: 22mm 0; border-bottom: 1px solid #E2E8F0; page-break-after: always; }'+
    '.cover-logo { font-size: 9pt; color: #64748B; text-transform: uppercase; letter-spacing: .15em; font-weight: 600; }'+
    '.cover-brand { font-size: 28pt; font-weight: 800; letter-spacing: -0.03em; background: linear-gradient(135deg, #7F77DD, #534AB7); -webkit-background-clip: text; background-clip: text; color: transparent; margin: 4mm 0 1mm; }'+
    '.cover-brand-sub { font-size: 11pt; color: #534AB7; font-weight: 500; letter-spacing: .02em; margin: 0 0 8mm; }'+
    '.cover-title { font-size: 26pt; font-weight: 700; color: #0F172A; line-height: 1.1; margin-bottom: 4mm; }'+
    '.cover-sub { font-size: 12pt; color: #475569; margin-bottom: 3mm; }'+
    '.cover-meta { margin-top: 12mm; font-size: 10pt; color: #64748B; }'+
    '.cover-meta strong { color: #1E293B; display: inline-block; min-width: 110pt; }'+
    '.summary-box { background: linear-gradient(135deg, #F8F7FF 0%, #F5F3FF 100%); border: 1px solid #E0DDF5; border-radius: 6pt; padding: 10pt 14pt; margin: 10pt 0; }'+
    '.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; margin: 10pt 0 14pt; }'+
    '.kpi-cell { background: #fff; border: 1px solid #E2E8F0; border-radius: 4pt; padding: 8pt 10pt; position: relative; }'+
    '.kpi-cell::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3pt; background: var(--acc,#7F77DD); border-radius: 4pt 4pt 0 0; }'+
    '.kpi-cell.green { --acc:#1D9E75; }'+
    '.kpi-cell.blue { --acc:#378ADD; }'+
    '.kpi-cell.purple { --acc:#7F77DD; }'+
    '.kpi-cell.amber { --acc:#EF9F27; }'+
    '.kpi-lbl { font-size: 7.5pt; color: #64748B; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; margin-bottom: 2pt; padding-top: 2pt; }'+
    '.kpi-val { font-size: 14pt; font-weight: 700; color: #0F172A; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }'+
    '.kpi-sub { font-size: 8pt; color: #64748B; margin-top: 2pt; }'+
    'table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 9pt; font-variant-numeric: tabular-nums; }'+
    'table th { background: #F8FAFC; font-weight: 600; color: #475569; text-align: left; padding: 6pt 8pt; border-bottom: 1.5px solid #CBD5E1; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .03em; }'+
    'table td { padding: 5pt 8pt; border-bottom: 0.5px solid #E2E8F0; }'+
    'table td.num, table th.num { text-align: right; font-variant-numeric: tabular-nums; }'+
    'table tr.tot { background: #F8FAFC; font-weight: 700; }'+
    'table tr.tot td { border-top: 1px solid #CBD5E1; }'+
    '.badge { display: inline-block; padding: 1pt 5pt; border-radius: 3pt; font-size: 7.5pt; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; vertical-align: middle; }'+
    '.badge.base { background: #EDE9FE; color: #5B21B6; }'+
    '.badge.fact { background: #DBEAFE; color: #1E40AF; }'+
    '.badge.fc { background: #FEF3C7; color: #92400E; }'+
    '.note { font-size: 8.5pt; color: #64748B; line-height: 1.5; padding: 6pt 10pt; background: #F8FAFC; border-left: 2px solid #94A3B8; border-radius: 0 4pt 4pt 0; margin: 6pt 0; }'+
    '.insight { padding: 6pt 10pt; background: #F0FDF4; border-left: 3px solid #1D9E75; border-radius: 0 4pt 4pt 0; margin: 5pt 0; font-size: 9.5pt; }'+
    '.insight.warn { background: #FFFBEB; border-left-color: #EF9F27; }'+
    '.insight.risk { background: #FEF2F2; border-left-color: #E24B4A; }'+
    '.footer { margin-top: 18pt; padding-top: 8pt; border-top: 1px solid #E2E8F0; font-size: 8pt; color: #94A3B8; display: flex; justify-content: space-between; }'+
    '.disclaimer { font-size: 7.5pt; color: #94A3B8; font-style: italic; margin-top: 10pt; padding: 8pt; border: 1px dashed #CBD5E1; border-radius: 4pt; line-height: 1.5; }'+
    '@media print { .no-print { display: none !important; } body { padding: 0; } .page-break { page-break-before: always; } .cover { page-break-after: always; } }'+
  '</style></head><body>';

  /* ═══ COVER PAGE ═══ */
  h+='<div class="cover">'+
    '<div class="cover-logo">UzAssets · Стратегическая группа</div>'+
    '<div class="cover-brand">UzAssets</div>'+
    '<div class="cover-brand-sub">Единая платформа трансформации</div>'+
    '<div style="'+_uzFlagCss('medium')+'width:180pt;margin:2mm 0 0"></div>'+
    '<div style="height:26mm"></div>'+
    '<div class="cover-title">Финансовая модель</div>'+
    '<div class="cover-sub">'+esc(co)+'</div>'+
    '<div style="height:8mm"></div>'+
    '<div style="font-size:12pt;color:#1E2A4A;font-weight:600">Бриф для Наблюдательного Совета</div>'+
    '<div class="cover-meta">'+
      '<div><strong>Компания:</strong> '+esc(co)+'</div>'+
      '<div><strong>Сценарий:</strong> '+(scenario==='base'?'Базовый':esc(scenario))+'</div>'+
      '<div><strong>Горизонт:</strong> '+years[0]+' – '+years[years.length-1]+' ('+(factYears.length)+' фактич. + '+(model.horizon.forecastYears||[]).length+' прогнозных лет)</div>'+
      '<div><strong>WACC:</strong> '+pct(model.assumptions.wacc)+' · <strong>g:</strong> '+pct(model.assumptions.terminalGrowth)+' · <strong>Tax:</strong> '+pct(model.assumptions.taxRate)+'</div>'+
      '<div style="margin-top:8mm"><strong>Дата:</strong> '+dateStr+'</div>'+
    '</div>'+
    '<div class="disclaimer" style="margin-top:12mm">Настоящий документ содержит конфиденциальную финансовую информацию АО «'+esc(co)+'». '+
    'Распространение за пределами Наблюдательного Совета и АО «UzAssets» запрещено. Все прогнозные показатели являются расчётными и подлежат регулярной переоценке.</div>'+
  '</div>';

  /* ═══ EXECUTIVE SUMMARY ═══ */
  h+='<h2>Резюме для совета директоров</h2>';
  h+='<div class="summary-box">';
  h+='<p style="margin:0 0 6pt">На основе driver-based финансовой модели компании <strong>'+esc(co)+'</strong> проведён анализ операционной деятельности '+
    'за '+(factYears[0]||'—')+'–'+(factYears[factYears.length-1]||'—')+' гг. и прогноз на '+(firstFc||'—')+'–'+(lastFc||'—')+' гг. '+
    'Модель построена на DCF-методологии с терминальной стоимостью.</p>';
  
  /* Ключевые выводы */
  var lastFactY=factYears[factYears.length-1];
  var revLastFact=out.pnl.revenue&&out.pnl.revenue[lastFactY];
  var revLastFc=out.pnl.revenue&&out.pnl.revenue[lastFc];
  var revGrowthTotal=(revLastFact&&revLastFc)?((revLastFc/revLastFact-1)*100):null;
  h+='<p style="margin:6pt 0 0"><strong>Ключевые выводы:</strong></p><ul style="margin:4pt 0 0 16pt;padding:0">';
  if(revenueCAGR!=null) h+='<li>Ожидаемый CAGR выручки '+(revenueCAGR*100).toFixed(1)+'% за '+years.length+' лет</li>';
  if(ebitdaCAGR!=null) h+='<li>Ожидаемый CAGR EBITDA '+(ebitdaCAGR*100).toFixed(1)+'% за '+years.length+' лет</li>';
  if(out.ratios.enterpriseValue!=null) h+='<li>Enterprise Value '+fmt(out.ratios.enterpriseValue/1000,1)+' млрд сум (WACC '+pct(model.assumptions.wacc)+')</li>';
  if(out.ratios.equityValue!=null) h+='<li>Equity Value '+fmt(out.ratios.equityValue/1000,1)+' млрд сум</li>';
  h+='</ul></div>';
  
  /* ═══ KPI BLOCKS ═══ */
  h+='<h3>Ключевые показатели (на последний прогнозный год '+lastFc+')</h3>';
  h+='<div class="kpi-grid">';
  h+='<div class="kpi-cell purple"><div class="kpi-lbl">Enterprise Value</div><div class="kpi-val">'+fmt((out.ratios.enterpriseValue||0)/1000,1)+'</div><div class="kpi-sub">млрд сум</div></div>';
  h+='<div class="kpi-cell green"><div class="kpi-lbl">Equity Value</div><div class="kpi-val">'+fmt((out.ratios.equityValue||0)/1000,1)+'</div><div class="kpi-sub">млрд сум</div></div>';
  h+='<div class="kpi-cell blue"><div class="kpi-lbl">NPV (прогноз)</div><div class="kpi-val">'+fmt((out.ratios.npv||0)/1000,1)+'</div><div class="kpi-sub">млрд сум</div></div>';
  h+='<div class="kpi-cell amber"><div class="kpi-lbl">EBITDA '+lastFc+'</div><div class="kpi-val">'+fmt((out.pnl.ebitda&&out.pnl.ebitda[lastFc]||0)/1000,1)+'</div><div class="kpi-sub">млрд сум</div></div>';
  h+='</div>';
  
  /* ═══ P&L CHART ═══ */
  h+='<h2>Выручка и EBITDA по годам</h2>';
  h+=buildChartSVG();
  
  /* ═══ P&L TABLE ═══ */
  h+='<h2>Отчёт о прибылях и убытках (P&L)</h2>';
  h+='<table><thead><tr><th>Показатель, млрд сум</th>';
  years.forEach(function(y){
    var isF=factYears.indexOf(y)>=0;
    h+='<th class="num">'+y+' '+(isF?'<span class="badge fact">факт</span>':'<span class="badge fc">прогноз</span>')+'</th>';
  });
  h+='</tr></thead><tbody>';
  var pnlRows=[
    {key:'revenue',label:'Выручка',bold:true},
    {key:'cogs',label:'Себестоимость',negate:true},
    {key:'grossProfit',label:'Валовая прибыль',bold:true,isTot:true},
    {key:'sga',label:'SG&A',negate:true},
    {key:'depreciation',label:'Амортизация',negate:true,muted:true},
    {key:'opProfit',label:'Операционная прибыль',bold:true,isTot:true},
    {key:'ebitda',label:'EBITDA',bold:true,highlight:true},
    {key:'finCost',label:'Финансовые расходы',negate:true},
    {key:'pbt',label:'Прибыль до налога',bold:true,isTot:true},
    {key:'tax',label:'Налог на прибыль',negate:true},
    {key:'netIncome',label:'Чистая прибыль',bold:true,isTot:true}
  ];
  pnlRows.forEach(function(r){
    var rowCls=r.isTot?'tot':'';
    h+='<tr'+(rowCls?' class="'+rowCls+'"':'')+'>';
    h+='<td'+(r.bold?' style="font-weight:600"':'')+(r.muted?' style="color:#64748B"':'')+(r.highlight?' style="color:#7F77DD;font-weight:700"':'')+'>'+esc(r.label)+'</td>';
    years.forEach(function(y){
      var v=out.pnl[r.key]&&out.pnl[r.key][y];
      var displayV=v;
      if(r.negate&&v!=null) displayV=-Math.abs(v);
      h+='<td class="num"'+(r.highlight?' style="color:#7F77DD;font-weight:700"':'')+'>'+fmt((displayV||0)/1000,1)+'</td>';
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  
  /* ═══ RATIOS ═══ */
  h+='<h3>Ключевые коэффициенты</h3>';
  h+='<table><thead><tr><th>Коэффициент</th>';
  years.forEach(function(y){ h+='<th class="num">'+y+'</th>'; });
  h+='</tr></thead><tbody>';
  [
    {key:'grossMargin',label:'Валовая маржа'},
    {key:'ebitdaMargin',label:'EBITDA маржа'},
    {key:'netMargin',label:'Чистая маржа'},
    {key:'roe',label:'ROE'},
    {key:'netDebtEbitda',label:'Net Debt / EBITDA'}
  ].forEach(function(r){
    h+='<tr><td>'+esc(r.label)+'</td>';
    years.forEach(function(y){
      var v=out.ratios[r.key]&&out.ratios[r.key][y];
      h+='<td class="num">'+(r.key==='netDebtEbitda'?(v!=null?v.toFixed(1)+'x':'—'):pct(v))+'</td>';
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  
  /* ═══ CASH FLOW ═══ */
  h+='<div class="page-break"></div>';
  h+='<h2>Денежный поток (Cash Flow)</h2>';
  h+='<table><thead><tr><th>Показатель, млрд сум</th>';
  years.forEach(function(y){ h+='<th class="num">'+y+'</th>'; });
  h+='</tr></thead><tbody>';
  [
    {key:'cfo',label:'Операционный CF'},
    {key:'cfi',label:'Инвестиционный CF'},
    {key:'cff',label:'Финансовый CF'},
    {key:'fcf',label:'Free Cash Flow',bold:true},
    {key:'fcff',label:'FCFF (для DCF)',bold:true,highlight:true}
  ].forEach(function(r){
    h+='<tr>';
    h+='<td'+(r.bold?' style="font-weight:600"':'')+(r.highlight?' style="color:#7F77DD"':'')+'>'+esc(r.label)+'</td>';
    years.forEach(function(y){
      var v=out.cf[r.key]&&out.cf[r.key][y];
      h+='<td class="num"'+(r.highlight?' style="color:#7F77DD;font-weight:700"':'')+'>'+fmt((v||0)/1000,1)+'</td>';
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  
  /* ═══ BALANCE SHEET ═══ */
  h+='<h2>Баланс (ключевые показатели)</h2>';
  h+='<table><thead><tr><th>Показатель, млрд сум</th>';
  years.forEach(function(y){ h+='<th class="num">'+y+'</th>'; });
  h+='</tr></thead><tbody>';
  [
    {key:'ppe',label:'Основные средства (PPE)'},
    {key:'cash',label:'Денежные средства'},
    {key:'totalDebt',label:'Общий долг'},
    {key:'netDebt',label:'Чистый долг',bold:true},
    {key:'equity',label:'Собственный капитал',bold:true}
  ].forEach(function(r){
    h+='<tr>';
    h+='<td'+(r.bold?' style="font-weight:600"':'')+'>'+esc(r.label)+'</td>';
    years.forEach(function(y){
      var v=out.bs[r.key]&&out.bs[r.key][y];
      h+='<td class="num">'+fmt((v||0)/1000,1)+'</td>';
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  
  /* ═══ VALUATION ═══ */
  h+='<h2>DCF-оценка</h2>';
  h+='<div class="summary-box">';
  h+='<table style="margin:0">';
  h+='<tr><td style="border:none;padding:4pt 8pt"><strong>Сумма PV(FCFF) прогнозных лет:</strong></td><td style="border:none;padding:4pt 8pt;text-align:right;font-weight:700">'+fmt((out.ratios.npv||0)/1000,2)+' млрд сум</td></tr>';
  var tv=(out.ratios.enterpriseValue-out.ratios.npv)||0;
  h+='<tr><td style="border:none;padding:4pt 8pt"><strong>+ PV(Terminal Value):</strong></td><td style="border:none;padding:4pt 8pt;text-align:right;font-weight:700">'+fmt(tv/1000,2)+' млрд сум</td></tr>';
  h+='<tr style="border-top:1px solid #CBD5E1"><td style="border:none;padding:4pt 8pt"><strong>= Enterprise Value:</strong></td><td style="border:none;padding:4pt 8pt;text-align:right;font-weight:700;color:#7F77DD">'+fmt((out.ratios.enterpriseValue||0)/1000,2)+' млрд сум</td></tr>';
  h+='<tr><td style="border:none;padding:4pt 8pt"><strong>− Чистый долг ('+lastFc+'):</strong></td><td style="border:none;padding:4pt 8pt;text-align:right">'+fmt((out.bs.netDebt&&out.bs.netDebt[lastFc]||0)/1000,2)+' млрд сум</td></tr>';
  h+='<tr style="border-top:2px solid #1E2A4A"><td style="border:none;padding:6pt 8pt"><strong style="font-size:11pt">= Equity Value:</strong></td><td style="border:none;padding:6pt 8pt;text-align:right;font-weight:700;font-size:13pt;color:#1D9E75">'+fmt((out.ratios.equityValue||0)/1000,2)+' млрд сум</td></tr>';
  h+='</table></div>';
  
  h+='<div class="note"><strong>Методология:</strong> Оценка выполнена по методу дисконтированных денежных потоков (DCF) на основе свободного денежного потока FCFF. '+
    'Использованные параметры: WACC = '+pct(model.assumptions.wacc)+', терминальный рост (g) = '+pct(model.assumptions.terminalGrowth)+', ставка налога = '+pct(model.assumptions.taxRate)+'. '+
    'Терминальная стоимость рассчитана по модели Гордона: TV = FCFF('+lastFc+') × (1+g) / (WACC − g).</div>';
  
  /* ═══ INSIGHTS ═══ */
  h+='<h2>Аналитические инсайты</h2>';
  /* Автоматические инсайты */
  var insights=[];
  if(revenueCAGR!=null && revenueCAGR>0.10){
    insights.push({type:'insight', text:'Прогнозируется устойчивый рост выручки CAGR '+(revenueCAGR*100).toFixed(1)+'% — выше инфляции, что свидетельствует о расширении операций в реальном выражении.'});
  } else if(revenueCAGR!=null && revenueCAGR<0){
    insights.push({type:'risk', text:'Отрицательный CAGR выручки '+(revenueCAGR*100).toFixed(1)+'% — требует пересмотра стратегии продаж и/или ценовой политики.'});
  }
  var ebLast=out.pnl.ebitda&&out.pnl.ebitda[lastFc];
  var revLast=out.pnl.revenue&&out.pnl.revenue[lastFc];
  var ebMargin=(ebLast&&revLast)?(ebLast/revLast):null;
  if(ebMargin!=null){
    if(ebMargin>0.25) insights.push({type:'insight', text:'Целевая EBITDA маржа '+(ebMargin*100).toFixed(1)+'% — сильная операционная эффективность, превосходит большинство аналогов.'});
    else if(ebMargin<0.10) insights.push({type:'warn', text:'EBITDA маржа прогнозируется на уровне '+(ebMargin*100).toFixed(1)+'% — низкая операционная рентабельность. Необходим анализ затратной базы.'});
  }
  var ndLast=out.bs.netDebt&&out.bs.netDebt[lastFc];
  if(ndLast!=null && ebLast!=null && ebLast>0){
    var ndEb=ndLast/ebLast;
    if(ndEb>4) insights.push({type:'risk', text:'Коэффициент Net Debt / EBITDA = '+ndEb.toFixed(1)+'x к '+lastFc+' — высокая долговая нагрузка, риск нарушения ковенант.'});
    else if(ndEb<2) insights.push({type:'insight', text:'Коэффициент Net Debt / EBITDA = '+ndEb.toFixed(1)+'x — комфортный уровень долговой нагрузки.'});
  }
  if(out.ratios.equityValue!=null && out.ratios.equityValue<0){
    insights.push({type:'risk', text:'Equity Value отрицательный — стоимость акционерного капитала не покрывается ожидаемыми денежными потоками при текущих допущениях.'});
  }
  if(!insights.length){
    insights.push({type:'insight', text:'Модель показывает стабильную финансовую динамику в пределах заданных допущений. Рекомендуется ежеквартальный мониторинг ключевых драйверов.'});
  }
  insights.forEach(function(ins){
    h+='<div class="insight '+(ins.type==='warn'?'warn':(ins.type==='risk'?'risk':''))+'">'+esc(ins.text)+'</div>';
  });
  
  /* ═══ RECOMMENDATIONS ═══ */
  h+='<h2>Рекомендации для Наблюдательного Совета</h2>';
  h+='<ol style="margin:0;padding-left:20pt;line-height:1.6">';
  h+='<li><strong>Утвердить</strong> финансовую модель компании как инструмент стратегического планирования на период '+years[0]+'–'+years[years.length-1]+' гг.</li>';
  h+='<li><strong>Ежеквартально пересматривать</strong> ключевые драйверы модели: объёмы, тарифы, CAPEX — с корректировкой прогноза.</li>';
  h+='<li><strong>Провести анализ чувствительности</strong> Enterprise Value к изменению ставки дисконтирования (WACC ±1п.п.) и темпа терминального роста.</li>';
  h+='<li><strong>Сравнить</strong> ключевые коэффициенты (EBITDA маржа, Net Debt/EBITDA, ROE) с отраслевыми бенчмарками.</li>';
  h+='<li><strong>Рассмотреть</strong> стресс-сценарий при снижении выручки на 15–20% для оценки устойчивости бизнес-модели.</li>';
  h+='</ol>';
  
  /* Footer */
  h+='<div style="'+_uzFlagCss('thin')+'margin-top:14pt;margin-bottom:4pt"></div>';
  h+='<div class="footer"><span>UzAssets · Единая платформа трансформации · Финансовая модель · '+esc(co)+'</span><span>'+dateStr+'</span></div>';
  
  h+='<div class="no-print" style="position:fixed;top:12pt;right:12pt;display:flex;gap:8pt;z-index:9999">';
  h+='<button onclick="window.print()" style="padding:8pt 16pt;background:#7F77DD;color:#fff;border:none;border-radius:6pt;font-size:10pt;cursor:pointer;font-weight:600;box-shadow:0 2pt 8pt rgba(127,119,221,.3);font-family:inherit">Печать / Сохранить PDF</button>';
  h+='<button onclick="window.close()" style="padding:8pt 12pt;background:#fff;color:#64748B;border:1px solid #CBD5E1;border-radius:6pt;font-size:10pt;cursor:pointer;font-family:inherit">Закрыть</button>';
  h+='</div>';
  
  h+='</body></html>';
  return h;
}

/* ── Editor (Driver-based, E2) ──────────────────────────────────────────── */
function _fmShowEditor(){
  if(!window._fmSelCo){
    _fmShowCompanyPicker(function(co){
      window._fmSelCo=co;
      var mc=document.getElementById('main-content');
      if(mc) mc.innerHTML=_fmRenderShell();
      _fmRepaint();
      setTimeout(_fmShowEditor, 100);
    },'Создание модели','Выберите компанию для которой хотите создать финансовую модель');
    return;
  }
  var co=window._fmSelCo;
  var scn=window._fmScenario||'base';
  var model=_fmGetOrCreate(co,scn);
  var years=[].concat(model.horizon.factYears||[], model.horizon.forecastYears||[]);
  var factSet={};(model.horizon.factYears||[]).forEach(function(y){factSet[y]=1;});
  window._fmEditor={model:model,co:co,scn:scn,years:years,factSet:factSet,tab:window._fmEditorTab||'overview'};
  var ov=document.createElement('div');
  ov.id='fm-editor-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,18,40,.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:10000;display:flex;align-items:center;justify-content:center;animation:fadeIn .15s';
  ov.addEventListener('click',function(e){if(e.target===ov)ov.remove();});
  var box=document.createElement('div');
  box.style.cssText='background:#fff;border-radius:14px;width:min(1100px,95vw);max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.20);animation:fmCardIn .25s cubic-bezier(.34,1.2,.64,1)';
  box.innerHTML=_fmEditorHtml();
  ov.appendChild(box);
  document.body.appendChild(ov);
  /* Stage 1: cleanup, validation, binding */
  _fmBackupCleanup();
  window._fmEditorDirty=false;
  setTimeout(function(){
    var modal=document.getElementById('fm-editor-modal');
    if(!modal)return;
    modal.querySelectorAll('input[data-fm], select[data-fm]').forEach(function(inp){
      var ev=inp.tagName==='SELECT'||inp.type==='checkbox'?'change':'input';
      inp.addEventListener(ev,function(){_fmEdMarkDirty(inp);});
      if(inp.type!=='checkbox'){
        var e=_fmValidateInput(inp);
        _fmApplyValidationStyle(inp,e);
      }
    });
    _fmUpdateDirtyBadge();
    _fmStashBaselineSnapshot();
    _fmRenderLivePreview();
    _fmRefreshTariffLinkage();
    var origCloseBtn=modal.querySelector('button[onclick*="fm-editor-modal"]');
    if(origCloseBtn){
      origCloseBtn.onclick=function(){_fmEdAttemptClose();};
    }
    var ovEl=document.getElementById('fm-editor-modal');
    if(ovEl) ovEl.onclick=function(e){if(e.target===ovEl)_fmEdAttemptClose();};
  },50);
}
window._fmShowEditor=_fmShowEditor;

function _fmEdAttemptClose(){
  if(window._fmEditorDirty){
    var errs=_fmValidateAll();
    var msg='Есть несохранённые изменения';
    if(errs.length) msg+=' и '+errs.length+' предупреждени'+(errs.length===1?'е':errs.length<5?'я':'й');
    msg+='. Закрыть без сохранения?';
    if(!confirm(msg))return;
  }
  _fmDetachBeforeUnload();
  var ov=document.getElementById('fm-editor-modal');
  if(ov)ov.remove();
}
window._fmEdAttemptClose=_fmEdAttemptClose;

function _fmEditorHtml(){
  var s=window._fmEditor;
  var tabs=[
    {id:'overview',l:'Обзор',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 5v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5l-5-3z"/><path d="M5 9h4"/></svg>', group:'Сводка'},
    {id:'revenue',l:'Выручка',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12l4-4 3 3 4-5M9 6h4v4"/></svg>', group:'P&L'},
    {id:'volumes',l:'Объёмы',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="8" width="2.5" height="4"/><rect x="5.75" y="5" width="2.5" height="7"/><rect x="9.5" y="2" width="2.5" height="10"/></svg>', group:'P&L'},
    {id:'tariffs',l:'Тарифы',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4.5 2h5M3 5h8M4.5 8h5M3 11h8"/></svg>', group:'P&L'},
    {id:'costs',l:'Затраты',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="4.5"/><path d="M7 4.5v5M5 6h4M5 8h4"/></svg>', group:'P&L'},
    {id:'capex',l:'CAPEX',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11.5h10M3.5 11.5V7l3-3 3 3v4.5M6 11.5V9h1.5v2.5"/></svg>', group:'Активы'},
    {id:'wc',l:'Оборотный капитал',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 7a5 5 0 0 1 9-3M12 7a5 5 0 0 1-9 3"/><path d="M11 2v3h-3M3 12V9h3"/></svg>', group:'Активы'},
    {id:'debt',l:'Долг',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="10" height="7" rx="1"/><path d="M5 4V3a2 2 0 1 1 4 0v1"/></svg>', group:'Капитал'},
    {id:'equity',l:'Собственный капитал',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="5" r="2.5"/><path d="M2.5 12a4.5 4.5 0 0 1 9 0"/></svg>', group:'Капитал'},
    {id:'assumptions',l:'Допущения',ico:'<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="2"/><path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.5 2.5l1.5 1.5M10 10l1.5 1.5M2.5 11.5L4 10M10 4l1.5-1.5"/></svg>', group:'Параметры'}
  ];
  var h='<div style="padding:16px 22px;border-bottom:1px solid rgba(0,0,0,.06);display:flex;align-items:center;justify-content:space-between">';
  h += '<div style="display:flex;align-items:center;gap:14px;flex:1"><div><div style="font-size:14px;font-weight:700;color:var(--t1);margin-bottom:2px">Редактор модели · '+esc(s.co)+'</div><div style="font-size:10.5px;color:var(--t3);letter-spacing:.04em;text-transform:uppercase;font-weight:600">'+s.years.length+' лет · '+(s.years[0]||'—')+'→'+(s.years[s.years.length-1]||'—')+'</div></div><span id="fm-ed-dirty-badge" style="display:none;align-items:center;gap:5px;padding:4px 9px;border-radius:5px;font-size:10.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase"></span></div>';
  h += '<button onclick="document.getElementById(\x27fm-editor-modal\x27).remove()" style="width:30px;height:30px;border:none;background:rgba(0,0,0,.04);border-radius:8px;cursor:pointer;color:var(--t3);display:flex;align-items:center;justify-content:center"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"/></svg></button>';
  h += '</div>';
  /* Tabs: группированные */
  h += '<div style="padding:10px 22px;border-bottom:1px solid rgba(0,0,0,.04);display:flex;gap:12px;overflow-x:auto;align-items:center;flex-wrap:wrap">';
  var curGrp=null;
  tabs.forEach(function(t){
    if(t.group!==curGrp){
      if(curGrp!==null) h += '<div style="width:1px;height:20px;background:rgba(0,0,0,.08)"></div>';
      h += '<div style="font-size:9.5px;color:var(--t3);font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-right:-4px">'+t.group+'</div>';
      curGrp=t.group;
    }
    var act=t.id===s.tab;
    h += '<button onclick="window._fmEditorTab=\x27'+t.id+'\x27;document.getElementById(\x27fm-editor-modal\x27).remove();_fmShowEditor()" style="display:flex;align-items:center;gap:6px;padding:6px 11px;border:none;border-radius:7px;background:'+(act?'#7F77DD':'rgba(0,0,0,.03)')+';color:'+(act?'#fff':'var(--t2)')+';font-size:11.5px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .15s;white-space:nowrap">'+t.ico+'<span>'+t.l+'</span></button>';
  });
  h += '</div>';
  /* Body */
  h += '<div style="flex:1;overflow-y:auto;padding:16px 22px" id="fm-ed-body">';
  h += _fmEditorTabContent(s.tab);
  h += '</div>';
  /* Live preview panel */
  h += '<div id="fm-ed-livepreview-wrap" style="padding:10px 22px 12px;border-top:1px solid rgba(0,0,0,.06);background:#FAFAFC">';
  h += '<div style="font-size:9.5px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:7px">Live preview · последний прогнозный год</div>';
  h += '<div id="fm-ed-livepreview"></div>';
  h += '</div>';
  /* Footer */
  h += '<div style="padding:12px 22px;border-top:1px solid rgba(0,0,0,.06);display:flex;gap:8px;justify-content:space-between;align-items:center">';
  h += '<div style="font-size:10.5px;color:var(--t3);line-height:1.5;max-width:520px">Изменения применяются ко всей модели: P&L, CF, BS, ratios пересчитываются автоматически. Ячейки факта (белые) редактируются так же как прогноз (жёлтые).</div>';
  h += '<div style="display:flex;gap:8px">';
  h += '<button onclick="document.getElementById(\x27fm-editor-modal\x27).remove()" style="padding:7px 14px;border:1px solid rgba(0,0,0,.1);border-radius:7px;background:#fff;color:var(--t2);font-size:12px;cursor:pointer;font-family:inherit">Отмена</button>';
  h += '<button onclick="_fmEditorSave()" style="padding:7px 18px;border:none;border-radius:7px;background:#7F77DD;color:#fff;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit">Сохранить</button>';
  h += '</div>';
  h += '</div>';
  return h;
}

function _fmEditorTabContent(tab){
  var s=window._fmEditor, m=s.model;
  if(tab==='overview') return _fmEdOverview(m);
  if(tab==='revenue') return _fmEdRevenue(m, s.years, s.factSet);
  if(tab==='volumes') return _fmEdDriverList(m.drivers.volumes, s.years, s.factSet, 'volumes', 'Ед. измерения', 'unit');
  if(tab==='tariffs') return _fmEdTariffs(m, s.years, s.factSet);
  if(tab==='costs') return _fmEdCosts(m, s.years, s.factSet);
  if(tab==='capex') return _fmEdDriverList(m.drivers.capex, s.years, s.factSet, 'capex', 'Категория', null);
  if(tab==='wc') return _fmEdWC(m.drivers.wc);
  if(tab==='debt') return _fmEdDebt(m, s.years, s.factSet);
  if(tab==='equity') return _fmEdEquity(m, s.years, s.factSet);
  if(tab==='assumptions') return _fmEdAssumptions(m);
  return '';
}

/* ── Editor: Revenue summary (если revenueDirect есть — можно редактировать напрямую) ── */
function _fmEdRevenue(m, years, factSet){
  m.revenueDirect=m.revenueDirect||{};
  var h='<div style="margin-bottom:12px"><div style="font-size:12px;color:var(--t1);font-weight:600;margin-bottom:4px">Прямая выручка по годам</div><div style="font-size:10.5px;color:var(--t3);line-height:1.5">Если указано — используется как итог напрямую. Иначе считается из Объёмов × Тарифы. Ввод в <strong>млн сум</strong> (UZSm).</div></div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px;margin-bottom:16px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Метрика</th>';
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '</tr></thead><tbody>';
  h += '<tr><td style="padding:6px 10px;color:var(--t1);font-weight:500">Выручка (Revenue)</td>';
  years.forEach(function(y){
    var isF=factSet[y];
    var v=m.revenueDirect[y]!=null?m.revenueDirect[y]:'';
    h += '<td style="padding:3px 3px"><input type="number" step="any" data-fm="revenueDirect" data-y="'+y+'" value="'+v+'" style="width:95px;padding:5px 6px;border:1px solid rgba(0,0,0,.06);border-radius:4px;font-size:11.5px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\';background:'+(isF?'#fff':'#FFFBF4')+';color:'+(isF?'var(--t1)':'#7A4A00')+'"></td>';
  });
  h += '</tr></tbody></table></div>';

  /* Показываем ожидаемые результаты из расчёта по волам×тарифам */
  if(m.drivers&&m.drivers.volumes&&m.drivers.volumes.length&&m.drivers.tariffs&&m.drivers.tariffs.length){
    h += '<div style="margin-top:16px;padding:12px 14px;background:rgba(127,119,221,.04);border-radius:8px;border-left:3px solid #7F77DD">';
    h += '<div style="font-size:11.5px;color:var(--t1);font-weight:600;margin-bottom:6px;display:flex;gap:6px;align-items:center"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#7F77DD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10V5M5 10V2M8 10V6M11 10H1"/></svg><span>Альтернатива: расчёт из драйверов</span></div>';
    h += '<div style="font-size:10.5px;color:var(--t2);line-height:1.5">Модель также поддерживает расчёт выручки через Объёмы × Тарифы. Настройте связи в табе "Тарифы" — каждому тарифу можно присвоить объём (volume reference).</div>';
    h += '</div>';
  }
  return h;
}

/* ── Editor: Tariffs с привязкой к Volume ── */
function _fmEdTariffs(m, years, factSet){
  var list=m.drivers.tariffs=m.drivers.tariffs||[];
  var vols=(m.drivers.volumes||[]).filter(function(v){return !v.isSub;});
  var h='<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;gap:12px">';
  h += '<div style="font-size:11px;color:var(--t3);line-height:1.5">Тарифы за единицу объёма. Можно привязать каждый тариф к конкретному объёму (volume reference) — система будет считать выручку по формуле Объём × Тариф.</div>';
  h += '<div style="display:flex;gap:6px;flex-shrink:0"><button onclick="_fmEdBulkForwardFill(\x27tariffs\x27)" title="Forward-fill для всех" style="padding:6px 10px;font-size:11px;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#fff;color:var(--t2);cursor:pointer;font-family:inherit;font-weight:500;display:inline-flex;align-items:center;gap:4px"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h7M6.5 3l3 3-3 3"/></svg>Все →</button>';
  h += '<button onclick="_fmEdRowAddInline(\x27tariffs\x27)" style="padding:6px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:rgba(127,119,221,.08);color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600;white-space:nowrap">+ Тариф</button></div>';
  h += '</div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Название</th>';
  h += '<th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Ед.</th>';
  h += '<th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Объём</th>';
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '<th style="width:130px;text-align:right;padding:8px 6px;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Действия</th></tr></thead><tbody>';
  if(!list.length){
    h += '<tr><td colspan="'+(years.length+4)+'" style="padding:24px;text-align:center;color:var(--t3);font-size:11.5px">Тарифов нет. Нажмите «+ Тариф» чтобы добавить.</td></tr>';
  }
  list.forEach(function(d,i){
    h += _fmEdRenderRow('tariffs',d,i,years,factSet,m);
  });
  h += '</tbody></table></div>';
  return h;
}

/* ── Editor: Costs с категорией (operating/SG&A) + isDA + type ── */
function _fmEdCosts(m, years, factSet){
  var list=m.drivers.costs=m.drivers.costs||[];
  var h='<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;gap:12px">';
  h += '<div style="font-size:11px;color:var(--t3);line-height:1.5">Затраты по категориям: <strong>Operating</strong> (себестоимость) и <strong>SG&A</strong> (админ.). Флаг «амортизация» → не входит в COGS, добавляется к EBITDA. Тип: fixed/variable/semi-variable.</div>';
  h += '<div style="display:flex;gap:6px;flex-shrink:0"><button onclick="_fmEdBulkForwardFill(\x27costs\x27)" title="Forward-fill для всех" style="padding:6px 10px;font-size:11px;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#fff;color:var(--t2);cursor:pointer;font-family:inherit;font-weight:500;display:inline-flex;align-items:center;gap:4px"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h7M6.5 3l3 3-3 3"/></svg>Все →</button>';
  h += '<button onclick="_fmEdRowAddInline(\x27costs\x27)" style="padding:6px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:rgba(127,119,221,.08);color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600;white-space:nowrap">+ Затрата</button></div>';
  h += '</div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Название</th>';
  h += '<th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Категория</th>';
  h += '<th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Тип</th>';
  h += '<th style="padding:8px 6px;text-align:center;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">D&A</th>';
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '<th style="width:130px;text-align:right;padding:8px 6px;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Действия</th></tr></thead><tbody>';
  if(!list.length){
    h += '<tr><td colspan="'+(years.length+5)+'" style="padding:24px;text-align:center;color:var(--t3);font-size:11.5px">Затрат нет. Нажмите «+ Затрата».</td></tr>';
  }
  var sCo=window._fmEditor; var mCo=sCo?sCo.model:{};
  list.forEach(function(d,i){
    h += _fmEdRenderRow('costs',d,i,years,factSet,mCo);
  });
  h += '</tbody></table></div>';
  return h;
}

/* ── Editor: Debt schedule по годам ── */
function _fmEdDebt(m, years, factSet){
  m.drivers.debt=m.drivers.debt||{ltDebt:{},stDebt:{},interestRate:0.09};
  var d=m.drivers.debt;
  var s=window._fmEditor||{};
  var h='<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--t1);font-weight:600;margin-bottom:4px">График долга по годам</div><div style="font-size:10.5px;color:var(--t3);line-height:1.5">Задайте остаток долга на конец каждого года. Система автоматически посчитает финансовые расходы (%) и включит их в P&L. <strong>Net Debt = LT + ST − Cash</strong>.</div></div>';
  /* Автозаполнение из кредитного портфеля — пока только для Uzbekistan Airports */
  if(s.co==='Uzbekistan Airports'){
    var loans=(_db.creditPortfolio&&_db.creditPortfolio.loans)||[];
    var uapCount=loans.filter(function(l){return l&&l.company&&String(l.company).indexOf('Uzbekistan Airports')>=0;}).length;
    if(uapCount>0){
      h+='<div style="margin-bottom:16px;padding:11px 13px;background:linear-gradient(135deg,rgba(127,119,221,.06),rgba(55,138,221,.05));border:1px solid rgba(127,119,221,.20);border-radius:9px;display:flex;gap:11px;align-items:center">';
      h+='<div style="flex:0 0 auto;width:34px;height:34px;border-radius:8px;background:#fff;border:1px solid rgba(127,119,221,.22);display:flex;align-items:center;justify-content:center"><svg width="15" height="15" viewBox="0 0 14 14" fill="none" stroke="#7F77DD" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11.5h10M3.5 11.5V7.5M6 11.5V5M8.5 11.5V8M11 11.5V3"/><path d="M2 3l3 1.5"/></svg></div>';
      h+='<div style="flex:1;min-width:0"><div style="font-size:11.5px;color:var(--t1);font-weight:600;margin-bottom:1px">Автозаполнение из кредитного портфеля</div><div style="font-size:10px;color:var(--t3);line-height:1.4">'+uapCount+' кредитов UzAirports → график LT/ST + средневзвешенная WACD на прогнозные годы. Существующие значения будут перезаписаны.</div></div>';
      h+='<button onclick="_fmAutofillBtnHandler()" style="flex:0 0 auto;padding:7px 13px;border:none;border-radius:6px;background:#7F77DD;color:#fff;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;letter-spacing:.02em;transition:background .15s" onmouseover="this.style.background=\x27#6960C7\x27" onmouseout="this.style.background=\x27#7F77DD\x27">Применить</button>';
      h+='</div>';
    }
  }
  h += '<div style="margin-bottom:16px;display:grid;grid-template-columns:1fr 140px;gap:12px;align-items:center;padding:12px 14px;background:rgba(127,119,221,.04);border-radius:8px">';
  h += '<div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:2px">Процентная ставка (WACD)</div><div style="font-size:10.5px;color:var(--t3)">Используется для расчёта финансовых расходов по всему долгу</div></div>';
  h += '<div style="position:relative"><input type="number" data-fm="debt" data-f="interestRate" value="'+((d.interestRate||0.09)*100).toFixed(1)+'" step="0.1" style="width:100%;padding:7px 26px 7px 10px;border:1px solid rgba(0,0,0,.1);border-radius:6px;font-size:13px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\'"><span style="position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--t3);font-size:12px">%</span></div>';
  h += '</div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600;width:180px">Категория</th>';
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '</tr></thead><tbody>';
  [
    {k:'ltDebt',l:'Долгосрочные кредиты и евробонды',sub:'LT debt & Eurobonds'},
    {k:'stDebt',l:'Краткосрочные кредиты',sub:'ST debt'}
  ].forEach(function(row){
    h += '<tr style="border-top:0.5px solid rgba(0,0,0,.04)">';
    h += '<td style="padding:6px 10px"><div style="font-size:11.5px;color:var(--t1);font-weight:500">'+row.l+'</div><div style="font-size:10px;color:var(--t3);margin-top:1px">'+row.sub+'</div></td>';
    years.forEach(function(y){
      var isF=factSet[y];
      var v=(d[row.k]&&d[row.k][y]!=null)?d[row.k][y]:'';
      h += '<td style="padding:2px 3px"><input type="number" step="any" data-fm="debt" data-f="'+row.k+'" data-y="'+y+'" value="'+v+'" style="width:90px;padding:4px 5px;border:1px solid rgba(0,0,0,.06);border-radius:4px;font-size:11px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\';background:'+(isF?'#fff':'#FFFBF4')+';color:'+(isF?'var(--t1)':'#7A4A00')+'"></td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  return h;
}

/* ── Editor: Equity (Share capital + opening RE) ── */
function _fmEdEquity(m, years, factSet){
  m.drivers.equity=m.drivers.equity||{shareCapital:{},openingCash:0,openingRE:0};
  var e=m.drivers.equity;
  var h='<div style="margin-bottom:14px"><div style="font-size:12px;color:var(--t1);font-weight:600;margin-bottom:4px">Собственный капитал</div><div style="font-size:10.5px;color:var(--t3);line-height:1.5">Уставный капитал по годам + начальные остатки cash и Retained earnings. <strong>Retained earnings</strong> рассчитываются автоматически: предыдущий RE + Net income − Дивиденды.</div></div>';

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px">';
  h += '<div style="padding:12px 14px;background:rgba(127,119,221,.04);border-radius:8px">';
  h += '<div style="font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-bottom:3px">Начальный баланс cash</div>';
  h += '<input type="number" data-fm="equity" data-f="openingCash" value="'+(e.openingCash||0)+'" step="any" style="width:100%;padding:7px 10px;border:1px solid rgba(0,0,0,.1);border-radius:6px;font-size:13px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\'">';
  h += '<div style="font-size:10px;color:var(--t3);margin-top:4px">На начало первого года горизонта (UZSm)</div>';
  h += '</div>';
  h += '<div style="padding:12px 14px;background:rgba(127,119,221,.04);border-radius:8px">';
  h += '<div style="font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-bottom:3px">Начальный RE</div>';
  h += '<input type="number" data-fm="equity" data-f="openingRE" value="'+(e.openingRE||0)+'" step="any" style="width:100%;padding:7px 10px;border:1px solid rgba(0,0,0,.1);border-radius:6px;font-size:13px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\'">';
  h += '<div style="font-size:10px;color:var(--t3);margin-top:4px">Retained earnings на начало (UZSm)</div>';
  h += '</div>';
  h += '</div>';

  h += '<div style="font-size:11px;color:var(--t1);font-weight:600;margin-bottom:6px">Уставный капитал по годам</div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600;width:180px">Метрика</th>';
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '</tr></thead><tbody>';
  h += '<tr><td style="padding:6px 10px;color:var(--t1);font-weight:500">Уставный капитал (Share capital)</td>';
  years.forEach(function(y){
    var isF=factSet[y];
    var v=(e.shareCapital&&e.shareCapital[y]!=null)?e.shareCapital[y]:'';
    h += '<td style="padding:2px 3px"><input type="number" step="any" data-fm="equity" data-f="shareCapital" data-y="'+y+'" value="'+v+'" style="width:90px;padding:4px 5px;border:1px solid rgba(0,0,0,.06);border-radius:4px;font-size:11px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\';background:'+(isF?'#fff':'#FFFBF4')+';color:'+(isF?'var(--t1)':'#7A4A00')+'"></td>';
  });
  h += '</tr></tbody></table></div>';
  return h;
}

function _fmEdDriverList(list, years, factSet, tabId, placeholder, extraFields){
  list=list||[];
  var xField = typeof extraFields === 'string' ? extraFields : (Array.isArray(extraFields) && extraFields.length > 1 ? extraFields[1] : null);
  var h='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:10px">';
  h += '<div style="font-size:11px;color:var(--t3);line-height:1.5;flex:1">Значения по годам. <span style="background:rgba(127,119,221,.12);padding:1px 6px;border-radius:3px;color:#6459C7;font-weight:600;letter-spacing:.04em">ПРОГНОЗ</span> — ячейки с прогнозом. Используйте кнопки <strong>→</strong> (forward-fill), <strong>%</strong> (рост год к году), <strong>~</strong> (интерполяция).</div>';
  h += '<div style="display:flex;gap:6px;flex-shrink:0">';
  h += '<button onclick="_fmEdBulkForwardFill(\x27'+tabId+'\x27)" title="Forward-fill для всех строк сразу" style="padding:6px 10px;font-size:11px;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#fff;color:var(--t2);cursor:pointer;font-family:inherit;font-weight:500;display:inline-flex;align-items:center;gap:4px"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h7M6.5 3l3 3-3 3"/></svg>Все →</button>';
  h += '<button onclick="_fmEdRowAddInline(\x27'+tabId+'\x27)" style="padding:6px 12px;font-size:11px;border:1px solid #7F77DD;border-radius:6px;background:rgba(127,119,221,.08);color:#6459C7;cursor:pointer;font-family:inherit;font-weight:600">+ Строка</button>';
  h += '</div></div>';
  h += '<div style="overflow-x:auto;border:1px solid rgba(0,0,0,.06);border-radius:8px"><table style="width:100%;border-collapse:collapse;font-size:11.5px">';
  h += '<thead><tr style="background:rgba(0,0,0,.02)"><th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Название</th>';
  if (xField) {
    h += '<th style="padding:8px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">'+esc(placeholder||'')+'</th>';
  }
  years.forEach(function(y){var isF=factSet[y];h += '<th style="padding:8px 6px;text-align:right;font-size:9.5px;color:'+(isF?'var(--t3)':'#A36500')+';font-weight:600">'+y+(isF?'':' П')+'</th>';});
  h += '<th style="width:130px;text-align:right;padding:8px 6px;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);font-weight:600">Действия</th></tr></thead><tbody>';
  var colsCount = (xField ? 1 : 0) + years.length + 2;
  if(!list.length){
    h += '<tr><td colspan="'+colsCount+'" style="padding:24px;text-align:center;color:var(--t3);font-size:11.5px">Строк нет. Нажмите «+ Строка» чтобы добавить.</td></tr>';
  }
  var s=window._fmEditor; var m=s?s.model:{};
  list.forEach(function(d,i){
    h += _fmEdRenderRow(tabId,d,i,years,factSet,m);
  });
  h += '</tbody></table></div>';
  return h;
}

function _fmEdWC(wc){
  wc=wc||{dso:30,dio:20,dpo:40,dap:15};
  var fields=[
    {k:'dso',l:'DSO (дней на получение дебиторки)',d:'Revenue × DSO/365'},
    {k:'dio',l:'DIO (дней на оборот запасов)',d:'COGS × DIO/365'},
    {k:'dpo',l:'DPO (дней отсрочки кредиторки)',d:'COGS × DPO/365 · со знаком минус'},
    {k:'dap',l:'DAP (дней по авансам полученным)',d:'Revenue × DAP/365 · со знаком минус'}
  ];
  var h='<div style="max-width:600px"><div style="font-size:11px;color:var(--t3);margin-bottom:14px;line-height:1.5">Оборачиваемость — основа расчёта изменения чистого оборотного капитала в ДДС. Типичные значения: DSO=25–40, DIO=20–30, DPO=30–50.</div>';
  fields.forEach(function(f){
    h += '<div style="margin-bottom:14px;display:grid;grid-template-columns:1fr 100px;gap:12px;align-items:center">';
    h += '<div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:2px">'+f.l+'</div><div style="font-size:10.5px;color:var(--t3)">'+f.d+'</div></div>';
    h += '<input type="number" data-fm="wc" data-f="'+f.k+'" value="'+(wc[f.k]||0)+'" step="1" style="padding:7px 10px;border:1px solid rgba(0,0,0,.1);border-radius:6px;font-size:13px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\'">';
    h += '</div>';
  });
  h += '</div>';
  return h;
}

function _fmEdAssumptions(m){
  var a=m.assumptions||{taxRate:0.15,wacc:0.12,dividendPayout:0.30};
  var fields=[
    {k:'taxRate',l:'Ставка налога на прибыль',d:'Обычно 15% в Узбекистане',pct:true,val:a.taxRate},
    {k:'wacc',l:'WACC (средневзвешенная стоимость капитала)',d:'Используется для дисконтирования FCFF в NPV',pct:true,val:a.wacc},
    {k:'dividendPayout',l:'Коэффициент выплаты дивидендов',d:'% чистой прибыли, направляемой на дивиденды',pct:true,val:a.dividendPayout}
  ];
  var h='<div style="max-width:600px">';
  fields.forEach(function(f){
    h += '<div style="margin-bottom:14px;display:grid;grid-template-columns:1fr 100px;gap:12px;align-items:center">';
    h += '<div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:2px">'+f.l+'</div><div style="font-size:10.5px;color:var(--t3)">'+f.d+'</div></div>';
    h += '<div style="position:relative"><input type="number" data-fm="asm" data-f="'+f.k+'" value="'+(f.val*100).toFixed(1)+'" step="0.1" style="width:100%;padding:7px 26px 7px 10px;border:1px solid rgba(0,0,0,.1);border-radius:6px;font-size:13px;font-family:inherit;outline:none;text-align:right;font-feature-settings:\'tnum\'"><span style="position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--t3);font-size:12px">%</span></div>';
    h += '</div>';
  });
  h += _fmEdRenderWACCLink();
  h += '</div>';
  return h;
}

function _fmEdAddRow(tabId){
  var s=window._fmEditor;
  var list=s.model.drivers[tabId];
  if(!Array.isArray(list)){list=s.model.drivers[tabId]=[];}
  list.push({id:'d'+Date.now(),name:'',unit:'',values:{}});
  window._fmEditorTab=tabId;
  document.getElementById('fm-editor-modal').remove();
  _fmShowEditor();
}
window._fmEdAddRow=_fmEdAddRow;

function _fmEdDelRow(tabId, idx){
  var s=window._fmEditor;
  var list=s.model.drivers[tabId];
  if(!Array.isArray(list))return;
  list.splice(idx,1);
  window._fmEditorTab=tabId;
  document.getElementById('fm-editor-modal').remove();
  _fmShowEditor();
}
window._fmEdDelRow=_fmEdDelRow;

function _fmEditorSave(){
  var s=window._fmEditor;
  if(!s)return;
  var m=s.model;
  /* Считываем все поля */
  document.querySelectorAll('#fm-editor-modal [data-fm]').forEach(function(inp){
    var tabId=inp.getAttribute('data-fm');
    var idx=inp.getAttribute('data-i');
    var field=inp.getAttribute('data-f');
    var yr=inp.getAttribute('data-y');
    var val=inp.value;
    var isChk=inp.type==='checkbox';
    if(tabId==='wc'){
      if(!m.drivers.wc)m.drivers.wc={};
      m.drivers.wc[field]=parseFloat(val)||0;
    }else if(tabId==='asm'){
      if(!m.assumptions)m.assumptions={};
      m.assumptions[field]=(parseFloat(val)||0)/100;
    }else if(tabId==='revenueDirect'){
      if(!m.revenueDirect)m.revenueDirect={};
      if(val==='')delete m.revenueDirect[yr];
      else m.revenueDirect[yr]=parseFloat(val)||0;
    }else if(tabId==='debt'){
      if(!m.drivers.debt)m.drivers.debt={ltDebt:{},stDebt:{}};
      if(field==='interestRate'){
        m.drivers.debt.interestRate=(parseFloat(val)||0)/100;
      }else if(field==='ltDebt'||field==='stDebt'){
        if(!m.drivers.debt[field])m.drivers.debt[field]={};
        if(val==='')delete m.drivers.debt[field][yr];
        else m.drivers.debt[field][yr]=parseFloat(val)||0;
      }
    }else if(tabId==='equity'){
      if(!m.drivers.equity)m.drivers.equity={shareCapital:{}};
      if(field==='openingCash'||field==='openingRE'){
        m.drivers.equity[field]=parseFloat(val)||0;
      }else if(field==='shareCapital'){
        if(!m.drivers.equity.shareCapital)m.drivers.equity.shareCapital={};
        if(val==='')delete m.drivers.equity.shareCapital[yr];
        else m.drivers.equity.shareCapital[yr]=parseFloat(val)||0;
      }
    }else if(idx!==null){
      var list=m.drivers[tabId]; if(!list)return;
      var row=list[parseInt(idx)]; if(!row)return;
      if(yr){
        if(!row.values)row.values={};
        if(val==='')delete row.values[yr];
        else row.values[yr]=parseFloat(val)||0;
      }else if(field){
        if(isChk) row[field]=inp.checked;
        else row[field]=val;
      }
    }
  });
  /* Записываем обратно в _db */
  _db.finModel=_db.finModel||{};
  _db.finModel[s.co]=_db.finModel[s.co]||{};
  _db.finModel[s.co][s.scn]=m;
  /* Stage 4: автоматическое создание D&A строки если её нет, но есть CAPEX */
  var addedAuto=_fmAutoEnsureDA(m);
  if(addedAuto&&typeof toast==='function') toast('Добавлена авто-строка «Амортизация» (CAPEX без D&A)');
  _fmRecompute(m);
  /* Прямой PUT вместо dbSaveKey чтобы гарантировать запись */
  if(typeof fetch==='function'&&typeof FB_URL==='function'){
    var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
    fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(_db.finModel)})
      .then(function(r){
        if(!r.ok)throw new Error('Firebase PUT '+r.status);
        if(typeof toast==='function') toast('Модель сохранена в Firebase');
      }).catch(function(e){
        console.error('[FM editor save] failed:',e);
        if(typeof toast==='function') toast('Ошибка: '+e.message);
      });
  }
  /* Stage 1: финальная валидация перед save */
  var errs=_fmValidateAll();
  if(errs.length){
    var msgList=errs.slice(0,5).map(function(e){return '· '+(e.row||e.tab+'/'+e.field)+(e.year?' ['+e.year+']':'')+': '+e.msg;}).join('\n');
    var more=errs.length>5?'\n... и ещё '+(errs.length-5):'';
    if(!confirm('Найдено '+errs.length+' предупреждени'+(errs.length===1?'е':errs.length<5?'я':'й')+':\n'+msgList+more+'\n\nСохранить несмотря на это?'))return;
  }
  _fmDetachBeforeUnload();
  _fmBackupClear(s.co,s.scn);
  document.getElementById('fm-editor-modal').remove();
  _fmRepaint();
}
window._fmEditorSave=_fmEditorSave;


/* ══ Excel экспорт v2 (Big 4 / IFI · universal · tooltips · 13 листов) ════ */
/* ════════════════════════════════════════════════════════════════════════════
   FM EXCEL EXPORT v2 — Big 4 / IFI grade financial model template
   v2 changes:
   - Universal sector resolver (с fallback на _db)
   - Cell comments (.c) на всех ключевых ячейках = tooltips on hover
   - Hint row (Excel row 3) на каждом листе — visible inline guidance
   - New "Инструкции" sheet с глоссарием и гайдом
   - Status panel на Cover — что заполнено / не заполнено
   - Better empty-data handling с чёткими сообщениями
   - Defaults: inflation/FX без year-binding (применяются ко всем годам)
   ════════════════════════════════════════════════════════════════════════════ */

/* Helpers: 0-indexed → Excel A1 */
function _fmExColLetter(c){
  var s='';
  while(c>=0){s=String.fromCharCode(65+c%26)+s;c=Math.floor(c/26)-1;}
  return s;
}
function _fmExAddr(r,c){return _fmExColLetter(c)+(r+1);}
function _fmExRange(r1,c1,r2,c2){return _fmExAddr(r1,c1)+':'+_fmExAddr(r2,c2);}

/* Cell builders */
function _fmExNum(v,fmt,comment){
  var cell=v==null||isNaN(v)?{v:'',t:'s'}:{v:v,t:'n',z:fmt||'#,##0'};
  if(comment)cell.c=[{a:'UzAssets',t:comment,T:true}];
  return cell;
}
function _fmExStr(s,comment){
  var cell={v:s||'',t:'s'};
  if(comment)cell.c=[{a:'UzAssets',t:comment,T:true}];
  return cell;
}
function _fmExFormula(f,fmt,comment){
  var cell={f:f,v:0,t:'n',z:fmt||'#,##0'};
  if(comment)cell.c=[{a:'UzAssets',t:comment,T:true}];
  return cell;
}
function _fmExComment(text){return [{a:'UzAssets',t:text,T:true}];}

/* Named range register */
function _fmExAddName(wb,name,sheet,addr){
  wb.Workbook.Names.push({Name:name, Ref:"'"+sheet+"'!"+addr});
}

/* Number formats library — Big 4 standard */
var _FM_FMT={
  acc:'#,##0;(#,##0);"-"',
  accNeg:'#,##0;[Red](#,##0);"-"',
  pct:'0.0%',
  pctP:'0.00%',
  ratio:'0.00"×"',
  ratioInt:'0"×"',
  date:'dd.mm.yyyy',
  yr:'0',
  txt:'@',
  qty:'#,##0',
  unit:'#,##0.00'
};

/* Universal sector resolver — несколько fallback источников */
function _fmExResolveSector(co){
  if(!co)return '—';
  /* 1. _db.companies[co].sector — primary platform data */
  try{
    if(typeof _db!=='undefined' && _db.companies && _db.companies[co] && _db.companies[co].sector){
      return _db.companies[co].sector;
    }
  }catch(e){}
  /* 2. Sector index map */
  try{
    if(typeof _db!=='undefined' && _db.sectorByCo && _db.sectorByCo[co]){
      return _db.sectorByCo[co];
    }
  }catch(e){}
  /* 3. Hardcoded fallback (legacy) */
  var fallback={
    'Uzbekistan Airports':'Транспорт',
    'Uzbekistan Airways':'Транспорт',
    'Ўзбекистон темир йўллари':'Транспорт',
    'Тошшахартрансхизмат':'Транспорт',
    'НГМК':'Горнодобыча',
    'АГМК':'Горнодобыча',
    'Навоийуран':'Горнодобыча',
    'Узбекуголь':'Горнодобыча',
    'Узметкомбинат':'Горнодобыча',
    'Узбекнефтегаз':'Нефть и газ',
    'Узтрансгаз':'Нефть и газ',
    'Худудгазтаъминот':'Нефть и газ',
    'UzGasTrade':'Нефть и газ',
    'ТЭС':'Энергетика',
    'НЭС':'Энергетика',
    'РЭС':'Энергетика',
    'Узбекгидроэнерго':'Энергетика',
    'UzAuto':'Автопром',
    'УзАвто Саноат':'Автопром',
    'АО Navoiyazot':'Химия',
    'АО Узкимёсаноат':'Химия',
    'Ўзбектелеком':'Связь',
    'Ўзбекистон почтаси':'Связь',
    'UzTelecom':'Связь',
    'Tenzorsoft':'IT'
  };
  return fallback[co] || '—';
}

/* Status assessment — что заполнено в модели */
function _fmExComputeStatus(model){
  var status={
    sections:[],
    totalFilled:0,
    totalSections:0,
    warnings:[]
  };
  if(!model)return status;
  var drv=model.drivers||{};
  function check(label,filled,detail){
    status.sections.push({label:label,filled:filled,detail:detail||''});
    status.totalSections++;
    if(filled)status.totalFilled++;
  }
  /* Volumes */
  var nVol=(drv.volumes||[]).length;
  check('Драйверы выручки (volumes)', nVol>0, nVol>0?(nVol+' строк'):'не заполнено');
  /* Tariffs */
  var nTar=(drv.tariffs||[]).length;
  check('Тарифы', nTar>0, nTar>0?(nTar+' строк'):'не заполнено');
  /* Costs */
  var nCost=(drv.costs||[]).length;
  check('Структура затрат', nCost>0, nCost>0?(nCost+' строк'):'не заполнено');
  /* CAPEX */
  var nCx=(drv.capex||[]).length;
  check('CAPEX', nCx>0, nCx>0?(nCx+' категорий'):'не заполнено');
  /* WC */
  var wc=drv.wc||{};
  var hasWC=(wc.dso||wc.dio||wc.dpo||wc.dap)>0;
  check('Оборотный капитал (DSO/DIO/DPO/DAP)', hasWC, hasWC?(wc.dso+'/'+wc.dio+'/'+wc.dpo+'/'+wc.dap+' дней'):'все нули');
  /* Debt schedule */
  var debt=drv.debt||{};
  var nDebtYrs=Object.keys(debt.ltDebt||{}).length+Object.keys(debt.stDebt||{}).length;
  check('График долга (LT/ST)', nDebtYrs>0, nDebtYrs>0?(nDebtYrs+' year-values'):'не заполнено');
  /* WACD */
  check('Эффективная ставка (WACD)', !!debt.interestRate, debt.interestRate?((debt.interestRate*100).toFixed(2)+'%'):'не заполнено');
  /* Equity opening */
  var eq=drv.equity||{};
  var hasOpen=eq.openingCash>0||eq.openingRE>0||eq.openingPPE>0;
  check('Opening BS (cash/RE/PPE)', hasOpen, hasOpen?'заполнено':'нули — BS может не сходиться');
  if(!hasOpen){
    status.warnings.push('Opening PP&E = 0 → Balance Sheet первого года не сойдётся, если share_capital > opening_cash');
  }
  /* Revenue Direct */
  var nRev=Object.keys(model.revenueDirect||{}).length;
  check('Выручка (rev_total)', nRev>0, nRev>0?(nRev+' лет'):'не заполнено');

  /* Forecast horizon check */
  var nFc=(model.horizon&&model.horizon.forecastYears||[]).length;
  if(nFc===0){
    status.warnings.push('Forecast years = 0 → DCF, DSCR, LLCR/PLCR не вычисляются');
  }
  return status;
}

/* ════════════════════════════════════════════════════════════════════════════
   MAIN ENTRY: _fmExportExcel
   ════════════════════════════════════════════════════════════════════════════ */
async function _fmExportExcel(coOverride){
  if(typeof _ensureXLSX==='function') await _ensureXLSX();
  if(typeof XLSX==='undefined'){
    alert('XLSX library не загружена');return;
  }
  var co=coOverride||window._fmSelCo;
  if(!co){
    if(typeof _fmShowCompanyPicker==='function'){
      _fmShowCompanyPicker(function(picked){
        window._fmSelCo=picked;
        _fmExportExcel(picked);
      },'Экспорт финансовой модели','Выберите компанию для экспорта');
    }
    return;
  }
  var scn=window._fmScenario||'base';
  var model=(_db.finModel&&_db.finModel[co]&&_db.finModel[co][scn])||(typeof _fmDefaultModel==='function'?_fmDefaultModel():null);
  if(!model){alert('Модель для '+co+' не найдена');return;}
  if(typeof _fmEnsureAssumptions==='function') _fmEnsureAssumptions(model);
  if(typeof _fmRecompute==='function') try{_fmRecompute(model);}catch(e){}

  /* Universal safety: model must have horizon */
  model.horizon=model.horizon||{factYears:[],forecastYears:[]};
  if((model.horizon.factYears||[]).length===0 && (model.horizon.forecastYears||[]).length===0){
    if(typeof toast==='function')toast('Модель пустая — добавьте годы в горизонт');
    else alert('Модель пустая — добавьте годы в горизонт');
    return;
  }

  var wb=_fmExBuildWorkbook(model,co,scn);
  var safeName=co.replace(/[^a-zA-Z0-9А-Яа-я]/g,'_');
  var dateTag=new Date().toISOString().split('T')[0];
  var fname='UzAssets_FinModel_'+safeName+'_'+scn+'_'+dateTag+'.xlsx';
  if(typeof _dlXlsx==='function'){_dlXlsx(wb,fname);}
  else{
    var out=XLSX.write(wb,{bookType:'xlsx',type:'array'});
    var blob=new Blob([out],{type:'application/octet-stream'});
    var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=fname;a.click();
    setTimeout(function(){URL.revokeObjectURL(a.href);},5000);
  }
  if(typeof toast==='function') toast('Финмодель экспортирована: '+fname);
}
window._fmExportExcel=_fmExportExcel;

/* ════════════════════════════════════════════════════════════════════════════
   BUILD WORKBOOK — координирует все листы (13 листов с Инструкциями)
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExBuildWorkbook(model,co,scn){
  var wb=XLSX.utils.book_new();
  wb.Workbook=wb.Workbook||{};
  wb.Workbook.Names=wb.Workbook.Names||[];

  var factYears=model.horizon.factYears||[];
  var fcYears=model.horizon.forecastYears||[];
  var allYears=[].concat(factYears,fcYears);

  var ctx={
    wb:wb,
    model:model,
    co:co,
    scn:scn,
    factYears:factYears,
    fcYears:fcYears,
    allYears:allYears,
    yearCol:function(y){var i=allYears.indexOf(y);return i>=0?(3+i):null;},
    yearColLetter:function(y){var c=this.yearCol(y);return c==null?'':_fmExColLetter(c);},
    nFact:factYears.length,
    nFc:fcYears.length,
    nYrs:allYears.length,
    status:_fmExComputeStatus(model),
    sheets:{
      cover:'00 Обзор',
      instr:'Инструкции',
      assum:'01 Допущения · WACC',
      rev:'10 Выручка',
      opex:'20 OPEX',
      capex:'30 CAPEX · WC',
      debt:'40 Долг',
      equity:'50 Капитал',
      pnl:'70 P&L',
      bs:'71 Баланс',
      cf:'72 Cash Flow',
      cov:'80 Покрытие',
      audit:'99 Audit trail'
    }
  };

  _fmExAddCover(ctx);
  _fmExAddInstructions(ctx);
  _fmExAddAssumptions(ctx);
  _fmExAddRevenue(ctx);
  _fmExAddOpex(ctx);
  _fmExAddCapexWc(ctx);
  _fmExAddDebt(ctx);
  _fmExAddEquity(ctx);
  _fmExAddPnL(ctx);
  _fmExAddBalanceSheet(ctx);
  _fmExAddCashFlow(ctx);
  _fmExAddCoverage(ctx);
  _fmExAddAuditTrail(ctx);

  return wb;
}

/* ════════════════════════════════════════════════════════════════════════════
   HELPER: header strip + hint row на Excel row 3
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExHeaderStrip(ws,title,subtitle,nCols,hint){
  ws['A1']=_fmExStr(title);
  ws['A2']=_fmExStr(subtitle||'');
  ws['!merges']=ws['!merges']||[];
  ws['!merges'].push({s:{r:0,c:0},e:{r:0,c:nCols-1}});
  if(subtitle) ws['!merges'].push({s:{r:1,c:0},e:{r:1,c:nCols-1}});
  if(hint){
    ws['A3']={v:'▶ '+hint, t:'s', c:_fmExComment(hint)};
    ws['!merges'].push({s:{r:2,c:0},e:{r:2,c:nCols-1}});
  }
}

function _fmExYearHeaders(ws,row,startCol,years,factSet){
  ws[_fmExAddr(row,0)]=_fmExStr('ID',_fmExComment('Краткий идентификатор. Используется для перекрёстных ссылок и named ranges.'));
  ws[_fmExAddr(row,1)]=_fmExStr('Метрика',_fmExComment('Описание показателя.'));
  ws[_fmExAddr(row,2)]=_fmExStr('Ед.',_fmExComment('Единица измерения. UZSm = миллионы сум.'));
  years.forEach(function(y,i){
    var lbl=String(y)+(factSet[y]?' Ф':' П');
    var cmt=factSet[y]?'Факт ('+y+') — исторические данные':'Прогноз ('+y+') — расчётные значения';
    ws[_fmExAddr(row,startCol+i)]={v:lbl, t:'s', c:_fmExComment(cmt)};
  });
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 00 · ОБЗОР (Cover & Summary + Status + How-to-use)
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddCover(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.cover;

  ws['A1']=_fmExStr('UzAssets · единая финансовая модель — шаблон v1.0');
  ws['A2']=_fmExStr(ctx.co+' · сценарий: '+(ctx.scn==='base'?'Базовый':ctx.scn==='opt'?'Оптимистичный':'Стрессовый'));

  /* ─── МЕТАДАННЫЕ ─── */
  ws['A4']=_fmExStr('━━━━ МЕТАДАННЫЕ ━━━━');
  var meta=[
    ['Сектор',           _fmExResolveSector(ctx.co), 'Сектор компании. Берётся из _db.companies или fallback-карты.'],
    ['Сценарий',         ctx.scn==='base'?'Базовый':(ctx.scn==='opt'?'Оптимистичный':'Стрессовый'), 'Текущий сценарий моделирования. Изменяется в редакторе.'],
    ['Валюта · единицы', 'UZS · млн (UZSm)', 'Все денежные значения в миллионах сум. Ratio показатели — безразмерные.'],
    ['FX as-of',         '01.01.2026',       'Дата фиксации валютных курсов. Историческая отсечка.'],
    ['Версия модели',    'v1.0 · '+new Date().toISOString().split('T')[0], 'Версия шаблона + дата экспорта.'],
    ['Горизонт',         (ctx.allYears[0]||'—')+' → '+(ctx.allYears[ctx.allYears.length-1]||'—')+' ('+ctx.nFact+' факт + '+ctx.nFc+' прогноз)', 'Период моделирования. Факт = исторические данные, прогноз = расчёт.']
  ];
  meta.forEach(function(pair,i){
    ws[_fmExAddr(4+i,0)]=_fmExStr(pair[0]);
    ws[_fmExAddr(4+i,1)]=_fmExStr(pair[1],pair[2]);
  });

  /* Active scenario named range */
  ws['A11']=_fmExStr('Активный сценарий');
  ws['B11']=_fmExStr(ctx.scn==='base'?'Base':(ctx.scn==='opt'?'Upside':'Downside'),'Named range scenario_active. Используется для фильтра OFFSET-формул в multi-scenario режиме (v2).');
  _fmExAddName(wb,'scenario_active',sn,'$B$11');

  /* ─── KPI ─── */
  var lastFc=ctx.fcYears[ctx.fcYears.length-1];
  var firstFc=ctx.fcYears[0];
  ws['A13']=_fmExStr('━━━━ КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ '+(lastFc?'— '+lastFc+' (последний прогнозный год)':'')+' ━━━━');
  ws['A14']={v:'▶ Значения автоматически вычисляются из драйверов и допущений. Не редактируйте — это формулы.',t:'s',c:_fmExComment('KPI рассчитываются через named ranges из листов 70/71/72/80. Чтобы изменить — правьте драйверы на листах 10/20/30/40/50.')};
  ws['!merges']=ws['!merges']||[];
  ws['!merges'].push({s:{r:13,c:0},e:{r:13,c:5}});

  if(lastFc){
    var kpis=[
      {lbl:'Revenue (UZSm)',           f:'revenue_'+lastFc,         z:_FM_FMT.acc,    c:'Выручка последнего прогнозного года = revenue_'+lastFc+' (named range из P&L).'},
      {lbl:'EBITDA (UZSm)',            f:'ebitda_'+lastFc,          z:_FM_FMT.acc,    c:'EBITDA = Operating Profit + D&A. Из P&L.'},
      {lbl:'EBITDA margin',            f:'IF(revenue_'+lastFc+'=0,0,ebitda_'+lastFc+'/revenue_'+lastFc+')', z:_FM_FMT.pct, c:'EBITDA margin = EBITDA / Revenue. Бенчмарк: транспорт 30-50%, добыча 40-60%, телеком 35-45%.'},
      {lbl:'Op profit (UZSm)',         f:'opprofit_'+lastFc,        z:_FM_FMT.acc,    c:'Операционная прибыль = Gross − OPEX − D&A.'},
      {lbl:'Net income (UZSm)',        f:'netinc_'+lastFc,          z:_FM_FMT.acc,    c:'Чистая прибыль = PBT − Tax.'},
      {lbl:'Net Debt (UZSm)',          f:'bs_net_debt_'+lastFc,     z:_FM_FMT.acc,    c:'Net Debt = Total Debt − Cash. Отрицательное значение = чистая денежная позиция.'},
      {lbl:'Net Debt / EBITDA (×)',    f:'IF(ebitda_'+lastFc+'=0,0,bs_net_debt_'+lastFc+'/ebitda_'+lastFc+')', z:_FM_FMT.ratio, c:'Долговая нагрузка. Бенчмарки: <2.5× низкая, 2.5-4× умеренная, >4× высокая.'},
      {lbl:'ROE',                       f:'IF(bs_total_equity_'+lastFc+'=0,0,netinc_'+lastFc+'/bs_total_equity_'+lastFc+')', z:_FM_FMT.pct, c:'Return on Equity = Net Income / Total Equity. Бенчмарк ≥ 15%.'},
      {lbl:'DSCR минимум',             f:'dscr_min',                 z:_FM_FMT.ratio,  c:'DSCR Min по прогнозным годам. IFI covenant ≥ 1.20× (некоторые требуют 1.30×).'},
      {lbl:'DSCR среднее',             f:'dscr_avg',                 z:_FM_FMT.ratio,  c:'Среднее DSCR. Не заменяет Min — covenant проверяется по worst year.'},
      {lbl:'LLCR',                      f:'llcr',                     z:_FM_FMT.ratio,  c:'Loan Life Coverage. NPV(CFADS over loan life) / Outstanding debt. ≥ 1.30× — IFI standard.'},
      {lbl:'PLCR',                      f:'plcr',                     z:_FM_FMT.ratio,  c:'Project Life Coverage. NPV(CFADS over project life) / Outstanding debt. PLCR ≥ LLCR обычно.'}
    ];
    kpis.forEach(function(k,i){
      var rIdx=15+i;
      ws[_fmExAddr(rIdx,0)]=_fmExStr(k.lbl);
      ws[_fmExAddr(rIdx,1)]={f:k.f,v:0,t:'n',z:k.z,c:_fmExComment(k.c)};
    });
  }else{
    ws['A16']=_fmExStr('— Нет прогнозных лет в горизонте, KPI не вычисляются —','Добавьте forecastYears в model.horizon и заполните драйверы.');
  }

  /* ─── INTEGRITY ─── */
  var checkRow=29;
  ws[_fmExAddr(checkRow-1,0)]=_fmExStr('━━━━ ПРОВЕРКА ЦЕЛОСТНОСТИ ━━━━');
  ws[_fmExAddr(checkRow,0)]={v:'▶ Должно быть OK для всех годов. BREAK = модель не сходится.',t:'s',c:_fmExComment('BS check: разница между Total Assets и Total Liab+Equity < 1 UZSm. Если BREAK — проверьте opening_ppe в "50 Капитал".\nCash tie-out: cumulative netcc + opening_cash должно совпасть с BS Cash. DRIFT = логическая ошибка в Cash Flow.')};
  ws['!merges'].push({s:{r:checkRow,c:0},e:{r:checkRow,c:5}});
  ws[_fmExAddr(checkRow+1,0)]=_fmExStr('BS balances ('+(firstFc||'—')+')');
  ws[_fmExAddr(checkRow+2,0)]=_fmExStr('Cash CF tie-out ('+(firstFc||'—')+')');
  if(firstFc){
    var firstFcCol=ctx.yearColLetter(firstFc);
    ws[_fmExAddr(checkRow+1,1)]={f:"'"+ctx.sheets.bs+"'!"+firstFcCol+"21",v:'',t:'s',c:_fmExComment('Ссылка на ячейку BS check в "71 Баланс" row 21.')};
    ws[_fmExAddr(checkRow+2,1)]={f:"'"+ctx.sheets.cf+"'!"+firstFcCol+"22",v:'',t:'s',c:_fmExComment('Ссылка на Cash tie-out в "72 Cash Flow" row 22.')};
  }

  /* ─── STATUS PANEL ─── */
  var statRow=34;
  ws[_fmExAddr(statRow-1,0)]=_fmExStr('━━━━ СТАТУС МОДЕЛИ ━━━━');
  var pct=ctx.status.totalSections?Math.round(100*ctx.status.totalFilled/ctx.status.totalSections):0;
  ws[_fmExAddr(statRow,0)]={v:'▶ Заполнено: '+ctx.status.totalFilled+' из '+ctx.status.totalSections+' разделов ('+pct+'%)',t:'s',c:_fmExComment('Если процент < 100%, недозаполненные секции отмечены ниже. Заполните их в редакторе на платформе или прямо в файле на соответствующих листах.')};
  ws['!merges'].push({s:{r:statRow,c:0},e:{r:statRow,c:5}});
  ctx.status.sections.forEach(function(sec,i){
    var rIdx=statRow+1+i;
    ws[_fmExAddr(rIdx,0)]=_fmExStr((sec.filled?'✓ ':'⚠ ')+sec.label);
    ws[_fmExAddr(rIdx,1)]=_fmExStr(sec.detail);
  });
  if(ctx.status.warnings.length){
    var warnStart=statRow+1+ctx.status.sections.length+1;
    ws[_fmExAddr(warnStart,0)]=_fmExStr('Предупреждения');
    ctx.status.warnings.forEach(function(w,i){
      ws[_fmExAddr(warnStart+1+i,0)]=_fmExStr('⚠ '+w);
    });
  }

  /* ─── HOW TO USE ─── */
  var howRow=statRow+1+ctx.status.sections.length+(ctx.status.warnings.length?(2+ctx.status.warnings.length):0)+2;
  ws[_fmExAddr(howRow,0)]=_fmExStr('━━━━ КАК ИСПОЛЬЗОВАТЬ ШАБЛОН ━━━━');
  var howto=[
    '1. Прочитайте лист "Инструкции" — глоссарий, обозначения, конвенции',
    '2. На "01 Допущения" — Tax rate, WACD, инфляция, FX',
    '3. На "10 Выручка" — Volumes × Tariffs или Revenue Total напрямую',
    '4. На "20 OPEX" — переменные (variable) + постоянные (fixed) + амортизация (isDA)',
    '5. На "30 CAPEX · WC" — инвестиции + DSO/DIO/DPO/DAP в днях',
    '6. На "40 Долг" — LT/ST по годам + WACD (эффективная ставка)',
    '7. На "50 Капитал" — Opening cash / RE / PPE для balance opening BS',
    '8. Output листы (70/71/72/80) — формулы read-only, перерасчёт автоматический',
    '9. KPI на этом листе обновятся при сохранении файла в Excel'
  ];
  howto.forEach(function(line,i){
    ws[_fmExAddr(howRow+1+i,0)]=_fmExStr(line);
  });

  ws['!ref']=_fmExRange(0,0,howRow+howto.length+2,5);
  ws['!cols']=[{wch:42},{wch:32},{wch:14},{wch:14},{wch:14},{wch:14}];
  ws['!merges']=ws['!merges']||[];
  ws['!merges'].push({s:{r:0,c:0},e:{r:0,c:5}});
  ws['!merges'].push({s:{r:1,c:0},e:{r:1,c:5}});
  /* Section dividers — merge across full width */
  ws['!merges'].push({s:{r:3,c:0},e:{r:3,c:5}});  /* МЕТАДАННЫЕ */
  ws['!merges'].push({s:{r:12,c:0},e:{r:12,c:5}}); /* KPI */
  ws['!merges'].push({s:{r:checkRow-1,c:0},e:{r:checkRow-1,c:5}}); /* INTEGRITY */
  ws['!merges'].push({s:{r:statRow-1,c:0},e:{r:statRow-1,c:5}}); /* STATUS */
  ws['!merges'].push({s:{r:howRow,c:0},e:{r:howRow,c:5}}); /* HOW TO */

  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ "Инструкции" (новый v2)
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddInstructions(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.instr;

  ws['A1']=_fmExStr('Инструкции — как пользоваться шаблоном');
  ws['A2']=_fmExStr('UzAssets · единая платформа трансформации');
  ws['!merges']=[{s:{r:0,c:0},e:{r:0,c:3}},{s:{r:1,c:0},e:{r:1,c:3}}];

  var sections=[];
  function pushSection(title, rows){
    sections.push({title:title, rows:rows});
  }

  pushSection('━━━━ ОБОЗНАЧЕНИЯ ━━━━',[
    ['Ф',     'факт (historical year, отчётность)'],
    ['П',     'прогноз (forecast year)'],
    ['UZSm',  'миллионы сум — все денежные значения'],
    ['×',     'кратность (ratio, безразмерное)'],
    ['%',     'процент'],
    ['─',     'визуальный разделитель секций'],
    ['▶',     'inline подсказка (можно навести мышью для деталей)'],
    ['✓',     'раздел заполнен'],
    ['⚠',     'раздел требует внимания']
  ]);

  pushSection('━━━━ СТРУКТУРА ШАБЛОНА ━━━━',[
    ['00 Обзор',         'KPI dashboard, status panel, integrity checks, how-to'],
    ['Инструкции',       'этот лист — глоссарий и гайд'],
    ['01 Допущения',     'Tax rate, WACC components, инфляция, FX'],
    ['10 Выручка',       'volumes × tariffs драйверы + revenue total'],
    ['20 OPEX',          'variable (COGS), fixed (OPEX), D&A — три группы расходов'],
    ['30 CAPEX · WC',    'инвестиции + DSO/DIO/DPO/DAP'],
    ['40 Долг',          'LT/ST debt по годам + WACD (эфф. ставка)'],
    ['50 Капитал',       'opening_cash, opening_re, opening_ppe'],
    ['70 P&L',           'отчёт о прибылях — формулы'],
    ['71 Баланс',        'BS roll-forward + BS check'],
    ['72 Cash Flow',     'CFO + CFI + CFF + Cash tie-out'],
    ['80 Покрытие',      'DSCR (per year, min, avg) + LLCR + PLCR'],
    ['99 Audit trail',   'версия модели, методология, ограничения']
  ]);

  pushSection('━━━━ КАК РЕДАКТИРОВАТЬ ━━━━',[
    ['Входные ячейки',   'на листах 01, 10, 20, 30, 40, 50 — заполняются вручную или импортом из платформы'],
    ['Формульные ячейки','на листах 70, 71, 72, 80 — НЕ ТРОГАЕМ, перерасчёт автоматический при сохранении'],
    ['Изменение формул', 'если необходимо — сначала разберитесь в логике, проверьте BS check после'],
    ['Проверка',         'после правок проверьте BS balances + Cash tie-out на "00 Обзор" — оба должны быть OK']
  ]);

  pushSection('━━━━ ГЛОССАРИЙ — IFI / Big 4 терминология ━━━━',[
    ['CFADS',  'Cash Flow Available for Debt Service = EBITDA − Tax − ΔNWC − CAPEX. Стандарт project finance.'],
    ['DSCR',   'Debt Service Coverage Ratio = CFADS / (Interest + Principal). IFI covenant ≥ 1.20×.'],
    ['LLCR',   'Loan Life Coverage Ratio = NPV(CFADS) / Outstanding debt. Считается за срок займа.'],
    ['PLCR',   'Project Life Coverage Ratio. Аналогично LLCR, но за весь project life (включая годы после погашения долга).'],
    ['WACD',   'Weighted Average Cost of Debt = эффективная ставка по портфелю кредитов. Применяется и для P&L процентов, и для NPV в LLCR.'],
    ['WACC',   'Weighted Average Cost of Capital = (1−w_d)·Re + w_d·Rd·(1−tax). Для DCF и оценки стоимости.'],
    ['NWC',    'Net Working Capital = (DSO/365)·Rev + (DIO/365)·COGS − (DPO/365)·COGS − (DAP/365)·Rev.'],
    ['ΔNWC',   'Изменение NWC YoY. Положительное = отток оборотного капитала.'],
    ['PP&E',   'Property, Plant & Equipment = основные средства. Roll-forward: Beg + CAPEX − D&A = End.'],
    ['CAPEX',  'Capital Expenditure = инвестиции в долгосрочные активы.'],
    ['D&A',    'Depreciation & Amortization = амортизация. Не cash-расход.'],
    ['EBITDA', 'Earnings Before Interest, Taxes, D&A. Прокси операционного денежного потока.'],
    ['Net Debt','Total Debt − Cash. Метрика чистой долговой нагрузки.'],
    ['Covenant','Условие в кредитном договоре. DSCR < threshold = breach = технический дефолт.'],
    ['IFC/EBRD/ADB','International Finance Corporation / European BRD / Asian DB — основные DFI.']
  ]);

  pushSection('━━━━ NAMED RANGES ━━━━',[
    ['Просмотр',   'В Excel: Ctrl+F3 → Менеджер имён. В Numbers: Edit → Named Ranges.'],
    ['Конвенция',  'Год добавлен через подчёркивание: revenue_2026, ebitda_2026, dscr_2027.'],
    ['Глобальные', 'tax_rate, wacc, wacd, scenario_active, dscr_min, dscr_avg, llcr, plcr.'],
    ['BS named',   'bs_<id>_<year> — например bs_total_assets_2026, bs_cash_2026.'],
    ['CF named',   'netcc_<year> для cumulative cash change. Используется в BS Cash roll.']
  ]);

  pushSection('━━━━ КОНВЕНЦИИ BIG 4 / IFI ━━━━',[
    ['Знаки',          'Расходы = отрицательные числа. (1,000) или −1,000 = расход.'],
    ['Округление',     'Денежные значения — целые или 1 знак после. Ratio — 2 знака.'],
    ['Год-маркер',     'У форecast-лет суффикс "П", у факта — "Ф".'],
    ['Hard inputs',    'Жёсткие ввод (исторические данные) и драйверы — заполняются на input-листах.'],
    ['Output линки',   'Output листы (70/71/72/80) ссылаются на input через named ranges, не прямые ссылки.'],
    ['BS integrity',   'Total Assets = Total Liab + Equity для каждого года. Расхождение > 1 UZSm = bug.']
  ]);

  pushSection('━━━━ ОГРАНИЧЕНИЯ V1 ━━━━',[
    ['Cell colors',           'Не реализованы (community SheetJS). Big 4 конвенция: синий = input, чёрный = formula, зелёный = link.'],
    ['Conditional formatting','Не реализовано — BS check показывает текстом OK/BREAK без цвета.'],
    ['Multi-scenario',        'Только активный сценарий. Multi-case через OFFSET — v2.'],
    ['Sensitivity tables',    'Excel Data Tables не сгенерированы — v2.'],
    ['Round-trip парсер',      'Импорт обратно в платформу через named ranges — v2.']
  ]);

  pushSection('━━━━ ПОДДЕРЖКА ━━━━',[
    ['Платформа',     'platform.uz-assets.uz · UzAssets единая платформа'],
    ['Документация',  'См. внутреннюю Knowledge Base UzAssets'],
    ['Контакт',        'Технический контакт UzAssets через платформу']
  ]);

  /* Render all sections */
  var r=3;
  sections.forEach(function(sec){
    ws[_fmExAddr(r,0)]=_fmExStr(sec.title);
    ws['!merges'].push({s:{r:r,c:0},e:{r:r,c:3}});
    r++;
    sec.rows.forEach(function(row){
      ws[_fmExAddr(r,0)]=_fmExStr(row[0]);
      ws[_fmExAddr(r,1)]=_fmExStr(row[1]);
      ws['!merges'].push({s:{r:r,c:1},e:{r:r,c:3}});
      r++;
    });
    r++; /* blank between sections */
  });

  ws['!ref']=_fmExRange(0,0,r,3);
  ws['!cols']=[{wch:18},{wch:60},{wch:30},{wch:30}];
  ws['!freeze']={ySplit:3};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 01 · ДОПУЩЕНИЯ + WACC (с подсказками)
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddAssumptions(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var asm=m.assumptions||{};
  var sn=ctx.sheets.assum;
  var nCols=3+ctx.nYrs;

  _fmExHeaderStrip(ws,'Допущения · Макро · WACC',ctx.co+' — централизованный лист предположений',nCols,
    'ВХОДНЫЕ ячейки. Меняйте Tax / WACD / инфляцию здесь — каскад через named ranges пересчитает P&L, BS, CF, DSCR.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,_fmFactSet(ctx));

  var rowIdx=4;
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('━━ MACRO ━━');rowIdx++;
  /* Inflation UZ — defaults applied universally */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('infl_uz');
  ws[_fmExAddr(rowIdx,1)]=_fmExStr('Инфляция UZ',_fmExComment('CPI Узбекистана. Бенчмарк 2024-2026: 7-10%. Источник: Госкомстат, ЦБУ.'));
  ws[_fmExAddr(rowIdx,2)]=_fmExStr('%');
  ctx.allYears.forEach(function(y,i){
    var v=(m.macro&&m.macro.inflation&&m.macro.inflation[y]);
    if(v==null)v=0.073; /* universal default — без year-binding */
    ws[_fmExAddr(rowIdx,3+i)]=_fmExNum(v,_FM_FMT.pct);
  });
  rowIdx++;
  /* Inflation US */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('infl_us');
  ws[_fmExAddr(rowIdx,1)]=_fmExStr('Инфляция US',_fmExComment('CPI США. Используется для real terms сравнения. Бенчмарк: 2-3%.'));
  ws[_fmExAddr(rowIdx,2)]=_fmExStr('%');
  ctx.allYears.forEach(function(y,i){
    var v=(m.macro&&m.macro.usInflation&&m.macro.usInflation[y])||0.025;
    ws[_fmExAddr(rowIdx,3+i)]=_fmExNum(v,_FM_FMT.pct);
  });
  rowIdx++;
  /* FX USD */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('fx_usd');
  ws[_fmExAddr(rowIdx,1)]=_fmExStr('FX USD/UZS',_fmExComment('Курс USD/UZS на конец года. На 01.01.2026: ≈12,078. ЦБУ публикует ежедневно.'));
  ws[_fmExAddr(rowIdx,2)]=_fmExStr('UZS');
  ctx.allYears.forEach(function(y,i){
    var v=(m.macro&&m.macro.fx&&m.macro.fx[y])||12078;
    ws[_fmExAddr(rowIdx,3+i)]=_fmExNum(v,_FM_FMT.acc);
  });
  rowIdx+=2;

  /* === ASSUMPTIONS === */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('━━ ASSUMPTIONS ━━');rowIdx++;
  var sv=[
    ['tax_rate',  'Ставка налога на прибыль','%',asm.taxRate||0.15,_FM_FMT.pct,
      'Эффективная ставка налога. Узбекистан стандарт = 15%. Применяется к max(0, PBT). Loss carryforward не моделируется в v1.'],
    ['div_payout','Доля выплаты дивидендов','%',asm.dividendPayout||0.30,_FM_FMT.pct,
      'Payout ratio = Dividends / Net Income. Госпредприятия Узбекистана: 30-50% по постановлению КабМина.'],
    ['terminal_g','Terminal growth rate','%',asm.terminalGrowth||0.03,_FM_FMT.pct,
      'Долгосрочный темп роста для DCF. Бенчмарк: ≤ номинальный рост ВВП. Часто 2-3%.']
  ];
  sv.forEach(function(row){
    ws[_fmExAddr(rowIdx,0)]=_fmExStr(row[0]);
    ws[_fmExAddr(rowIdx,1)]=_fmExStr(row[1],_fmExComment(row[5]));
    ws[_fmExAddr(rowIdx,2)]=_fmExStr(row[2]);
    ws[_fmExAddr(rowIdx,3)]=_fmExNum(row[3],row[4]);
    _fmExAddName(wb,row[0],sn,'$D$'+(rowIdx+1));
    rowIdx++;
  });
  rowIdx++;

  /* === WACC COMPONENTS === */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('━━ WACC COMPONENTS ━━');rowIdx++;
  var waccItems=[
    ['rfr',         'Risk-free rate (CBU)','%',         asm.riskFreeRate||0.14,           _FM_FMT.pct, 'Безрисковая ставка. Используем ставку рефинансирования ЦБУ. На 2026: 14%.'],
    ['beta',        'Beta (industry)','×',              asm.beta||1.0,                    _FM_FMT.unit,'Beta отрасли (Damodaran). Транспорт ~0.8-1.0, добыча ~1.1-1.3, финсектор ~1.0-1.2.'],
    ['mrp',         'Market risk premium','%',          asm.marketRiskPremium||0.06,      _FM_FMT.pct, 'MRP — премия за рыночный риск. Бенчмарк Damodaran для РФ/CIS: 5-7%.'],
    ['country_adj', 'Country risk premium','%',         asm.countryAdjustment||-0.058,    _FM_FMT.pct, 'Страновая корректировка для Узбекистана. Может быть отрицательной (т.к. rfr УЗ уже выше US).'],
    ['cost_debt',   'Effective cost of debt','%',       asm.effectiveCostOfDebt||0.09,    _FM_FMT.pct, 'Стоимость заёмного капитала. Дублирует WACD из "40 Долг" в идеале.'],
    ['debt_ratio',  'Debt / (D+E) target','%',          0.40,                              _FM_FMT.pct, 'Целевая доля долга. Часто 30-50% для зрелых компаний.']
  ];
  waccItems.forEach(function(row){
    ws[_fmExAddr(rowIdx,0)]=_fmExStr(row[0]);
    ws[_fmExAddr(rowIdx,1)]=_fmExStr(row[1],_fmExComment(row[5]));
    ws[_fmExAddr(rowIdx,2)]=_fmExStr(row[2]);
    ws[_fmExAddr(rowIdx,3)]=_fmExNum(row[3],row[4]);
    _fmExAddName(wb,row[0],sn,'$D$'+(rowIdx+1));
    rowIdx++;
  });
  /* Cost of equity — CAPM */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('cost_equity');
  ws[_fmExAddr(rowIdx,1)]=_fmExStr('Cost of equity (CAPM)',_fmExComment('CAPM: Re = rfr + beta × MRP + country adj. Для УЗ ГП с beta=1, MRP=6%, ca=-5.8% → Re ≈ 14.2%.'));
  ws[_fmExAddr(rowIdx,2)]=_fmExStr('%');
  ws[_fmExAddr(rowIdx,3)]={f:'rfr+beta*mrp+country_adj',v:0,t:'n',z:_FM_FMT.pct,c:_fmExComment('Формула: rfr + beta·mrp + country_adj')};
  _fmExAddName(wb,'cost_equity',sn,'$D$'+(rowIdx+1));
  rowIdx++;
  /* WACC */
  ws[_fmExAddr(rowIdx,0)]=_fmExStr('wacc');
  ws[_fmExAddr(rowIdx,1)]=_fmExStr('WACC = w_e·Re + w_d·Rd·(1-tax)',_fmExComment('Финальная WACC. Используется для DCF. Формула учитывает tax shield на debt.'));
  ws[_fmExAddr(rowIdx,2)]=_fmExStr('%');
  ws[_fmExAddr(rowIdx,3)]={f:'(1-debt_ratio)*cost_equity+debt_ratio*cost_debt*(1-tax_rate)',v:0,t:'n',z:_FM_FMT.pct,c:_fmExComment('(1−debt_ratio)·cost_equity + debt_ratio·cost_debt·(1−tax_rate)')};
  _fmExAddName(wb,'wacc',sn,'$D$'+(rowIdx+1));

  ws['!ref']=_fmExRange(0,0,rowIdx+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:38},{wch:8}].concat(ctx.allYears.map(function(){return {wch:13};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

function _fmFactSet(ctx){var s={};ctx.factYears.forEach(function(y){s[y]=1;});return s;}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 10 · ВЫРУЧКА
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddRevenue(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.rev;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Драйверы выручки',ctx.co+' — Volumes × Tariffs · Revenue Total',nCols,
    'ВХОДНЫЕ ячейки. Volumes/Tariffs — для прозрачности. Реальная выручка идёт в P&L через rev_total (последняя строка).');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var r=4;
  ws[_fmExAddr(r,0)]=_fmExStr('━━ VOLUMES ━━',_fmExComment('Натуральные объёмы продукции/услуг. Например: пассажиропоток (тыс.), добыча (тонн), генерация (МВт·ч).'));r++;
  var vols=(m.drivers&&m.drivers.volumes)||[];
  if(vols.length===0){
    ws[_fmExAddr(r,0)]=_fmExStr('—');
    ws[_fmExAddr(r,1)]={v:'Нет драйверов volume. Добавьте строки в редакторе → Драйверы → Объёмы.',t:'s',c:_fmExComment('Volumes — натуральные объёмы продукции/услуг по годам. Каждая строка должна иметь id, name, unit и 9 годовых значений.')};
    r++;
  }else{
    vols.forEach(function(v){
      ws[_fmExAddr(r,0)]=_fmExStr(v.id||('vol_'+r));
      ws[_fmExAddr(r,1)]=_fmExStr(v.name||'',_fmExComment('Volume driver. Изменяется в редакторе → Драйверы → Объёмы.'));
      ws[_fmExAddr(r,2)]=_fmExStr(v.unit||'');
      ctx.allYears.forEach(function(y,i){
        var val=(v.values&&v.values[y]!=null)?v.values[y]:null;
        ws[_fmExAddr(r,3+i)]=_fmExNum(val,_FM_FMT.qty);
      });
      r++;
    });
  }

  r++;
  ws[_fmExAddr(r,0)]=_fmExStr('━━ TARIFFS ━━',_fmExComment('Цены за единицу объёма. Например: тариф на пассажира (UZS), цена за тонну ($), тариф МВт·ч (сум).'));r++;
  var tariffs=(m.drivers&&m.drivers.tariffs)||[];
  if(tariffs.length===0){
    ws[_fmExAddr(r,0)]=_fmExStr('—');
    ws[_fmExAddr(r,1)]={v:'Нет тарифов. Добавьте в редакторе → Драйверы → Тарифы.',t:'s'};
    r++;
  }else{
    tariffs.forEach(function(t){
      ws[_fmExAddr(r,0)]=_fmExStr(t.id||('trf_'+r));
      ws[_fmExAddr(r,1)]=_fmExStr(t.name||'',_fmExComment('Tariff per unit. Изменяется в редакторе.'));
      ws[_fmExAddr(r,2)]=_fmExStr(t.unit||'');
      ctx.allYears.forEach(function(y,i){
        var val=(t.values&&t.values[y]!=null)?t.values[y]:null;
        ws[_fmExAddr(r,3+i)]=_fmExNum(val,_FM_FMT.unit);
      });
      r++;
    });
  }

  r++;
  ws[_fmExAddr(r,0)]=_fmExStr('━━ REVENUE TOTAL (UZSm) ━━',_fmExComment('ИТОГОВАЯ ВЫРУЧКА в UZSm. Это значение идёт в P&L. Если у вас детальные volumes/tariffs — заполните их выше для прозрачности, но revenueDirect здесь — основной источник.'));r++;
  ws[_fmExAddr(r,0)]=_fmExStr('rev_total');
  ws[_fmExAddr(r,1)]=_fmExStr('Итого выручка (используется в P&L)',_fmExComment('rev_<year> named ranges. Используются P&L row 5: =rev_2026, =rev_2027, etc.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var val=(m.revenueDirect&&m.revenueDirect[y]!=null)?m.revenueDirect[y]:null;
    ws[_fmExAddr(r,3+i)]=_fmExNum(val,_FM_FMT.acc);
  });
  ctx.allYears.forEach(function(y,i){
    _fmExAddName(wb,'rev_'+y,sn,'$'+_fmExColLetter(3+i)+'$'+(r+1));
  });
  _fmExAddName(wb,'tbl_revenue',sn,'$D$'+(r+1)+':$'+_fmExColLetter(3+ctx.nYrs-1)+'$'+(r+1));

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:12},{wch:36},{wch:10}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 20 · OPEX
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddOpex(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.opex;
  var nCols=4+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Операционные расходы (OPEX)',ctx.co+' — variable / fixed / D&A',nCols,
    'ВХОДНЫЕ ячейки. type="variable" → COGS · type="fixed" → OPEX · isDA=true → амортизация (не cash).');

  /* Расширенная шапка с Type column */
  ws['A4']=_fmExStr('ID');
  ws['B4']=_fmExStr('Метрика');
  ws['C4']=_fmExStr('Тип',_fmExComment('"variable" → попадает в Себестоимость (COGS). "fixed" → в Операционные расходы. isDA=true → в амортизацию (учитывается отдельно).'));
  ws['D4']=_fmExStr('Ед.');
  ctx.allYears.forEach(function(y,i){
    ws[_fmExAddr(3,4+i)]=_fmExStr(String(y)+(fs[y]?' Ф':' П'));
  });

  var r=4;
  var costs=(m.drivers&&m.drivers.costs)||[];
  function writeGroup(title,filter,hint){
    ws[_fmExAddr(r,0)]=_fmExStr('━━ '+title+' ━━',_fmExComment(hint));r++;
    var anyRows=false;
    costs.filter(filter).forEach(function(c){
      anyRows=true;
      ws[_fmExAddr(r,0)]=_fmExStr(c.id||('cost_'+r));
      ws[_fmExAddr(r,1)]=_fmExStr(c.name||'');
      ws[_fmExAddr(r,2)]=_fmExStr(c.type||'fixed');
      ws[_fmExAddr(r,3)]=_fmExStr(c.unit||'UZSm');
      ctx.allYears.forEach(function(y,i){
        var val=(c.values&&c.values[y]!=null)?c.values[y]:null;
        ws[_fmExAddr(r,4+i)]=_fmExNum(val,_FM_FMT.acc);
      });
      r++;
    });
    if(!anyRows){
      ws[_fmExAddr(r,0)]=_fmExStr('—');
      ws[_fmExAddr(r,1)]={v:'Нет данных. Добавьте в редакторе → Драйверы → Затраты.',t:'s'};
      r++;
    }
    return r;
  }
  var startVar=r;
  writeGroup('VARIABLE COSTS','variable',function(c){return c.type==='variable'&&!c.isDA;},
    'Переменные затраты. Сумма попадает в COGS (себестоимость) в P&L через cogs_<year>.');
  writeGroup('VARIABLE COSTS', function(c){return c.type==='variable'&&!c.isDA;}, 'Переменные затраты → COGS.');
}
function writeGroupOpexFix(){} /* placeholder, не используется */

/* Стандартная версия writeGroup без вспомогательных */
function _fmExAddOpex(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.opex;
  var nCols=4+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Операционные расходы (OPEX)',ctx.co+' — variable / fixed / D&A',nCols,
    'ВХОДНЫЕ ячейки. type="variable" → COGS · type="fixed" → OPEX · isDA=true → амортизация (не cash).');

  ws['A4']=_fmExStr('ID');
  ws['B4']=_fmExStr('Метрика');
  ws['C4']=_fmExStr('Тип',_fmExComment('"variable" → COGS · "fixed" → OPEX · isDA=true → D&A.'));
  ws['D4']=_fmExStr('Ед.');
  ctx.allYears.forEach(function(y,i){
    ws[_fmExAddr(3,4+i)]=_fmExStr(String(y)+(fs[y]?' Ф':' П'));
  });

  var r=4;
  var costs=(m.drivers&&m.drivers.costs)||[];
  function writeGroup(title,filter,hint){
    ws[_fmExAddr(r,0)]=_fmExStr('━━ '+title+' ━━',_fmExComment(hint));r++;
    var any=false;
    costs.filter(filter).forEach(function(c){
      any=true;
      ws[_fmExAddr(r,0)]=_fmExStr(c.id||('cost_'+r));
      ws[_fmExAddr(r,1)]=_fmExStr(c.name||'');
      ws[_fmExAddr(r,2)]=_fmExStr(c.type||'fixed');
      ws[_fmExAddr(r,3)]=_fmExStr(c.unit||'UZSm');
      ctx.allYears.forEach(function(y,i){
        var val=(c.values&&c.values[y]!=null)?c.values[y]:null;
        ws[_fmExAddr(r,4+i)]=_fmExNum(val,_FM_FMT.acc);
      });
      r++;
    });
    if(!any){
      ws[_fmExAddr(r,0)]=_fmExStr('—');
      ws[_fmExAddr(r,1)]={v:'Нет данных в этой группе. Добавьте в редакторе.',t:'s'};
      r++;
    }
  }
  var startVar=r;
  writeGroup('VARIABLE COSTS', function(c){return c.type==='variable'&&!c.isDA;},
    'Переменные затраты. Сумма → cogs_<year> → COGS в P&L.');
  var endVar=r-1;
  r++;
  var startFix=r;
  writeGroup('FIXED COSTS · SG&A', function(c){return c.type!=='variable'&&!c.isDA;},
    'Постоянные затраты + SG&A. Сумма → opex_<year> → OPEX в P&L.');
  var endFix=r-1;
  r++;
  var startDA=r;
  writeGroup('DEPRECIATION & AMORTIZATION', function(c){return c.isDA;},
    'Амортизация. Не cash-расход. Возвращается в CFO в Cash Flow. Сумма → da_<year>.');
  var endDA=r-1;
  r++;

  /* TOTALS via formulas */
  ws[_fmExAddr(r,0)]=_fmExStr('━━ TOTALS ━━');r++;
  ws[_fmExAddr(r,0)]=_fmExStr('cogs_total');
  ws[_fmExAddr(r,1)]=_fmExStr('Себестоимость (variable)',_fmExComment('Сумма всех variable cost rows. Используется в P&L row 6: =0-cogs_<year>.'));
  ws[_fmExAddr(r,2)]=_fmExStr('formula');
  ws[_fmExAddr(r,3)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(4+i);
    var rng=col+(startVar+1+1)+':'+col+(endVar+1);
    ws[_fmExAddr(r,4+i)]={f:'IFERROR(SUM('+rng+'),0)',v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'cogs_'+y,sn,'$'+col+'$'+(r+1));
  });
  r++;
  ws[_fmExAddr(r,0)]=_fmExStr('opex_total');
  ws[_fmExAddr(r,1)]=_fmExStr('OPEX (fixed + SG&A)',_fmExComment('Сумма всех fixed cost rows. → opex_<year> в P&L.'));
  ws[_fmExAddr(r,2)]=_fmExStr('formula');
  ws[_fmExAddr(r,3)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(4+i);
    var rng=col+(startFix+1+1)+':'+col+(endFix+1);
    ws[_fmExAddr(r,4+i)]={f:'IFERROR(SUM('+rng+'),0)',v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'opex_'+y,sn,'$'+col+'$'+(r+1));
  });
  r++;
  ws[_fmExAddr(r,0)]=_fmExStr('da_total');
  ws[_fmExAddr(r,1)]=_fmExStr('Амортизация (D&A)',_fmExComment('Сумма всех isDA=true rows. → da_<year>. Возвращается в CFO в Cash Flow (как non-cash add-back).'));
  ws[_fmExAddr(r,2)]=_fmExStr('formula');
  ws[_fmExAddr(r,3)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(4+i);
    var rng=col+(startDA+1+1)+':'+col+(endDA+1);
    ws[_fmExAddr(r,4+i)]={f:'IFERROR(SUM('+rng+'),0)',v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'da_'+y,sn,'$'+col+'$'+(r+1));
  });

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:36},{wch:11},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:4,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 30 · CAPEX + WC
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddCapexWc(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.capex;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'CAPEX · Working Capital',ctx.co+' — инвестиции и оборотный капитал',nCols,
    'ВХОДНЫЕ ячейки. CAPEX → Cash Flow Investing. NWC days → BS Net Working Capital.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var r=4;
  ws[_fmExAddr(r,0)]=_fmExStr('━━ CAPEX ━━',_fmExComment('Капитальные вложения по годам. Учитываются в PP&E roll-forward и в CFI.'));r++;
  var capex=(m.drivers&&m.drivers.capex)||[];
  var startCx=r;
  if(capex.length===0){
    ws[_fmExAddr(r,0)]=_fmExStr('—');
    ws[_fmExAddr(r,1)]={v:'Нет CAPEX. Добавьте в редакторе → Драйверы → CAPEX.',t:'s'};
    r++;
  }else{
    capex.forEach(function(c){
      ws[_fmExAddr(r,0)]=_fmExStr(c.id||('cx_'+r));
      ws[_fmExAddr(r,1)]=_fmExStr(c.name||'',_fmExComment('CAPEX category. Несколько категорий суммируются в capex_<year>.'));
      ws[_fmExAddr(r,2)]=_fmExStr(c.unit||'UZSm');
      ctx.allYears.forEach(function(y,i){
        var val=(c.values&&c.values[y]!=null)?c.values[y]:null;
        ws[_fmExAddr(r,3+i)]=_fmExNum(val,_FM_FMT.acc);
      });
      r++;
    });
  }
  var endCx=r-1;
  ws[_fmExAddr(r,0)]=_fmExStr('capex_total');
  ws[_fmExAddr(r,1)]=_fmExStr('CAPEX total (формула)',_fmExComment('Сумма всех categories. → capex_<year> → используется в CFI и PP&E roll.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    var rng=col+(startCx+1)+':'+col+(endCx+1);
    ws[_fmExAddr(r,3+i)]={f:'IFERROR(SUM('+rng+'),0)',v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'capex_'+y,sn,'$'+col+'$'+(r+1));
  });
  r+=2;

  ws[_fmExAddr(r,0)]=_fmExStr('━━ WORKING CAPITAL · TURNOVER DAYS ━━',_fmExComment('Дни оборачиваемости. NWC = (DSO/365)·Rev + (DIO/365)·COGS − (DPO/365)·COGS − (DAP/365)·Rev. Применяется в BS row 5.'));r++;
  var wc=(m.drivers&&m.drivers.wc)||{dso:30,dio:20,dpo:40,dap:15};
  var wcRows=[
    ['dso','Days Sales Outstanding (DSO)','дней',wc.dso||30,'Дни в дебиторке. Бенчмарк: транспорт 30-45, B2B услуги 45-60.'],
    ['dio','Days Inventory Outstanding (DIO)','дней',wc.dio||20,'Дни в запасах. Бенчмарк: услуги 0-10, добыча 30-60, ритейл 30-45.'],
    ['dpo','Days Payables Outstanding (DPO)','дней',wc.dpo||40,'Дни в кредиторке. Бенчмарк: 30-60. Высокий DPO = эконом-эффект.'],
    ['dap','Days Advances Paid (DAP)','дней',wc.dap||15,'Авансы выданные. Часто 0-30 для большинства отраслей.']
  ];
  wcRows.forEach(function(row){
    ws[_fmExAddr(r,0)]=_fmExStr(row[0]);
    ws[_fmExAddr(r,1)]=_fmExStr(row[1],_fmExComment(row[4]));
    ws[_fmExAddr(r,2)]=_fmExStr(row[2]);
    ws[_fmExAddr(r,3)]=_fmExNum(row[3],_FM_FMT.qty);
    _fmExAddName(wb,row[0],sn,'$D$'+(r+1));
    r++;
  });

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:36},{wch:10}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 40 · ДОЛГ
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddDebt(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.debt;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'График долга',ctx.co+' — Long-term · Short-term · WACD',nCols,
    'ВХОДНЫЕ: LT/ST debt + WACD. WACD играет двойную роль: процентные расходы и discount rate для LLCR/PLCR.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var r=4;
  ws[_fmExAddr(r,0)]=_fmExStr('━━ AGGREGATED DEBT SCHEDULE (UZSm) ━━',_fmExComment('LT/ST debt — closing balance каждого года. Принципалы вычисляются как разница YoY.'));r++;
  var debt=m.drivers&&m.drivers.debt||{ltDebt:{},stDebt:{},interestRate:0.09};
  
  var ltRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('lt_debt');
  ws[_fmExAddr(r,1)]=_fmExStr('Долгосрочный долг',_fmExComment('Длинные кредиты: > 1 года. Заполняется на конец каждого года.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var v=(debt.ltDebt&&debt.ltDebt[y]!=null)?debt.ltDebt[y]:null;
    ws[_fmExAddr(r,3+i)]=_fmExNum(v,_FM_FMT.acc);
    _fmExAddName(wb,'lt_'+y,sn,'$'+_fmExColLetter(3+i)+'$'+ltRow);
  });
  r++;
  
  var stRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('st_debt');
  ws[_fmExAddr(r,1)]=_fmExStr('Краткосрочный долг',_fmExComment('Короткие кредиты + текущая часть LT. Срок ≤ 1 года.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var v=(debt.stDebt&&debt.stDebt[y]!=null)?debt.stDebt[y]:null;
    ws[_fmExAddr(r,3+i)]=_fmExNum(v,_FM_FMT.acc);
    _fmExAddName(wb,'st_'+y,sn,'$'+_fmExColLetter(3+i)+'$'+stRow);
  });
  r++;
  
  var totalDebtRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('total_debt');
  ws[_fmExAddr(r,1)]=_fmExStr('Всего долг (формула)',_fmExComment('LT + ST. → totdebt_<year> используется в BS row 12 и Coverage.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    ws[_fmExAddr(r,3+i)]={f:col+ltRow+'+'+col+stRow,v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'totdebt_'+y,sn,'$'+col+'$'+totalDebtRow);
  });
  r+=2;

  var wacdRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('wacd');
  ws[_fmExAddr(r,1)]=_fmExStr('Эффективная ставка (WACD)',_fmExComment('Weighted Average Cost of Debt. Эффективная ставка по портфелю кредитов.\nДВОЙНАЯ РОЛЬ: (1) interest expense в P&L = avg debt × wacd. (2) discount rate для NPV в LLCR/PLCR.\nТипично 7-12% для УЗ.'));
  ws[_fmExAddr(r,2)]=_fmExStr('%');
  ws[_fmExAddr(r,3)]=_fmExNum(debt.interestRate||0.09,_FM_FMT.pct);
  _fmExAddName(wb,'wacd',sn,'$D$'+wacdRow);
  r+=2;

  var principalRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('principal');
  ws[_fmExAddr(r,1)]=_fmExStr('Погашение основного долга',_fmExComment('Principal repayment = max(0, prev_debt − cur_debt). Положительное число = погашение. Если долг растёт — 0 (наращивание учтено в Δ Debt в CFF).'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    var prevCol=i>0?_fmExColLetter(3+i-1):null;
    if(prevCol){
      ws[_fmExAddr(r,3+i)]={f:'MAX(0,'+prevCol+totalDebtRow+'-'+col+totalDebtRow+')',v:0,t:'n',z:_FM_FMT.acc};
    }else{
      ws[_fmExAddr(r,3+i)]=_fmExNum(0,_FM_FMT.acc);
    }
    _fmExAddName(wb,'principal_'+y,sn,'$'+col+'$'+principalRow);
  });
  r++;
  
  var interestRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('interest');
  ws[_fmExAddr(r,1)]=_fmExStr('Процентные расходы (формула)',_fmExComment('Interest = avg(debt[y-1], debt[y]) × WACD. Используется в P&L Fin Cost.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    var prevCol=i>0?_fmExColLetter(3+i-1):null;
    if(prevCol){
      ws[_fmExAddr(r,3+i)]={f:'(('+col+totalDebtRow+'+'+prevCol+totalDebtRow+')/2)*wacd',v:0,t:'n',z:_FM_FMT.acc};
    }else{
      ws[_fmExAddr(r,3+i)]={f:col+totalDebtRow+'*wacd',v:0,t:'n',z:_FM_FMT.acc};
    }
    _fmExAddName(wb,'interest_'+y,sn,'$'+col+'$'+interestRow);
  });
  r++;
  
  var debtSvcRow=r+1;
  ws[_fmExAddr(r,0)]=_fmExStr('debt_service');
  ws[_fmExAddr(r,1)]=_fmExStr('Обслуживание долга (Interest + Principal)',_fmExComment('Полное обслуживание долга для DSCR knaminator. → debtsvc_<year>. Используется в Coverage row 6.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    ws[_fmExAddr(r,3+i)]={f:col+principalRow+'+'+col+interestRow,v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'debtsvc_'+y,sn,'$'+col+'$'+debtSvcRow);
  });

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:38},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 50 · СОБСТВЕННЫЙ КАПИТАЛ
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddEquity(ctx){
  var ws={};
  var wb=ctx.wb;
  var m=ctx.model;
  var sn=ctx.sheets.equity;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Собственный капитал',ctx.co+' — Share capital · Opening BS values',nCols,
    'ВХОДНЫЕ: уставный капитал по годам + opening balances. Opening_PPE критично для balance opening BS!');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var r=4;
  ws[_fmExAddr(r,0)]=_fmExStr('share_capital');
  ws[_fmExAddr(r,1)]=_fmExStr('Уставный капитал',_fmExComment('Issued share capital по годам. Обычно стабильно — растёт только при допэмиссии.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  var eq=m.drivers&&m.drivers.equity||{};
  ctx.allYears.forEach(function(y,i){
    var v=(eq.shareCapital&&eq.shareCapital[y]!=null)?eq.shareCapital[y]:null;
    ws[_fmExAddr(r,3+i)]=_fmExNum(v,_FM_FMT.acc);
    _fmExAddName(wb,'sharecap_'+y,sn,'$'+_fmExColLetter(3+i)+'$'+(r+1));
  });
  r+=2;

  ws[_fmExAddr(r,0)]=_fmExStr('━━ OPENING BALANCE SHEET ━━',_fmExComment('Начальные значения BS на момент start of forecast. КРИТИЧНО для balance integrity!\nФормула: Opening Cash + Opening PP&E + Opening NWC = Opening Debt + Share Capital + Opening RE.\nЕсли opening_ppe = 0, BS первого года не сходится.'));r++;

  ws[_fmExAddr(r,0)]=_fmExStr('opening_cash');
  ws[_fmExAddr(r,1)]=_fmExStr('Начальный остаток денежных средств',_fmExComment('Cash на начало периода (= конец предыдущего года). Из последней отчётности.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ws[_fmExAddr(r,3)]=_fmExNum(eq.openingCash||0,_FM_FMT.acc);
  _fmExAddName(wb,'opening_cash',sn,'$D$'+(r+1));
  r++;
  
  ws[_fmExAddr(r,0)]=_fmExStr('opening_re');
  ws[_fmExAddr(r,1)]=_fmExStr('Начальная нераспределённая прибыль',_fmExComment('Retained Earnings на начало периода. Из BS последней отчётности.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ws[_fmExAddr(r,3)]=_fmExNum(eq.openingRE||0,_FM_FMT.acc);
  _fmExAddName(wb,'opening_re',sn,'$D$'+(r+1));
  r++;
  
  ws[_fmExAddr(r,0)]=_fmExStr('opening_ppe');
  ws[_fmExAddr(r,1)]=_fmExStr('Начальные основные средства (PP&E)',_fmExComment('⚠ КРИТИЧНО! Без этого BS не сойдётся первый год.\nФормула balance: opening_ppe ≈ share_capital + opening_re + opening_debt − opening_cash.\nЕсли не известно точно — введите balancing значение.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ws[_fmExAddr(r,3)]=_fmExNum(eq.openingPPE||0,_FM_FMT.acc);
  _fmExAddName(wb,'opening_ppe',sn,'$D$'+(r+1));

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:42},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 70 · P&L
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddPnL(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.pnl;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Отчёт о прибылях и убытках (P&L)',ctx.co+' — формулы read-only',nCols,
    '⚠ ФОРМУЛЫ — НЕ ТРОГАТЬ. Все ячейки ссылаются на named ranges из листов 10/20/30/40.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var rows=[
    {id:'revenue',  lbl:'Выручка',                   unit:'UZSm', fOf:function(y){return 'rev_'+y;}, c:'rev_<year> из "10 Выручка". Если 0 — заполните rev_total там.'},
    {id:'cogs',     lbl:'Себестоимость (-)',          unit:'UZSm', fOf:function(y){return '-cogs_'+y;}, c:'cogs_<year> из "20 OPEX" — сумма variable costs.'},
    {id:'grossp',   lbl:'Валовая прибыль',            unit:'UZSm', fOf:function(y,col,r){return col+(r-1)+'+'+col+r;}, c:'Revenue + COGS (где COGS уже отрицательный).'},
    {id:'opex',     lbl:'Операционные расходы (-)',   unit:'UZSm', fOf:function(y){return '-opex_'+y;}, c:'opex_<year> из "20 OPEX" — сумма fixed costs.'},
    {id:'da',       lbl:'Амортизация (-)',            unit:'UZSm', fOf:function(y){return '-da_'+y;}, c:'da_<year> из "20 OPEX" — сумма isDA=true rows.'},
    {id:'opprofit', lbl:'Операционная прибыль',       unit:'UZSm', fOf:function(y,col,r){return col+(r-2)+'+'+col+(r-1)+'+'+col+r;}, c:'Gross + OPEX + D&A (последние два уже отрицательные).'},
    {id:'fincost',  lbl:'Финансовые расходы (-)',     unit:'UZSm', fOf:function(y){return '-interest_'+y;}, c:'interest_<year> из "40 Долг". Avg debt × WACD.'},
    {id:'pbt',      lbl:'Прибыль до налогов',          unit:'UZSm', fOf:function(y,col,r){return col+(r-1)+'+'+col+r;}, c:'Op Profit − Fin Cost.'},
    {id:'tax',      lbl:'Налог на прибыль (-)',        unit:'UZSm', fOf:function(y,col,r){return '-MAX(0,'+col+r+')*tax_rate';}, c:'Применяется только к положительной PBT (loss carryforward не моделируется).'},
    {id:'netinc',   lbl:'Чистая прибыль',             unit:'UZSm', fOf:function(y,col,r){return col+(r-1)+'+'+col+r;}, c:'PBT − Tax. → используется в RE roll и CFO.'},
    {id:'spacer1',  lbl:'',                           unit:'',     fOf:null},
    {id:'ebitda',   lbl:'EBITDA',                     unit:'UZSm', fOf:function(y){return 'EBITDA_PLACEHOLDER';}, c:'Op Profit + D&A. Используется в DSCR/LLCR.'}
  ];

  rows.forEach(function(row,idx){
    var r=4+idx;
    ws[_fmExAddr(r,0)]=_fmExStr(row.id||'');
    ws[_fmExAddr(r,1)]=_fmExStr(row.lbl||'',row.c?_fmExComment(row.c):null);
    ws[_fmExAddr(r,2)]=_fmExStr(row.unit||'');
    if(!row.fOf){return;}
    ctx.allYears.forEach(function(y,i){
      var col=_fmExColLetter(3+i);
      var formula=row.fOf(y,col,r);
      if(row.id==='ebitda'){
        var opRow=4+5+1; /* opprofit at idx 5 → Excel row 10 */
        formula=col+opRow+'+da_'+y;
      }
      if(formula.charAt(0)==='-'){formula='0'+formula;}
      ws[_fmExAddr(r,3+i)]={f:formula,v:0,t:'n',z:_FM_FMT.acc};
    });
    if(row.id&&row.id!=='spacer1'){
      ctx.allYears.forEach(function(y,i){
        var col=_fmExColLetter(3+i);
        _fmExAddName(wb,row.id+'_'+y,sn,'$'+col+'$'+(r+1));
      });
    }
  });

  ws['!ref']=_fmExRange(0,0,4+rows.length+2,nCols-1);
  ws['!cols']=[{wch:12},{wch:36},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 71 · BALANCE SHEET
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddBalanceSheet(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.bs;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Баланс (Balance Sheet)',ctx.co+' — формулы · BS check',nCols,
    '⚠ ФОРМУЛЫ — НЕ ТРОГАТЬ. BS check (row 21) должен быть OK для всех лет. Если BREAK — проверьте opening_ppe.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var R={
    nwc:5, cash:6, ppe:7, totalAssets:8,
    lt:10, st:11, totalDebt:12, netDebt:13,
    shareCap:15, re:16, totalEquity:17, totalLieq:19,
    bsCheck:21
  };

  function writeRow(rowExcel, id, lbl, unit, formulaFn, comment){
    var rIdx=rowExcel-1;
    ws[_fmExAddr(rIdx,0)]=_fmExStr(id);
    ws[_fmExAddr(rIdx,1)]=_fmExStr(lbl,comment?_fmExComment(comment):null);
    ws[_fmExAddr(rIdx,2)]=_fmExStr(unit);
    ctx.allYears.forEach(function(y,i){
      var col=_fmExColLetter(3+i);
      var f=formulaFn(y,col,i);
      ws[_fmExAddr(rIdx,3+i)]={f:f,v:0,t:'n',z:_FM_FMT.acc};
      if(id) _fmExAddName(wb,'bs_'+id+'_'+y,sn,'$'+col+'$'+rowExcel);
    });
  }

  writeRow(R.nwc,'nwc','NWC = DSO/365·Rev + DIO/365·COGS − DPO/365·COGS − DAP/365·Rev','UZSm',
    function(y){return '(dso/365)*rev_'+y+'+(dio/365)*cogs_'+y+'-(dpo/365)*cogs_'+y+'-(dap/365)*rev_'+y;},
    'Net Working Capital. Положительное → деньги связаны в обороте. ΔNWC идёт в CFO.');

  writeRow(R.cash,'cash','Денежные средства (Cash)','UZSm',
    function(y,col,i){
      var s='opening_cash';
      for(var j=0;j<=i;j++) s+='+netcc_'+ctx.allYears[j];
      return s;
    },
    'Cash[y] = opening_cash + cumulative netcc до года y. Должен совпадать с CF cash_end (tie-out).');

  writeRow(R.ppe,'ppe','Основные средства (PP&E) — roll-forward','UZSm',
    function(y,col,i){
      if(i===0) return 'MAX(0,opening_ppe+capex_'+y+'-da_'+y+')';
      var prevCol=_fmExColLetter(3+i-1);
      return 'MAX(0,'+prevCol+R.ppe+'+capex_'+y+'-da_'+y+')';
    },
    'PP&E[y] = max(0, prev_PPE + CAPEX − D&A). Roll-forward. Первый год использует opening_ppe.');

  writeRow(R.totalAssets,'total_assets','Всего активы','UZSm',
    function(y,col){return 'MAX(0,'+col+R.nwc+')+'+col+R.cash+'+'+col+R.ppe;},
    'Total Assets = MAX(0,NWC) + Cash + PP&E. Если NWC < 0 → переходит в обязательства.');

  writeRow(R.lt,'lt_dbt_ref','Долгосрочный долг (из 40)','UZSm',
    function(y){return 'lt_'+y;},
    'Reference на lt_<year> из "40 Долг".');

  writeRow(R.st,'st_dbt_ref','Краткосрочный долг (из 40)','UZSm',
    function(y){return 'st_'+y;},
    'Reference на st_<year> из "40 Долг".');

  writeRow(R.totalDebt,'total_debt','Всего долг','UZSm',
    function(y){return 'totdebt_'+y;},
    'Reference на totdebt_<year>. = LT + ST.');

  writeRow(R.netDebt,'net_debt','Чистый долг (Total Debt − Cash)','UZSm',
    function(y,col){return col+R.totalDebt+'-'+col+R.cash;},
    'Net Debt = Total Debt − Cash. Может быть отрицательной = чистая денежная позиция.');

  writeRow(R.shareCap,'share_cap','Уставный капитал (из 50)','UZSm',
    function(y){return 'sharecap_'+y;},
    'Reference на sharecap_<year>.');

  writeRow(R.re,'re','Нераспределённая прибыль (roll-forward)','UZSm',
    function(y,col,i){
      var s='opening_re';
      for(var j=0;j<=i;j++){
        var yy=ctx.allYears[j];
        s+='+netinc_'+yy+'-MAX(0,netinc_'+yy+')*div_payout';
      }
      return s;
    },
    'RE[y] = opening_re + cumulative (NI − Dividends). Dividends = max(0, NI) × div_payout.');

  writeRow(R.totalEquity,'total_equity','Всего собственный капитал','UZSm',
    function(y,col){return col+R.shareCap+'+'+col+R.re;},
    'Equity = Share Capital + RE.');

  writeRow(R.totalLieq,'total_lieq','Всего обязательства + капитал','UZSm',
    function(y,col){return col+R.totalDebt+'+'+col+R.totalEquity+'+MAX(0,-'+col+R.nwc+')';},
    'Total Liab + Equity = Debt + Equity + MAX(0, −NWC). Должен равняться Total Assets.');

  /* BS check */
  var rIdx=R.bsCheck-1;
  ws[_fmExAddr(rIdx,0)]=_fmExStr('BS CHECK');
  ws[_fmExAddr(rIdx,1)]=_fmExStr('|Assets − LiabEq| < 1 → OK',_fmExComment('Если все ячейки = OK, BS сходится. Если BREAK — модель не сходится. Чаще всего проблема в opening_ppe (см. "50 Капитал").'));
  ws[_fmExAddr(rIdx,2)]=_fmExStr('OK?');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    ws[_fmExAddr(rIdx,3+i)]={f:'IF(ABS('+col+R.totalAssets+'-'+col+R.totalLieq+')<1,"OK","BREAK")',v:'',t:'s'};
  });

  ws['!ref']=_fmExRange(0,0,R.bsCheck+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:48},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
  ctx.bsRows=R;
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 72 · CASH FLOW
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddCashFlow(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.cf;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Отчёт о движении денежных средств',ctx.co+' — CFO + CFI + CFF · Cash tie-out',nCols,
    '⚠ ФОРМУЛЫ. Cash tie-out (row 22) должен быть OK. DRIFT = расхождение между CF Cash и BS Cash.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var R={
    niRef:5, daRef:6, dnwc:7, cfo:8,
    capexRef:10, cfi:11,
    ddebt:13, div:14, cff:15,
    netcc:17, cashEnd:19,
    tieOut:22
  };

  function writeCfRow(rowExcel, id, lbl, unit, formulaFn, namedRangePrefix, comment){
    var rIdx=rowExcel-1;
    ws[_fmExAddr(rIdx,0)]=_fmExStr(id);
    ws[_fmExAddr(rIdx,1)]=_fmExStr(lbl,comment?_fmExComment(comment):null);
    ws[_fmExAddr(rIdx,2)]=_fmExStr(unit);
    ctx.allYears.forEach(function(y,i){
      var col=_fmExColLetter(3+i);
      var f=formulaFn(y,col,i);
      if(f.charAt(0)==='-') f='0'+f;
      ws[_fmExAddr(rIdx,3+i)]={f:f,v:0,t:'n',z:_FM_FMT.acc};
      if(namedRangePrefix){
        _fmExAddName(wb,namedRangePrefix+'_'+y,sn,'$'+col+'$'+rowExcel);
      }
    });
  }

  writeCfRow(R.niRef,'ni_ref','Чистая прибыль (из 70)','UZSm',
    function(y){return 'netinc_'+y;}, 'cf_ni', 'Reference на netinc_<year> из P&L.');
  writeCfRow(R.daRef,'da_ref','+ Амортизация','UZSm',
    function(y){return 'da_'+y;}, 'cf_da', 'D&A добавляется обратно — это non-cash расход.');
  writeCfRow(R.dnwc,'dnwc','− ΔNWC','UZSm',
    function(y,col,i){
      if(i===0) return '-bs_nwc_'+y;
      return '-(bs_nwc_'+y+'-bs_nwc_'+ctx.allYears[i-1]+')';
    }, 'cf_dnwc', 'Изменение NWC. Если NWC растёт — отток (минус). Если уменьшается — приток.');
  writeCfRow(R.cfo,'cfo','CFO (Operating Cash Flow)','UZSm',
    function(y,col){return col+R.niRef+'+'+col+R.daRef+'+'+col+R.dnwc;}, 'cf_cfo',
    'Cash Flow from Operations = NI + D&A − ΔNWC.');

  writeCfRow(R.capexRef,'capex_ref','− CAPEX','UZSm',
    function(y){return '-capex_'+y;}, 'cf_capex', 'CAPEX — единственный invested cash flow в простой модели.');
  writeCfRow(R.cfi,'cfi','CFI (Investing Cash Flow)','UZSm',
    function(y,col){return col+R.capexRef;}, 'cf_cfi', 'Cash Flow from Investing = −CAPEX.');

  writeCfRow(R.ddebt,'ddebt','Δ Debt','UZSm',
    function(y,col,i){
      if(i===0) return 'totdebt_'+y;
      return 'totdebt_'+y+'-totdebt_'+ctx.allYears[i-1];
    }, 'cf_ddebt', 'Изменение долга YoY. + = привлекли, − = погасили.');
  writeCfRow(R.div,'div','− Дивиденды','UZSm',
    function(y){return '-MAX(0,netinc_'+y+')*div_payout';}, 'cf_div', 'Dividends = max(0, NI) × div_payout. Только из положительной NI.');
  writeCfRow(R.cff,'cff','CFF (Financing Cash Flow)','UZSm',
    function(y,col){return col+R.ddebt+'+'+col+R.div;}, 'cf_cff', 'Cash Flow from Financing = ΔDebt − Dividends.');

  writeCfRow(R.netcc,'netcc','Net cash change','UZSm',
    function(y,col){return col+R.cfo+'+'+col+R.cfi+'+'+col+R.cff;}, 'netcc',
    'Net Cash Change = CFO + CFI + CFF. Используется в BS Cash roll: Cash[y] = opening_cash + Σ netcc.');

  writeCfRow(R.cashEnd,'cash_end','Cash на конец периода (из BS)','UZSm',
    function(y){return 'bs_cash_'+y;}, 'cf_cashend', 'Reference на bs_cash_<year>.');

  /* Tie-out */
  var rIdx=R.tieOut-1;
  ws[_fmExAddr(rIdx,0)]=_fmExStr('CASH TIE-OUT');
  ws[_fmExAddr(rIdx,1)]=_fmExStr('|CF[end] − BS[Cash]| < 1 → OK',_fmExComment('Должно быть OK. DRIFT = логическая ошибка в Cash Flow или Balance Sheet.'));
  ws[_fmExAddr(rIdx,2)]=_fmExStr('check');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    var cumNetcc='opening_cash';
    for(var j=0;j<=i;j++){cumNetcc+='+netcc_'+ctx.allYears[j];}
    ws[_fmExAddr(rIdx,3+i)]={f:'IF(ABS(bs_cash_'+y+'-('+cumNetcc+'))<1,"OK","DRIFT")',v:'',t:'s'};
  });

  ws['!ref']=_fmExRange(0,0,R.tieOut+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:46},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 80 · COVERAGE
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddCoverage(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.cov;
  var nCols=3+ctx.nYrs;
  var fs=_fmFactSet(ctx);

  _fmExHeaderStrip(ws,'Покрытие долга — DSCR · LLCR · PLCR (IFI standard)',ctx.co+' — covenant ≥ 1.20×',nCols,
    '⚠ ФОРМУЛЫ. DSCR < 1.00× = covenant breach. IFI стандарт: DSCR ≥ 1.20×, LLCR ≥ 1.30×.');
  _fmExYearHeaders(ws,3,3,ctx.allYears,fs);

  var r=4;
  ws[_fmExAddr(r,0)]=_fmExStr('cfads');
  ws[_fmExAddr(r,1)]=_fmExStr('CFADS = EBITDA − Tax − ΔWC − CAPEX',_fmExComment('Cash Flow Available for Debt Service. Project finance стандарт. Числитель DSCR.'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    var dnwcExpr=(i===0)?'bs_nwc_'+y:'(bs_nwc_'+y+'-bs_nwc_'+ctx.allYears[i-1]+')';
    var formula='ebitda_'+y+'-MAX(0,pbt_'+y+')*tax_rate-'+dnwcExpr+'-capex_'+y;
    ws[_fmExAddr(r,3+i)]={f:formula,v:0,t:'n',z:_FM_FMT.acc};
    _fmExAddName(wb,'cfads_'+y,sn,'$'+col+'$'+(r+1));
  });
  r++;

  ws[_fmExAddr(r,0)]=_fmExStr('debt_svc_ref');
  ws[_fmExAddr(r,1)]=_fmExStr('Debt service (Interest + Principal)',_fmExComment('Знаменатель DSCR. Reference на debtsvc_<year> из "40 Долг".'));
  ws[_fmExAddr(r,2)]=_fmExStr('UZSm');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    ws[_fmExAddr(r,3+i)]={f:'debtsvc_'+y,v:0,t:'n',z:_FM_FMT.acc};
  });
  r++;

  ws[_fmExAddr(r,0)]=_fmExStr('dscr');
  ws[_fmExAddr(r,1)]=_fmExStr('DSCR = CFADS / Debt Service',_fmExComment('Per-period coverage ratio. IFI covenant ≥ 1.20×. Если debt service = 0 — DSCR = 0 (как защита от деления на ноль).'));
  ws[_fmExAddr(r,2)]=_fmExStr('×');
  ctx.allYears.forEach(function(y,i){
    var col=_fmExColLetter(3+i);
    ws[_fmExAddr(r,3+i)]={f:'IF(debtsvc_'+y+'<=0,0,cfads_'+y+'/debtsvc_'+y+')',v:0,t:'n',z:_FM_FMT.ratio};
    _fmExAddName(wb,'dscr_'+y,sn,'$'+col+'$'+(r+1));
  });
  r+=2;

  ws[_fmExAddr(r,0)]=_fmExStr('━━ SUMMARY ━━');r++;
  var firstFcCol=ctx.fcYears.length?_fmExColLetter(3+ctx.nFact):'D';
  var lastFcCol=ctx.fcYears.length?_fmExColLetter(3+ctx.nYrs-1):'D';
  var dscrRow=4+2+1;

  ws[_fmExAddr(r,0)]=_fmExStr('dscr_min');
  ws[_fmExAddr(r,1)]=_fmExStr('DSCR Min (forecast years)',_fmExComment('Минимум DSCR по прогнозным годам. По нему IFI проверяют covenant compliance.'));
  ws[_fmExAddr(r,2)]=_fmExStr('×');
  ws[_fmExAddr(r,3)]={f:'MIN('+firstFcCol+dscrRow+':'+lastFcCol+dscrRow+')',v:0,t:'n',z:_FM_FMT.ratio};
  _fmExAddName(wb,'dscr_min',sn,'$D$'+(r+1));
  r++;

  ws[_fmExAddr(r,0)]=_fmExStr('dscr_avg');
  ws[_fmExAddr(r,1)]=_fmExStr('DSCR Avg (forecast years)',_fmExComment('Среднее DSCR. Не заменяет Min для covenants, но даёт overall picture.'));
  ws[_fmExAddr(r,2)]=_fmExStr('×');
  ws[_fmExAddr(r,3)]={f:'AVERAGE('+firstFcCol+dscrRow+':'+lastFcCol+dscrRow+')',v:0,t:'n',z:_FM_FMT.ratio};
  _fmExAddName(wb,'dscr_avg',sn,'$D$'+(r+1));
  r++;

  ws[_fmExAddr(r,0)]=_fmExStr('llcr');
  ws[_fmExAddr(r,1)]=_fmExStr('LLCR = NPV(CFADS, WACD) / Outstanding debt at start',_fmExComment('Loan Life Coverage. Forward-looking aggregate. IFI standard ≥ 1.30×. WACD используется для дисконтирования.'));
  ws[_fmExAddr(r,2)]=_fmExStr('×');
  var cfadsRow=4+1;
  if(ctx.fcYears.length){
    var startDebtCell="totdebt_"+ctx.fcYears[0];
    ws[_fmExAddr(r,3)]={f:'IF('+startDebtCell+'<=0,0,NPV(wacd,'+firstFcCol+cfadsRow+':'+lastFcCol+cfadsRow+')/'+startDebtCell+')',v:0,t:'n',z:_FM_FMT.ratio};
  }else{
    ws[_fmExAddr(r,3)]=_fmExNum(0,_FM_FMT.ratio);
  }
  _fmExAddName(wb,'llcr',sn,'$D$'+(r+1));
  r++;

  ws[_fmExAddr(r,0)]=_fmExStr('plcr');
  ws[_fmExAddr(r,1)]=_fmExStr('PLCR = NPV(CFADS) / Debt — project life',_fmExComment('Project Life Coverage. Аналогично LLCR, но за весь forecast horizon. PLCR ≥ LLCR обычно.'));
  ws[_fmExAddr(r,2)]=_fmExStr('×');
  ws[_fmExAddr(r,3)]={f:'llcr',v:0,t:'n',z:_FM_FMT.ratio};
  _fmExAddName(wb,'plcr',sn,'$D$'+(r+1));
  r+=2;

  ws[_fmExAddr(r,0)]=_fmExStr('━━ COVENANT ZONES ━━');r++;
  var zones=[
    ['≥ 1.30×',     'Комфорт — IFC/EBRD/ADB одобрят без conditions'],
    ['1.10–1.30×',  'Зона covenant — большинство DFI требуют ≥ 1.20× как минимум'],
    ['1.00–1.10×',  'Тонко — DSCR положительный, но buffer минимальный'],
    ['< 1.00×',     'COVENANT BREACH — технический дефолт']
  ];
  zones.forEach(function(z){
    ws[_fmExAddr(r,0)]=_fmExStr(z[0]);
    ws[_fmExAddr(r,1)]=_fmExStr(z[1]);
    r++;
  });

  ws['!ref']=_fmExRange(0,0,r+2,nCols-1);
  ws['!cols']=[{wch:14},{wch:54},{wch:8}].concat(ctx.allYears.map(function(){return {wch:14};}));
  ws['!freeze']={xSplit:3,ySplit:4};
  XLSX.utils.book_append_sheet(wb,ws,sn);
}

/* ════════════════════════════════════════════════════════════════════════════
   ЛИСТ 99 · AUDIT TRAIL
   ════════════════════════════════════════════════════════════════════════════ */
function _fmExAddAuditTrail(ctx){
  var ws={};
  var wb=ctx.wb;
  var sn=ctx.sheets.audit;

  ws['A1']=_fmExStr('Audit trail · Версия модели');
  ws['A2']=_fmExStr(ctx.co+' — журнал изменений и ограничений');
  ws['!merges']=[{s:{r:0,c:0},e:{r:0,c:3}},{s:{r:1,c:0},e:{r:1,c:3}}];

  var trail=[
    ['━━ ВЕРСИЯ ━━',''],
    ['Версия шаблона','v1.0 (с tooltips, Инструкции, Status panel)'],
    ['Дата экспорта',new Date().toISOString()],
    ['Компания',ctx.co],
    ['Сценарий',ctx.scn],
    ['Платформа','UzAssets · единая платформа трансформации'],
    ['Источник данных','_db.finModel · Firebase RTDB'],
    ['',''],
    ['━━ МЕТОДОЛОГИЯ ━━',''],
    ['P&L','Driver-based: Revenue → COGS/OPEX → Gross/Op Profit → Fin Cost → PBT → Tax → NI'],
    ['BS','3-statement integrity: PP&E roll, Cash via cumulative CF, RE roll, Net Debt'],
    ['CF','Indirect method: NI + D&A − ΔWC − CAPEX + ΔDebt − Dividends'],
    ['DSCR','CFADS / (Interest + Principal) per period, IFI standard'],
    ['LLCR','NPV(CFADS, WACD) over loan life / Outstanding debt'],
    ['PLCR','NPV(CFADS, WACD) over project life / Outstanding debt'],
    ['WACC','(1−w_d)·CAPM + w_d·cost_debt·(1−tax)'],
    ['',''],
    ['━━ СООТВЕТСТВИЕ ━━',''],
    ['Стандарты','IFRS · FAST Standard · IFC project finance template'],
    ['BS check','Total Assets − Total Liab+Eq < 1 UZSm для всех годов'],
    ['Cash tie-out','BS Cash совпадает с CF cumulative net cash change'],
    ['Named ranges','400+ ranges для round-trip и cross-sheet ссылок'],
    ['',''],
    ['━━ ОГРАНИЧЕНИЯ V1 ━━',''],
    ['Cell colors','Не реализованы (community SheetJS, требуется XLSX-Pro)'],
    ['Conditional formatting','Не реализовано — checks показаны текстом OK/BREAK'],
    ['Multi-scenario','Только активный сценарий (base/opt/str) — multi-case через OFFSET в v2'],
    ['Sensitivity tables','Excel Data Tables не сгенерированы — v2'],
    ['Round-trip парсер','Импорт обратно в платформу через named ranges — v2'],
    ['Loss carryforward','Tax = max(0, PBT) × tax_rate. Перенос убытков не моделируется.'],
    ['',''],
    ['━━ ОБРАТНАЯ СВЯЗЬ ━━',''],
    ['Платформа','platform.uz-assets.uz'],
    ['При вопросах','Технический контакт UzAssets']
  ];
  trail.forEach(function(row,i){
    ws[_fmExAddr(2+i,0)]=_fmExStr(row[0]);
    ws[_fmExAddr(2+i,1)]=_fmExStr(row[1]);
  });

  ws['!ref']=_fmExRange(0,0,2+trail.length+2,3);
  ws['!cols']=[{wch:24},{wch:60}];
  ws['!merges'].push({s:{r:0,c:0},e:{r:0,c:3}});
  ws['!merges'].push({s:{r:1,c:0},e:{r:1,c:3}});
  XLSX.utils.book_append_sheet(wb,ws,sn);
}


/* ── Excel импорт (EY/PwC template) ────────────────────────────────────── */
function _fmShowImport(){
  if(typeof XLSX==='undefined'){
    if(typeof toast==='function')toast('Библиотека XLSX не загружена');
    return;
  }
  /* Показываем модалку выбора компании перед загрузкой */
  _fmShowCompanyPicker(function(selectedCo){
    window._fmSelCo=selectedCo;
    var inp=document.createElement('input');
    inp.type='file';
    inp.accept='.xlsx,.xls';
    inp.onchange=function(e){
      var file=e.target.files[0];if(!file)return;
      var fr=new FileReader();
      fr.onload=function(ev){
        try{
          var wb=XLSX.read(ev.target.result,{type:'array',cellDates:true});
          _fmParseTemplate(wb);
        }catch(err){
          alert('Ошибка парсинга: '+err.message);
        }
      };
      fr.readAsArrayBuffer(file);
    };
    inp.click();
  },'Загрузка модели для компании','Выберите для какой компании загрузить Excel-шаблон');
}
window._fmShowImport=_fmShowImport;

/* ── Модалка выбора компании ────────────────────────────────────────────── */
function _fmShowCompanyPicker(onSelect, title, subtitle){
  var ov=document.createElement('div');
  ov.id='fm-co-picker';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,18,40,.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:10001;display:flex;align-items:center;justify-content:center;padding:24px;animation:uzaOvIn .25s ease both';
  ov.addEventListener('click',function(e){if(e.target===ov)ov.remove();});
  var box=document.createElement('div');
  box.style.cssText='background:#fff;border-radius:16px;width:min(560px,92vw);max-height:85vh;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(15,23,60,.18),0 8px 24px rgba(15,23,60,.08);animation:uzaModalIn .45s cubic-bezier(.34,1.2,.64,1) both;overflow:hidden';
  var h='<div style="padding:18px 22px 16px;border-bottom:1px solid rgba(15,23,60,.06);background:linear-gradient(180deg,rgba(127,119,221,.04),transparent)">';
  h += '<div style="font-size:15px;font-weight:500;color:var(--t1);letter-spacing:-.01em;margin-bottom:3px">'+esc(title||'Выберите компанию')+'</div>';
  h += '<div style="font-size:11.5px;color:var(--t3);line-height:1.55;letter-spacing:.02em">'+esc(subtitle||'')+'</div>';
  h += '</div>';
  /* Search */
  h += '<div style="padding:12px 22px 10px;border-bottom:1px solid rgba(15,23,60,.04)">';
  h += '<input type="text" id="fm-co-search" placeholder="Поиск компании..." oninput="_fmFilterCoList(this.value)" style="width:100%;padding:9px 13px;border:1px solid rgba(15,23,60,.1);border-radius:8px;font-size:12.5px;font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s" onfocus="this.style.borderColor=\x27#7F77DD\x27" onblur="this.style.borderColor=\x27rgba(0,0,0,.08)\x27">';
  h += '</div>';
  /* Company list */
  h += '<div style="flex:1;overflow-y:auto;padding:8px 14px" id="fm-co-list">';
  /* Группируем по секторам */
  var sectors={};
  COMPANIES.forEach(function(c){
    if(!sectors[c.sector]) sectors[c.sector]=[];
    sectors[c.sector].push(c);
  });
  var sectorLabels={
    'mining':'Горнодобыча',
    'oil_gas':'Нефть и газ',
    'energy':'Энергетика',
    'transport':'Транспорт',
    'other':'Прочие'
  };
  Object.keys(sectors).forEach(function(sec){
    var secLbl=sectorLabels[sec]||sec;
    var secColor=SECTOR_SOLID[sec]||'#888';
    h += '<div style="margin:8px 0 5px;font-size:10px;font-weight:500;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;padding:0 8px;display:flex;align-items:center;gap:6px"><span style="width:5px;height:5px;border-radius:50%;background:'+secColor+'"></span>'+secLbl+'</div>';
    sectors[sec].forEach(function(c){
      var hasModel=!!(_db.finModel&&_db.finModel[c.name]);
      h += '<button class="fm-co-pick-item" data-co-name="'+esc(c.name).toLowerCase()+'" onclick="_fmPickerSelect(\x27'+esc(c.name).replace(/'/g,"\\x27")+'\x27)" style="display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border:none;background:transparent;border-radius:7px;cursor:pointer;text-align:left;transition:background .12s;margin-bottom:2px" onmouseover="this.style.background=\x27rgba(127,119,221,.06)\x27" onmouseout="this.style.background=\x27transparent\x27">';
      h += '<span style="width:7px;height:7px;border-radius:50%;background:'+secColor+';flex-shrink:0"></span>';
      h += '<span style="flex:1;font-size:12.5px;color:var(--t1);font-weight:500">'+esc(c.name)+'</span>';
      if(hasModel){
        h += '<span style="font-size:9.5px;padding:2px 9px;background:#E1F5EE;color:#0F6E56;border-radius:11px;font-weight:500;letter-spacing:.05em;text-transform:uppercase">модель есть</span>';
      }
      h += '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--t3);opacity:.5"><path d="M4 3l4 3-4 3"/></svg>';
      h += '</button>';
    });
  });
  h += '</div>';
  /* Footer */
  h += '<div style="padding:14px 22px;border-top:1px solid rgba(15,23,60,.06);background:#FAFAFC;display:flex;justify-content:flex-end">';
  h += '<button onclick="document.getElementById(\x27fm-co-picker\x27).remove()" style="padding:8px 16px;border:1px solid rgba(15,23,60,.1);border-radius:8px;background:#fff;color:var(--t2);font-size:12px;cursor:pointer;font-family:inherit;font-weight:500;transition:all .15s" onmouseover="this.style.background=\x27#F1F5F9\x27;this.style.color=\x27var(--t1)\x27" onmouseout="this.style.background=\x27#fff\x27;this.style.color=\x27var(--t2)\x27">Отмена</button>';
  h += '</div>';
  box.innerHTML=h;
  ov.appendChild(box);
  document.body.appendChild(ov);
  window._fmPickerCallback=onSelect;
  setTimeout(function(){var s=document.getElementById('fm-co-search');if(s)s.focus();},50);
}
window._fmShowCompanyPicker=_fmShowCompanyPicker;

function _fmPickerSelect(co){
  var cb=window._fmPickerCallback;
  document.getElementById('fm-co-picker')?.remove();
  window._fmPickerCallback=null;
  if(typeof cb==='function') cb(co);
}
window._fmPickerSelect=_fmPickerSelect;

function _fmFilterCoList(q){
  q=(q||'').toLowerCase().trim();
  document.querySelectorAll('#fm-co-list .fm-co-pick-item').forEach(function(btn){
    var n=btn.getAttribute('data-co-name')||'';
    btn.style.display=(!q||n.indexOf(q)>=0)?'flex':'none';
  });
  /* Скрываем заголовки секторов если в них нет видимых элементов */
  var list=document.getElementById('fm-co-list');
  if(!list)return;
  var children=list.children;
  for(var i=0;i<children.length;i++){
    var el=children[i];
    if(el.tagName==='DIV'){
      /* Заголовок секции — проверяем есть ли видимые кнопки после до следующего DIV */
      var hasVisible=false;
      for(var j=i+1;j<children.length;j++){
        var next=children[j];
        if(next.tagName==='DIV')break;
        if(next.style.display!=='none'){hasVisible=true;break;}
      }
      el.style.display=hasVisible?'block':'none';
    }
  }
}
window._fmFilterCoList=_fmFilterCoList;

function _fmParseTemplate(wb){
  var co=window._fmSelCo;
  var scn=window._fmScenario||'base';
  var model=_fmGetOrCreate(co,scn);
  /* Helper: вытащить все year-колонки из row 2 (0-indexed) */
  function getYearCols(ws){
    var range=XLSX.utils.decode_range(ws['!ref']);
    var yrs={};
    for(var c=range.s.c;c<=range.e.c;c++){
      var cell=ws[XLSX.utils.encode_cell({r:2,c:c})];
      if(cell&&typeof cell.v==='number'&&cell.v>=2000&&cell.v<=2050){
        yrs[cell.v]=c;
      }
    }
    return yrs;
  }
  /* Helper: считать ряд по кол-лейбел=3, кол-unit=4, кол-type=5, значения из yearCols */
  function readRow(ws,r,yearCols,lblCol,unitCol,typeCol){
    var lbl=ws[XLSX.utils.encode_cell({r:r,c:(lblCol!=null?lblCol:3)})];
    if(!lbl||lbl.v==null||String(lbl.v).trim().length<2)return null;
    var unit=unitCol!=null?ws[XLSX.utils.encode_cell({r:r,c:unitCol})]:null;
    var typ=typeCol!=null?ws[XLSX.utils.encode_cell({r:r,c:typeCol})]:null;
    var values={};var hasData=false;
    Object.keys(yearCols).forEach(function(y){
      var cell=ws[XLSX.utils.encode_cell({r:r,c:yearCols[y]})];
      if(cell&&typeof cell.v==='number'&&!isNaN(cell.v)){
        values[y]=cell.v;hasData=true;
      }
    });
    if(!hasData)return null;
    return {
      name:String(lbl.v).trim(),
      unit:unit&&unit.v?String(unit.v).trim():'',
      type:typ&&typ.v?String(typ.v).trim():'',
      values:values
    };
  }

  /* СБРАСЫВАЕМ все драйверы */
  model.drivers={volumes:[],tariffs:[],costs:[],capex:[],wc:{dso:30,dio:20,dpo:40,dap:15}};
  model.macro={inflation:{},usInflation:{},fx:{}};
  model.revenueDirect={}; /* Revenue summary напрямую из файла */

  var stats={volumes:0,tariffs:0,costs:0,capex:0,years:[],revenue:0,unitCosts:0};
  var sheets=wb.SheetNames;

  /* ═══ 1. REVENUE sheet ═══ */
  if(sheets.indexOf('Revenue')>=0){
    var ws=wb.Sheets['Revenue'];
    var yearCols=getYearCols(ws);
    stats.years=Object.keys(yearCols).map(Number).sort(function(a,b){return a-b;});

    /* 1.1 Macro: inflation row 7 (0-idx), usInflation row 8, fx row 11 */
    Object.keys(yearCols).forEach(function(y){
      var c=yearCols[y];
      var uzi=ws[XLSX.utils.encode_cell({r:7,c:c})];
      if(uzi&&typeof uzi.v==='number')model.macro.inflation[y]=uzi.v;
      var usi=ws[XLSX.utils.encode_cell({r:8,c:c})];
      if(usi&&typeof usi.v==='number')model.macro.usInflation[y]=usi.v;
      var fx=ws[XLSX.utils.encode_cell({r:11,c:c})];
      if(fx&&typeof fx.v==='number')model.macro.fx[y]=fx.v;
    });

    /* 1.2 Revenue summary — rows 16-23 (0-idx), колонка C3 = название, C4 = unit, значения C7-C15
       Это уже готовые цифры выручки — кладём в revenueDirect. */
    var revMap={};
    for(var r=16;r<=23;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('total')>=0)continue;
      revMap[row.name]=row.values;
      /* Суммируем в revenueDirect */
      Object.keys(row.values).forEach(function(y){
        model.revenueDirect[y]=(model.revenueDirect[y]||0)+row.values[y];
      });
      stats.revenue++;
    }

    /* 1.3 Volumes — rows 30-38 (0-idx). Главный: R31 Passengers (Total).
       Подпункты R32/33/34 = International/Domestic/Transit (sub). */
    for(var r=30;r<=38;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('volume drivers')>=0)continue;
      /* Отмечаем sub-items чтобы они не считались дважды при расчёте revenue */
      var isSub=row.name.startsWith('  ')||row.name.startsWith('\t');
      model.drivers.volumes.push({
        id:'vol_'+r,
        name:row.name.trim(),
        unit:row.unit,
        values:row.values,
        isSub:isSub
      });
      stats.volumes++;
    }

    /* 1.4 Tariffs — rows 44-51 (0-idx), колонка C3 */
    for(var r=44;r<=51;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('tariffs')>=0&&row.name.toLowerCase().indexOf('unit')>=0)continue;
      model.drivers.tariffs.push({
        id:'trf_'+r,
        name:row.name.trim(),
        unit:row.unit,
        values:row.values
      });
      stats.tariffs++;
    }
  }

  /* ═══ 2. COST OF SALES AND OPEX sheet ═══ */
  if(sheets.indexOf('Cost of sales and OPEX')>=0){
    var ws=wb.Sheets['Cost of sales and OPEX'];
    var yearCols=getYearCols(ws);

    /* 2.1 Airport operating costs — rows 18-26, колонка C3, C4=unit, C5=Variable|Fixed */
    for(var r=18;r<=26;r++){
      var row=readRow(ws,r,yearCols,3,4,5);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('total cost')>=0)continue;
      var isDA=row.name.toLowerCase().indexOf('depreciat')>=0||row.name.toLowerCase().indexOf('amortiz')>=0||row.name.toLowerCase().indexOf('амортиза')>=0;
      model.drivers.costs.push({
        id:'cost_'+r,
        name:row.name,
        type:row.type||'fixed',
        unit:row.unit||'UZSm',
        values:row.values,
        isDA:isDA,
        category:'operating'
      });
      stats.costs++;
    }

    /* 2.2 SG&A — rows 43-48 */
    for(var r=43;r<=48;r++){
      var row=readRow(ws,r,yearCols,3,4,5);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('total')>=0)continue;
      var isDA=row.name.toLowerCase().indexOf('depreciat')>=0||row.name.toLowerCase().indexOf('admin asset')>=0;
      model.drivers.costs.push({
        id:'sga_'+r,
        name:row.name,
        type:row.type||'fixed',
        unit:row.unit||'UZSm',
        values:row.values,
        isDA:isDA,
        category:'sga'
      });
      stats.costs++;
    }

    /* 2.3 Variable cost drivers — rows 29-32 — volumes handled (unit drivers) */
    for(var r=29;r<=32;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      /* Эти не добавляем как volumes (уже есть) — только для unit cost calculation */
    }

    /* 2.4 Variable unit costs — rows 35-38 — сохраняем как assumptions */
    model.unitCosts=[];
    for(var r=35;r<=38;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      model.unitCosts.push({name:row.name,unit:row.unit,values:row.values});
      stats.unitCosts++;
    }
  }

  /* ═══ 3. BALANCE SHEET SCHEDULES ═══ */
  if(sheets.indexOf('Balance sheet schedules')>=0){
    var ws=wb.Sheets['Balance sheet schedules'];
    var yearCols=getYearCols(ws);

    /* 3.1 Working Capital turnover (последнее factual значение) — rows 25, 29, 33, 37, 41 */
    function takeLastFact(rowIdx){
      var row=readRow(ws,rowIdx,yearCols,3,4);
      if(!row)return null;
      var curY=new Date().getFullYear();
      var vals=Object.keys(row.values).filter(function(y){return parseInt(y)<=curY;}).sort();
      return vals.length?row.values[vals[vals.length-1]]:null;
    }
    var dso=takeLastFact(24); if(dso!=null) model.drivers.wc.dso=Math.round(dso);
    var dio=takeLastFact(28); if(dio!=null) model.drivers.wc.dio=Math.round(dio);
    var dpoLT=takeLastFact(32); if(dpoLT!=null) model.drivers.wc.dpo=Math.round(dpoLT);
    var dap=takeLastFact(40); if(dap!=null) model.drivers.wc.dap=Math.round(dap);

    /* 3.2 CAPEX — row 55 CAPEX breakdown total */
    var capexTotal=readRow(ws,54,yearCols,3,4);
    if(capexTotal){
      model.drivers.capex.push({id:'capex_total',name:'CAPEX (всего)',values:capexTotal.values});
      stats.capex++;
    }
    /* Детализация CAPEX — rows 57-62 (Gross Book Value opening = фактически CAPEX breakdown) */
    for(var r=57;r<=62;r++){
      var row=readRow(ws,r,yearCols,3,4);
      if(!row)continue;
      if(row.name.toLowerCase().indexOf('total')>=0||row.name.toLowerCase().indexOf('gross book')>=0)continue;
      model.drivers.capex.push({id:'capex_'+r,name:row.name,values:row.values});
      stats.capex++;
    }
  }

  /* ═══ 3.5 Control - dashboard → Key drivers + Debt + Equity ═══ */
  if(sheets.indexOf('Control - dashboard')>=0){
    var ws=wb.Sheets['Control - dashboard'];
    /* Строки 6-16 (0-idx: 5-15), C1 = имя аэропорта, C2 = загрузка % */
    model.airportLoad=[];
    for(var r=5;r<=15;r++){
      var nameCell=ws[XLSX.utils.encode_cell({r:r,c:1})];
      var loadCell=ws[XLSX.utils.encode_cell({r:r,c:2})];
      if(!nameCell||!nameCell.v)continue;
      var name=String(nameCell.v).trim();
      if(name.length<2||name.toLowerCase().indexOf('key')>=0)continue;
      /* Валидация: принимаем только коэффициенты 0-1.2.
         Если в ячейке >1.2 или отрицательное — считаем placeholder/ошибкой → null */
      var rawLoad=(loadCell&&typeof loadCell.v==='number'&&!isNaN(loadCell.v))?loadCell.v:null;
      var load=(rawLoad!=null && rawLoad>0 && rawLoad<=1.2)?rawLoad:null;
      model.airportLoad.push({name:name,load:load});
    }
    /* Key ratios (column 2 0-idx) из Control dashboard */
    model.keyRatios={};
    var ratioLabels={
      'Gross profit margin, %':'grossMargin',
      'EBITDA margin, %':'ebitdaMargin',
      'Net income margin, %':'netMargin',
      'Net debt (incl. Eurobonds)':'netDebt',
      'Net debt to EBITDA':'netDebtEbitda',
      'ROE, %':'roe',
      'DSCR':'dscr',
      'Receivable turnover days':'receivableTurnover',
      'Payables turnover days':'payablesTurnover',
      'Inventory turnover days':'inventoryTurnover'
    };
    for(var r=18;r<=28;r++){
      var lblCell=ws[XLSX.utils.encode_cell({r:r,c:1})];
      var valCell=ws[XLSX.utils.encode_cell({r:r,c:2})];
      if(!lblCell||!lblCell.v||!valCell||typeof valCell.v!=='number')continue;
      var key=ratioLabels[String(lblCell.v).trim()];
      if(key) model.keyRatios[key]=valCell.v;
    }

    /* Balance Sheet columns: 0-idx 17-25 для 2022-2030 */
    var bsYearCols={};
    for(var c=16;c<=28;c++){
      var hdr=ws[XLSX.utils.encode_cell({r:2,c:c})];
      if(hdr&&typeof hdr.v==='number'&&hdr.v>=2000&&hdr.v<=2050) bsYearCols[hdr.v]=c;
    }

    /* R24 (0-idx 23) = Кредиты, займы и евробонды (LT debt) */
    model.drivers.debt=model.drivers.debt||{ltDebt:{},stDebt:{},interestRate:0.09};
    Object.keys(bsYearCols).forEach(function(y){
      var c=bsYearCols[y];
      var cell=ws[XLSX.utils.encode_cell({r:23,c:c})];
      if(cell&&typeof cell.v==='number') model.drivers.debt.ltDebt[y]=Math.abs(cell.v);
    });

    /* Share capital R20 0-idx = Уставной капитал */
    model.drivers.equity=model.drivers.equity||{shareCapital:{},openingCash:0,openingRE:0};
    Object.keys(bsYearCols).forEach(function(y){
      var c=bsYearCols[y];
      var cell=ws[XLSX.utils.encode_cell({r:20,c:c})];
      if(cell&&typeof cell.v==='number') model.drivers.equity.shareCapital[y]=cell.v;
    });
    /* Opening RE = Retained earnings в первом году (R22 0-idx = Нераспределенная прибыль) */
    var firstY=Object.keys(bsYearCols).map(Number).sort(function(a,b){return a-b;})[0];
    if(firstY){
      var reCell=ws[XLSX.utils.encode_cell({r:22,c:bsYearCols[firstY]})];
      if(reCell&&typeof reCell.v==='number') model.drivers.equity.openingRE=reCell.v;
    }
  }

  /* ═══ 4. Обновляем горизонт ═══ */
  if(stats.years.length){
    var curY=new Date().getFullYear();
    var factYears=stats.years.filter(function(y){return y<=curY;});
    var fcYears=stats.years.filter(function(y){return y>curY;});
    if(factYears.length) model.horizon.factYears=factYears;
    if(fcYears.length) model.horizon.forecastYears=fcYears;
    if(factYears.length&&fcYears.length){
      model.horizon.startYear=factYears[0];
      model.horizon.endYear=fcYears[fcYears.length-1];
    }
  }

  /* ═══ 5. Сохраняем ═══ */
  _db.finModel=_db.finModel||{};
  _db.finModel[co]=_db.finModel[co]||{};
  _db.finModel[co][scn]=model;
  _fmRecompute(model);

  /* Diagnostics: сколько реально данных для сохранения */
  var jsonLen=JSON.stringify(_db.finModel).length;
  console.log('[FM] Размер модели для сохранения:',jsonLen,'байт');
  console.log('[FM] Структура:',_db.finModel);

  /* Используем ПРЯМОЙ PUT вместо PATCH — гарантирует запись целиком.
     PATCH делает merge что может пропускать некоторые поля, PUT полностью перезаписывает узел. */
  if(typeof fetch==='function'&&typeof FB_URL==='function'){
    var url=FB_URL().replace(/\.json.*$/,'')+'/finModel.json';
    console.log('[FM] PUT →',url);
    fetch(url,{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(_db.finModel)
    }).then(function(r){
      if(!r.ok){
        console.error('[FM] PUT failed:',r.status,r.statusText);
        if(typeof toast==='function') toast('Ошибка: Firebase вернул '+r.status);
        throw new Error('Firebase PUT error: '+r.status);
      }
      return r.json();
    }).then(function(result){
      console.log('[FM] ✓ Firebase подтвердил запись. Проверяю что действительно сохранилось...');
      /* Reread для верификации */
      return fetch(url);
    }).then(function(r){return r.json();}).then(function(saved){
      if(saved&&saved[co]&&saved[co][scn]){
        var savedModel=saved[co][scn];
        var savedVolumes=(savedModel.drivers&&savedModel.drivers.volumes)||[];
        var savedCosts=(savedModel.drivers&&savedModel.drivers.costs)||[];
        console.log('[FM] ✓ Верификация: в Firebase лежит',savedVolumes.length,'volumes,',savedCosts.length,'costs');
        if(savedVolumes.length===0&&(model.drivers.volumes||[]).length>0){
          console.error('[FM] ВНИМАНИЕ: Firebase удалил volumes! Возможно проблема Firebase rules или sparse arrays.');
          if(typeof toast==='function') toast('Предупреждение: Firebase не сохранил все данные. Проверьте консоль.');
        }
      }else{
        console.error('[FM] Firebase вернул пустой результат после записи');
      }
    }).catch(function(e){
      console.error('[FM] save-verify error:',e);
    });
  }

  var msg='Импорт завершён:\n';
  msg+='  \u2022 Годы: '+stats.years.length+' ('+stats.years.join(', ')+')\n';
  msg+='  \u2022 Revenue summary: '+stats.revenue+' строк\n';
  msg+='  \u2022 Объёмы (Volumes): '+stats.volumes+'\n';
  msg+='  \u2022 Тарифы: '+stats.tariffs+'\n';
  msg+='  \u2022 Затраты: '+stats.costs+'\n';
  msg+='  \u2022 Unit costs: '+stats.unitCosts+'\n';
  msg+='  \u2022 CAPEX: '+stats.capex+'\n';
  msg+='  \u2022 WC: DSO='+model.drivers.wc.dso+' DIO='+model.drivers.wc.dio+' DPO='+model.drivers.wc.dpo+' DAP='+model.drivers.wc.dap+'\n\n';
  msg+='Проверьте консоль (F12) для отчёта о сохранении в Firebase.';
  alert(msg);
  /* Перерисовываем shell полностью чтобы dropdown получил новую компанию */
  var mc=document.getElementById('main-content');
  if(mc) mc.innerHTML=_fmRenderShell();
  _fmRepaint();
}

/* ═══════════════════════════════════════════════════════════════════════════
   ECONOMIC EFFECT MODULE — «Экономический эффект портфеля»
   Two entry points, single engine:
   1. Executive Dashboard block — между «Финансы» и «BP-трекер»
   2. Company Dashboard — badge в topbar + KPI-tile в Обзоре → модалка с иерархией
   ═══════════════════════════════════════════════════════════════════════════ */

window._EE = window._EE || {};
window._eeAggCache = {};
window._eeStatusFilter = window._eeStatusFilter || 'all'; /* all | done | active | plan */

/* ───── Helper: получить курс USD на год (из YearRegistry платформы) ───── */
