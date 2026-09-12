<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GoMerry $1</title>
<script src="https://www.paypal.com/sdk/js?client-id=BAAKnJCVrPoYLyEIbjyPO386i1lwPehh1cOxlVOjMIAJhq6hqibOOSMEKaCvvNgxftzoJ9TyZSEIrFTD9g&currency=USD"></script>
<style>body{font-family:Arial;background:#f0f8ff;padding:15px}.card{background:white;padding:20px;border-radius:15px;max-width:420px;margin:15px auto;box-shadow:0 5px 20px rgba(0,0,0,0.1)}input,select{width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #ddd}button{width:100%;padding:14px;background:#0070ba;color:white;border:none;border-radius:8px;font-size:17px;font-weight:bold}.hidden{display:none}</style>
</head><body>
<div class="card" id="s1">
<h2>🎉 GoMerry - Pay $1 to Play LIVE</h2>
<p>Pay $1 real to unlock. Choose $1-$100, win <b>10X</b>!</p>
<input id="regName" placeholder="Your Name">
<input id="regPhone" placeholder="Phone / Email">
<div id="paypal-button" style="margin-top:15px"></div>
<p id="regStatus" style="color:green;font-weight:bold"></p>
<p style="font-size:12px;color:green">✅ LIVE PayPal - Real $1 will go to victorkiragu06@gmail.com</p>
</div>
<div class="card hidden" id="s2">
<h2>Choose Amount - Win 10X</h2>
<select id="rangeSel" onchange="updR()"><option value="1-10">$1-10 Win up to $100</option><option value="10-50">$10-50 Win up to $500</option><option value="50-100">$50-100 Win up to $1000</option><option value="1-100">$1-100 Win up to $1000</option></select>
<p>Your Pay: $<span id="aT">5</span> → Potential Win: $<span id="wT">50</span></p>
<input type="range" id="rng" min="1" max="10" value="5" style="width:100%" oninput="updA()">
<input id="name" placeholder="Confirm Name"><input id="phone" readonly style="background:#eee">
<button onclick="join()">JOIN & WIN 10X</button>
<div id="res" style="margin-top:15px"></div><p id="gInfo" style="text-align:center"></p>
</div>
<script>
let rmin=1,rmax=10,amt=5;
function updR(){let v=document.getElementById('rangeSel').value;[rmin,rmax]=v.split('-').map(Number);let r=document.getElementById('rng');r.min=rmin;r.max=rmax;r.value=Math.floor((rmin+rmax)/2);updA();load();}
function updA(){amt=document.getElementById('rng').value;document.getElementById('aT').innerText=amt;document.getElementById('wT').innerText=amt*10;}
paypal.Buttons({createOrder:(d,a)=>{if(!regName.value||!regPhone.value){alert('Enter name & phone first');return;}return a.order.create({purchase_units:[{amount:{value:'1.00'},description:'GoMerry $1 Registration'}]})},onApprove:(d,a)=>a.order.capture().then(()=>{fetch('/api/verify_registration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:regPhone.value,name:regName.value,orderID:d.orderID,amount:1})}).then(r=>r.json()).then(()=>{regStatus.innerText='✅ $1 Paid REAL! Order '+d.orderID;s1.classList.add('hidden');s2.classList.remove('hidden');name.value=regName.value;phone.value=regPhone.value;updR();})}),onError:e=>alert('PayPal Error:'+e)}).render('#paypal-button');
function join(){fetch('/api/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.value,phone:phone.value,range_min:rmin,range_max:rmax,amount:parseInt(amt)})}).then(r=>r.json()).then(d=>{if(d.error){alert(d.error);return;}res.innerHTML=`<div style="background:#e8ffe8;padding:15px;border-radius:10px;text-align:center"><h3>✅ Joined Group #${d.group_number}</h3><p>Range: ${d.range}<br>You: $${amt} | Win: $${d.lifetime_amount}<br>Members: ${d.count}/10 | Pool: $${d.total}<br>${d.is_full?'🎉 Winner: '+d.beneficiary.name:''}</p></div>`;load();})}
function load(){fetch(`/api/group_status/${rmin}/${rmax}`).then(r=>r.json()).then(d=>{gInfo.innerText=`Live Group: ${d.count||0}/10 | Pool: $${d.total||0}`;});}
</script></body></html>
