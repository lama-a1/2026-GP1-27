function copyInvite(){const el=document.getElementById('inviteLink');if(!el)return;navigator.clipboard.writeText(el.value).then(()=>alert('تم نسخ رابط الدعوة')).catch(()=>{el.select();document.execCommand('copy');alert('تم نسخ الرابط')})}
function showFilename(input){const el=document.getElementById('filename');if(el)el.textContent=input.files.length?input.files[0].name:''}
