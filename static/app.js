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
    button.disabled=!valid || button.dataset.registrationUnavailable==='true';
    button.setAttribute('aria-disabled',String(button.disabled));
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



(function(){
  const form=document.querySelector('form[data-step="5"][data-cloud-upload="1"]');
  if(!form)return;
  form.addEventListener('submit',async function(event){
    const file=form.querySelector('input[type="file"][name="video"]')?.files?.[0];
    if(!file)return;
    event.preventDefault();
    const button=form.querySelector('button[type="submit"]');
    const status=document.getElementById('video-upload-status');
    const message=document.getElementById('video-upload-message');
    const bar=document.getElementById('video-upload-progress');
    const csrf=form.querySelector('[name="csrf_token"]').value;
    const caseId=form.dataset.caseId;
    const base='/api/cases/'+encodeURIComponent(caseId)+'/videos/';
    if(status)status.hidden=false;
    if(button)button.disabled=true;
    const setMessage=(value)=>{if(message)message.textContent=value;};
    try{
      setMessage('جارٍ تجهيز الفيديو...');
      const response=await fetch(base+'presign',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({filename:file.name,size:file.size})});
      const ticket=await response.json();
      if(!response.ok)throw new Error(ticket.error||'تعذر بدء رفع الفيديو.');
      if(ticket.provider==='cloudinary'){
        const chunkSize=20*1024*1024;
        const uploadId='siyaq-'+Date.now()+'-'+Math.random().toString(36).slice(2);
        for(let offset=0;offset<file.size;offset+=chunkSize){
          const end=Math.min(file.size,offset+chunkSize);
          const part=file.slice(offset,end);
          const payload=new FormData();
          payload.append('file',part,file.name);
          payload.append('api_key',ticket.api_key);
          payload.append('timestamp',String(ticket.timestamp));
          payload.append('signature',ticket.signature);
          payload.append('public_id',ticket.public_id);
          payload.append('type',ticket.delivery_type);
          await new Promise((resolve,reject)=>{
            const xhr=new XMLHttpRequest();
            xhr.open('POST',ticket.upload_url);
            xhr.setRequestHeader('X-Unique-Upload-Id',uploadId);
            xhr.setRequestHeader('Content-Range','bytes '+offset+'-'+(end-1)+'/'+file.size);
            xhr.upload.onprogress=(ev)=>{
              if(ev.lengthComputable){
                const pct=Math.round((offset+ev.loaded)/file.size*100);
                if(bar)bar.style.width=pct+'%';
                setMessage('جارٍ رفع الفيديو... '+pct+'٪');
              }
            };
            xhr.onload=()=>{
              let result={};try{result=JSON.parse(xhr.responseText);}catch(_){}
              if(xhr.status>=200&&xhr.status<300 && !result.error)resolve(result);
              else reject(new Error(result.error?.message||'تعذر رفع الفيديو. يرجى المحاولة مرة أخرى.'));
            };
            xhr.onerror=()=>reject(new Error('تعذر الاتصال بخدمة رفع الفيديو.'));
            xhr.send(payload);
          });
        }
      }else{
      await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();
        xhr.open('PUT',ticket.upload_url);
        xhr.setRequestHeader('Content-Type',ticket.content_type);
        xhr.upload.onprogress=(ev)=>{if(ev.lengthComputable){const pct=Math.round(ev.loaded/ev.total*100);if(bar)bar.style.width=pct+'%';setMessage('جارٍ رفع الفيديو... '+pct+'٪');}};
        xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve():reject(new Error('تعذر رفع الفيديو. يرجى المحاولة مرة أخرى.'));
        xhr.onerror=()=>reject(new Error('تعذر الاتصال بخدمة رفع الفيديو.'));
        xhr.send(file);
      });
      }
      setMessage('جارٍ حفظ الفيديو...');
      const done=await fetch(base+'complete',{method:'POST',headers:{'X-CSRF-Token':csrf}});
      const result=await done.json();
      if(!done.ok)throw new Error(result.error||'تعذر حفظ الفيديو.');
      window.location.assign(result.next_url);
    }catch(error){setMessage(error.message||'حدث خطأ أثناء رفع الفيديو.');if(button)button.disabled=false;}
  });
})();


(function(){
  const button=document.getElementById('locate-me-btn');
  const field=document.getElementById('accident-location');
  const feedback=document.getElementById('location-feedback');
  const mapLink=document.getElementById('location-map-link');
  if(!button||!field||!feedback)return;
  button.addEventListener('click',function(){
    if(!navigator.geolocation){feedback.textContent='تحديد الموقع غير مدعوم في هذا المتصفح. يمكنك كتابة العنوان يدويًا.';return;}
    button.disabled=true;
    feedback.textContent='جارٍ تحديد موقعك، يرجى السماح بالوصول إلى الموقع...';
    navigator.geolocation.getCurrentPosition(function(position){
      const lat=position.coords.latitude.toFixed(6);
      const lon=position.coords.longitude.toFixed(6);
      field.value=lat+', '+lon;
      if(mapLink)mapLink.dataset.coords=field.value;
      field.dispatchEvent(new Event('input',{bubbles:true}));
      field.dispatchEvent(new Event('change',{bubbles:true}));
      if(mapLink){
        mapLink.href='https://www.google.com/maps?q='+encodeURIComponent(lat+','+lon);
        mapLink.hidden=false;
      }
      feedback.textContent='تم تحديد موقعك. تأكدي أنه موقع الحادث، ويمكنك تعديل الحقل يدويًا.';
      button.disabled=false;
    },function(error){
      const messages={1:'لم يتم السماح بالوصول للموقع. فعّلي الإذن من المتصفح أو اكتبي العنوان يدويًا.',2:'تعذر تحديد الموقع حاليًا. يمكنك كتابة العنوان يدويًا.',3:'استغرق تحديد الموقع وقتًا طويلًا. حاولي مجددًا أو اكتبي العنوان يدويًا.'};
      feedback.textContent=messages[error.code]||'تعذر تحديد الموقع. يمكنك كتابة العنوان يدويًا.';
      button.disabled=false;
    },{enableHighAccuracy:true,timeout:15000,maximumAge:0});
  });
  field.addEventListener('input',function(){
    if(mapLink&&mapLink.hidden===false&&field.value!==mapLink.dataset.coords){mapLink.hidden=true;}
  });
})();
