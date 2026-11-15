<?php
/* Car Counter - main page (shown inside FPP's normal page frame, or inside standalone/web/index.php). */
require_once __DIR__ . '/lib.php';
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
#cc .sched-row { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .6rem; border: 1px solid var(--line); border-radius: 8px; padding: .5rem .7rem; margin-bottom: .5rem; max-width: 640px; }
#cc .sched-days { display: flex; gap: 3px; }
#cc .sched-days button { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--line); background: none; color: inherit; cursor: pointer; font-weight: 600; }
#cc .sched-days button.on { background: #1f6feb; border-color: #1f6feb; color: #fff; }
#cc .sched-row input[type=time] { padding: .3rem .4rem; width: 8.5rem; max-width: 8.5rem; }
#cc .sched-quick button { border: 0; background: none; color: #1f6feb; cursor: pointer; font-size: .8rem; padding: 0 .3rem; }
#cc .sched-del { margin-left: auto; }
#cc .setup-item { display: flex; align-items: center; gap: .8rem; padding: .55rem 0; border-bottom: 1px solid var(--line); }
#cc .setup-item:last-child { border-bottom: 0; }
#cc .setup-ico { flex: none; width: 1.7rem; height: 1.7rem; border-radius: 50%; border: 2px solid var(--line); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .95rem; }
#cc .setup-item.done .setup-ico { background: var(--accent); border-color: var(--accent); color: #fff; }
#cc .setup-txt { flex: 1; min-width: 0; }
#cc .setup-txt b { display: block; }
#cc .setup-txt span { font-size: .85rem; opacity: .7; }
#cc .lane-now { font-size: 2.2rem; font-weight: 700; line-height: 1.1; }
#cc .lane-step { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; margin: .7rem 0; }
#cc .lane-val { font-weight: 700; min-width: 5rem; }
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
    <button data-tab="people">Crowd (phones)</button>
    <button data-tab="website">Website Sync</button>
    <button data-tab="log">Log</button>
  </div>

  <!-- ===================== Dashboard ===================== -->
  <div id="tab-dash">
    <div class="panel" id="setupBox" style="display:none">
      <h3>Let’s get you set up</h3>
      <div id="setupList"></div>
      <div class="row"><button class="b" id="setupHide">Hide this</button></div>
    </div>
    <div class="grid">
      <div class="card"><div class="sub" id="tonightLabel">Tonight</div><div class="big" id="vTonight">–</div><div class="sub" id="vTonightSub"></div></div>
      <div class="card"><div class="sub">Last night</div><div class="big" id="vLast">–</div><div class="sub" id="vLastSub"></div></div>
      <div class="card"><div class="sub">Season total</div><div class="big" id="vSeason">–</div><div class="sub" id="vSeasonSub"></div></div>
      <div class="card" id="cardPeople" style="display:none"><div class="sub">People tonight (est.)</div><div class="big" id="vPeople">–</div><div class="sub" id="vPeopleSub"></div></div>
      <div class="card" id="cardDevices" style="display:none"><div class="sub">Devices nearby now</div><div class="big" id="vDevices">–</div><div class="sub" id="vDevicesSub"></div></div>
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
      <table class="t" style="margin-top:1rem"><thead><tr id="tblHead"><th>Night</th><th class="n">Cars</th><th class="n">Off-hours</th><th>First car</th><th>Last car</th></tr></thead><tbody id="tblDays"></tbody></table>
      <div class="row"><a class="b" style="text-decoration:none" id="csvLink" href="#">Download CSV</a></div>
    </div>
  </div>

  <!-- ===================== Settings ===================== -->
  <div id="tab-settings" style="display:none">
    <div class="panel" id="wireUsb"><h3>Wiring – USB-to-serial adapter (CP2102)</h3>
      <table class="t" style="max-width:420px"><thead><tr><th>Lidar wire</th><th>Adapter pin</th></tr></thead><tbody>
        <tr><td>Red (5 V power)</td><td>5V</td></tr>
        <tr><td>Black (ground)</td><td>GND</td></tr>
        <tr><td>Green (lidar TX)</td><td>RXD</td></tr>
        <tr><td>White (lidar RX)</td><td>TXD</td></tr>
      </tbody></table>
      <div class="help" style="opacity:.9;margin-top:.5rem">
        The data wires cross over: the lidar's TX goes to the adapter's RXD, and the lidar's RX to the adapter's TXD.
        Plug the adapter into any USB port on the Pi – no serial-port setup and no reboot needed.
        Power the lidar from the adapter's <strong>5V</strong> pin (it needs 5 V; its data signals are 3.3 V). If your adapter has a 3.3V/5V logic selector, choose 3.3V.
        Wire colours differ between sensor models – check your datasheet.
      </div>
    </div>
    <div class="panel" id="wireGpio" style="display:none"><h3>Wiring – Pi GPIO header</h3>
      <table class="t" style="max-width:420px"><thead><tr><th>Lidar wire</th><th>Pi pin</th></tr></thead><tbody>
        <tr><td>Red (5 V power)</td><td>Pin 2 (5V)</td></tr>
        <tr><td>Black (ground)</td><td>Pin 6 (GND)</td></tr>
        <tr><td>Green (lidar TX)</td><td>Pin 10 (GPIO15 / RXD)</td></tr>
        <tr><td>White (lidar RX)</td><td>Pin 8 (GPIO14 / TXD)</td></tr>
      </tbody></table>
      <div class="help" style="opacity:.9;margin-top:.5rem">
        First time using the GPIO serial port? <?php if (CC_STANDALONE) { ?>Run <code>sudo /opt/car-counter/scripts/enable_uart.sh</code> over SSH once and reboot (or re-run the installer with <code>--uart</code>).<?php } else { ?>Run <code>sudo /home/fpp/media/plugins/<?php echo htmlspecialchars($ccPlugin); ?>/scripts/enable_uart.sh</code> over SSH once and reboot.<?php } ?>
        If an LED-panel HAT or bonnet uses these GPIO pins, use a USB-to-serial adapter instead.
      </div>
    </div>
    <div class="panel"><h3>Sensor</h3><div id="fSensor"></div></div>
    <div class="panel" id="laneHelper"><h3>Count only one lane (optional)</h3>
      <div class="help" style="opacity:.9">On a two-way road, cars arriving pass in one lane and cars leaving pass in the other. Aim the sensor across the road, then let it ignore the lane nearest to it, so each car is counted once instead of twice. Two quick steps:</div>
      <div class="lane-step"><span>Live reading</span><span class="lane-now" id="laneNow">–</span></div>
      <div class="lane-step"><span><b>1.</b> Put a car (or yourself) in the lane <b>nearest</b> the sensor, hold still, then</span><button class="b" id="laneNear">Record near lane</button><span class="lane-val" id="laneNearV"></span></div>
      <div class="lane-step"><span><b>2.</b> Do the same in the <b>far</b> lane, then</span><button class="b" id="laneFar">Record far lane</button><span class="lane-val" id="laneFarV"></span></div>
      <div class="msg" id="laneMsg"></div>
      <div class="row"><button class="b primary" id="laneApply" disabled>Use these settings</button><button class="b" id="laneReset">Count both lanes again</button></div>
    </div>
    <div class="panel"><h3>Detection</h3><div id="fDetect"></div></div>
    <div class="panel"><h3>When to count</h3><div id="fSched"></div></div>
    <div class="row"><button class="b primary" id="btnSaveSettings">Save settings</button><span class="msg" id="saveMsg1"></span></div>
  </div>

  <!-- ===================== Crowd ===================== -->
  <div id="tab-people" style="display:none">
    <div class="panel"><h3>BaldrickSignals crowd board</h3>
      <div class="help" style="opacity:.9;margin-bottom:.6rem">A BaldrickSignals board estimates how many phones are near your display. This plugin checks the board on a schedule, keeps the numbers that fall inside your show hours, and reports them as <strong>people (estimated)</strong> – separate from the car count, since one car can hold several people. Only the board's address is needed; the board must be on the same network as this Pi.</div>
      <div id="fPeople"></div>
      <div class="row"><button class="b primary" id="btnSavePeople">Save</button><button class="b" id="btnTestPeople">Test board</button><button class="b" id="btnPollPeople">Check now</button><span class="msg" id="saveMsgPeople"></span></div>
    </div>
    <div class="panel"><h3>Board status</h3><div id="peopleStatus" class="msg">Not enabled.</div>
      <div id="peopleTestBox" style="display:none">
        <div class="sub" style="margin-top:.6rem">What the plugin read from the board (first and last lines):</div>
        <pre id="peopleLines" style="max-height:11rem;overflow:auto"></pre>
        <div class="msg" id="peopleDetect"></div>
      </div>
    </div>
    <div class="panel"><h3>How the numbers are worked out</h3>
      <div class="help" style="opacity:.9">The board reports an estimate of the devices it can see right now (it already applies the offset and multiplier you set on the board). For each show night this plugin records the <strong>peak</strong> (the most at once) and an <strong>estimated visitor total</strong> – the number of arrivals seen as the count rises through the evening, after ignoring one-reading blips. Readings outside the show schedule are ignored. It is an estimate, not a head count.</div>
    </div>
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
  var tabs = ['dash', 'settings', 'people', 'website', 'log'];
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
      { k: 'connection', l: 'How is the lidar connected?', t: 'select', o: [['usb', 'USB-to-serial adapter (CP2102 etc.) – easiest'], ['gpio', 'Pi GPIO header pins'], ['custom', 'Custom serial port (advanced)']], h: 'A USB adapter needs no serial-port setup and avoids conflicts with LED-panel HATs.' },
      { k: 'usb_device', l: 'USB adapter', t: 'select', o: [['', 'Auto-detect (recommended)']], h: 'Only change this if you have more than one USB serial device plugged in.' },
      { k: 'serial_port', l: 'Serial port', t: 'text', list: 'ccPorts', h: 'Full device path, e.g. /dev/ttyAMA1.' },
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
      { k: 'schedule_mode', l: 'Count cars', t: 'select', o: [['window', 'During the show schedule (below)'], ['playing', 'Only while FPP is playing'], ['always', 'Always']], h: 'Detections outside the schedule are kept as “off-hours” so you can see them, but are not added to your totals.' },
      { k: 'fpp_host', l: 'Falcon Player address', t: 'text', h: '<?php echo CC_STANDALONE ? 'Required for this mode: the IP address of your master Falcon Player, e.g. 192.168.1.50.' : 'Leave blank to use this Pi. Or enter the address of another Falcon Player to follow that one.'; ?> If it cannot be reached the show schedule below is used instead.' },
      { k: 'schedules', l: 'Show schedule', t: 'schedules', h: 'Used in “During the show schedule” mode, and as the backup when the Falcon Player cannot be reached. Add one entry per set of days with the same hours (e.g. Sun–Thu 5:30 PM–10:00 PM, and Fri–Sat 5:30 PM–11:00 PM). An end time earlier than the start time runs past midnight and counts as part of the day it started.' },
      { k: 'grace_min', l: 'Grace period (min)', t: 'number', h: '“Only while FPP is playing” mode: keep counting this long after the show stops.' },
      { k: 'rollover_hour', l: 'New night starts at', t: 'number', h: 'Hour (0–12). Cars counted after midnight still belong to the previous show night until this hour.' }
    ],
    fPeople: [
      { k: 'people_enabled', l: 'Use BaldrickSignals', t: 'checkbox' },
      { k: 'people_host', l: 'Board IP address', t: 'text', ph: '192.168.1.50', h: 'The address shown on the board’s web page (or baldrickboard.local). Give the board a fixed IP in your router so it does not change.' },
      { k: 'people_interval_min', l: 'Check the board every (min)', t: 'number', h: 'How often to read the board. Each check only downloads the readings since the last check. Outside show hours it checks hourly.' },
      { k: 'people_clock', l: 'Board clock', t: 'select', o: [['local', 'Shows local time (same as this Pi)'], ['utc', 'Shows UTC']], h: 'Only matters if the board’s timestamps have no time zone. Use “Test board” to confirm the newest reading is about now.' },
      { k: 'people_time_col', l: 'Time column (advanced)', t: 'number', h: '0 = detect automatically. Otherwise the column number (1 = first) holding the timestamp.' },
      { k: 'people_count_col', l: 'Count column (advanced)', t: 'number', h: '0 = detect automatically. Otherwise the column number holding the crowd/device count. Use “Test board” to see what was detected.' }
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
  var DAY_LETTERS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
  var DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  function schedRow(e) {
    var r = document.createElement('div'); r.className = 'sched-row';
    var days = document.createElement('div'); days.className = 'sched-days';
    for (var d = 0; d < 7; d++) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = DAY_LETTERS[d]; b.title = DAY_NAMES[d];
      b.setAttribute('data-day', d); b.setAttribute('aria-pressed', 'false');
      if (e.days.indexOf(d) >= 0) { b.classList.add('on'); b.setAttribute('aria-pressed', 'true'); }
      b.onclick = function () { var on = this.classList.toggle('on'); this.setAttribute('aria-pressed', on ? 'true' : 'false'); };
      days.appendChild(b);
    }
    function setDays(list) {
      Array.prototype.forEach.call(days.children, function (btn) {
        var on = list.indexOf(+btn.getAttribute('data-day')) >= 0; btn.classList.toggle('on', on); btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    var quick = document.createElement('span'); quick.className = 'sched-quick';
    [['Every day', [0,1,2,3,4,5,6]], ['Weekdays', [1,2,3,4,5]], ['Weekends', [0,6]]].forEach(function (q) {
      var qb = document.createElement('button'); qb.type = 'button'; qb.textContent = q[0]; qb.onclick = function () { setDays(q[1]); }; quick.appendChild(qb);
    });
    var st = document.createElement('input'); st.type = 'time'; st.value = e.start; st.className = 'sched-start'; st.setAttribute('aria-label', 'Start time');
    var to = document.createElement('span'); to.textContent = 'to';
    var en = document.createElement('input'); en.type = 'time'; en.value = e.end; en.className = 'sched-end'; en.setAttribute('aria-label', 'End time');
    var del = document.createElement('button'); del.type = 'button'; del.className = 'b danger sched-del'; del.textContent = 'Remove';
    del.onclick = function () { r.parentNode.removeChild(r); schedEmptyNote(); };
    r.appendChild(days); r.appendChild(st); r.appendChild(to); r.appendChild(en); r.appendChild(del); r.appendChild(quick);
    return r;
  }
  function schedRows() {
    var out = [];
    Array.prototype.forEach.call(document.querySelectorAll('#schedEditor .sched-row'), function (r) {
      var days = [];
      Array.prototype.forEach.call(r.querySelectorAll('.sched-days button.on'), function (b) { days.push(+b.getAttribute('data-day')); });
      out.push({ days: days, start: r.querySelector('.sched-start').value, end: r.querySelector('.sched-end').value });
    });
    return out;
  }
  function schedEmptyNote() {
    var rows = schedRows(), bad = rows.some(function (x) { return !x.days.length || !x.start || !x.end; });
    $('schedEmpty').textContent = !rows.length ? 'No schedule entries – nothing will be counted.' : (bad ? 'Every entry needs at least one day and both times, or it is ignored.' : '');
  }
  function fillSchedules() {
    var ed = $('schedEditor'); ed.textContent = '';
    (cfg.schedules || []).forEach(function (e) { ed.appendChild(schedRow(e)); });
    schedEmptyNote();
  }
  var portInfo = { usb: [], gpio: false, all: [] };
  function populateUsb() {
    var sel = $('cf_usb_device'), cur = cfg ? cfg.usb_device : sel.value;
    sel.textContent = '';
    function opt(v, t) { var o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o); }
    opt('', portInfo.usb.length ? 'Auto-detect (recommended)' : 'Auto-detect (none plugged in yet)');
    portInfo.usb.forEach(function (p) { opt(p.path, p.label); });
    if (cur && !portInfo.usb.some(function (p) { return p.path === cur; })) opt(cur, cur + ' (not detected)');
    sel.value = cur || '';
    var n = $('usbDetected');
    if (portInfo.usb.length) { n.textContent = 'Detected: ' + portInfo.usb[0].label + (portInfo.usb.length > 1 ? ' (+' + (portInfo.usb.length - 1) + ' more)' : ''); n.className = 'msg ok'; }
    else { n.textContent = 'No USB serial adapter detected. Plug it into a USB port on the Pi, then reload this page.'; n.className = 'msg bad'; }
  }
  function applyConnection() {
    var m = $('cf_connection').value;
    $('row_usb_device').style.display = (m === 'usb') ? '' : 'none';
    $('row_serial_port').style.display = (m === 'custom') ? '' : 'none';
    $('wireUsb').style.display = (m === 'usb') ? '' : 'none';
    $('wireGpio').style.display = (m === 'gpio') ? '' : 'none';
  }
  function applyModeVisibility() {
    var f = $('schedField'); if (f) f.style.display = ($('cf_schedule_mode').value !== 'always') ? '' : 'none';
    var h = $('row_fpp_host'); if (h) h.style.display = ($('cf_schedule_mode').value === 'playing') ? '' : 'none';
  }
  function buildForm(boxId) {
    var box = $(boxId);
    FIELDS[boxId].forEach(function (f) {
      var row = document.createElement('div'); row.className = 'field'; row.id = 'row_' + f.k;
      var lab = document.createElement('label'); lab.textContent = f.l; lab.htmlFor = 'cf_' + f.k;
      var cell = document.createElement('div'), inp;
      if (f.t === 'schedules') {
        var ed = document.createElement('div'); ed.id = 'schedEditor';
        var add = document.createElement('button'); add.type = 'button'; add.className = 'b'; add.id = 'schedAdd'; add.textContent = '+ Add schedule';
        add.onclick = function () {
          var last = schedRows().slice(-1)[0];
          ed.insertBefore(schedRow(last ? { days: [], start: last.start, end: last.end } : { days: [0,1,2,3,4,5,6], start: '17:30', end: '22:00' }), add.parentNode === ed ? add : null);
          schedEmptyNote();
        };
        var note = document.createElement('div'); note.id = 'schedEmpty'; note.className = 'msg bad';
        cell.appendChild(ed); cell.appendChild(note); cell.appendChild(add);
        if (f.h) { var hh = document.createElement('div'); hh.className = 'help'; hh.textContent = f.h; cell.appendChild(hh); }
        row.id = 'schedField'; row.appendChild(lab); row.appendChild(cell); box.appendChild(row);
        return;
      }
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
  ['fSensor', 'fDetect', 'fSched', 'fPeople', 'fWebsite'].forEach(buildForm);
  $('cf_schedule_mode').addEventListener('change', applyModeVisibility);
  $('cf_connection').addEventListener('change', applyConnection);
  (function () { var n = document.createElement('div'); n.id = 'usbDetected'; n.className = 'msg'; $('row_usb_device').lastChild.appendChild(n); })();
  var dl = document.createElement('datalist'); dl.id = 'ccPorts'; $('cc').appendChild(dl);

  function fillForms() {
    Object.keys(FIELDS).forEach(function (box) {
      FIELDS[box].forEach(function (f) {
        if (f.t === 'schedules') { fillSchedules(); return; }
        var el = $('cf_' + f.k);
        if (f.t === 'checkbox') el.checked = !!cfg[f.k];
        else if (f.k === 'secret') { el.value = ''; el.placeholder = cfg.secret_set ? '•••••••• (saved – leave blank to keep)' : 'paste the secret here'; }
        else el.value = cfg[f.k];
      });
    });
    populateUsb();
    applyConnection();
    applyModeVisibility();
  }
  function collect(boxes) {
    var out = {};
    boxes.forEach(function (box) {
      FIELDS[box].forEach(function (f) {
        if (f.t === 'schedules') { out.schedules = schedRows().filter(function (x) { return x.days.length && x.start && x.end; }); return; }
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
    }).catch(function () { setMsg(msgEl, 'Save failed (could not reach the counter).', false); });
  }
  $('btnSaveSettings').onclick = function () { save(['fSensor', 'fDetect', 'fSched'], $('saveMsg1')); };
  $('btnSaveWeb').onclick = function () { save(['fWebsite'], $('saveMsg2')); };
  $('btnSavePeople').onclick = function () { save(['fPeople'], $('saveMsgPeople')); };
  $('btnTestPeople').onclick = function () {
    save(['fPeople'], $('saveMsgPeople')).then(function () { sendCommand({ cmd: 'people_test' }, $('saveMsgPeople')); });
  };
  $('btnPollPeople').onclick = function () { sendCommand({ cmd: 'people_poll' }, $('saveMsgPeople')); };

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
    }).catch(function () { setMsg(msgEl, 'Could not reach the counter.', false); });
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
    $('laneNow').textContent = dist === null ? 'no return' : dist + ' cm';
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

    renderPeople(s);

    var sy2 = s.sync || {};
    var txt = sy2.ts ? ('Last attempt ' + fmtTime(sy2.ts) + ' – ' + (sy2.last_ok ? 'OK' : 'FAILED') + ': ' + sy2.message) : 'No upload attempted yet.';
    if (sy2.last_ok_ts) txt += '  Last successful upload: ' + fmtTime(sy2.last_ok_ts) + '.';
    $('syncStatus').textContent = txt;
    $('syncStatus').className = 'msg' + (sy2.ts ? (sy2.last_ok ? ' ok' : ' bad') : '');
  }

  function renderPeople(s) {
    var pp = s.people || {}, st = pp.status || {}, on = !!pp.enabled;
    $('cardPeople').style.display = on ? '' : 'none';
    $('cardDevices').style.display = on ? '' : 'none';
    if (on) {
      var t = pp.today || {};
      $('vPeople').textContent = t.samples ? t.people : '–';
      $('vPeopleSub').textContent = t.samples ? 'Peak at once: ' + t.people_peak : 'No readings in show hours yet';
      $('vDevices').textContent = st.latest_count === null || st.latest_count === undefined ? '–' : st.latest_count;
      $('vDevicesSub').textContent = st.latest_ts ? 'Reading from ' + fmtClock(st.latest_ts) : (st.ok === false ? 'Board not reachable' : 'Waiting for first check');
    }
    var el = $('peopleStatus');
    if (!on) { el.textContent = 'Not enabled. Tick “Use BaldrickSignals”, enter the board’s address and press Save.'; el.className = 'msg'; }
    else if (!st.last_poll) { el.textContent = 'Waiting for the first check of ' + pp.host + '…'; el.className = 'msg'; }
    else {
      var txt = 'Last check ' + fmtTime(st.last_poll) + ' – ' + (st.ok ? 'OK' : 'FAILED: ' + st.error);
      if (st.ok) txt += '. Newest reading: ' + st.latest_count + ' device(s) at ' + fmtTime(st.latest_ts) + '; the board holds ' + st.rows + ' rows. Checking every ' + pp.interval_min + ' min during the show.';
      if (st.clock_warning) txt += '  ' + st.clock_warning;
      el.textContent = txt; el.className = 'msg ' + (st.ok ? 'ok' : 'bad');
    }
    var tr = pp.test, box = $('peopleTestBox');
    if (tr && tr.ts) {
      box.style.display = '';
      $('peopleLines').textContent = (tr.lines || []).join('\n') || '(nothing received)';
      var d = (tr.url ? 'Read from ' + tr.url + '. ' : '') + (tr.ok ? 'Detected – time: ' + tr.time_col + ' · count: ' + tr.count_col + ' · ' + tr.rows + ' rows. ' + (tr.message || '') + (tr.note ? ' ' + tr.note : '') : (tr.message || 'Failed'));
      $('peopleDetect').textContent = d; $('peopleDetect').className = 'msg ' + (tr.ok ? 'ok' : 'bad');
    } else { box.style.display = 'none'; }
  }

  function renderStats() {
    if (!stats) return;
    var days = stats.days.filter(function (d) { return d.total > 0 || d.offhours > 0 || d.people > 0; });
    var last = days.slice(-14);
    bars('chartDays', 'labelsDays', last.map(function (d) { return d.date.slice(5); }), last.map(function (d) { return d.total; }));
    var tb = $('tblDays'); tb.textContent = '';
    var hasPeople = days.some(function (d) { return d.people !== undefined; });
    var head = $('tblHead'); head.textContent = '';
    ['Night', 'Cars', 'Off-hours', 'First car', 'Last car'].concat(hasPeople ? ['People (est.)', 'Peak'] : []).forEach(function (h, i) {
      var th = document.createElement('th'); th.textContent = h; if (i === 1 || i === 2 || i > 4) th.className = 'n'; head.appendChild(th);
    });
    days.slice(-30).reverse().forEach(function (d) {
      var tr = document.createElement('tr');
      var cells = [d.date, d.total, d.offhours, fmtClock(d.first_ts), fmtClock(d.last_ts)];
      if (hasPeople) cells.push(d.people === undefined ? '–' : d.people, d.people_peak === undefined ? '–' : d.people_peak);
      cells.forEach(function (v, i) {
        var td = document.createElement('td'); td.textContent = v; if (i === 1 || i === 2 || i > 4) td.className = 'n'; tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    var prev = days.filter(function (d) { return !status || d.date < status.show_date; }).slice(-1)[0];
    $('vLast').textContent = prev ? prev.total : '–';
    $('vLastSub').textContent = prev ? prev.date : '';
  }


  // ---- Setup checklist ---------------------------------------------------
  var STANDALONE = <?php echo CC_STANDALONE ? 'true' : 'false'; ?>;
  function gotoTab(t) { var b = document.querySelector('#tabs [data-tab="' + t + '"]'); if (b) b.click(); }
  function setupHidden() { try { return localStorage.getItem('ccSetupHidden') === '1'; } catch (e) { return false; } }
  $('setupHide').onclick = function () { try { localStorage.setItem('ccSetupHidden', '1'); } catch (e) {} $('setupBox').style.display = 'none'; };
  function renderSetup() {
    if (!cfg) return;
    var sensorOk = !!(running && status && status.sensor && status.sensor.ok);
    var web = !!(cfg.sync_enabled && cfg.wp_url && cfg.secret_set);
    var items = [
      { done: sensorOk, req: true, t: 'Connect the lidar sensor', d: sensorOk ? 'Sensor is sending readings.' : 'Plug it in and choose how it is connected.', tab: 'settings' },
      { done: !!(cfg.schedules && cfg.schedules.length) || cfg.schedule_mode === 'always', req: false, t: 'Set your show hours', d: 'Cars are only counted during these hours.', tab: 'settings' },
      { done: cfg.min_cm > 30, req: false, t: 'Count only one lane (optional)', d: 'Avoids counting cars twice on a two-way road.', tab: 'settings' },
      { done: web, req: true, t: 'Connect to your website', d: web ? 'Uploading to ' + cfg.wp_url + '.' : 'Enter your website address and secret.', tab: 'website' }
    ];
    if (STANDALONE) items.push({ done: cfg.schedule_mode === 'playing' && !!cfg.fpp_host, req: false, t: 'Follow your Falcon Player (optional)', d: 'Only count while your show is playing.', tab: 'settings' });
    items.push({ done: !!(cfg.people_enabled && cfg.people_host), req: false, t: 'Count phones with a BaldrickSignals board (optional)', d: 'Estimates how many people are watching.', tab: 'people' });
    var box = $('setupList'); box.textContent = '';
    items.forEach(function (it) {
      var row = document.createElement('div'); row.className = 'setup-item' + (it.done ? ' done' : '');
      var ico = document.createElement('div'); ico.className = 'setup-ico'; ico.textContent = it.done ? '✓' : '';
      var txt = document.createElement('div'); txt.className = 'setup-txt';
      var b = document.createElement('b'); b.textContent = it.t; var sp = document.createElement('span'); sp.textContent = it.d;
      txt.appendChild(b); txt.appendChild(sp);
      row.appendChild(ico); row.appendChild(txt);
      if (!it.done) { var go = document.createElement('button'); go.className = 'b'; go.textContent = 'Set up'; go.onclick = function () { gotoTab(it.tab); }; row.appendChild(go); }
      box.appendChild(row);
    });
    var needed = items.some(function (it) { return it.req && !it.done; });
    $('setupBox').style.display = (needed && !setupHidden()) ? '' : 'none';
  }

  // ---- One-lane helper ----------------------------------------------------
  var laneNear = null, laneFar = null;
  function sampleDistance(n) {
    var vals = [];
    function one(i) {
      return api('status').then(function (r) {
        var d = r.status && r.status.sensor ? r.status.sensor.distance_cm : null;
        if (d !== null && d !== undefined) vals.push(d);
      }).then(function () {
        if (i + 1 >= n) return vals;
        return new Promise(function (res) { setTimeout(res, 250); }).then(function () { return one(i + 1); });
      });
    }
    return one(0).then(function (v) {
      if (v.length < Math.ceil(n / 2)) return null;
      v.sort(function (a, b) { return a - b; }); return v[Math.floor(v.length / 2)];
    });
  }
  function laneUpdate() {
    $('laneNearV').textContent = laneNear === null ? '' : laneNear + ' cm';
    $('laneFarV').textContent = laneFar === null ? '' : laneFar + ' cm';
    var ok = laneNear !== null && laneFar !== null && laneFar >= laneNear + 30;
    $('laneApply').disabled = !ok;
    var m = $('laneMsg');
    if (laneNear !== null && laneFar !== null && !ok) setMsg(m, 'The two readings are too close together – check the near lane is really closer to the sensor than the far lane.', false);
    else if (ok) setMsg(m, 'Cars closer than ' + Math.round((laneNear + laneFar) / 2) + ' cm (the near lane) will be ignored; cars farther out will be counted.', true);
  }
  function laneRecord(which) {
    var m = $('laneMsg'); setMsg(m, 'Reading… hold still for a moment.', true);
    sampleDistance(5).then(function (v) {
      if (v === null) { setMsg(m, 'The sensor sees nothing there. Put a car or person in that lane, hold still and try again.', false); return; }
      if (which === 'near') laneNear = v; else laneFar = v;
      laneUpdate();
    });
  }
  $('laneNear').onclick = function () { laneRecord('near'); };
  $('laneFar').onclick = function () { laneRecord('far'); };
  $('laneApply').onclick = function () {
    var min = Math.round((laneNear + laneFar) / 2), max = cfg.max_cm;
    if (max < laneFar + 50) max = laneFar + 150;
    api('save_config', { min_cm: min, max_cm: max }).then(function (r) {
      setMsg($('laneMsg'), r.ok ? 'Saved: nearest ' + min + ' cm, farthest ' + max + ' cm. Drive a car through each way to check it counts once.' : (r.error || 'Save failed'), r.ok);
      return api('config').then(function (c) { cfg = c; fillForms(); renderSetup(); });
    });
  };
  $('laneReset').onclick = function () {
    api('save_config', { min_cm: 30 }).then(function (r) {
      laneNear = laneFar = null; laneUpdate();
      setMsg($('laneMsg'), r.ok ? 'Both lanes will be counted again (nearest distance set back to 30 cm).' : 'Save failed', r.ok);
      return api('config').then(function (c) { cfg = c; fillForms(); renderSetup(); });
    });
  };

  function refresh() {
    return api('status').then(function (r) { running = r.running; status = r.status; renderStatus(); renderStats(); renderSetup(); }).catch(function () {
      running = false; renderStatus();
    });
  }
  function refreshStats() { api('stats').then(function (s) { stats = s; renderStats(); renderStatus(); }); }

  $('csvLink').href = AJAX + '&action=csv';
  api('config').then(function (c) { cfg = c; fillForms(); renderSetup(); });
  api('ports').then(function (p) {
    portInfo = p; dl.textContent = '';
    (p.all || []).forEach(function (x) { var o = document.createElement('option'); o.value = x; dl.appendChild(o); });
    populateUsb();
  });
  (function () { var h = (location.hash || '').replace('#', ''); if (h) gotoTab(h); })();
  refreshStats(); refresh();
  setInterval(refresh, 1000);
  setInterval(refreshStats, 15000);
})();
</script>
