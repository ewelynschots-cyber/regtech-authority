'use strict';
const $ = selector => document.querySelector(selector);
const statuses = {open:'Aberto', in_review:'Em revisão', resolved:'Resolvido', dismissed:'Descartado'};
const brl = value => Number(value).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const node = (tag, content, className) => { const el=document.createElement(tag); if(content!==undefined) el.textContent=content; if(className) el.className=className; return el; };
let currentReport=null, historyPage=1;
function message(text, error=false) { $('#message').textContent=text; $('#message').className=error?'error':'success'; }
async function api(path, options={}) {
  const response=await fetch('/api/financial'+path, options);
  let data; try { data=await response.json(); } catch { throw new Error('Não foi possível concluir. Verifique a inicialização do banco e os logs do serviço.'); }
  if(!response.ok) throw new Error(data.message||'Não foi possível concluir a solicitação.');
  return data;
}
async function busy(form, fn) {
  if(form.classList.contains('busy')) return;
  form.classList.add('busy'); form.setAttribute('aria-busy','true'); message('Processando…');
  try { await fn(); } catch(error) { message(error.message,true); }
  finally { form.classList.remove('busy'); form.removeAttribute('aria-busy'); }
}
function activate(tab) {
  ['fidc','cdb','credits','history'].forEach(id=>{ $('#'+id).hidden=id!==tab; });
  document.querySelectorAll('[data-tab]').forEach(el=>{ const active=el.dataset.tab===tab; el.classList.toggle('active',active); el.setAttribute('aria-pressed',String(active)); });
  $('#report').hidden=true;
  if(tab==='history') loadHistory(1).catch(error=>message(error.message,true));
}
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>activate(button.dataset.tab)));
const today=new Date().toLocaleDateString('en-CA');
document.querySelectorAll('input[type=date]').forEach(input=>{ input.max=today; if(input.name==='as_of') input.value=today; });
function inputField(parent,label,name,value='',type='text',required=true) {
  const wrapper=node('label',label); const input=node('input'); input.name=name; input.type=type; input.value=value; input.required=required;
  if(type==='number'){input.min='0';input.step='.01';} wrapper.append(input);parent.append(wrapper);return input;
}
function addEntry(kind, values={}) {
  const target=$('#'+(kind==='peer'?'peers':'positions')); const box=node('div',undefined,'entry');
  const remove=node('button','Remover','remove');remove.type='button';remove.addEventListener('click',()=>box.remove());box.append(remove);
  const grid=node('div',undefined,'grid'); box.append(grid);
  const fields=kind==='peer' ? [['Identificador da oferta','offer_id'],['Emissor','issuer_ref'],['Conglomerado','conglomerate_ref'],['Remuneração (% do CDI)','rate_percent_cdi','number'],['Fonte da oferta','source_ref']] : [['Identificador da posição','position_id'],['Conglomerado','conglomerate_ref'],['Saldo com juros (R$)','balance','number'],['Fonte do saldo','source_ref']];
  fields.forEach(([label,name,type])=>{const input=inputField(grid,label,kind+'_'+name,values[name]||'',type||'text');input.dataset.field=name;});
  if(kind==='position') {
    const wrapper=node('label','Elegibilidade FGC conferida');const select=node('select');select.name='position_eligible';select.dataset.field='eligible';
    [['','Pendente'],['true','Elegível'],['false','Não elegível']].forEach(([value,label])=>{const option=node('option',label);option.value=value;select.append(option);});
    select.value=values.eligible===true?'true':values.eligible===false?'false':'';wrapper.append(select);grid.append(wrapper);
  }
  target.append(box);
}
$('#add-peer').addEventListener('click',()=>addEntry('peer'));
$('#add-position').addEventListener('click',()=>addEntry('position'));
function entryData(selector) { return [...document.querySelectorAll(selector+' .entry')].map(box=>Object.fromEntries([...box.querySelectorAll('input,select')].map(input=>[input.dataset.field||input.name,input.value]))); }
$('#fidc-form').addEventListener('submit',event=>{event.preventDefault();busy(event.target,async()=>{
  const result=await api('/fidc/import',{method:'POST',body:new FormData(event.target)});showReport(result);message('Carteira analisada e registrada.');
});});
$('#cdb-form').addEventListener('submit',event=>{event.preventDefault();busy(event.target,async()=>{
  const form=event.target, values=Object.fromEntries(new FormData(form));
  const terms={as_of:values.as_of,term_days:Number(values.term_days),liquidity:values.liquidity,indexer:'CDI',currency:'BRL'};
  const offer={...terms,offer_id:'oferta-analisada',issuer_ref:values.issuer_ref,conglomerate_ref:values.conglomerate_ref,rate_percent_cdi:values.rate_percent_cdi,source_ref:values.source_ref};
  const payload={name:values.name,offer,comparables:entryData('#peers').map(row=>({...terms,...row})),positions:entryData('#positions').map(row=>({...row,as_of:values.as_of,eligible:row.eligible===''?null:row.eligible==='true'}))};
  if(form.elements.use_financials.checked) payload.financials={issuer_ref:values.issuer_ref,as_of:values.financial_as_of,source_ref:values.financial_source_ref,equity:values.equity,net_income:values.net_income,deposits:values.deposits};
  if(values.concentration_limit_percent!=='') payload.concentration_limit_percent=values.concentration_limit_percent;
  if(form.elements.use_fgc.checked) payload.fgc={eligibility_confirmed:form.elements.eligibility_confirmed.checked,balances_include_interest:form.elements.balances_include_interest.checked,history_confirmed:form.elements.history_confirmed.checked,prior_payments_current_window:values.prior_payments_current_window,source_ref:values.fgc_source_ref};
  showReport(await api('/cdb',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));message('Emissor e oferta analisados.');
});});
$('#demo-cdb').addEventListener('click',()=>busy($('#cdb-form'),async()=>{
  const response=await fetch('/static/examples/cdb.json'); if(!response.ok) throw new Error('Exemplo indisponível');const example=await response.json();const form=$('#cdb-form');form.reset();
  const values={name:example.name,...example.offer,equity:example.financials.equity,net_income:example.financials.net_income,deposits:example.financials.deposits,financial_as_of:example.financials.as_of,financial_source_ref:example.financials.source_ref,concentration_limit_percent:example.concentration_limit_percent};
  Object.entries(values).forEach(([key,value])=>{if(form.elements[key])form.elements[key].value=value;});form.elements.use_financials.checked=true;
  $('#peers').replaceChildren();example.comparables.forEach(row=>addEntry('peer',row));$('#positions').replaceChildren();example.positions.forEach(row=>addEntry('position',row));
  message('Exemplo fictício carregado. Clique em Analisar emissor e oferta.');
}));
function metric(value,label) {const el=node('div',undefined,'metric');el.append(node('strong',value),node('span',label));return el;}
function table(parent, headers, rows) {const wrap=node('div',undefined,'table-wrap'),table=node('table'),head=node('tr');headers.forEach(h=>head.append(node('th',h)));table.append(head);rows.forEach(row=>{const tr=node('tr');row.forEach(cell=>tr.append(node('td',String(cell??'—'))));table.append(tr);});wrap.append(table);parent.append(wrap);}
function showReport(data) {
  currentReport=data;const result=data.result;$('#report').hidden=false;$('#report-title').textContent=result.name;$('#report-module').textContent=({fidc:'LASTRO E RECEBÍVEIS · FIDCs',cdb:'EMISSOR E CAPTAÇÃO · CDBs',credits:'PRECATÓRIOS E DIREITOS CREDITÓRIOS'})[result.module];
  $('#export-link').href='/api/financial/analyses/'+encodeURIComponent(data.id)+'/export';
  $('#checklist-link').href='/api/financial/analyses/'+encodeURIComponent(data.id)+'/checklist.csv';
  const metrics=$('#report-summary');metrics.replaceChildren();metrics.append(metric(String(result.summary.alert_count),'Pontos de atenção'));
  const detail=$('#report-detail');detail.replaceChildren();
  if(result.module==='credits') {
    window.renderCreditReport(result, metrics, detail);
  } else if(result.module==='fidc') {
    metrics.append(metric(String(result.summary.receivable_count),'Títulos importados'),metric(brl(result.summary.declared_total),'Total declarado, incluindo possíveis duplicidades'));
    table(detail,['Título','Cedente','Devedor','Valor','Documento'],result.receivables.map(r=>[r.title_id,r.originator_id,r.debtor_id,brl(r.amount),r.document_ref]));
  } else {
    metrics.append(metric(result.comparison.median_percent_cdi===null?'Inconclusiva':result.comparison.median_percent_cdi+'% CDI','Mediana dos comparáveis'),metric(String(result.summary.comparable_count),'Ofertas aceitas'));
    detail.append(node('p','Taxa analisada: '+result.offer.rate_percent_cdi+'% do CDI. Diferença para a mediana: '+(result.comparison.difference_percentage_points??'não calculada')+' pontos percentuais.'));
    detail.append(node('p','Prazo: '+result.offer.term_days+' dias · Liquidez: '+(result.offer.liquidity==='daily'?'Diária':'No vencimento')+' · Data-base: '+result.as_of));
    table(detail,['Oferta aceita','Emissor','Taxa (% CDI)','Fonte'],result.comparison.accepted.map(r=>[r.offer_id,r.issuer_ref,r.rate_percent_cdi,r.source_ref]));
    if(result.comparison.excluded.length){detail.append(node('h3','Ofertas excluídas'));table(detail,['Oferta','Critérios divergentes'],result.comparison.excluded.map(r=>[r.offer.offer_id,r.reasons.join(', ')]));}
    if(result.financials){detail.append(node('h3','Dados financeiros · '+result.financials.as_of));table(detail,['Patrimônio líquido','Resultado','Depósitos'],[[brl(result.financials.equity),brl(result.financials.net_income),brl(result.financials.deposits)]]);}
    detail.append(node('h3','Exposição declarada por conglomerado'));table(detail,['Conglomerado','Saldo','Participação (%)'],result.exposure.groups.map(r=>[r.conglomerate_ref,brl(r.balance),r.share_percent]));
    if(result.exposure.fgc.status==='conditional_estimate') detail.append(node('p','Estimativa FGC condicionada aos dados conferidos: '+brl(result.exposure.fgc.estimated_total)+'. Excesso elegível: '+brl(result.exposure.fgc.eligible_excess)+'.'));
    if(result.exposure.fgc.status==='insufficient_data') detail.append(node('p','Estimativa FGC inconclusiva: faltam dados ou conferências.'));
  }
  detail.append(node('p',result.method,'hint'));
  const container=$('#alerts');container.replaceChildren();
  if(!result.alerts.length) container.append(node('p','Nenhum ponto de atenção identificado pelas regras aplicadas aos dados fornecidos.'));
  result.alerts.forEach(alert=>{
    const box=node('article',undefined,'alert');box.append(node('div',statuses[alert.status]+' · '+alert.id,'status'),node('p',alert.message+(alert.row?' · Linha '+alert.row:'')));
    const details=node('details'),summary=node('summary','Ver evidência e revisar');details.append(summary,node('pre',JSON.stringify(alert.evidence,null,2)));
    const form=node('form',undefined,'review-form');const statusLabel=node('label','Novo status'),select=node('select');select.name='status';Object.entries(statuses).forEach(([value,label])=>{const option=node('option',label);option.value=value;select.append(option);});select.value=alert.status;statusLabel.append(select);form.append(statusLabel);
    inputField(form,'Nome do revisor declarado','reviewer');inputField(form,'Justificativa','reason');inputField(form,'Referência da evidência de revisão','evidence_ref');const button=node('button','Registrar revisão','primary');button.type='submit';form.append(button);details.append(form);box.append(details);container.append(box);
    form.addEventListener('submit',event=>{event.preventDefault();busy(form,async()=>{
      const values=Object.fromEntries(new FormData(form));const updated=await api('/analyses/'+data.id+'/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...values,alert_id:alert.id,expected_revision:data.revision})});showReport(updated);message('Revisão registrada com histórico preservado.');
    });});
  });
  const sources=$('#sources');sources.replaceChildren();result.sources.forEach(source=>sources.append(node('p',source)));sources.append(node('pre','Entrada SHA-256: '+data.input_sha256+'\nResultado SHA-256: '+data.result_sha256+'\nRevisão: '+data.revision));
  sources.append(node('p',Object.values(data.integrity).every(Boolean)?'Hashes e encadeamento conferem.':'Divergência de integridade: consulte o dossiê exportado.'));
  result.reference_sources.forEach(source=>{const p=node('p'),a=node('a',source);a.href=source;a.target='_blank';a.rel='noopener noreferrer';p.append(a);sources.append(p);});
  const reviews=$('#reviews');reviews.replaceChildren();if(!data.reviews.length) reviews.append(node('p','Nenhuma revisão registrada.'));
  data.reviews.forEach(row=>{const event=row.event;const record=node('div',undefined,'record');record.append(node('strong',event.alert_id+' · '+statuses[event.previous_status]+' → '+statuses[event.status]),node('p',event.reason),node('small',event.reviewer_declared+' · '+event.created_at+' · Evidência: '+event.evidence_ref));reviews.append(record);});
}
async function loadHistory(page=1){historyPage=page;const data=await api('/analyses?page='+page);const list=$('#history-list');list.replaceChildren();if(!data.items.length)list.append(node('p','Nenhuma análise registrada.'));data.items.forEach(item=>{const box=node('div',undefined,'record'),button=node('button',item.name+' · '+({fidc:'FIDCs',cdb:'CDBs',credits:'Créditos'})[item.module]);button.type='button';button.addEventListener('click',()=>busy(box,async()=>{showReport(await api('/analyses/'+item.id));message('Análise carregada.');}));box.append(button,node('small',item.created_at+' · '+item.summary.alert_count+' pontos de atenção'));list.append(box);});const pages=$('#history-pagination');pages.replaceChildren();if(page>1){const previous=node('button','Anterior','secondary');previous.addEventListener('click',()=>loadHistory(page-1).catch(error=>message(error.message,true)));pages.append(previous);}if(page<data.pages){const next=node('button','Próxima','secondary');next.addEventListener('click',()=>loadHistory(page+1).catch(error=>message(error.message,true)));pages.append(next);}}
$('#reload-history').addEventListener('click',()=>loadHistory(historyPage).catch(error=>message(error.message,true)));
