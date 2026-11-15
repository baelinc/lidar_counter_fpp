<?php
/* Standalone page: a minimal frame around the same settings/dashboard page the FPP plugin shows. */
$app = dirname(__DIR__, 2);
?><!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Car Counter</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 1rem; }
  body > header { max-width: 1100px; margin: 0 0 1rem; opacity: .75; font-size: .9rem; }
  input, select, textarea { font: inherit; }
</style>
</head><body>
<header><div class="logo">&#128663;</div><div><b>Car Counter</b>Roadside counter</div></header>
<?php require $app . '/ui.php'; ?>
<style><?php readfile(__DIR__ . '/theme.css'); ?></style>
</body></html>
