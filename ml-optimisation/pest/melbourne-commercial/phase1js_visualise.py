"""
Phase 1 — Per-Tech Dashboard
Single self-contained HTML map: select a preferred resource (tech) to see
their FLs distributed across {week}-{day} slots.

Filter chip behaviour:
  Click       = solo (select only this one)
  Shift+Click = toggle (multi-select)
  "all"       = restore all
"""

import io, os, sys, json
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_CSV  = os.path.join(DIR, 'phase1js_setup_output.csv')
FL_CSV     = os.path.join(DIR, 'phase1js_fl_assignments.csv')
SLOT_CSV   = os.path.join(DIR, 'phase1js_slot_capacity.csv')
TECH_CSV   = os.path.join(DIR, 'phase1js_tech_summary.csv')
OUT_HTML   = os.path.join(DIR, 'phase1js_dashboard.html')

setup = pd.read_csv(SETUP_CSV)
fl    = pd.read_csv(FL_CSV)
slot  = pd.read_csv(SLOT_CSV)
techs = pd.read_csv(TECH_CSV)

# Build per (tech, FL) records for the map
def setups_for_tech_fl(g):
    rows = []
    for _, r in g.iterrows():
        wk = r.get('week')
        wk = '' if (pd.isna(wk) or wk == 0) else int(wk)
        rows.append({
            'freq'    : str(r.get('Recurrence Frequency','')),
            'duration': float(r.get('effective_duration', 0) or 0),
            'pattern' : str(r.get('*New Date Pattern','')),
            'week'    : wk,
            'day'     : str(r.get('day','')),
        })
    return rows

setup_grp = setup.groupby(['tech','%FL_id']).apply(setups_for_tech_fl).rename('setup_list').reset_index()
fl_full = fl.merge(setup_grp, on=['tech','%FL_id'], how='left')
fl_full['setups'] = fl_full['setup_list']

records = []
for _, r in fl_full.iterrows():
    setups_list = r['setups'] if isinstance(r['setups'], list) else []
    weeks = sorted({s['week'] for s in setups_list if s['week'] != ''})
    freqs = sorted({s['freq'] for s in setups_list if s['freq']})
    records.append({
        'fl_id'    : r['%FL_id'],
        'name'     : str(r['FL_name']),
        'city'     : str(r.get('city','')),
        'lat'      : float(r['latitude']),
        'lon'      : float(r['longitude']),
        'tech'     : str(r['tech']),
        'day'      : str(r['day']),
        'week'     : int(r['week']) if not pd.isna(r['week']) else 0,
        'hrs'      : float(r['monthly_hrs']),
        'setups'   : setups_list,
        'weeks'    : weeks,
        'freqs'    : freqs,
        'outlier'  : bool(r.get('is_outlier', False)),
        'disconn'  : bool(r.get('in_disconnected_zone', False)),
    })

slot_records = slot.to_dict(orient='records')
tech_records = techs.to_dict(orient='records')

DAY_COLOURS = {
    'Monday'   : '#3498db',
    'Tuesday'  : '#27ae60',
    'Wednesday': '#e74c3c',
    'Thursday' : '#9b59b6',
    'Friday'   : '#f1c40f',
}

data = {
    'fls'        : records,
    'slots'      : slot_records,
    'techs'      : tech_records,
    'dayColours' : DAY_COLOURS,
}

js_data = json.dumps(data, default=str)

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>BSO Phase 1 Dashboard (v2 Joint Slots) — GM-MCP</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
<style>
 body{margin:0;font-family:'Segoe UI',Arial,sans-serif;display:flex;height:100vh;background:#f4f6f8}
 #sidebar{width:340px;background:#2c3e50;color:#fff;padding:18px;overflow-y:auto;flex-shrink:0}
 #sidebar h1{margin:0 0 4px;font-size:1.15rem}
 #sidebar .sub{color:#9bb;font-size:.78rem;margin-bottom:12px}
 #sidebar .hint{color:#9bb;font-size:.68rem;margin:4px 0 8px;font-style:italic}
 #sidebar h3{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:#9bb;margin:14px 0 4px;border-bottom:1px solid #3d5468;padding-bottom:4px;display:flex;align-items:center;justify-content:space-between}
 .filter-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px}
 .chip{font-size:.72rem;padding:4px 9px;background:#34495e;border:1px solid #3d5468;color:#fff;border-radius:14px;cursor:pointer;user-select:none}
 .chip.active{background:#3498db;border-color:#3498db;font-weight:600}
 .chip.day{padding-left:18px;position:relative}
 .chip.day::before{content:'';position:absolute;left:5px;top:50%;transform:translateY(-50%);width:9px;height:9px;border-radius:50%;background:var(--c)}
 select,input[type=text]{width:100%;padding:6px;border-radius:6px;border:1px solid #3d5468;background:#34495e;color:#fff;font-size:.82rem;box-sizing:border-box}
 .stats{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
 .stat{background:#34495e;padding:8px;border-radius:6px}
 .stat .v{font-size:1.1rem;font-weight:700}
 .stat .l{font-size:.65rem;color:#9bb;text-transform:uppercase}
 button.toggle-all,button.heat-btn{font-size:.7rem;padding:3px 8px;background:#3d5468;color:#fff;border:none;border-radius:4px;cursor:pointer}
 button.heat-btn{display:block;width:100%;margin-top:14px;padding:8px;font-weight:600;background:#3498db}
 button.heat-btn:hover{background:#2980b9}
 #main{flex:1;position:relative}
 #map{position:absolute;inset:0}
 .leaflet-popup-content{font-size:.78rem;max-height:280px;overflow-y:auto}
 .pop h4{margin:0 0 4px;font-size:.85rem}
 .pop .city{color:#666;margin-bottom:6px}
 .pop table{border-collapse:collapse;width:100%;margin-top:4px}
 .pop td,.pop th{padding:2px 4px;border-bottom:1px solid #eee;text-align:left}
 .legend{position:absolute;bottom:20px;right:20px;background:#fff;padding:10px 12px;border-radius:6px;font-size:.75rem;box-shadow:0 2px 6px rgba(0,0,0,.2);z-index:500}
 .legend b{display:block;margin-bottom:4px;color:#2c3e50}
 .legend .row{display:flex;align-items:center;gap:6px;margin:2px 0}
 .legend .sw{width:14px;height:14px;border-radius:50%;border:1px solid #999}
 #modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center}
 #modal.show{display:flex}
 #modal .box{background:#fff;border-radius:10px;padding:20px;max-width:95vw;max-height:90vh;overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.3)}
 #modal h2{margin:0 0 8px;font-size:1.1rem;color:#2c3e50;display:flex;justify-content:space-between;align-items:center}
 #modal .close{background:none;border:none;font-size:1.4rem;cursor:pointer;color:#888;padding:0 6px}
 #modal .desc{color:#666;font-size:.78rem;margin-bottom:12px}
 table.heat{border-collapse:collapse;font-size:.72rem}
 table.heat th,table.heat td{border:1px solid #eee;padding:4px 8px;text-align:center}
 table.heat th{background:#f4f6f8;color:#555;position:sticky;top:0}
 table.heat td.lbl{text-align:left;background:#fafbfc;color:#444;font-weight:600;position:sticky;left:0;white-space:nowrap;max-width:160px;overflow:hidden;text-overflow:ellipsis}
</style>
</head>
<body>
<div id="sidebar">
 <h1>BSO Phase 1 — GM-MCP <span style="font-size:0.55em;opacity:0.7;font-weight:normal">v2 · joint slots</span></h1>
 <div class="sub" id="hdrcount"></div>
 <div class="hint">Click chip = solo · Shift+click = toggle · "all" = reset</div>

 <h3>Preferred Resource (Tech) <button class="toggle-all" onclick="resetAll('tech')">all</button></h3>
 <select id="techSel" multiple size="10"></select>
 <div class="hint">Hold Ctrl/Shift to multi-select. Empty = show all.</div>

 <h3>Week of Month <button class="toggle-all" onclick="resetAll('week')">all</button></h3>
 <div class="filter-row" id="weekChips"></div>

 <h3>Day of Week <button class="toggle-all" onclick="resetAll('day')">all</button></h3>
 <div class="filter-row" id="dayChips"></div>

 <h3>Frequency <button class="toggle-all" onclick="resetAll('freq')">all</button></h3>
 <div class="filter-row" id="freqChips"></div>

 <h3>Search</h3>
 <input type="text" id="search" placeholder="FL name or suburb…">

 <h3>Stats (filtered)</h3>
 <div class="stats">
  <div class="stat"><div class="v" id="sFls">–</div><div class="l">FL rows</div></div>
  <div class="stat"><div class="v" id="sHrs">–</div><div class="l">Hrs/mo</div></div>
  <div class="stat"><div class="v" id="sTechs">–</div><div class="l">Techs</div></div>
  <div class="stat"><div class="v" id="sOver">–</div><div class="l">Over-cap slots</div></div>
 </div>

 <button class="heat-btn" onclick="openHeat()">Open Slot Heatmap</button>
</div>

<div id="main">
 <div id="map"></div>
</div>

<div id="modal" onclick="if(event.target===this)closeHeat()">
 <div class="box">
  <h2>Slot Capacity Heatmap <button class="close" onclick="closeHeat()">×</button></h2>
  <div class="desc">Hours per (tech × week × day) vs 8h target. Filtered to selected techs.</div>
  <div id="heatTable"></div>
 </div>
</div>

<script>
const DATA = __DATA__;
const ALL_DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday'];
const ALL_WEEKS = [1,2,3,4];
const allTechs = [...new Set(DATA.fls.map(f=>f.tech))].sort();
const allFreqs = [...new Set(DATA.fls.flatMap(f=>f.freqs))].sort();

const sel = {
  tech: new Set(),  // empty = all
  week: new Set(ALL_WEEKS),
  day : new Set(ALL_DAYS),
  freq: new Set(allFreqs),
};

function makeChip(label, key, val, color){
  const c = document.createElement('span');
  c.className = 'chip active' + (key==='day'?' day':'');
  c.textContent = label;
  c.dataset.val = val;
  if(color) c.style.setProperty('--c', color);
  c.onclick = (e) => {
    if(e.shiftKey){
      if(sel[key].has(val)){ sel[key].delete(val); c.classList.remove('active'); }
      else { sel[key].add(val); c.classList.add('active'); }
    } else {
      sel[key].clear(); sel[key].add(val);
      const target = document.getElementById(key+'Chips');
      [...target.children].forEach(ch => {
        const v = key==='week' ? Number(ch.dataset.val) : ch.dataset.val;
        ch.classList.toggle('active', v === val);
      });
    }
    refresh();
  };
  return c;
}

function resetAll(key){
  if(key==='tech'){
    sel.tech = new Set();
    document.getElementById('techSel').selectedIndex = -1;
    refresh();
    return;
  }
  const all = key==='week'?ALL_WEEKS:key==='day'?ALL_DAYS:allFreqs;
  sel[key] = new Set(all);
  const target = document.getElementById(key+'Chips');
  [...target.children].forEach(c=>c.classList.add('active'));
  refresh();
}

const wkC = document.getElementById('weekChips');
ALL_WEEKS.forEach(w => wkC.appendChild(makeChip('Wk '+w, 'week', w)));
const dayC = document.getElementById('dayChips');
ALL_DAYS.forEach(d => dayC.appendChild(makeChip(d.slice(0,3), 'day', d, DATA.dayColours[d])));
const freqC = document.getElementById('freqChips');
allFreqs.forEach(f => freqC.appendChild(makeChip(f, 'freq', f)));

// Tech listbox — sorted by hours desc using tech_summary
const techHrs = {};
DATA.techs.forEach(t => techHrs[t.tech] = t.monthly_hrs);
const techSel = document.getElementById('techSel');
allTechs.sort((a,b)=>(techHrs[b]||0)-(techHrs[a]||0)).forEach(t => {
  const o = document.createElement('option');
  o.value = t;
  o.textContent = `${t}  (${(techHrs[t]||0).toFixed(0)}h)`;
  techSel.appendChild(o);
});
techSel.addEventListener('change', () => {
  sel.tech = new Set([...techSel.selectedOptions].map(o => o.value));
  refresh();
});

document.getElementById('search').addEventListener('input', refresh);

const map = L.map('map').setView([-37.85, 145.0], 10);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(map);

const layer = L.layerGroup().addTo(map);

const legend = L.control({position:'bottomright'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div','legend');
  d.innerHTML = '<b>Day of Week</b>' + ALL_DAYS.map(day =>
    `<div class="row"><span class="sw" style="background:${DATA.dayColours[day]}"></span>${day}</div>`
  ).join('') +
  '<b style="margin-top:8px">Topology flags</b>' +
  '<div class="row"><span class="sw" style="background:#999;border:2.5px solid #c0392b"></span>Disconnected zone</div>' +
  '<div class="row"><span class="sw" style="background:#999;border:1.5px dashed #222"></span>Outlier (MAD)</div>';
  return d;
};
legend.addTo(map);

function flMatches(f, q){
  if(sel.tech.size > 0 && !sel.tech.has(f.tech)) return false;
  if(!sel.day.has(f.day)) return false;
  const ok = f.setups.some(s => {
    const wkOk = s.week === '' || sel.week.has(s.week);
    const fqOk = !s.freq || sel.freq.has(s.freq);
    return wkOk && fqOk;
  });
  if(!ok) return false;
  if(q && !(f.name.toLowerCase().includes(q) || (f.city||'').toLowerCase().includes(q))) return false;
  return true;
}

function popupHtml(f){
  const rows = f.setups.map(s => {
    const slot = s.week ? `${s.week}-${s.day.slice(0,3)}` : (s.day?'Every '+s.day.slice(0,3):'');
    return `<tr><td>${s.freq}</td><td>${s.duration} min</td><td><b>${slot}</b></td></tr>`;
  }).join('');
  return `<div class="pop"><h4>${f.name}</h4>
    <div class="city">${f.city||''}</div>
    <div><b>${f.tech}</b> · ${f.day} · Wk ${f.week} · ${f.hrs.toFixed(2)} h/mo · ${f.setups.length} setup(s)</div>
    <table><tr><th>Frequency</th><th>Dur</th><th>Slot</th></tr>${rows}</table></div>`;
}

function refresh(){
  layer.clearLayers();
  const q = document.getElementById('search').value.trim().toLowerCase();
  let nFls=0, hrs=0, techsSeen=new Set();
  DATA.fls.forEach(f => {
    if(!flMatches(f,q)) return;
    nFls++; hrs += f.hrs; techsSeen.add(f.tech);
    const color = DATA.dayColours[f.day] || '#888';
    // Topology flags:
    //  disconn  → bold red border (FL sits in a zone with > 1 spatial component)
    //  outlier  → dashed black border (FL flagged as MAD-outlier from tech centroid)
    let border = color, weight = 1, dash = null, radius = 4;
    if (f.disconn) { border = '#c0392b'; weight = 2.5; radius = 5; }
    else if (f.outlier) { border = '#222'; weight = 1.5; dash = '2,2'; }
    const opts = {radius:radius, color:border, fillColor:color,
                  fillOpacity:.85, weight:weight};
    if (dash) opts.dashArray = dash;
    const m = L.circleMarker([f.lat, f.lon], opts);
    m.bindPopup(popupHtml(f));
    layer.addLayer(m);
  });
  document.getElementById('sFls').textContent  = nFls.toLocaleString();
  document.getElementById('sHrs').textContent  = hrs.toFixed(0);
  document.getElementById('sTechs').textContent = techsSeen.size;
  document.getElementById('hdrcount').textContent =
    `${DATA.fls.length} tech-FL rows · ${DATA.techs.length} techs · ${DATA.slots.length} day-slots`;

  const techFilter = sel.tech.size>0;
  const slotsF = DATA.slots.filter(s => !techFilter || sel.tech.has(s.tech));
  const overCap = slotsF.filter(s => s.over_capacity || s.load_hrs > 8).length;
  document.getElementById('sOver').textContent = overCap;
}

function buildHeat(){
  const techFilter = sel.tech.size>0;
  const slotsF = DATA.slots.filter(s => !techFilter || sel.tech.has(s.tech));
  const grid = {};
  slotsF.forEach(s => {
    if(!grid[s.tech]) grid[s.tech] = {};
    grid[s.tech][`${s.week}-${s.day}`] = s.load_hrs;
  });
  const techList = Object.keys(grid).sort((a,b)=>(techHrs[b]||0)-(techHrs[a]||0));
  let html = '<table class="heat"><thead><tr><th>Tech</th>';
  ALL_WEEKS.forEach(w => ALL_DAYS.forEach(d => html += `<th>W${w} ${d.slice(0,3)}</th>`));
  html += '</tr></thead><tbody>';
  techList.forEach(t => {
    html += `<tr><td class="lbl">${t}</td>`;
    ALL_WEEKS.forEach(w => ALL_DAYS.forEach(d => {
      const v = grid[t] && grid[t][`${w}-${d}`];
      const num = (v==null||v===0)?'':v.toFixed(1);
      const bg = v==null||v===0?'#fff' : v>12?'#c0392b':v>10?'#e67e22':v>8?'#f1c40f':v>6?'#dff0d8':'#eafaf1';
      const fg = v>10?'#fff':'#222';
      html += `<td style="background:${bg};color:${fg}">${num}</td>`;
    }));
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('heatTable').innerHTML = html;
}

function openHeat(){ buildHeat(); document.getElementById('modal').classList.add('show'); }
function closeHeat(){ document.getElementById('modal').classList.remove('show'); }
document.addEventListener('keydown', e => { if(e.key==='Escape') closeHeat(); });

refresh();
</script>
</body>
</html>"""

html = html.replace('__DATA__', js_data)
with open(OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)

size_mb = os.path.getsize(OUT_HTML) / (1024*1024)
print(f"Wrote {OUT_HTML} ({size_mb:.2f} MB)")
print(f"  Tech-FL rows: {len(records):,}  |  Techs: {len(tech_records)}")
print(f"  Slots: {len(slot_records)}  |  Setups: {len(setup):,}")
