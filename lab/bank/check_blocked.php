<?php
/**
 * check_blocked.php — IP blocklist gate + POST body logger.
 *
 * Two responsibilities:
 *   1. Block requests from IPs in /data/blocked_ips.json (written by backend).
 *   2. Append a synthetic Apache-format log line for POST requests so the
 *      detector can see POST body parameters (Apache only logs the request
 *      line, which omits POST body — this bridges that gap).
 */

// ── POST body → access.log ────────────────────────────────────────────────
// Apache logs GET params automatically; POST params are invisible to it.
// We write a synthetic Combined Log line so the detector sees everything.
if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST)) {
    $_log_params = http_build_query($_POST);
    $_log_uri    = $_SERVER['REQUEST_URI'] ?? '/';
    $_log_ip     = $_SERVER['REMOTE_ADDR'] ?? '-';
    $_log_ts     = date('d/M/Y:H:i:s O');
    // Build a fake-Apache request string that includes POST params as a query string
    $_log_req    = "POST {$_log_uri}?{$_log_params} HTTP/1.1";
    $_log_line   = "{$_log_ip} - - [{$_log_ts}] \"{$_log_req}\" 200 -\n";
    @file_put_contents('/var/log/bank/access.log', $_log_line, FILE_APPEND | LOCK_EX);
}
$_blocked_file = '/data/blocked_ips.json';
if (file_exists($_blocked_file)) {
    $_blocked = @json_decode(file_get_contents($_blocked_file), true);
    if (is_array($_blocked)) {
        $_client_ip = $_SERVER['REMOTE_ADDR'] ?? '';
        if ($_client_ip !== '' && in_array($_client_ip, $_blocked, true)) {
            http_response_code(403);
            echo '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>403 Forbidden — Meridian National Bank</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:"Segoe UI",sans-serif;background:#0a0e1a;color:#c8d6e5;
       display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:12px}
  .code{font-size:72px;font-weight:700;color:#dc3232}
  .msg{font-size:16px;color:#8a9bb0}
  .badge{margin-top:24px;font-size:11px;color:#3a4e60;letter-spacing:1px;text-transform:uppercase}
  .ip{font-family:monospace;color:#e05555}
</style></head>
<body>
  <div class="code">403</div>
  <div class="msg">Access Denied</div>
  <p style="font-size:13px;color:#5a7090">
    IP address <span class="ip">' . htmlspecialchars($_client_ip) . '</span>
    has been blocked by the automated security system.
  </p>
  <div class="badge">&#9632; SPECTER-AI &bull; Team Aegis &bull; Active Defense Engaged</div>
</body></html>';
            exit;
        }
    }
}
