'use strict';
document.querySelector('#login-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,button=form.querySelector('button'),message=document.querySelector('#login-message');
  button.disabled=true;message.textContent='Entrando…';
  try{
    const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({email:form.elements.email.value,password:form.elements.password.value})});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'Não foi possível entrar.');
    form.elements.password.value='';window.location.assign('/');
  }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
});
