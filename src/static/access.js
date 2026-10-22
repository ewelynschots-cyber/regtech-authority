'use strict';
// Session cookie is HttpOnly. CSRF is held only in this page's memory.
window.regtechIdentity=null;
const originalFetch=window.fetch.bind(window);
const identityReady=originalFetch('/api/auth/me',{credentials:'same-origin'}).then(async response=>{
  if(!response.ok){window.location.replace('/login');throw new Error('Entre novamente.');}
  const data=await response.json();window.regtechIdentity=data.user;
  const label=document.querySelector('#access-identity');label.textContent=data.user.name+' · '+data.user.organization.name+' · '+({admin:'Administrador',analyst:'Analista',viewer:'Leitura'})[data.user.role];
  document.querySelector('#access-workspace').hidden=false;
  document.querySelector('#users-admin').hidden=data.user.role!=='admin';
  return data;
});
// Gate every private request, including automated lookups and multipart uploads.
window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,window.location.href);
  const settings={...options};
  if(url.origin===window.location.origin && url.pathname.startsWith('/api/')){
    const identity=await identityReady;const headers=new Headers(options.headers||{});
    if(!['GET','HEAD','OPTIONS'].includes((settings.method||'GET').toUpperCase()))headers.set('X-CSRF-Token',identity.csrf_token);
    settings.headers=headers;settings.credentials='same-origin';
  }
  const response=await originalFetch(input,settings);
  if(url.origin===window.location.origin && url.pathname.startsWith('/api/') && response.status===401)window.location.replace('/login');
  return response;
};
identityReady.catch(()=>{});
document.querySelector('#logout').addEventListener('click',async()=>{
  const response=await fetch('/api/auth/logout',{method:'POST'});if(response.ok)window.location.replace('/login');
});
document.querySelector('#user-create').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,target=document.querySelector('#user-result');
  try{
    const payload=Object.fromEntries(new FormData(form));
    const response=await fetch('/api/auth/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'Conta não criada.');
    form.reset();target.textContent='Conta criada para '+data.user.name+'.';await loadUsers();
  }catch(error){target.textContent=error.message;}
});
async function loadUsers(){
  const response=await fetch('/api/auth/users');const data=await response.json();if(!response.ok)throw new Error(data.message);
  const target=document.querySelector('#user-list');target.replaceChildren();
  for(const user of data.items){
    const row=document.createElement('div');row.className='record';
    const text=document.createElement('p');text.textContent=user.name+' · '+user.email+' · '+user.role+' · '+(user.is_active?'Ativo':'Inativo');row.append(text);
    if(user.role!=='admin'){
      for(const [label,payload] of [[user.is_active?'Desativar':'Reativar',{is_active:!user.is_active}],[user.role==='viewer'?'Alterar para analista':'Alterar para leitura',{role:user.role==='viewer'?'analyst':'viewer'}]]){
        const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=label;
        button.addEventListener('click',async()=>{try{const result=await fetch('/api/auth/users/'+user.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!result.ok)throw new Error('Não foi possível alterar a conta.');await loadUsers();}catch(error){document.querySelector('#user-result').textContent=error.message;}});row.append(button);
      }
    }
    target.append(row);
  }
}
document.querySelector('#reload-users').addEventListener('click',()=>loadUsers().catch(error=>{document.querySelector('#user-result').textContent=error.message;}));
