"""Интерактивный 3D-просмотр (одна HTML-страница с встроенными данными)."""
import json

TEMPLATE = r"""<title>Каркас SPIN</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Unbounded:wght@600&display=swap">
<style>
/* Раскладка: слева 3D-сцена во всю высоту, справа — колонка спецификации; на телефоне колонка уходит вниз */
:root{
  --bg:#eef1f3; --panel:#ffffff; --stage:#e3e8ec; --ink:#1c2127; --muted:#5b6571;
  --line:#d4dae0; --accent:#a86f2c; --accent-ink:#ffffff; --chip:#f4f6f8;
  --f-ui:"Golos Text", "Segoe UI", Roboto, Arial, sans-serif;
  --f-num:"JetBrains Mono", ui-monospace, Consolas, monospace;
  --f-brand:"Unbounded", "Golos Text", Arial, sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#111417; --panel:#181c21; --stage:#0d1013; --ink:#e6e9ed; --muted:#9aa4ae;
  --line:#2a3139; --accent:#d9a254; --accent-ink:#1a1206; --chip:#20262c; color-scheme:dark; } }
:root[data-theme="dark"]{
  --bg:#111417; --panel:#181c21; --stage:#0d1013; --ink:#e6e9ed; --muted:#9aa4ae;
  --line:#2a3139; --accent:#d9a254; --accent-ink:#1a1206; --chip:#20262c; color-scheme:dark; }
html,body{height:100%}
body{background:var(--bg); color:var(--ink); font:14px/1.45 var(--f-ui)}
.app{height:100%; display:grid; grid-template-columns:minmax(0,1fr) 360px}
.stage{position:relative; background:var(--stage); min-height:0}
.stage canvas{display:block; width:100%; height:100%; touch-action:none}
.views{position:absolute; left:16px; top:16px; display:flex; gap:6px; flex-wrap:wrap}
.views button,.seg button{font:500 12px var(--f-ui); color:var(--ink); background:var(--panel);
  border:1px solid var(--line); border-radius:6px; padding:6px 10px; cursor:pointer}
.views button:hover,.seg button:hover{border-color:var(--accent)}
.views button:focus-visible,.seg button:focus-visible,.chip:focus-within,input:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.hint{position:absolute; left:16px; bottom:14px; color:var(--muted); font-size:12px; max-width:calc(100% - 32px)}
.rail{background:var(--panel); border-left:1px solid var(--line); overflow:auto; padding-block:18px; padding-inline:18px;
  display:flex; flex-direction:column; gap:18px; min-width:0}
.brand{display:flex; flex-direction:column; gap:4px}
.brand h1{margin:0; font:600 22px/1.1 var(--f-brand); letter-spacing:.06em}
.brand p{margin:0; color:var(--muted); text-wrap:balance}
h2{margin:0 0 8px; font:600 11px var(--f-ui); letter-spacing:.09em; text-transform:uppercase; color:var(--muted)}
.chips{display:flex; flex-wrap:wrap; gap:6px}
.chip{display:inline-flex; align-items:center; gap:7px; padding:5px 10px 5px 8px; border:1px solid var(--line);
  border-radius:999px; background:var(--chip); cursor:pointer; user-select:none; font-size:13px}
.chip input{position:absolute; opacity:0; pointer-events:none}
.chip i{width:11px; height:11px; border-radius:3px; display:inline-block; border:1px solid rgba(0,0,0,.15)}
.chip:has(input:not(:checked)){opacity:.45}
.seg{display:flex; gap:4px; margin-bottom:8px}
.seg button[aria-pressed="true"]{background:var(--accent); color:var(--accent-ink); border-color:var(--accent)}
.range{display:flex; align-items:center; gap:10px}
.range input{flex:1; accent-color:var(--accent)}
.range output{font:500 12px var(--f-num); min-width:64px; text-align:right; font-variant-numeric:tabular-nums}
.card{border:1px solid var(--line); border-radius:8px; padding:12px; display:flex; flex-direction:column; gap:6px}
.card .code{font:600 18px var(--f-num)}
.card .name{font-weight:500}
.card .meta{color:var(--muted); font-size:13px}
.card.empty{color:var(--muted)}
table{width:100%; border-collapse:collapse; font-size:13px}
td{padding:4px 0; border-bottom:1px solid var(--line); vertical-align:top}
td.n{font-family:var(--f-num); text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; padding-left:10px}
td .sub{color:var(--muted); font-size:12px}
.sw{display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:6px; vertical-align:baseline}
.foot{color:var(--muted); font-size:12px}
@media (max-width: 820px){
  .app{grid-template-columns:1fr; grid-template-rows:62vh auto; height:auto}
  .stage{height:62vh}
  .rail{border-left:0; border-top:1px solid var(--line); overflow:visible}
}
@media (prefers-reduced-motion: reduce){ *{transition:none!important} }
</style>

<div class="app">
  <main class="stage" id="stage">
    <canvas id="c" aria-label="3D-модель каркаса кресла"></canvas>
    <div class="views" role="group" aria-label="Вид">
      <button type="button" data-view="iso">3D</button>
      <button type="button" data-view="front">Спереди</button>
      <button type="button" data-view="side">Сбоку</button>
      <button type="button" data-view="top">Сверху</button>
      <button type="button" data-view="bottom">Снизу</button>
    </div>
    <div class="hint" id="hint">Вращать — левая кнопка или палец · сдвиг — правая · клик по детали показывает её данные</div>
  </main>
  <aside class="rail">
    <div class="brand">
      <h1>SPIN</h1>
      <p>Поворотное кресло: каркас из фанеры 18 мм, поролон, механизм 195×195</p>
    </div>
    <section>
      <h2>Слои</h2>
      <div class="chips" id="layers"></div>
    </section>
    <section>
      <h2>Разрез</h2>
      <div class="seg" id="axis" role="group" aria-label="Плоскость разреза">
        <button type="button" data-axis="none" aria-pressed="true">Нет</button>
        <button type="button" data-axis="x" aria-pressed="false">По оси (x)</button>
        <button type="button" data-axis="y" aria-pressed="false">Поперёк (y)</button>
        <button type="button" data-axis="z" aria-pressed="false">План (z)</button>
      </div>
      <div class="range"><input id="cut" type="range" min="-420" max="420" step="1" value="0" aria-label="Положение разреза, мм"><output id="cutv">x = 0</output></div>
    </section>
    <section>
      <h2>Деталь</h2>
      <div class="card empty" id="pick">Нажмите на деталь в сцене.</div>
    </section>
    <section>
      <h2>Высоты от пола, мм</h2>
      <table id="levels"></table>
    </section>
    <section>
      <h2>Поролон</h2>
      <table id="foam"></table>
    </section>
    <section>
      <h2>Сводка</h2>
      <table id="summary"></table>
    </section>
    <p class="foot">Форма обивки — по 3D-модели SK-00033861, приведённой к 800×820×720. Размеры деталей — в DXF и чертежах проекта.</p>
  </aside>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
const COLORS = {
  surface:'#7f939a', plate:'#dcbf8c', rib:'#cda56a', part:'#b98d55',
  seat:'#eec35a', back:'#e59f8b', arm:'#f1da8e', top:'#9db6c8',
  outer:'#c9ccd1', belt:'#3e4a35', steel:'#26292d'
};
const canvas = document.getElementById('c'), stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1, 2));
renderer.localClippingEnabled = true;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 10, 20000);
camera.up.set(0,0,1);
const controls = new THREE.OrbitControls(camera, canvas);
controls.target.set(0, 20, 360); controls.enableDamping = true; controls.dampingFactor = .12;
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f96, .85));
const sun = new THREE.DirectionalLight(0xffffff, .7); sun.position.set(900,-1400,1800); scene.add(sun);
const fillLight = new THREE.DirectionalLight(0xffffff, .25); fillLight.position.set(-1200,900,600); scene.add(fillLight);

const clip = new THREE.Plane(new THREE.Vector3(-1,0,0), 0);
const clipPlanes = [clip];
const groups = {};
function group(key){ if(!groups[key]){ groups[key]=new THREE.Group(); scene.add(groups[key]); } return groups[key]; }
function mat(color, extra){ return new THREE.MeshStandardMaterial(Object.assign({color, roughness:.8, metalness:0, side:THREE.DoubleSide, clippingPlanes:clipPlanes}, extra||{})); }
function b64(s, T){ const bin = atob(s); const buf = new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) buf[i]=bin.charCodeAt(i); return new T(buf.buffer); }
function shapeOf(outer, holes){
  const sh = new THREE.Shape(outer.map(p=>new THREE.Vector2(p[0],p[1])));
  (holes||[]).forEach(h=>sh.holes.push(new THREE.Path(h.map(p=>new THREE.Vector2(p[0],p[1])))));
  return sh;
}
function extrude(outer, holes, depth){ return new THREE.ExtrudeGeometry(shapeOf(outer, holes), {depth, bevelEnabled:false, curveSegments:1}); }

// обивка
const sv = b64(D.surface.v, Int16Array), si = D.surface.itype==='uint16' ? b64(D.surface.i, Uint16Array) : b64(D.surface.i, Uint32Array);
const sg = new THREE.BufferGeometry();
sg.setAttribute('position', new THREE.Float32BufferAttribute(Float32Array.from(sv), 3));
sg.setIndex(new THREE.BufferAttribute(si, 1)); sg.computeVertexNormals();
const surfMat = mat(COLORS.surface, {transparent:true, opacity:.22, depthWrite:false, roughness:.95});
const surf = new THREE.Mesh(sg, surfMat); group('surface').add(surf);

// каркас
const pickables = [];
D.parts.forEach(p=>{
  const key = p.kind==='plate' ? 'plate' : (p.code.startsWith('ПГ') ? 'part' : 'rib');
  const g = extrude(p.outer, p.holes, p.t);
  const m = mat(COLORS[key], {roughness:.7});
  p.inst.forEach((ins, k)=>{
    const geo = g.clone();
    if(ins===null){ geo.translate(0,0,p.z0); }
    else {
      geo.translate(0,0,-p.t/2);
      const a = ins.m, M = new THREE.Matrix4();
      M.set(a[0][0],a[0][1],a[0][2],a[0][3], a[1][0],a[1][1],a[1][2],a[1][3], a[2][0],a[2][1],a[2][2],a[2][3], 0,0,0,1);
      geo.applyMatrix4(M);
    }
    geo.computeVertexNormals();
    const mm = m.clone(); mm.clippingPlanes = clipPlanes;   // clone() копирует плоскости — возвращаем общую
    const mesh = new THREE.Mesh(geo, mm);
    const xs = p.outer.map(q=>q[0]), ys = p.outer.map(q=>q[1]);
    mesh.userData = {code:p.code, name:p.name, size:[Math.max(...xs)-Math.min(...xs), Math.max(...ys)-Math.min(...ys)], t:p.t,
      qty:p.inst.length, kind:p.kind, info:D.info[p.code]||{}};
    group('frame').add(mesh); pickables.push(mesh);
  });
});

// поролон
D.foam.forEach(f=>{
  let geo, color = f.code.startsWith('С') && !f.code.startsWith('Сп') ? COLORS.seat : f.code.startsWith('Сп') ? COLORS.back : f.code.startsWith('В') ? COLORS.top : COLORS.arm;
  if(f.kind==='mesh'){
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(Float32Array.from(b64(f.v, Int16Array)), 3));
    g.setIndex(new THREE.BufferAttribute(f.itype==='uint16' ? b64(f.i, Uint16Array) : b64(f.i, Uint32Array), 1));
    g.computeVertexNormals();
    const mesh = new THREE.Mesh(g, mat(COLORS.outer, {transparent:true, opacity:.55, depthWrite:false, roughness:1}));
    mesh.userData = {code:f.code, name:f.name, foam:true, info:{}};
    group('foam').add(mesh); pickables.push(mesh); return;
  }
  if(f.kind==='yz'){ geo = extrude(f.outer, [], f.x1-f.x0); const M=new THREE.Matrix4(); M.set(0,0,1,f.x0, 1,0,0,0, 0,1,0,0, 0,0,0,1); geo.applyMatrix4(M); }
  else if(f.kind==='xy'){ geo = extrude(f.outer, [], f.t); geo.translate(0,0,f.z0); }
  else { const s=[0,1,2].map(i=>f.max[i]-f.min[i]); geo = new THREE.BoxGeometry(s[0],s[1],s[2]); geo.translate((f.max[0]+f.min[0])/2,(f.max[1]+f.min[1])/2,(f.max[2]+f.min[2])/2); }
  geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, mat(color, {transparent:true, opacity:.88, roughness:1}));
  mesh.userData = {code:f.code, name:f.name, foam:true, info:D.info[f.code]||{}};
  group('foam').add(mesh); pickables.push(mesh);
});

// ремни
const beltMat = mat(COLORS.belt, {roughness:.9});
D.belts.forEach(b=>{
  const A=new THREE.Vector3(...b.a), B=new THREE.Vector3(...b.b), W=new THREE.Vector3(...b.w).normalize();
  const L=A.distanceTo(B), X=B.clone().sub(A).normalize(), Z=new THREE.Vector3().crossVectors(X,W).normalize();
  const geo=new THREE.BoxGeometry(L,50,2); const M=new THREE.Matrix4().makeBasis(X,W,Z); M.setPosition(A.clone().add(B).multiplyScalar(.5)); geo.applyMatrix4(M);
  const mesh=new THREE.Mesh(geo, beltMat); mesh.userData={code:'Ремень', name:'Ремень мебельный эластичный 50 мм', info:{}}; group('belts').add(mesh); pickables.push(mesh);
});

// основание и механизм
const P = D.params, steel = mat(COLORS.steel, {metalness:.5, roughness:.45});
const disc = new THREE.Mesh(new THREE.CylinderGeometry(P.DISC_D/2, P.DISC_D/2, P.DISC_T, 96).rotateX(Math.PI/2).translate(0,0,P.PAD_H+P.DISC_T/2), steel);
disc.userData={code:'Диск', name:'Стальной диск основания Ø'+P.DISC_D+'×'+P.DISC_T, info:{}};
const sw = new THREE.Group();
const pl1 = new THREE.Mesh(new THREE.BoxGeometry(P.SW,P.SW,3).translate(0,0,P.PAD_H+P.DISC_T+1.5), steel);
const pl2 = new THREE.Mesh(new THREE.BoxGeometry(P.SW,P.SW,3).translate(0,0,P.Z_P1-1.5), steel);
const ring = new THREE.Mesh(new THREE.CylinderGeometry(P.SW*.42,P.SW*.42,P.SWH-6,64).rotateX(Math.PI/2).translate(0,0,P.PAD_H+P.DISC_T+P.SWH/2), steel);
[pl1,pl2,ring].forEach(m=>{m.userData={code:'Механизм', name:'Поворотный механизм '+P.SW+'×'+P.SW+', h='+P.SWH, info:{}}; sw.add(m); pickables.push(m);});
group('base').add(disc); group('base').add(sw); pickables.push(disc);

// слои
const LAYERS = [
  ['surface','Обивка', COLORS.surface, true], ['frame','Каркас', COLORS.plate, true],
  ['foam','Поролон', COLORS.seat, true], ['belts','Ремни', COLORS.belt, true], ['base','Основание', COLORS.steel, true]];
const lay = document.getElementById('layers');
LAYERS.forEach(([k,label,color,on])=>{
  const id='lay-'+k, el=document.createElement('label'); el.className='chip'; el.htmlFor=id;
  el.innerHTML='<input type="checkbox" id="'+id+'"'+(on?' checked':'')+'><i style="background:'+color+'"></i>'+label;
  lay.appendChild(el);
  el.querySelector('input').addEventListener('change', e=>{ groups[k].visible = e.target.checked; render(); });
});

// разрез
let axis='none';
const cut = document.getElementById('cut'), cutv = document.getElementById('cutv');
function applyClip(){
  const v = +cut.value;
  if(axis==='none'){ clip.normal.set(0,0,-1); clip.constant = 1e5; cutv.textContent='—'; }
  if(axis==='x'){ clip.normal.set(-1,0,0); clip.constant = v; cutv.textContent='x = '+v; }
  if(axis==='y'){ clip.normal.set(0,1,0); clip.constant = -v; cutv.textContent='y = '+v; }
  if(axis==='z'){ clip.normal.set(0,0,-1); clip.constant = v; cutv.textContent='z = '+v; }
  cut.disabled = axis==='none'; render();
}
document.querySelectorAll('#axis button').forEach(b=>b.addEventListener('click',()=>{
  axis=b.dataset.axis; document.querySelectorAll('#axis button').forEach(x=>x.setAttribute('aria-pressed', x===b?'true':'false'));
  if(axis==='z'){ cut.min=0; cut.max=760; cut.value=470; } else if(axis==='y'){ cut.min=-420; cut.max=440; cut.value=0; } else { cut.min=-420; cut.max=420; cut.value=0; }
  applyClip();
}));
cut.addEventListener('input', applyClip);

// виды
const VIEWS = { iso:[1500,-1750,1150], front:[0,-2600,420], side:[2600,0,420], top:[0,-1,2900], bottom:[0,-1,-2600] };
function setView(k){ const p=VIEWS[k]; camera.position.set(p[0],p[1],p[2]); controls.target.set(0,20,k==='top'||k==='bottom'?300:370); controls.update(); render(); }
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));

// выбор детали
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(); let down=null, picked=null;
canvas.addEventListener('pointerdown', e=>{ down=[e.clientX,e.clientY]; });
canvas.addEventListener('pointerup', e=>{
  if(!down || Math.hypot(e.clientX-down[0], e.clientY-down[1])>5) return;
  const r = canvas.getBoundingClientRect(); ndc.set(((e.clientX-r.left)/r.width)*2-1, -((e.clientY-r.top)/r.height)*2+1);
  ray.setFromCamera(ndc, camera);
  const vis = pickables.filter(m=>{ let o=m; while(o){ if(!o.visible) return false; o=o.parent; } return true; });
  const hits = ray.intersectObjects(vis, false).filter(h=>clip.distanceToPoint(h.point)>=0);
  if(picked && picked.material.emissive) picked.material.emissive.setHex(0);
  picked = hits.length ? hits[0].object : null;
  if(picked && picked.material.emissive) picked.material.emissive.setHex(0x553300);
  showPick(picked ? picked.userData : null); render();
});
const pickEl = document.getElementById('pick');
function esc(s){ return String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function showPick(u){
  if(!u){ pickEl.className='card empty'; pickEl.textContent='Нажмите на деталь в сцене.'; return; }
  pickEl.className='card';
  let h='<div class="code">'+esc(u.code)+'</div><div class="name">'+esc(u.name)+'</div>';
  if(u.size) h+='<div class="meta">Габарит '+Math.round(u.size[0])+' × '+Math.round(u.size[1])+' мм, толщина '+u.t+' мм · '+u.qty+' шт.</div>';
  if(u.info && u.info.material) h+='<div class="meta">'+esc(u.info.material)+'</div>';
  if(u.info && u.info.note) h+='<div class="meta">'+esc(u.info.note)+'</div>';
  pickEl.innerHTML=h;
}

// таблицы
function fill(id, rows){ document.getElementById(id).innerHTML = rows.map(r=>'<tr><td>'+r[0]+'</td><td class="n">'+r[1]+'</td></tr>').join(''); }
fill('levels', D.summary.levels.map(r=>[esc(r[0]), esc(r[1])]));
fill('foam', D.summary.foam.map(r=>['<span class="sw" style="background:'+r[3]+'"></span>'+esc(r[0])+'<div class="sub">'+esc(r[1])+'</div>', esc(r[2])]));
fill('summary', D.summary.totals.map(r=>[esc(r[0]), esc(r[1])]));

// рендер
let needs=true;
function render(){ needs=true; }
function resize(){ const w=stage.clientWidth, h=stage.clientHeight; renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix(); render(); }
new ResizeObserver(resize).observe(stage);
controls.addEventListener('change', render);
function loop(){ requestAnimationFrame(loop); controls.update(); if(needs){ needs=false; renderer.render(scene,camera); } }
setView('iso'); applyClip(); resize(); loop();
})();
</script>
"""


def build_html(data):
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", js)
