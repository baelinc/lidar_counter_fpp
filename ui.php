<?php
/* Car Counter - main page (shown inside FPP's normal page frame). */
$ccPlugin = basename(__DIR__);
?>
<style>
#cc { max-width: 1100px; --line: rgba(128,128,128,.35); --accent: #2f7d32; --warn: #c77700; --bad: #c62828; }
#cc h2 { margin: 0 0 .6rem; }
#cc .cc-pills { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
#cc .pill { border: 1px solid var(--line); border-radius: 999px; padding: .2rem .8rem; font-size: .9rem; }
#cc .pill.ok { border-color: var(--accent); color: var(--accent); }
#cc .pill.warn { border-color: var(--warn); color: var(--warn); }
#cc .pill.bad { border-color: var(--bad); color: var(--bad); }
#cc .tabs { display: flex; gap: .25rem; border-bottom: 1px solid var(--line); margin-bottom: 1rem; }
#cc .tabs button { border: 1px solid transparent; border-bottom: 0; background: none; padding: .5rem 1rem; cursor: pointer; font-size: 1rem; color: inherit; border-radius: 6px 6px 0 0; }
#cc .tabs button.active { border-color: var(--line); font-weight: 600; background: rgba(128,128,128,.12); }
#cc .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .8rem; margin-bottom: 1rem; }
#cc .card { border: 1px solid var(--line); border-radius: 8px; padding: .8rem 1rem; }
#cc .card .big { font-size: 2.6rem; font-weight: 700; line-height: 1.1; }
#cc .card .sub { opacity: .7; font-size: .85rem; }
#cc .panel { border: 1px solid var(--line); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
#cc .panel h3 { font-size: 1.1rem; margin: 0 0 .6rem; }
#cc .row { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: .5rem 0; }
#cc button.b { border: 1px solid var(--line); background: rgba(128,128,128,.12); color: inherit; padding: .45rem .9rem; border-radius: 6px; cursor: pointer; font-size: .95rem; }
#cc button.b:hover { background: rgba(128,128,128,.25); }
#cc button.b.primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
#cc button.b.danger { border-color: var(--bad); color: var(--bad); }
#cc button.b.on { background: var(--warn); border-color: var(--warn); color: #fff; }
#cc button.b:disabled { opacity: .5; cursor: default; }
#cc .msg { min-height: 1.4em; font-size: .95rem; }
#cc .msg.ok { color: var(--accent); } #cc .msg.bad { color: var(--bad); }
#cc .track { position: relative; height: 26px; border: 1px solid var(--line); border-radius: 4px; margin: .5rem 0; background: rgba(128,128,128,.08); }
#cc .zone { position: absolute; top: 0; bottom: 0; background: rgba(47,125,50,.25); border-left: 2px solid var(--accent); border-right: 2px solid var(--accent); }
#cc .marker { position: absolute; top: -3px; bottom: -3px; width: 4px; background: #1f6feb; transition: left .15s; }
#cc .marker.hit { background: var(--bad); }
#cc .chart { display: flex; align-items: flex-end; gap: 3px; height: 150px; border-bottom: 1px solid var(--line); padding-top: 14px; }
#cc .chart .col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; min-width: 0; }
#cc .chart .bar { width: 100%; max-width: 70px; background: #1f6feb; border-radius: 3px 3px 0 0; min-height: 1px; }
#cc .chart .val { font-size: .7rem; opacity: .8; }
#cc .labels { display: flex; gap: 3px; font-size: .7rem; opacity: .7; }
#cc .labels span { flex: 1; text-align: center; overflow: hidden; }
#cc table.t { border-collapse: collapse; width: 100%; font-size: .92rem; }
#cc table.t th, #cc table.t td { border-bottom: 1px solid var(--line); padding: .3rem .5rem; text-align: left; }
#cc table.t td.n, #cc table.t th.n { text-align: right; }
#cc .field { display: grid; grid-template-columns: 220px 1fr; gap: .5rem 1rem; align-items: start; margin: .6rem 0; }
#cc .field label { font-weight: 600; padding-top: .35rem; }
#cc .field input[type=text], #cc .field input[type=number], #cc .field input[type=password], #cc .field input[type=time], #cc .field select { width: 100%; max-width: 380px; padding: .35rem .5rem; }
#cc .help { font-size: .82rem; opacity: .7; margin-top: .2rem; }
#cc pre { max-height: 380px; overflow: auto; border: 1px solid var(--line); border-radius: 6px; padding: .6rem; font-size: .8rem; }
#cc .warnbox { border: 1px solid var(--warn); color: var(--warn); border-radius: 6px; padding: .5rem .8rem; margin-bottom: 1rem; }
@media (max-width: 700px) { #cc .field { grid-template-columns: 1fr; } }
</style>

<div id="cc">
  <h2>Car Counter <small id="ccVersion" style="font-size:.5em;opacity:.6"></small></h2>
  <div class="cc-pills">
    <span class="pill" id="pillDaemon">Service: …</span>
    <span class="pill" id="pillSensor">Sensor: …</span>
    <span class="pill" id="pillCounting">Counting: …</span>
    <span class="pill" id="pillSync" style="display:none"></span>
  </div>
  <div id="warnings"></div>

  <div class="tabs" id="tabs">
    <button data-tab="dash" class="active">Dashboard</button>
    <button data-tab="settings">Sensor &amp; Schedule</button>
    <button data-tab="website">Website Sync</button>
    <button data-tab="log">Log</button>
  </div>

  <!-- ===================== Dashboard ===================== -->
  <div id="tab-dash">
    <div class="grid">
      <div class="card"><div class="sub" id="tonightLabel">Tonight</div><div class="big" id="vTonight">–</div><div class="sub" id="vTonightSub"></div></div>
      <div class="card"><div class="sub">Last night</div><div class="big" id="vLast">–</div><div class="sub" id="vLastSub"></div></div>
      <div class="card"><div class="sub">Season total</div><div class="big" id="vSeason">–</div><div class="sub" id="vSeasonSub"></div></div>
      <div class="card"><div class="sub">Off-hours detections tonight</div><div class="big" id="vOff">–</div><div class="sub">Not included in totals</div></div>
    </div>

    <div class="panel">
      <h3>Live sensor</h3>
      <div class="row"><strong id="vDist" style="font-size:1.6rem">–</strong><span id="vState" class="pill">idle</span><span class="sub" id="vSensorDetail"></span></div>
      <div class="track"><div class="zone" id="zone"></div><div class="marker" id="marker" style="left:0"></div></div>
      <div class="help">The green band is the detection zone. A vehicle is counted when the reading stays inside it. An empty road should read "no return" or sit to the right of the band.</div>
      <div class="row">
        <button class="b" id="btnPlus">+1 car</button>
        <button class="b" id="btnMinus">−1 car</button>
        <button class="b danger" id="btnReset">Reset tonight</button>
        <button class="b" id="btnTest">Test mode</button>
        <button class="b" id="btnCal">Calibrate empty road</button>
      </div>
      <div class="msg" id="cmdMsg"></div>
    </div>

    <div class="panel">
      <h3>Tonight by hour</h3>
      <div class="chart" id="chartHours"></div><div class="labels" id="labelsHours"></div>
    </div>
    <div class="panel">
      <h3>Recent nights</h3>
      <div class="chart" id="chartDays"></div><div class="labels" id="labelsDays"></div>
      <table class="t" style="margin-top:1rem"><thead><tr><th>Night</th><th class="n">Cars</th><th class="n">Off-hours</th><th>First car</th><th>Last car</th></tr></thead><tbody id="tblDays"></tbody></table>
      <div class="row"><a class="b" style="text-decoration:none" id="csvLink" href="#">Download CSV</a></div>
    </div>
  </div>

  <!-- ===================== Settings ===================== -->
  <div id="tab-settings" style="display:none">
    <div class="panel"><h3>Wiring (TFmini / TFmini-S / TFmini Plus / TF-Luna)</h3>
      <div class="help" style="opacity:.9">
        Red → 5V (pin 2) &nbsp;·&nbsp; Black → GND (pin 6) &nbsp;·&nbsp; Green (sensor TX) → Pi RX, GPIO15 (pin 10) &nbsp;·&nbsp; White (sensor RX) → Pi TX, GPIO14 (pin 8).<br>
        Using a USB-to-serial adapter instead? Choose <code>/dev/ttyUSB0</code> – this avoids any conflict with LED panel HATs that use the GPIO header.<br>
        First time using the GPIO serial port? Run <code>sudo /home/fpp/media/plugins/<?php echo htmlspecialchars($ccPlugin); ?>/scripts/enable_uart.sh</code> over SSH once and reboot.
      </div>
    </div>
    <div class="panel"><h3>Sensor</h3><div id="fSensor"></div></div>
    <div class="panel"><h3>Detection</h3><div id="fDetect"></div></div>
    <div class="panel"><h3>When to count</h3><div id="fSched"></div></div>
    <div class="row"><button class="b primary" id="btnSaveSettings">Save settings</button><span class="msg" id="saveMsg1"></span></div>
  </div>

  <!-- ===================== Website ===================== -->
  <div id="tab-website" style="display:none">
    <div class="panel"><h3>WordPress connection</h3>
      <div class="help" style="opacity:.9;margin-bottom:.6rem">Install the <em>Light Show Car Counter</em> plugin on your WordPress site, then copy the website address and shared secret from <em>Settings → Light Show Car Counter</em> into the boxes below.</div>
      <div id="fWebsite"></div>
      <div class="row"><button class="b primary" id="btnSaveWeb">Save</button><button class="b" id="btnTestWeb">Test connection</button><button class="b" id="btnSyncNow">Upload now</button><span class="msg" id="saveMsg2"></span></div>
    </div>
    <div class="panel"><h3>Sync status</h3><div id="syncStatus" class="msg"></div></div>
  </div>

  <!-- ===================== Log ===================== -->
  <div id="tab-log" style="display:none">
    <div class="row">
      <button class="b" id="btnLog">Refresh</button>
      <button class="b" data-svc="restart">Restart counter service</button>
      <button class="b" data-svc="start">Start</button>
      <button class="b" data-svc="stop">Stop</button>
      <span class="msg" id="svcMsg"></span>
    </div>
    <pre id="logBox">Loading…</pre>
    <div class="sub" id="errLabel" style="display:none">Crash output:</div><pre id="errBox" style="display:none"></pre>
  </div>
</div>

<script>
(function () {
  var AJAX = 'plugin.php?plugin=' + encodeURIComponent(<?php echo json_encode($ccPlugin); ?>) + '&page=ajax.php&nopage=1';
  var $ = function (id) { return document.getElementById(id); };
  var cfg = null, status = null, running = false, stats = null;

  function api(action, body) {
    var opt = { cache: 'no-store' };
    if (body !== undefined) {
      opt.method = 'POST';
      opt.headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
      opt.body = JSON.stringify(body);
    }
    return fetch(AJAX + '&action=' + action, opt).then(function (r) { return r.json(); });
  }
  function setMsg(el, text, ok) { el.textContent = text || ''; el.className = 'msg' + (text ? (ok ? ' ok' : ' bad') : ''); }
  function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '–'; }
  function fmtClock(ts) { return ts ? new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '–'; }
  function pill(id, text, cls) { var e = $(id); e.textContent = text; e.className = 'pill ' + (cls || ''); }

  /* ---------- tabs ---------- */
  var tabs = ['dash', 'settings', 'website', 'log'];
  $('tabs').addEventListener('click', function (e) {
    var t = e.target.getAttribute && e.target.getAttribute('data-tab');
    if (!t) return;
    tabs.forEach(function (n) {
      $('tab-' + n).style.display = (n === t) ? '' : 'none';
    });
    Array.prototype.forEach.call($('tabs').children, function (b) { b.classList.toggle('active', b === e.target); });
    if (t === 'log') loadLog();
  });

  /* ---------- settings forms ---------- */
  var FIELDS = {
    fSensor: [
      { k: 'show_name', l: 'Show name', t: 'text', h: 'Shown on your website.' },
      { k: 'serial_port', l: 'Serial port', t: 'text', list: 'ccPorts', h: '/dev/serial0 for the GPIO pins, or /dev/ttyUSB0 for a USB-serial adapter.' },
      { k: 'baud', l: 'Baud rate', t: 'select', o: [9600, 19200, 38400, 57600, 115200, 230400], h: 'TFmini, TFmini-S, TFmini Plus and TF-Luna all default to 115200.' },
      { k: 'unit', l: 'Sensor distance unit', t: 'select', o: [['cm', 'Centimetres (factory default)'], ['mm', 'Millimetres']], h: 'Only change if you switched the sensor into millimetre output.' }
    ],
    fDetect: [
      { k: 'min_cm', l: 'Nearest distance (cm)', t: 'number', h: 'Readings closer than this are ignored.' },
      { k: 'max_cm', l: 'Farthest distance (cm)', t: 'number', h: 'Anything between nearest and farthest counts as a vehicle. Use “Calibrate empty road” on the Dashboard to set this automatically.' },
      { k: 'confirm_ms', l: 'Confirm time (ms)', t: 'number', h: 'How long something must stay in the beam before it counts. Raise it to ignore pedestrians and animals; lower it if fast cars are missed.' },
      { k: 'clear_ms', l: 'Clear time (ms)', t: 'number', h: 'How long the beam must be empty before the next car can count. Stops windows and slow traffic being counted twice.' },
      { k: 'min_strength', l: 'Minimum signal strength', t: 'number', h: '0 = off. Raise to ignore weak, unreliable returns (see the strength shown in the live panel).' },
      { k: 'max_dwell_s', l: 'Blocked-beam warning (s)', t: 'number', h: 'Show a warning if the beam is blocked this long (e.g. a fallen sign). A parked car is still counted once.' }
    ],
    fSched: [
      { k: 'schedule_mode', l: 'Count cars', t: 'select', o: [['window', 'During show hours (below)'], ['playing', 'Only while FPP is playing'], ['always', 'Always']], h: 'Detections outside the schedule are kept as “off-hours” so you can see them, but are not added to your totals.' },
      { k: 'window_start', l: 'Show starts', t: 'time' },
      { k: 'window_end', l: 'Show ends', t: 'time', h: 'End earlier than start for shows that run past midnight.' },
      { k: 'grace_min', l: 'Grace period (min)', t: 'number', h: '“Only while FPP is playing” mode: keep counting this long after the show stops.' },
      { k: 'rollover_hour', l: 'New night starts at', t: 'number', h: 'Hour (0–12). Cars counted after midnight still belong to the previous show night until this hour.' }
    ],
    fWebsite: [
      { k: 'sync_enabled', l: 'Upload to website', t: 'checkbox' },
      { k: 'wp_url', l: 'Website address', t: 'text', ph: 'https://www.example.com', h: 'Just the site address – no /wp-json path.' },
      { k: 'secret', l: 'Shared secret', t: 'password', h: 'Copied from the WordPress plugin settings.' },
      { k: 'sync_time', l: 'Nightly upload time', t: 'time', h: 'Choose a time after your show ends. If the Pi was off or the site was down it catches up automatically.' },
      { k: 'sync_days', l: 'Nights to include', t: 'number', h: 'Each upload re-sends the last N nights so a missed night heals itself.' },
      { k: 'live_interval_min', l: 'Live update every (min)', t: 'number', h: '0 = nightly only. Set e.g. 10 to let the website show tonight’s count while the show is running.' },
      { k: 'verify_tls', l: 'Verify HTTPS certificate', t: 'checkbox', h: 'Leave on unless your site uses a self-signed certificate.' }
    ]
  };
  function buildForm(boxId) {
    var box = $(boxId);
    FIELDS[boxId].forEach(function (f) {
      var row = document.createElement('div'); row.className = 'field';
      var lab = document.createElement('label'); lab.textContent = f.l; lab.htmlFor = 'cf_' + f.k;
      var cell = document.createElement('div'), inp;
      if (f.t === 'select') {
        inp = document.createElement('select');
        f.o.forEach(function (o) {
          var op = document.createElement('option');
          op.value = Array.isArray(o) ? o[0] : o; op.textContent = Array.isArray(o) ? o[1] : o; inp.appendChild(op);
        });
      } else {
        inp = document.createElement('input'); inp.type = f.t;
        if (f.list) inp.setAttribute('list', f.list);
        if (f.ph) inp.placeholder = f.ph;
        if (f.t === 'password') inp.autocomplete = 'new-password';
      }
      inp.id = 'cf_' + f.k; inp.setAttribute('data-key', f.k);
      cell.appendChild(inp);
      if (f.h) { var h = document.createElement('div'); h.className = 'help'; h.textContent = f.h; cell.appendChild(h); }
      row.appendChild(lab); row.appendChild(cell); box.appendChild(row);
    });
  }
  ['fSensor', 'fDetect', 'fSched', 'fWebsite'].forEach(buildForm);
  var dl = document.createElement('datalist'); dl.id = 'ccPorts'; $('cc').appendChild(dl);

  function fillForms() {
    Object.keys(FIELDS).forEach(function (box) {
      FIELDS[box].forEach(function (f) {
        var el = $('cf_' + f.k);
        if (f.t === 'checkbox') el.checked = !!cfg[f.k];
        else if (f.k === 'secret') { el.value = ''; el.placeholder = cfg.secret_set ? '•••••••• (saved – leave blank to keep)' : 'paste the secret here'; }
        else el.value = cfg[f.k];
      });
    });
  }
  function collect(boxes) {
    var out = {};
    boxes.forEach(function (box) {
      FIELDS[box].forEach(function (f) {
        var el = $('cf_' + f.k);
        out[f.k] = (f.t === 'checkbox') ? el.checked : el.value;
      });
    });
    return out;
  }
  function save(boxes, msgEl) {
    return api('save_config', collect(boxes)).then(function (r) {
      setMsg(msgEl, r.ok ? 'Saved – the counter picks this up within a second.' : (r.error || 'Save failed'), r.ok);
      return api('config').then(function (c) { cfg = c; fillForms(); return r.ok; });
    }).catch(function () { setMsg(msgEl, 'Save failed (could not reach FPP).', false); });
  }
  $('btnSaveSettings').onclick = function () { save(['fSensor', 'fDetect', 'fSched'], $('saveMsg1')); };
  $('btnSaveWeb').onclick = function () { save(['fWebsite'], $('saveMsg2')); };

  /* ---------- commands ---------- */
  function sendCommand(payload, msgEl, waitForFinal) {
    setMsg(msgEl, 'Working…', true);
    return api('command', payload).then(function (r) {
      if (!r.ok) { setMsg(msgEl, r.error || 'Failed', false); return; }
      var tries = 0;
      (function poll() {
        api('status').then(function (s) {
          var res = s.status && s.status.result;
          if (res && res.id === r.id && !res.pending) { setMsg(msgEl, res.message, res.ok); refresh(); return; }
          if (res && res.id === r.id && res.pending) setMsg(msgEl, res.message, true);
          if (++tries < 40) setTimeout(poll, 700); else setMsg(msgEl, 'No response from the counter service.', false);
        });
      })();
    }).catch(function () { setMsg(msgEl, 'Could not reach FPP.', false); });
  }
  $('btnPlus').onclick = function () { sendCommand({ cmd: 'adjust', delta: 1 }, $('cmdMsg')); };
  $('btnMinus').onclick = function () { sendCommand({ cmd: 'adjust', delta: -1 }, $('cmdMsg')); };
  $('btnReset').onclick = function () {
    if (confirm('Reset tonight’s count to zero?')) sendCommand({ cmd: 'reset_today' }, $('cmdMsg'));
  };
  $('btnTest').onclick = function () {
    var on = !(status && status.test_mode);
    sendCommand({ cmd: 'test_mode', on: on }, $('cmdMsg'));
  };
  $('btnCal').onclick = function () {
    if (confirm('Make sure no cars or people are in front of the sensor. Continue?')) sendCommand({ cmd: 'calibrate' }, $('cmdMsg'));
  };
  $('btnTestWeb').onclick = function () { sendCommand({ cmd: 'sync_test' }, $('saveMsg2')); };
  $('btnSyncNow').onclick = function () { sendCommand({ cmd: 'sync_now' }, $('saveMsg2')); };
  Array.prototype.forEach.call(document.querySelectorAll('[data-svc]'), function (b) {
    b.onclick = function () {
      setMsg($('svcMsg'), 'Working…', true);
      api('service', { op: b.getAttribute('data-svc') }).then(function (r) {
        setMsg($('svcMsg'), r.output || 'Done', true); setTimeout(refresh, 1500);
      });
    };
  });
  $('btnLog').onclick = loadLog;
  function loadLog() {
    api('log').then(function (r) {
      $('logBox').textContent = r.log || '(log is empty)';
      $('logBox').scrollTop = 1e9;
      var has = !!(r.errors && r.errors.trim());
      $('errBox').style.display = $('errLabel').style.display = has ? '' : 'none';
      $('errBox').textContent = r.errors || '';
    });
  }

  /* ---------- rendering ---------- */
  function bars(chartId, labelId, labels, values) {
    var chart = $(chartId), lab = $(labelId), max = Math.max.apply(null, values.concat([1]));
    chart.textContent = ''; lab.textContent = '';
    values.forEach(function (v, i) {
      var col = document.createElement('div'); col.className = 'col';
      var val = document.createElement('div'); val.className = 'val'; val.textContent = v > 0 ? v : '';
      var bar = document.createElement('div'); bar.className = 'bar'; bar.style.height = Math.round(v / max * 100) + '%';
      col.appendChild(val); col.appendChild(bar); chart.appendChild(col);
      var s = document.createElement('span'); s.textContent = labels[i]; lab.appendChild(s);
    });
  }

  function renderStatus() {
    if (!running || !status) {
      pill('pillDaemon', 'Service: not running', 'bad'); pill('pillSensor', 'Sensor: –', ''); pill('pillCounting', 'Counting: –', '');
      $('warnings').textContent = '';
      return;
    }
    var s = status;
    $('ccVersion').textContent = 'v' + s.version;
    pill('pillDaemon', 'Service: running', 'ok');
    pill('pillSensor', s.sensor.ok ? 'Sensor: OK (' + s.sensor.fps + ' Hz)' : 'Sensor: no data', s.sensor.ok ? 'ok' : 'bad');
    var c = s.counting;
    pill('pillCounting', (s.test_mode ? 'TEST MODE – not recording' : (c.active ? 'Counting: ON' : 'Counting: paused')) + ' (' + c.reason + ')', s.test_mode ? 'warn' : (c.active ? 'ok' : 'warn'));
    var ps = $('pillSync');
    if (s.sync_enabled) {
      ps.style.display = '';
      var sy = s.sync || {};
      pill('pillSync', sy.last_ok === false ? 'Website: last upload failed' : (sy.last_ok_ts ? 'Website: synced ' + fmtClock(sy.last_ok_ts) : 'Website: waiting for first upload'), sy.last_ok === false ? 'bad' : 'ok');
    } else { ps.style.display = 'none'; }

    var w = $('warnings'); w.textContent = '';
    (s.warnings || []).forEach(function (t) { var d = document.createElement('div'); d.className = 'warnbox'; d.textContent = t; w.appendChild(d); });

    $('tonightLabel').textContent = 'Tonight (' + s.show_date + ')';
    $('vTonight').textContent = s.today.total;
    $('vTonightSub').textContent = s.today.first_ts ? 'First car ' + fmtClock(s.today.first_ts) : 'No cars yet';
    $('vSeason').textContent = s.season_total;
    $('vOff').textContent = s.today.offhours;
    var nights = stats ? stats.days.filter(function (d) { return d.total > 0; }).length : 0;
    $('vSeasonSub').textContent = nights + ' night' + (nights === 1 ? '' : 's') + ' recorded';

    var d = s.detector, dist = s.sensor.distance_cm;
    $('vDist').textContent = dist === null ? 'no return' : dist + ' cm';
    var st = $('vState'); st.textContent = s.calibrating ? 'calibrating' : d.state; st.className = 'pill ' + (d.state === 'present' ? 'ok' : (d.state === 'confirming' ? 'warn' : ''));
    $('vSensorDetail').textContent = 'signal ' + s.sensor.strength + (s.test_mode ? ' · test cars: ' + s.test_count : '');
    var scale = Math.max(d.max_cm * 1.3, 400);
    $('zone').style.left = (d.min_cm / scale * 100) + '%';
    $('zone').style.width = ((d.max_cm - d.min_cm) / scale * 100) + '%';
    var m = $('marker'); m.style.left = (dist === null ? 99.5 : Math.min(99.5, dist / scale * 100)) + '%';
    m.className = 'marker' + (d.in_zone ? ' hit' : '');
    $('btnTest').textContent = s.test_mode ? 'Stop test mode' : 'Test mode';
    $('btnTest').classList.toggle('on', !!s.test_mode);

    var hrs = s.today.hours, lo = 24, hi = -1;
    hrs.forEach(function (v, h) { if (v > 0) { lo = Math.min(lo, h); hi = Math.max(hi, h); } });
    if (hi < 0) { lo = 17; hi = 22; }
    while (hi - lo < 5) { if (hi < 23) hi++; if (hi - lo < 5 && lo > 0) lo--; }
    var L = [], V = [];
    for (var h = lo; h <= hi; h++) { L.push(h); V.push(hrs[h]); }
    bars('chartHours', 'labelsHours', L, V);

    var sy2 = s.sync || {};
    var txt = sy2.ts ? ('Last attempt ' + fmtTime(sy2.ts) + ' – ' + (sy2.last_ok ? 'OK' : 'FAILED') + ': ' + sy2.message) : 'No upload attempted yet.';
    if (sy2.last_ok_ts) txt += '  Last successful upload: ' + fmtTime(sy2.last_ok_ts) + '.';
    $('syncStatus').textContent = txt;
    $('syncStatus').className = 'msg' + (sy2.ts ? (sy2.last_ok ? ' ok' : ' bad') : '');
  }

  function renderStats() {
    if (!stats) return;
    var days = stats.days.filter(function (d) { return d.total > 0 || d.offhours > 0; });
    var last = days.slice(-14);
    bars('chartDays', 'labelsDays', last.map(function (d) { return d.date.slice(5); }), last.map(function (d) { return d.total; }));
    var tb = $('tblDays'); tb.textContent = '';
    days.slice(-30).reverse().forEach(function (d) {
      var tr = document.createElement('tr');
      [d.date, d.total, d.offhours, fmtClock(d.first_ts), fmtClock(d.last_ts)].forEach(function (v, i) {
        var td = document.createElement('td'); td.textContent = v; if (i === 1 || i === 2) td.className = 'n'; tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    var prev = days.filter(function (d) { return !status || d.date < status.show_date; }).slice(-1)[0];
    $('vLast').textContent = prev ? prev.total : '–';
    $('vLastSub').textContent = prev ? prev.date : '';
  }

  function refresh() {
    return api('status').then(function (r) { running = r.running; status = r.status; renderStatus(); renderStats(); }).catch(function () {
      running = false; renderStatus();
    });
  }
  function refreshStats() { api('stats').then(function (s) { stats = s; renderStats(); renderStatus(); }); }

  $('csvLink').href = AJAX + '&action=csv';
  api('config').then(function (c) { cfg = c; fillForms(); });
  api('ports').then(function (p) { dl.textContent = ''; p.forEach(function (x) { var o = document.createElement('option'); o.value = x; dl.appendChild(o); }); });
  refreshStats(); refresh();
  setInterval(refresh, 1000);
  setInterval(refreshStats, 15000);
})();
</script>
