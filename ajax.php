<?php
/* JSON endpoint used by ui.php.  Loaded through FPP's plugin.php with nopage=1. */
require_once __DIR__ . '/lib.php';

$action = isset($_REQUEST['action']) ? (string)$_REQUEST['action'] : '';
$isPost = ($_SERVER['REQUEST_METHOD'] === 'POST');

function cc_out($data, $code = 200) {
    http_response_code($code);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode($data);
    exit;
}

$mutating = array('save_config', 'command', 'service');
if (in_array($action, $mutating, true)) {
    // POST only, and only from our own page (a custom header cannot be set by a cross-site form).
    if (!$isPost || !isset($_SERVER['HTTP_X_REQUESTED_WITH'])) {
        cc_out(array('ok' => false, 'error' => 'Forbidden'), 403);
    }
}
$body = array();
if ($isPost) {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!is_array($body)) $body = array();
}

switch ($action) {
    case 'status':
        $s = cc_status();
        cc_out(array('running' => $s['running'], 'status' => $s['data']));

    case 'stats':
        $st = cc_read_json(CC_RUN_DIR . '/stats.json');
        cc_out($st === null ? array('days' => array(), 'season_total' => 0, 'best' => null) : $st);

    case 'config':
        $cfg = cc_config();
        $cfg['secret_set'] = ($cfg['secret'] !== '');
        unset($cfg['secret']);
        cc_out($cfg);

    case 'save_config':
        if (!cc_save_config($body)) cc_out(array('ok' => false, 'error' => 'Could not write config file'), 500);
        cc_out(array('ok' => true));

    case 'command':
        $allowed = array('adjust', 'reset_today', 'test_mode', 'calibrate', 'sync_now', 'sync_test');
        $cmd = isset($body['cmd']) ? (string)$body['cmd'] : '';
        if (!in_array($cmd, $allowed, true)) cc_out(array('ok' => false, 'error' => 'Unknown command'), 400);
        $payload = array('cmd' => $cmd);
        if ($cmd === 'adjust') $payload['delta'] = (isset($body['delta']) && (int)$body['delta'] < 0) ? -1 : 1;
        if ($cmd === 'test_mode') $payload['on'] = !empty($body['on']);
        if (!cc_status()['running']) cc_out(array('ok' => false, 'error' => 'The counter service is not running.'), 503);
        $id = cc_send_command($payload);
        if ($id === false) cc_out(array('ok' => false, 'error' => 'Could not queue command'), 500);
        cc_out(array('ok' => true, 'id' => $id));

    case 'service':
        $op = isset($body['op']) ? (string)$body['op'] : '';
        $res = cc_service($op);
        cc_out(array('ok' => true, 'output' => $res));

    case 'log':
        cc_out(array('log' => cc_tail(CC_LOG_FILE, 200), 'errors' => cc_tail(CC_ERR_FILE, 30)));

    case 'ports':
        $ports = array();
        foreach (array('/dev/serial0', '/dev/ttyAMA*', '/dev/ttyS0', '/dev/ttyUSB*', '/dev/ttyACM*') as $pat) {
            foreach (glob($pat) ?: array() as $p) $ports[] = $p;
        }
        cc_out(array_values(array_unique($ports)));

    case 'csv':
        $st = cc_read_json(CC_RUN_DIR . '/stats.json');
        header('Content-Type: text/csv');
        header('Content-Disposition: attachment; filename="car-counts-' . date('Y-m-d') . '.csv"');
        $out = fopen('php://output', 'w');
        $head = array('date', 'cars', 'offhours_detections');
        for ($h = 0; $h < 24; $h++) $head[] = sprintf('h%02d', $h);
        fputcsv($out, $head, ',', '"', '\\');
        foreach (($st['days'] ?? array()) as $d) {
            fputcsv($out, array_merge(array($d['date'], $d['total'], $d['offhours']), $d['hours']), ',', '"', '\\');
        }
        exit;

    default:
        cc_out(array('ok' => false, 'error' => 'Unknown action'), 400);
}
