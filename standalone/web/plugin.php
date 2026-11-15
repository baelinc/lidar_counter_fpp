<?php
/* ui.php talks to "plugin.php?plugin=...&page=ajax.php&nopage=1" (FPP's URL shape); answer it with the same ajax.php. */
$app = dirname(__DIR__, 2);
if (($_GET['page'] ?? '') !== 'ajax.php') { http_response_code(404); exit; }
require $app . '/ajax.php';
