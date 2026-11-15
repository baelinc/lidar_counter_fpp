<?php
/* Front door for the standalone web page (php -S ... router.php).
 * - Only index.php and plugin.php (the JSON endpoint) are served; nothing else in the install is reachable.
 * - HTTP Basic login (user "admin"); the password hash lives in CC_WEB_PASSWORD_FILE (set by install.sh).
 *   With no password configured the page refuses to open rather than being open to the network. */

function cc_deny($code, $msg, $challenge = false) {
    http_response_code($code);
    if ($challenge) header('WWW-Authenticate: Basic realm="Car Counter", charset="UTF-8"');
    header('Content-Type: text/plain; charset=utf-8');
    echo $msg . "\n";
    return true;
}

function cc_basic_credentials() {
    $h = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if ($h === '' && function_exists('getallheaders')) {
        foreach (getallheaders() as $k => $v) if (strcasecmp($k, 'Authorization') === 0) $h = $v;
    }
    if (stripos($h, 'Basic ') !== 0) return array('', '');
    $dec = base64_decode(substr($h, 6), true);
    if ($dec === false || strpos($dec, ':') === false) return array('', '');
    return explode(':', $dec, 2);
}

$noauth = (getenv('CC_WEB_NOAUTH') === '1');          // development / tests only
if (!$noauth) {
    $file = getenv('CC_WEB_PASSWORD_FILE') ?: '/etc/car-counter/web.pass';
    $hash = trim((string)@file_get_contents($file));
    if ($hash === '') return cc_deny(503, 'No password is set. Run:  sudo car-counter-passwd');
    list($user, $pass) = cc_basic_credentials();
    if (!hash_equals('admin', (string)$user) || !password_verify((string)$pass, $hash)) {
        if ($user !== '' || $pass !== '') sleep(1);       // slow down guessing
        return cc_deny(401, 'Login required (user: admin)', true);
    }
}

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
if ($path === '/' || $path === '/index.php') { require __DIR__ . '/index.php'; return true; }
if ($path === '/plugin.php')                 { require __DIR__ . '/plugin.php'; return true; }
return cc_deny(404, 'Not found');
