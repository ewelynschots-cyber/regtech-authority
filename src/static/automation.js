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
