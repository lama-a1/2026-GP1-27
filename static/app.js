function copyInvite(){const el=document.getElementById('inviteLink');if(!el)return;navigator.clipboard.writeText(el.value).then(()=>alert('تم نسخ رابط الدعوة')).catch(()=>{el.select();document.execCommand('copy');alert('تم نسخ الرابط')})}
function showFilename(input){const el=document.getElementById('filename');if(el)el.textContent=input.files.length?input.files[0].name:''}

(function(){
  function updateForm(form){
    const button=form.querySelector('button.guarded-submit');
    if(!button)return;
    const fields=[...form.elements].filter(el=>el.matches&&el.matches('input,textarea,select')).filter(el=>el.type!=='hidden'&&el.name!=='csrf_token');
    const valid=fields.every(el=>{
      if(el.type==='checkbox')return !el.required||el.checked;
      if(el.type==='file')return !el.required||el.files.length>0;
      return el.checkValidity();
    });
    button.disabled=!valid;
    button.setAttribute('aria-disabled',String(!valid));
  }
  function attach(form){
    const refresh=()=>updateForm(form);
    form.addEventListener('input',refresh);
    form.addEventListener('change',refresh);
    form.addEventListener('submit',function(e){
      updateForm(form);
      const btn=form.querySelector('button.guarded-submit');
      if(btn&&btn.disabled){e.preventDefault();form.reportValidity();return;}
      if(btn){btn.disabled=true;btn.setAttribute('aria-busy','true');}
    });
    refresh();
  }
  document.querySelectorAll('form.siyaq-validated-form').forEach(attach);
})();
