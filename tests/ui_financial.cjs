// DOM integration smoke test. Does not replace visual/browser QA.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {JSDOM, VirtualConsole, CookieJar} = require('jsdom');
const root = path.resolve(__dirname, '..');
let server, dom, directory;

async function main() {
  const port = await new Promise(resolve => {
    const socket = net.createServer();
    socket.listen(0, '127.0.0.1', () => { const port = socket.address().port; socket.close(() => resolve(port)); });
  });
  const base = `http://127.0.0.1:${port}`;
  directory = mkdtempSync(path.join(tmpdir(), 'regtech-ui-'));
  server = spawn(process.env.PYTHON || 'python', [path.join(root,'tests','ui_server.py'), path.join(directory, 'test.db'), String(port)], {cwd:root, stdio:['ignore','ignore','pipe']});
  let serverOutput='';server.stderr.on('data', chunk => {serverOutput+=chunk;});
  let ready=false;
  for(let i=0;i<100;i++) { try { const response=await fetch(base); if(response.ok) {ready=true;break;} } catch {} await new Promise(r=>setTimeout(r,100)); }
  assert.ok(ready, 'Test server did not start: '+serverOutput);
  const errors=[], virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>errors.push(error.message));
  const login=await fetch(base+'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'admin@example.test',password:'fictitious-password-2026'})});
  assert.equal(login.status,200);
  const cookie=login.headers.get('set-cookie').split(';')[0];
  const cookieJar=new CookieJar();cookieJar.setCookieSync(cookie,base);
  const authedFetch=(url,options={})=>{const headers=new Headers(options.headers||{});if(new URL(url,base).origin===base)headers.set('Cookie',cookie);return fetch(url,{...options,headers});};
  dom=await JSDOM.fromURL(base,{cookieJar,resources:'usable',runScripts:'dangerously',virtualConsole,
    beforeParse(window){window.Headers=Headers;window.fetch=(url,options)=>authedFetch(new URL(url,window.location.href),options);}});
  const {window}=dom, doc=window.document;
  const wait=async(fn)=>{for(let n=0;n<100;n++){if(fn())return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timeout: '+doc.querySelector('#message')?.textContent);};
  await wait(()=>doc.readyState==='complete' && window.regtechIdentity);
  assert.match(doc.querySelector('#access-identity').textContent,/Revisor fictício/);
  assert.equal(doc.querySelector('#access-workspace').hidden,false);
  doc.querySelector('[data-tab=cdb]').click();assert.equal(doc.querySelector('#cdb').hidden,false);
  // Repeated demo loading must not mix candidate values with dynamic peer/position fields.
  for(let run=0;run<2;run++){
    doc.querySelector('#demo-cdb').click();
    await wait(()=>doc.querySelector('#message').textContent.startsWith('Exemplo fictício carregado'));
    assert.equal(doc.querySelectorAll('#peers .entry').length,3);
    assert.equal(doc.querySelector('#cdb-form').elements.conglomerate_ref.value,'GRUPO-A');
  }
  doc.querySelector('#cdb-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await wait(()=>doc.querySelector('#message').textContent==='Emissor e oferta analisados.');
  assert.match(doc.querySelector('#report-summary').textContent,/106.00% CDI/);
  const form=doc.querySelector('.review-form');form.elements.status.value='in_review';
  form.elements.reviewer.value='Revisor fictício';form.elements.reason.value='Revisão de teste';form.elements.evidence_ref.value='FONTE-TESTE';
  form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await wait(()=>doc.querySelector('#message').textContent==='Revisão registrada com histórico preservado.');
  assert.match(doc.querySelector('#reviews').textContent,/Revisor fictício/);
  doc.querySelector('[data-tab=history]').click();await wait(()=>doc.querySelector('#history-list button'));
  doc.querySelector('#history-list button').click();await wait(()=>doc.querySelector('#message').textContent==='Análise carregada.');
  const exported=await authedFetch(new URL(doc.querySelector('#export-link').getAttribute('href'),base));
  assert.equal(exported.status,200);const json=await exported.json();assert.equal(json.revision,1);
  assert.deepEqual(json.integrity,{input_matches:true,result_matches:true,review_chain_matches:true});
  assert.equal(errors.length,0);
  doc.querySelector('[data-tab=credits]').click();
  assert.equal(doc.querySelector('#credits').hidden,false);
  for(let run=0;run<2;run++){
    doc.querySelector('#demo-credits').click();
    await wait(()=>doc.querySelector('#message').textContent.startsWith('Exemplo fictício de precatório carregado'));
    assert.equal(doc.querySelector('#credits-form').elements.credit_face_amount.value,'100000.00');
    assert.equal(doc.querySelectorAll('#credit-assignments .entry').length,2);
    assert.equal(doc.querySelectorAll('#credit-scenarios .entry').length,2);
  }
  doc.querySelector('#credits-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await wait(()=>doc.querySelector('#message').textContent==='Crédito e cadeia de cessões analisados e registrados.');
  assert.match(doc.querySelector('#report-module').textContent,/PRECATÓRIOS/);
  assert.match(doc.querySelector('#report-detail').textContent,/CESSIONARIO-C-FICTICIO/);
  assert.match(doc.querySelector('#report-detail').textContent,/25.0000%/);
  const creditExport=await authedFetch(new URL(doc.querySelector('#export-link').getAttribute('href'),base));
  const creditJson=await creditExport.json();
  assert.equal(creditJson.result.module,'credits');
  assert.equal(creditJson.result.credits[0].assignment_chain.declared_holder_nominal_share,'40000.00');
  assert.equal(errors.length,0);
  const creditForm=doc.querySelector('#credits-form');
  creditForm.elements.credit_process_number.value='00008323520184013202';
  creditForm.elements.credit_court.value='';
  creditForm.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await wait(()=>doc.querySelector('#message').textContent==='Crédito e cadeia de cessões analisados e registrados.' && doc.querySelector('#process-lookup-result').textContent.includes('Metadados públicos localizados'));
  assert.equal(creditForm.elements.credit_court.value,'TRF1');
  const enriched=await (await authedFetch(new URL(doc.querySelector('#export-link').getAttribute('href'),base))).json();
  assert.equal(enriched.result.process_queries.length,1);
  assert.equal(enriched.result.credits[0].holder_confirmed,null);
  const checklist=await authedFetch(new URL(doc.querySelector('#checklist-link').getAttribute('href'),base));
  assert.equal(checklist.status,200);assert.match(await checklist.text(),/Tarefa de diligência/);
  assert.equal(errors.length,0);
  console.log('PASS: CDB/credit workflows, automatic process lookup (mocked), court prefill, query evidence and checklist CSV.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  dom?.window.close();
  if(server && server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}
  if(directory)rmSync(directory,{recursive:true,force:true});
});
