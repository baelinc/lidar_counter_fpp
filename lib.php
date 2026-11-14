<?php
/* Shared helpers for the Car Counter plugin pages. */

/* Locations (the daemon uses the same defaults; the CC_* environment overrides exist for testing). */
define('CC_DATA_DIR', getenv('CC_DATA_DIR') ?: '/home/fpp/media/config/fpp-car-counter');
define('CC_RUN_DIR',  getenv('CC_RUN_DIR')  ?: '/dev/shm/fpp-car-counter');
define('CC_LOG_FILE', getenv('CC_LOG_FILE') ?: '/home/fpp/media/logs/fpp-car-counter.log');
define('CC_ERR_FILE', getenv('CC_ERR_FILE') ?: '/home/fpp/media/logs/fpp-car-counter.err');

/* key => [type, default, extra]   (must mirror SCHEMA in counter/car_counter.py) */
function cc_schema() {
    return array(
        'show_name'         => array('str', 'My Light Show', 80),
        'serial_port'       => array('str', '/dev/serial0', 120),
        'baud'              => array('choice', 115200, array(9600, 19200, 38400, 57600, 115200, 230400)),
        'unit'              => array('choice', 'cm', array('cm', 'mm')),
        'min_cm'            => array('int', 30, array(1, 5000)),
        'max_cm'            => array('int', 1200, array(2, 20000)),
        'min_strength'      => array('int', 0, array(0, 65534)),
        'confirm_ms'        => array('int', 250, array(20, 5000)),
        'clear_ms'          => array('int', 800, array(100, 30000)),
        'max_dwell_s'       => array('int', 120, array(5, 3600)),
        'schedule_mode'     => array('choice', 'window', array('always', 'window', 'playing')),
        'window_start'      => array('time', '17:00', null),
        'window_end'        => array('time', '22:00', null),
        'grace_min'         => array('int', 10, array(0, 240)),
        'rollover_hour'     => array('int', 6, array(0, 12)),
        'sync_enabled'      => array('bool', false, null),
        'wp_url'            => array('str', '', 300),
        'secret'            => array('str', '', 200),
        'sync_time'         => array('time', '23:00', null),
        'sync_days'         => array('int', 7, array(1, 60)),
        'live_interval_min' => array('int', 0, array(0, 240)),
        'verify_tls'        => array('bool', true, null),
    );
}

function cc_coerce($key, $value) {
    $s = cc_schema()[$key];
    list($type, $def, $extra) = $s;
    switch ($type) {
        case 'str':
            return substr(trim((string)$value), 0, $extra);
        case 'bool':
            if (is_string($value)) return in_array(strtolower(trim($value)), array('1', 'true', 'yes', 'on'), true);
            return (bool)$value;
        case 'int':
            if (!is_numeric($value)) return $def;
            return max($extra[0], min($extra[1], (int)round((float)$value)));
        case 'choice':
            if (is_int($def)) $value = (int)$value;
            return in_array($value, $extra, true) ? $value : $def;
        case 'time':
            return (is_string($value) && preg_match('/^([01]?\d|2[0-3]):[0-5]\d$/', trim($value))) ? trim($value) : $def;
    }
    return $def;
}

/* Schedule entries: array of array('days' => [0..6, 0 = Sunday], 'start' => 'HH:MM', 'end' => 'HH:MM'). */
function cc_coerce_schedules($value) {
    $out = array();
    if (!is_array($value)) return $out;
    foreach (array_slice(array_values($value), 0, 28) as $e) {
        if (!is_array($e) || !isset($e['days']) || !is_array($e['days'])) continue;
        $days = array();
        foreach ($e['days'] as $d) {
            if (is_numeric($d) && (int)$d >= 0 && (int)$d <= 6) $days[(int)$d] = (int)$d;
        }
        ksort($days);
        $start = isset($e['start']) ? trim((string)$e['start']) : '';
        $end   = isset($e['end']) ? trim((string)$e['end']) : '';
        $ok = '/^([01]?\d|2[0-3]):[0-5]\d$/';
        if (!$days || !preg_match($ok, $start) || !preg_match($ok, $end)) continue;
        $out[] = array('days' => array_values($days), 'start' => $start, 'end' => $end);
    }
    return $out;
}

function cc_read_json($path) {
    $raw = @file_get_contents($path);
    if ($raw === false) return null;
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}

function cc_config() {
    $raw = cc_read_json(CC_DATA_DIR . '/config.json');
    $out = array();
    foreach (cc_schema() as $k => $s) {
        $out[$k] = ($raw !== null && array_key_exists($k, $raw)) ? cc_coerce($k, $raw[$k]) : $s[1];
    }
    if ($out['max_cm'] <= $out['min_cm']) $out['max_cm'] = $out['min_cm'] + 10;
    $out['wp_url'] = rtrim($out['wp_url'], '/');
    if ($raw !== null && isset($raw['schedules']) && is_array($raw['schedules'])) {
        $out['schedules'] = cc_coerce_schedules($raw['schedules']);
    } else {   // older config (single window) or fresh install: one entry for every day
        $out['schedules'] = array(array('days' => range(0, 6), 'start' => $out['window_start'], 'end' => $out['window_end']));
    }
    return $out;
}

/* Merge the submitted values over the saved config. A blank secret keeps the old one. */
function cc_save_config($changes) {
    $cfg = cc_config();
    $schema = cc_schema();
    foreach ($changes as $k => $v) {
        if ($k === 'schedules') { $cfg['schedules'] = cc_coerce_schedules($v); continue; }
        if (!isset($schema[$k])) continue;
        if ($k === 'secret' && trim((string)$v) === '') continue;
        $cfg[$k] = cc_coerce($k, $v);
    }
    if ($cfg['max_cm'] <= $cfg['min_cm']) $cfg['max_cm'] = $cfg['min_cm'] + 10;
    $cfg['wp_url'] = rtrim($cfg['wp_url'], '/');
    if (!is_dir(CC_DATA_DIR)) @mkdir(CC_DATA_DIR, 0775, true);
    $tmp = CC_DATA_DIR . '/config.json.tmp.' . getmypid();
    if (file_put_contents($tmp, json_encode($cfg)) === false) return false;
    @chmod($tmp, 0600);
    return rename($tmp, CC_DATA_DIR . '/config.json');
}

function cc_status() {
    $st = cc_read_json(CC_RUN_DIR . '/status.json');
    $running = ($st !== null && isset($st['ts']) && (microtime(true) - $st['ts']) < 6);
    return array('running' => $running, 'data' => $running ? $st : null);
}

function cc_send_command($cmd) {
    if (!is_dir(CC_RUN_DIR . '/cmd')) return false;
    $id = bin2hex(random_bytes(6));
    $cmd['id'] = $id;
    $name = sprintf('%s/cmd/%.6f-%s', CC_RUN_DIR, microtime(true), $id);
    if (file_put_contents($name . '.tmp', json_encode($cmd)) === false) return false;
    @chmod($name . '.tmp', 0666);
    return rename($name . '.tmp', $name . '.json') ? $id : false;
}

function cc_service($op) {
    if (!in_array($op, array('start', 'stop', 'restart'), true)) return 'bad op';
    $script = __DIR__ . '/scripts/service.sh';
    $out = array();
    exec(escapeshellarg($script) . ' ' . $op . ' 2>&1', $out);
    return implode("\n", $out);
}

function cc_tail($path, $lines = 150) {
    $fh = @fopen($path, 'r');
    if (!$fh) return '';
    $size = filesize($path);
    fseek($fh, max(0, $size - 65536));
    $data = stream_get_contents($fh);
    fclose($fh);
    $arr = explode("\n", rtrim($data));
    return implode("\n", array_slice($arr, -$lines));
}
