'use strict';
(() => {
  const form=$('#credits-form');
  const optional=['document_ref','document_amount','process_number','court','precatorio_number','nature','final_judgment_ref','requisition_ref','payment_order_ref','holder_check_ref','paid_amount','reserved_amount','encumbrance_ref','dispute_ref'];
  const confirmation=['claim_confirmed','holder_confirmed'];
  function addCreditEntry(kind, values={}) {
    const target=$(kind==='assignment'?'#credit-assignments':'#credit-scenarios');
    const box=node('div',undefined,'entry'), remove=node('button','Remover','remove'),grid=node('div',undefined,'grid');
    remove.type='button';remove.addEventListener('click',()=>box.remove());box.append(remove,grid);
    const fields=kind==='assignment' ? [
      ['Identificador da cessão','assignment_id'],['Data da cessão','date','date'],
      ['Cedente','transferor_ref'],['Cessionário','transferee_ref'],['Valor nominal transferido (R$)','face_amount','number'],
      ['Instrumento de cessão','instrument_ref','text',false],['Protocolo de comunicação ao tribunal','court_notification_ref','text',false],
      ['Comprovação de comunicação ao devedor','debtor_notification_ref','text',false]
    ] : [
      ['Nome do cenário','name'],['Meses até o recebimento hipotético','months_to_receipt','number'],
      ['Recebimento bruto da parcela (R$)','expected_gross_amount','number'],['Custos no recebimento (R$)','receipt_costs','number'],
      ['Tributos estimados (R$)','taxes','number'],['Taxa anual de desconto (%) · opcional','discount_rate_annual_percent','number',false]
    ];
    fields.forEach(([label,key,type='text',required=true])=>{
      const input=inputField(grid,label,kind+'_'+key,values[key]??'',type,required);input.dataset.field=key;
      if(type==='date') input.max=form.elements.as_of.value;
      if(key==='months_to_receipt'){input.min='1';input.max='600';input.step='1';}
      if(key==='face_amount')input.min='.01';
    });target.append(box);
  }
  function entries(selector) {return [...document.querySelectorAll(selector+' .entry')].map(box=>Object.fromEntries([...box.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])));}
  $('#add-assignment').addEventListener('click',()=>addCreditEntry('assignment'));
  $('#add-credit-scenario').addEventListener('click',()=>addCreditEntry('scenario'));
  form.addEventListener('submit',event=>{event.preventDefault();busy(form,async()=>{
    if(window.ensureCreditProcessLookup) await window.ensureCreditProcessLookup(form);
    const values=Object.fromEntries(new FormData(form));
    const credit={kind:values.credit_kind,assignments:entries('#credit-assignments')};
    for(const key of ['credit_id','debtor_ref','original_holder_ref','declared_holder_ref','face_amount','encumbrance_status','dispute_status']) credit[key]=values['credit_'+key];
    optional.forEach(key=>{if(values['credit_'+key]!=='')credit[key]=values['credit_'+key];});
    confirmation.forEach(key=>{const value=values['credit_'+key];credit[key]=value===''?null:value==='true';});
    if(form.elements.use_economic.checked) credit.economic={acquired_face_amount:values.economic_acquired_face_amount,purchase_price:values.economic_purchase_price,upfront_costs:values.economic_upfront_costs,scenarios:entries('#credit-scenarios').map(row=>({...row,months_to_receipt:Number(row.months_to_receipt)}))};
    const payload={name:values.name,as_of:values.as_of,source_ref:values.source_ref,credits:[credit]};
    if(values.linked_fidc_analysis_id)payload.linked_fidc_analysis_id=values.linked_fidc_analysis_id;
    if(window.creditProcessLookupIds) payload.process_lookup_ids=window.creditProcessLookupIds(form);
    const report=await api('/credits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    showReport(report);message('Crédito e cadeia de cessões analisados e registrados.');
  });});
  $('#credits-import-form').addEventListener('submit',event=>{event.preventDefault();busy(event.target,async()=>{
    showReport(await api('/credits/import',{method:'POST',body:new FormData(event.target)}));
    message('Carteira de créditos importada e analisada.');
  });});
  $('#demo-credits').addEventListener('click',()=>busy(form,async()=>{
    const response=await fetch('/static/examples/credits.json');if(!response.ok)throw new Error('Exemplo indisponível');
    const payload=await response.json(),credit=payload.credits[0];form.reset();
    for(const key of ['name','as_of','source_ref'])form.elements[key].value=payload[key];
    for(const [key,value] of Object.entries(credit)){
      const input=form.elements['credit_'+key];if(input)input.value=value===null?'':String(value);
    }
    $('#credit-assignments').replaceChildren();credit.assignments.forEach(row=>addCreditEntry('assignment',row));
    $('#credit-scenarios').replaceChildren();
    if(credit.economic){form.elements.use_economic.checked=true;for(const key of ['acquired_face_amount','purchase_price','upfront_costs'])form.elements['economic_'+key].value=credit.economic[key];credit.economic.scenarios.forEach(row=>addCreditEntry('scenario',row));}
    message('Exemplo fictício de precatório carregado. Clique em Analisar crédito e cessões.');
  }));
  window.renderCreditReport=(result,metrics,detail)=>{
    if(window.renderProcessQueries)window.renderProcessQueries(result,detail);
    metrics.append(metric(String(result.summary.credit_count),'Créditos analisados'),metric(brl(result.summary.declared_face_total),'Total nominal declarado, incluindo possíveis repetições'));
    if(result.linked_fidc_analysis_id) detail.append(node('p','Análise FIDC vinculada: '+result.linked_fidc_analysis_id));
    const kinds={precatorio:'Precatório',judicial:'Crédito judicial',contractual:'Crédito contratual'};
    result.credits.forEach(credit=>{
      detail.append(node('h3',credit.credit_id+' · '+kinds[credit.kind]));
      table(detail,['Devedor','Titular declarado','Processo / tribunal','Precatório'],[[credit.debtor_ref,credit.declared_holder_ref,[credit.process_number,credit.court].filter(Boolean).join(' / '),credit.precatorio_number]]);
      table(detail,['Valor nominal','Pagamentos informados','Reservas informadas','Referência após deduções'],[[brl(credit.face_amount),credit.paid_amount===null?'Pendente':brl(credit.paid_amount),credit.reserved_amount===null?'Pendente':brl(credit.reserved_amount),credit.reference_after_deductions===null?'Inconclusiva':brl(credit.reference_after_deductions)]]);
      const chain=credit.assignment_chain;
      detail.append(node('p',chain.arithmetic_consistent?'Cadeia nominal aritmeticamente consistente com os dados informados.':'Cadeia nominal inconclusiva: participação final não inferida.'));
      table(detail,['Cessão','Data','Cedente → cessionário','Valor nominal','Aplicada na reconstrução'],chain.events.map(row=>[row.assignment_id,row.date,row.transferor_ref+' → '+row.transferee_ref,brl(row.face_amount),row.applied_to_nominal_ledger?'Sim':'Não']));
      table(detail,['Titular na reconstrução nominal','Participação nominal'],chain.nominal_holdings.map(row=>[row.holder_ref,brl(row.face_amount)]));
      detail.append(node('p',chain.basis,'hint'));
      if(credit.economic){
        const economic=credit.economic;detail.append(node('h3','Cenários · '+credit.credit_id));
        detail.append(node('p','Parcela nominal: '+brl(economic.acquired_face_amount)+' · Preço: '+brl(economic.purchase_price)+' · Deságio sobre a parcela: '+economic.purchase_discount_percent+'% · Investimento com custos: '+brl(economic.total_initial_investment)));
        table(detail,['Cenário','Meses','Recebimento líquido','Resultado','Retorno total (%)','Anualizado (%)','VPL'],economic.scenarios.map(row=>[row.name,row.months_to_receipt,brl(row.net_receipt),brl(row.profit_or_loss),row.total_return_percent,row.annualized_return_percent,row.net_present_value===null?'Não calculado':brl(row.net_present_value)]));
        detail.append(node('p',economic.basis,'hint'));
      }
    });
  };
})();
