// copy the invite link
function copyInvite(){const el=document.getElementById('inviteLink');if(!el)return;navigator.clipboard.writeText(el.value).then(()=>alert('تم نسخ رابط الدعوة')).catch(()=>{el.select();document.execCommand('copy');alert('تم نسخ الرابط')})}
// show the name of the chosen video
function showFilename(input){
  const el=document.getElementById('filename');
  if(el)el.textContent=input.files.length?input.files[0].name:'';
  const controls=document.getElementById('video-selection-controls');
  if(controls)controls.hidden=!input.files.length;
  const form=input.closest('form');
  if(form)form.dispatchEvent(new Event('change',{bubbles:true}));
}
(function(){
  // remove the chosen video
  const clear=document.getElementById('clear-selected-video');
  const file=document.querySelector('input[name="video"]');
  if(clear&&file)clear.addEventListener('click',()=>{file.value='';showFilename(file);});
})();
(function(){
  // the invite button works only when the email is valid
  const form=document.getElementById('party-invite-form');
  const field=document.querySelector('input[name="recipient_email"][form="party-invite-form"]');
  const button=document.getElementById('send-party-invite');
  if(!form||!field||!button)return;
  function update(){button.disabled=!(field.value.trim()&&field.checkValidity());}
  field.addEventListener('input',update);
  field.addEventListener('change',update);
  form.addEventListener('submit',function(event){
    update();
    if(button.disabled){event.preventDefault();field.reportValidity();}
  });
  update();
})();

(function(){
  // keep the submit button disabled until the form is filled correctly
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
  // upload the video to Cloudinary in parts and show the progress
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
      const response=await fetch(base+'presign',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({filename:file.name,size:file.size,camera:(form.querySelector('[name="camera"]:checked')||{}).value||''})});
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
      // stay on the video step so the user can check or delete the video
      window.location.assign('/cases/'+encodeURIComponent(caseId)+'/steps/5');
    }catch(error){setMessage(error.message||'حدث خطأ أثناء رفع الفيديو.');if(button)button.disabled=false;}
  });
})();


(function(){
  // "my location" button: fill in the accident location from the browser
  const button=document.getElementById('locate-me-btn');
  const field=document.getElementById('accident-location');
  const feedback=document.getElementById('location-feedback');
  const mapLink=document.getElementById('location-map-link');
  if(!button||!field||!feedback)return;
  button.addEventListener('click',function(){
    if(!navigator.geolocation){feedback.textContent='تحديد الموقع غير مدعوم في هذا المتصفح، ويمكن كتابة العنوان يدويًا.';return;}
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
      feedback.textContent='تم تحديد الموقع. يُرجى التأكد أنه موقع الحادث، مع إمكانية تعديله يدويًا.';
      button.disabled=false;
    },function(error){
      const messages={1:'لم يتم السماح بالوصول للموقع. يمكن تفعيل الإذن من المتصفح أو كتابة العنوان يدويًا.',2:'تعذر تحديد الموقع حاليًا، ويمكن كتابة العنوان يدويًا.',3:'استغرق تحديد الموقع وقتًا طويلًا. يمكن المحاولة مجددًا أو كتابة العنوان يدويًا.'};
      feedback.textContent=messages[error.code]||'تعذر تحديد الموقع، ويمكن كتابة العنوان يدويًا.';
      button.disabled=false;
    },{enableHighAccuracy:true,timeout:15000,maximumAge:0});
  });
  field.addEventListener('input',function(){
    if(mapLink&&mapLink.hidden===false&&field.value!==mapLink.dataset.coords){mapLink.hidden=true;}
  });
})();

// sign up form: show the error under each field and the password strength
(function(){
  const form=document.querySelector('form.explain-errors');
  if(!form)return;
  const digits=v=>v.replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d)).trim();
  function strength(pw){
    let score=0;
    if(pw.length>=8)score++;
    if(/[A-Za-z؀-ۿ]/.test(pw)&&/\d/.test(pw))score++;
    if(/[A-Z]/.test(pw)&&/[a-z]/.test(pw)||pw.length>=12)score++;
    if(/[^A-Za-z0-9؀-ۿ\s]/.test(pw))score++;
    return pw?Math.max(score,1):0;
  }
  const meter=form.querySelector('.pw-meter'),label=form.querySelector('.pw-label');
  const names=['','ضعيفة','متوسطة','جيدة','قوية'];
  function paintMeter(){
    const pw=form.password.value,s=strength(pw);
    meter.dataset.level=s;
    label.textContent=pw?('قوة كلمة المرور: '+names[s]+(s<2?' — يلزم حروف وأرقام (٨ أحرف على الأقل).':'')):'٨ أحرف على الأقل، وتتضمن حرفًا ورقمًا.';
  }
  function errors(){
    const e={};
    const name=form.full_name.value.trim();
    if(!name)e.full_name='الاسم الثلاثي مطلوب.';
    else if(name.split(/\s+/).length<3)e.full_name='الاسم الثلاثي مطلوب: الاسم الأول واسم الأب واسم العائلة.';
    const birth=form.birth_date.value;
    if(!birth)e.birth_date='تاريخ الميلاد مطلوب.';
    else{
      const b=new Date(birth+'T00:00'),t=new Date();
      let age=t.getFullYear()-b.getFullYear();
      if(t.getMonth()<b.getMonth()||(t.getMonth()===b.getMonth()&&t.getDate()<b.getDate()))age--;
      if(b>t)e.birth_date='تاريخ الميلاد لا يمكن أن يكون في المستقبل.';
      else if(age<18)e.birth_date='يجب أن يكون عمرك 18 سنة أو أكثر.';
    }
    const nid=digits(form.national_id.value);
    if(!nid)e.national_id='رقم الهوية أو الإقامة مطلوب.';
    else if(!/^[12]\d{9}$/.test(nid))e.national_id='يجب أن يبدأ بـ 1 (هوية) أو 2 (إقامة) ويتكون من 10 أرقام.';
    const email=form.email.value.trim();
    if(!email)e.email='البريد الإلكتروني مطلوب.';
    else if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))e.email='صيغة البريد غير صحيحة، مثال: name@example.com';
    const phone=digits(form.phone.value);
    if(!phone)e.phone='رقم الجوال مطلوب.';
    else if(!/^05\d{8}$/.test(phone))e.phone='رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام.';
    const pw=form.password.value;
    if(!pw)e.password='كلمة المرور مطلوبة.';
    else if(pw.length<8||!/[A-Za-z؀-ۿ]/.test(pw)||!/\d/.test(pw))e.password='كلمة المرور ضعيفة: يلزم ٨ أحرف على الأقل، منها حرف ورقم.';
    if(!form.confirm_password.value)e.confirm_password='تأكيد كلمة المرور مطلوب.';
    else if(form.confirm_password.value!==pw)e.confirm_password='كلمتا المرور غير متطابقتين.';
    return e;
  }
  function paint(){
    const e=errors();
    form.querySelectorAll('[data-error-for]').forEach(el=>{
      const msg=e[el.dataset.errorFor]||'';
      el.textContent=msg;el.hidden=!msg;
      const input=form.elements[el.dataset.errorFor];
      if(input)input.classList.toggle('is-invalid',!!msg);
    });
    return e;
  }
  form.password.addEventListener('input',paintMeter);
  form.addEventListener('input',()=>{if(form.dataset.tried)paint();});
  form.addEventListener('submit',ev=>{
    form.dataset.tried='1';
    const e=paint();
    if(Object.keys(e).length){ev.preventDefault();form.querySelector('.is-invalid')?.focus();}
  });
  paintMeter();
})();

// plate fields: check the letters and numbers and show a preview of the plate
(function(){
  const AR2EN={'أ':'A','ب':'B','ح':'J','د':'D','ر':'R','س':'S','ص':'X','ط':'T','ع':'E','ق':'G','ك':'K','ل':'L','م':'Z','ن':'N','هـ':'H','و':'U','ى':'V'};
  const EN2AR=Object.fromEntries(Object.entries(AR2EN).map(([a,e])=>[e,a]));
  const toAr=d=>String(d).replace(/\d/g,x=>'٠١٢٣٤٥٦٧٨٩'[x]);
  const toEn=v=>String(v).replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  function tokens(v){
    return Array.from(v.replace(/ـ/g,'').replace(/\s+/g,'')).map(t=>{
      if(EN2AR[t.toUpperCase()])return EN2AR[t.toUpperCase()];
      if(t==='ه')return 'هـ';
      if(['ا','إ','آ'].includes(t))return 'أ';if(t==='ي')return 'ى';return t;});
  }
  document.querySelectorAll('[data-plate-field]').forEach(box=>{
    const L=box.querySelector('[name=plate_letters]'),N=box.querySelector('[name=plate_numbers]');
    const err=box.querySelector('[data-plate-error]');
    const pv=k=>box.querySelector('[data-pv="'+k+'"]');
    function check(){
      const t=tokens(L.value),n=toEn(N.value).trim();let msg='';
      if(!t.length)msg='حروف اللوحة مطلوبة.';
      else if(t.length>3)msg='حروف اللوحة 3 كحد أقصى.';
      else if(t.some(x=>!AR2EN[x]))msg='الحرف «'+t.find(x=>!AR2EN[x])+'» غير مستخدم في اللوحات السعودية.';
      else if(!/^\d{1,4}$/.test(n))msg='أرقام اللوحة من 1 إلى 4 أرقام.';
      return msg;
    }
    function paint(show){
      const t=tokens(L.value),n=toEn(N.value).replace(/\D/g,'');
      pv('let-ar').textContent=t.length?t.join(' '):'—';
      pv('let-en').textContent=t.length?t.map(x=>AR2EN[x]||'?').join(' '):'—';
      pv('num-ar').textContent=n?toAr(n):'—';
      pv('num-en').textContent=n||'—';
      const msg=check();
      if(show||box.dataset.tried){err.textContent=msg;err.hidden=!msg;L.classList.toggle('is-invalid',!!msg&&/حروف|الحرف/.test(msg));N.classList.toggle('is-invalid',!!msg&&/أرقام/.test(msg));}
      L.setCustomValidity(msg&&/حروف|الحرف/.test(msg)?msg:'');N.setCustomValidity(msg&&/أرقام/.test(msg)?msg:'');
      return !msg;
    }
    box.querySelectorAll('[data-letter]').forEach(b=>b.addEventListener('click',()=>{
      const t=tokens(L.value);
      if(b.dataset.letter==='back')t.pop();else if(t.length<3)t.push(b.dataset.letter);
      L.value=t.join(' ');L.dispatchEvent(new Event('input',{bubbles:true}));
    }));
    N.addEventListener('input',()=>{N.value=toEn(N.value).replace(/\D/g,'').slice(0,4);});
    [L,N].forEach(el=>el.addEventListener('input',()=>paint(false)));
    [L,N].forEach(el=>el.addEventListener('invalid',()=>{box.dataset.tried='1';paint(true);}));
    const form=box.closest('form');
    form&&form.addEventListener('submit',e=>{box.dataset.tried='1';if(!paint(true)){e.preventDefault();e.stopImmediatePropagation();}},true);
    box._repaint=()=>paint(false);
    paint(false);
  });
  document.querySelectorAll('[data-color-field]').forEach(box=>{
    const input=box.querySelector('[name=color]');
    const sync=()=>box.querySelectorAll('[data-color]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.color===input.value.trim())));
    box.querySelectorAll('[data-color]').forEach(b=>b.addEventListener('click',()=>{input.value=b.dataset.color;sync();input.dispatchEvent(new Event('input',{bubbles:true}));}));
    input.addEventListener('input',sync);box._repaint=sync;sync();
  });
})();

// password strength for the expert account (at least 12 characters)
(function(){
  document.querySelectorAll('[data-pw-strength]').forEach(box=>{
    const min=+box.dataset.pwStrength,input=box.querySelector('input'),meter=box.querySelector('.pw-meter'),label=box.querySelector('.pw-label');
    const names=['','ضعيفة','متوسطة','جيدة','قوية'];
    input.addEventListener('input',()=>{
      const pw=input.value;let s=0;
      if(pw.length>=min)s++;
      if(/[a-z]/.test(pw)&&/[A-Z]/.test(pw))s++;
      if(/\d/.test(pw))s++;
      if(/[^A-Za-z0-9]/.test(pw))s++;
      if(pw&&pw.length<min)s=1;
      meter.dataset.level=pw?Math.max(s,1):0;
      label.textContent=!pw?'١٢ حرفًا على الأقل.':('قوة كلمة المرور: '+names[Math.max(s,1)]+(pw.length<min?' — يلزم '+min+' حرفًا على الأقل.':''));
    });
  });
})();

// car year: numbers only, and show the error while typing
(function(){
  const max=new Date().getFullYear()+1, min=1950;
  document.querySelectorAll('input[name="year"]').forEach(input=>{
    let err=document.createElement('span');
    err.className='field-error'; err.hidden=true;
    input.insertAdjacentElement('afterend',err);
    function check(final){
      const v=input.value;
      let msg='';
      if(!v) msg=final?'سنة الصنع مطلوبة':'';
      else if(v.length<4) msg=final?'سنة الصنع 4 أرقام، مثال: 2022':'';
      else if(+v<min||+v>max) msg='سنة الصنع بين '+min+' و'+max;
      err.textContent=msg; err.hidden=!msg;
      input.classList.toggle('is-invalid',!!msg);
      input.setCustomValidity(msg);
      return !msg;
    }
    input.addEventListener('input',()=>{
      const clean=input.value.replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/\D/g,'').slice(0,4);
      if(clean!==input.value){input.value=clean; if(!clean){err.textContent='سنة الصنع أرقام فقط';err.hidden=false;input.classList.add('is-invalid');input.setCustomValidity('سنة الصنع أرقام فقط');return;}}
      check(false);
    });
    input.addEventListener('keypress',e=>{if(e.key.length===1&&!/[0-9٠-٩]/.test(e.key)){e.preventDefault();err.textContent='سنة الصنع أرقام فقط';err.hidden=false;input.classList.add('is-invalid');}});
    input.addEventListener('blur',()=>check(true));
    input.addEventListener('invalid',()=>check(true));
    if(input.value)check(false);
  });
})();
