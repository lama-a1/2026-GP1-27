/* fill the description from the selected pictures (the user can still edit it) */
(function(){
  const root=document.getElementById('desc-step');
  if(!root)return;
  const type=root.dataset.type; // the case is either rear-end or lane-change
  const saved=JSON.parse(root.dataset.meta||'{}');
  const form=root.closest('form');
  const $=id=>document.getElementById(id);
  const ZN={front:'المقدمة','front-left':'المقدمة من اليسار','front-right':'المقدمة من اليمين',left:'الجانب الأيسر',right:'الجانب الأيمن','rear-left':'المؤخرة من اليسار','rear-right':'المؤخرة من اليمين',rear:'المؤخرة'};
  const MINE='#2f7a52',OTHER='#d9573a',GREY='#9aa3ab',ME='أنت',OT='الطرف الآخر';
  const F='font-family="Tajawal,Tahoma,sans-serif"';
  const st={
    pos:saved.pos||root.dataset.role||'',
    rcase:saved.rcase||'',
    side:saved.side||'',
    who:saved.who||'',
    zone:saved.zone||'',
    edited:false
  };
  if(type==='REAR_END'&&!st.zone&&st.pos)st.zone=st.pos==='FRONT'?'rear':'front';

  const car=(x,y,c,o={})=>{
    const tl=o.brake?'#ff3b2f':'#b3271b';
    const glow=o.brake?'<ellipse cx="0" cy="36" rx="16" ry="6" fill="#ff3b2f" opacity=".35"/>':'';
    return `<g transform="translate(${x} ${y}) rotate(${o.rot||0})">${glow}
     <rect x="-20.5" y="-14" width="4" height="7" rx="1.5" fill="${c}"/><rect x="16.5" y="-14" width="4" height="7" rx="1.5" fill="${c}"/>
     <rect x="-17" y="-31" width="34" height="62" rx="9" fill="${c}"/>
     <rect x="-12" y="-31" width="7" height="3.5" rx="1.5" fill="#fff1c9"/><rect x="5" y="-31" width="7" height="3.5" rx="1.5" fill="#fff1c9"/>
     <path d="M-13 -11 Q0 -16 13 -11 L11 -19 Q0 -22 -11 -19 Z" fill="#000" opacity=".42"/>
     <rect x="-11" y="-8" width="22" height="20" rx="3" fill="#000" opacity=".16"/>
     <path d="M-12 16 Q0 13 12 16 L11 22 Q0 24 -11 22 Z" fill="#000" opacity=".42"/>
     <rect x="-13" y="27.5" width="8" height="3.5" rx="1.5" fill="${tl}"/><rect x="5" y="27.5" width="8" height="3.5" rx="1.5" fill="${tl}"/></g>`;
  };
  const star=(x,y)=>{let p=[];for(let i=0;i<16;i++){const r=i%2?6:14,a=Math.PI*i/8;p.push((x+r*Math.cos(a)).toFixed(1)+','+(y+r*Math.sin(a)).toFixed(1))}return `<polygon points="${p.join(' ')}" fill="#ffc22e"/>`};
  const tag=(x,y,t,anchor='middle')=>{const w=t.length*5.6+16,x0=anchor==='end'?x-w:anchor==='start'?x:x-w/2;
    return `<rect x="${x0}" y="${y-10}" width="${w}" height="20" rx="10" fill="#fff"/><text x="${x0+w/2}" y="${y+4}" text-anchor="middle" font-size="11" font-weight="700" fill="#17231b" ${F}>${t}</text>`};
  const road=h=>`<rect width="200" height="${h}" rx="10" fill="#dfe8e2"/><rect x="22" width="156" height="${h}" fill="#3a3d45"/>
    <line x1="31" y1="0" x2="31" y2="${h}" stroke="#fff" stroke-width="3"/><line x1="169" y1="0" x2="169" y2="${h}" stroke="#fff" stroke-width="3"/>
    <line x1="100" y1="4" x2="100" y2="${h}" stroke="#fff" stroke-width="3" stroke-dasharray="16 14"/>`;
  const trail=(x1,y1,x2,y2)=>`<path d="M${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2+20}, ${x2} ${y2}" fill="none" stroke="#f0937a" stroke-width="2.5" stroke-dasharray="6 5"/>`;
  const svg=(h,inner)=>`<svg viewBox="0 0 200 ${h}" aria-hidden="true">${inner}</svg>`;
  const who2=isMe=>isMe?[MINE,ME]:[OTHER,OT];
  const R=134;
  function posScene(pos){
    const [fc,ft]=who2(pos==='FRONT'),[rc,rt]=who2(pos==='REAR');
    return svg(220,road(220)+car(R,78,fc)+car(R,146,rc)+star(R,112)+tag(114,78,ft,'end')+tag(114,146,rt,'end'));
  }
  function rearScene(kind,pos){
    pos=pos||'REAR';
    const [fc,ft]=who2(pos==='FRONT'),[rc,rt]=who2(pos==='REAR');
    if(kind==='normal')return svg(240,road(240)+car(R,44,GREY)+car(R,118,fc,{brake:1})+car(R,186,rc)+star(R,152)+tag(114,44,'زحمة','end')+tag(114,118,ft,'end')+tag(114,186,rt,'end'));
    if(kind==='sudden')return svg(240,road(240)+`<circle cx="${R}" cy="40" r="15" fill="#e5483b"/><text x="${R}" y="47" text-anchor="middle" font-size="20" font-weight="700" fill="#fff" ${F}>!</text>`+tag(114,40,'ما فيه شي قدام','end')+car(R,118,fc,{brake:1})+car(R,186,rc)+star(R,152)+tag(114,118,ft,'end')+tag(114,186,rt,'end'));
    return svg(240,road(240)+trail(66,236,124,140)+car(128,110,fc,{rot:16})+car(R,190,rc)+star(R,154)+tag(96,92,ft,'end')+tag(114,200,rt,'end'));
  }
  function laneScene(who,side){
    side=side||'left';
    const L=66,myX=side==='left'?R:L,otX=side==='left'?L:R,myY=150,otY=120;
    let parts='',moved=false;
    const draw=(x,y,c,t,moving,targetX)=>{
      if(!moving)return car(x,y,c)+tag(x,y-48,t);
      const d=targetX>x?1:-1;moved=true;
      return trail(x,y+75,x+d*20,y+30)+car(x+d*22,y,c,{rot:d*18})+tag(x,y-48,t);
    };
    parts+=draw(otX,otY,OTHER,OT,who==='other'||who==='both',myX);
    parts+=draw(myX,myY,MINE,ME,who==='me'||who==='both',otX);
    return svg(230,road(230)+parts+(moved?star(100,who==='both'?126:(who==='me'?120:142)):''));
  }
  const POS={FRONT:'المركبة الأمامية',REAR:'المركبة الخلفية'};
  const RC={normal:['الأمامية خففت أو وقفت بشكل طبيعي','بسبب زحمة أو إشارة أو عائق أمامها'],
            sudden:['الأمامية وقفت فجأة دون سبب','لا يوجد أمامها ما يستدعي الوقوف'],
            cutin:['الأمامية دخلت المسار قبل الصدمة بقليل','غيّرت مسارها أمام الخلفية ثم وقع الصدم']};
  const WHO={me:'أنا غيّرت المسار',other:'الطرف الآخر غيّر المسار',both:'كلانا غيّر المسار في الوقت نفسه'};
  const SIDE={left:'على يساري',right:'على يميني'};
  const opt=(key,val,art,label,sub,you)=>`<button type="button" class="desc-opt" data-k="${key}" data-v="${val}" aria-pressed="${st[key]===val}">${art}${you?'<em class="you">أنت</em>':''}<span>${label}</span>${sub?`<small>${sub}</small>`:''}</button>`;
  // put the selected answers into the description
  function sentence(){
    const z=ZN[st.zone];
    if(type==='REAR_END'){
      if(!st.pos||!st.rcase||!z)return '';
      const me=st.pos==='FRONT';
      const s={normal:me?'كنت أخفف السرعة بشكل طبيعي وصدمتني السيارة التي خلفي':'كانت السيارة التي أمامي تخفف السرعة بشكل طبيعي فصدمتها',
               sudden:me?'توقفت فجأة فصدمتني السيارة التي خلفي':'توقفت السيارة التي أمامي فجأة دون سبب فصدمتها',
               cutin:me?'دخلت المسار أمام سيارة الطرف الآخر قبل الصدمة بقليل فصدمتني من الخلف':'دخلت سيارة الطرف الآخر المسار أمامي قبل الصدمة بقليل فصدمتها'}[st.rcase];
      return `مكان الصدمة: ${z}\nكنت في ${POS[st.pos]}، و${s}، والصدمة في ${z} من سيارتي.`;
    }
    if(!st.who||!st.side||!z)return '';
    const w={me:'غيّرت المسار',other:'غيّر الطرف الآخر المسار',both:'غيّر الطرفان المسار في الوقت نفسه'}[st.who];
    return `مكان الصدمة: ${z}\n${w}، وكانت سيارة الطرف الآخر ${SIDE[st.side]}، والصدمة في ${z} من سيارتي.`;
  }
  const ta=$('desc-text');
  if(ta.value.trim()&&ta.value.trim()!==sentence().trim())st.edited=true;
  function count(){const n=ta.value.trim().length;$('desc-count').innerHTML=`<span class="${n<10||n>500?'bad':''}">${n} / 500</span>`}
  function render(){
    if(type==='REAR_END'){
      $('d-pos').innerHTML=['REAR','FRONT'].map(v=>opt('pos',v,posScene(v),POS[v],'',1)).join('');
      $('d-rcase').innerHTML=['normal','sudden','cutin'].map(v=>opt('rcase',v,rearScene(v,st.pos),...RC[v])).join('');
    }else{
      $('d-side').innerHTML=['left','right'].map(v=>opt('side',v,laneScene('none',v),SIDE[v])).join('');
      $('d-who').innerHTML=['me','other','both'].map(v=>opt('who',v,laneScene(v,st.side),WHO[v])).join('');
    }
    root.querySelectorAll('.zone').forEach(z=>z.classList.toggle('on',z.dataset.z===st.zone));
    $('zone-text').textContent=ZN[st.zone]||'لم يُحدَّد بعد';
    ['pos','rcase','side','who','zone'].forEach(k=>{const el=form.elements[k];if(el)el.value=st[k]||'';});
    const sen=sentence();
    // keep what the user typed if they edited the description
    if(!st.edited&&sen&&ta.value!==sen){ta.value=sen;ta.dispatchEvent(new Event('change',{bubbles:true}));}
    $('desc-refill').hidden=!st.edited||!sen;
    count();
  }
  root.addEventListener('click',e=>{
    const b=e.target.closest('.desc-opt[data-k]');if(!b)return;
    st[b.dataset.k]=b.dataset.v;
    if(b.dataset.k==='pos')st.zone=b.dataset.v==='FRONT'?'rear':'front';
    render();
  });
  root.querySelectorAll('.zone').forEach(z=>{const f=()=>{st.zone=z.dataset.z;render()};z.addEventListener('click',f);z.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();f()}})});
  ta.addEventListener('input',()=>{st.edited=ta.value!==sentence();$('desc-refill').hidden=!st.edited||!sentence();count()});
  $('desc-refill').addEventListener('click',()=>{st.edited=false;render()});
  form.addEventListener('submit',e=>{
    const missing=[];
    if(type==='REAR_END'){if(!st.pos)missing.push('موقع مركبتك');if(!st.rcase)missing.push('ما حدث قبل الصدمة');}
    else{if(!st.side)missing.push('جهة سيارة الطرف الآخر');if(!st.who)missing.push('من غيّر المسار');}
    if(!st.zone)missing.push('مكان الصدمة');
    const n=ta.value.trim().length;
    let msg=missing.length?'يرجى تحديد: '+missing.join('، ')+'.':'';
    if(!msg&&(n<10||n>500))msg='وصف الحادث يجب أن يكون من 10 إلى 500 حرف.';
    const err=$('desc-error');err.textContent=msg;err.hidden=!msg;
    if(msg){e.preventDefault();e.stopImmediatePropagation();err.scrollIntoView({behavior:'smooth',block:'center'});}
  },true);
  render();
})();
