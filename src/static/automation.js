'use strict';
(() => {
  let snapshot=null;
  const form=$('#credits-form');
  const normalize=value=>value.replace(/[.\-\s]/g,'');
  const labels={found:'Metadados públicos localizados',not_found:'Sem correspondência na base consultada',unavailable:'Consulta pendente / fonte indisponível'};
  const errors={not_configured:'Conexão CNJ ainda não configurada.',unsupported_court:'Tribunal ainda não atendido por esta integração.',access_rejected:'A fonte recusou a credencial ou o acesso.',rate_limited:'A fonte limitou temporariamente as consultas.',timeout:'A fonte não respondeu no prazo.',connection_error:'Não foi possível conectar à fonte.',invalid_response:'Resposta da fonte não pôde ser validada.',partial_response:'Resposta parcial; a conferência continua pendente.',upstream_http_error:'A fonte retornou um erro temporário.'};
  async function requestLookup(number){
    const response=await fetch('/api/automation/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_number:number})});
    let data;try{data=await response.json();}catch{throw new Error('Não foi possível consultar a fonte processual.');}
    if(!response.ok)throw new Error(data.message||'Consulta processual não concluída.');
    return data;
  }
  function displaySnapshot(data){
    const payload=data.payload,target=$('#process-lookup-result');target.replaceChildren();
    target.append(node('p',labels[payload.status]+'. Consulta em '+payload.checked_at+(data.cache_used?' · Resultado reaproveitado do cache recente.':'')));
    if(payload.error_code)target.append(node('p',errors[payload.error_code]||'Conferência pendente.'));
    if(payload.process.court && !form.elements.credit_court.value.trim())form.elements.credit_court.value=payload.process.court;
    target.append(node('p','Tribunal identificado pela numeração: '+(payload.process.court||'não suportado')+'.'));
    if(payload.records.length)table(target,['Grau','Classe','Órgão julgador','Atualização registrada na fonte'],payload.records.map(record=>[record.grau,record.classe?.nome,record.orgaoJulgador?.nome,record.dataHoraUltimaAtualizacao]));
    target.append(node('p','Esta consulta não preenche automaticamente credor, titularidade, saldo ou confirmação de pagamento.','hint'));
  }
  async function lookupCurrent(){
    const number=normalize(form.elements.credit_process_number.value);
    const data=await requestLookup(number);snapshot=data;displaySnapshot(data);return data;
  }
  $('#lookup-process').addEventListener('click',()=>busy(form,async()=>{await lookupCurrent();message('Consulta processual registrada com fonte e data.');}));
  form.elements.credit_process_number.addEventListener('input',()=>{snapshot=null;$('#process-lookup-result').replaceChildren();});
  $('#demo-credits').addEventListener('click',()=>{snapshot=null;$('#process-lookup-result').replaceChildren();});
  window.ensureCreditProcessLookup=async()=>{
    const number=normalize(form.elements.credit_process_number.value);
    if(!/^[0-9]{20}$/.test(number))return;
    if(snapshot?.payload.process.number===number)return;
    await lookupCurrent();
  };
  window.creditProcessLookupIds=()=>snapshot?.payload.process.number===normalize(form.elements.credit_process_number.value)?[snapshot.id]:[];
  window.renderProcessQueries=(result,detail)=>{
    for(const query of result.process_queries||[]){
      const payload=query.payload;detail.append(node('h3','Consulta automática · '+payload.process.formatted));
      detail.append(node('p',labels[payload.status]+' · '+payload.checked_at));
      if(payload.error_code)detail.append(node('p',errors[payload.error_code]||'Conferência pendente.'));
      table(detail,['Tribunal','Grau','Classe','Órgão julgador','Atualização na fonte'],payload.records.map(record=>[record.tribunal,record.grau,record.classe?.nome,record.orgaoJulgador?.nome,record.dataHoraUltimaAtualizacao]));
      for(const record of payload.records){
        const movements=[...(record.movimentos||[])].sort((a,b)=>String(b.dataHora||'').localeCompare(String(a.dataHora||'')));
        if(movements.length){detail.append(node('h3','Movimentações públicas · '+(record.grau||'')));table(detail,['Data','Movimentação'],movements.slice(0,20).map(m=>[m.dataHora,m.nome]));if(movements.length>20)detail.append(node('p','Mostrando as 20 mais recentes. O dossiê contém todas as movimentações retornadas.','hint'));}
      }
    }
  };
})();

$('#pdf-extract-form').addEventListener('submit',event=>{
  event.preventDefault();
  busy(event.target,async()=>{
    const response=await fetch('/api/automation/documents/extract',{method:'POST',body:new FormData(event.target)});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'Falha na extração.');
    const target=$('#pdf-result');target.replaceChildren(node('p',data.notice));
    target.append(node('p',data.complete?'Extração concluída.':'Extração parcial: confira as páginas sem texto.'));
    for(const candidate of data.candidates){
      const line=node('p',`Página ${candidate.page} · ${candidate.value} · ${candidate.method}`);
      if(candidate.field==='process_number'){
        const button=node('button','Aplicar número do processo');button.type='button';
        button.addEventListener('click',()=>{const input=$('#credits-form').elements.credit_process_number;input.value=candidate.value;input.dispatchEvent(new Event('input',{bubbles:true}));});line.append(button);
      }
      target.append(line);
    }
    for(const page of data.pages){const details=node('details');details.append(node('summary',`Página ${page.page} · ${page.method}`),node('pre',page.text||'Texto não extraído.'));target.append(details);}
  });
});
for(const [id,enabled] of [['enable-monitor',true],['disable-monitor',false]]){
  $('#'+id).addEventListener('click',()=>busy($('#credits-form'),async()=>{
    const response=await fetch('/api/automation/monitors',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_number:$('#credits-form').elements.credit_process_number.value,enabled})});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'Falha no monitoramento.');
    message(enabled?'Reconsulta registrada. A execução depende do agendador do servidor.':'Reconsulta desativada.');
  }));
}
