<?php
/**
 * check_blocked.php — IP blocklist + account lockout gate + POST body logger.
 *
 * Three responsibilities:
 *   1. Append a synthetic Apache-format log line for POST requests so the
 *      detector can see POST body parameters.
 *   2. Block requests from IPs in /data/blocked_ips.json (written by backend).
 *   3. Block POST logins where the username is in /data/locked_users.json.
 */

// ── POST body → access.log ────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST)) {
    $_log_params = http_build_query($_POST);
    $_log_uri    = $_SERVER['REQUEST_URI'] ?? '/';
    $_log_ip     = $_SERVER['REMOTE_ADDR'] ?? '-';
    $_log_ts     = date('d/M/Y:H:i:s O');
    $_log_req    = "POST {$_log_uri}?{$_log_params} HTTP/1.1";
    $_log_line   = "{$_log_ip} - - [{$_log_ts}] \"{$_log_req}\" 200 -\n";
    @file_put_contents('/var/log/bank/access.log', $_log_line, FILE_APPEND | LOCK_EX);
}

// ── IP blocklist ──────────────────────────────────────────────────────────
$_blocked_file = '/data/blocked_ips.json';
if (file_exists($_blocked_file)) {
    $_blocked = @json_decode(file_get_contents($_blocked_file), true);
    if (is_array($_blocked)) {
        $_client_ip = $_SERVER['REMOTE_ADDR'] ?? '';
        if ($_client_ip !== '' && in_array($_client_ip, $_blocked, true)) {
            http_response_code(403);
            echo '<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>403 Access Denied | USF Bank</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="./style.css">
  <style>
    body { display: block; overflow: auto; min-height: 100vh; }
    .denied-topbar {
      background: rgba(8,18,15,0.97);
      border-bottom: 1px solid rgba(137,255,224,0.18);
      padding: 0 32px; height: 56px;
      display: flex; align-items: center; gap: 12px;
    }
    .denied-topbar img { height: 32px; width: auto; }
    .denied-topbar .brand {
      font-size: 18px; font-weight: 800; color: #f3fffb;
    }
    .denied-topbar .brand span { color: #19e6bd; }
    .denied-topbar .defense-badge {
      margin-left: auto; font-size: 12px; font-weight: 700;
      color: #19e6bd; letter-spacing: 1px; text-transform: uppercase;
    }
    .denied-main {
      display: flex; align-items: center; justify-content: center;
      min-height: calc(100vh - 96px); padding: 40px 20px;
    }
    .denied-card {
      width: min(520px, 94vw);
      padding: 48px 40px;
      border-radius: 16px;
      background: rgba(13,25,21,0.94);
      border: 1px solid rgba(220,50,50,0.4);
      box-shadow: 0 0 60px rgba(220,50,50,0.15), 0 30px 90px rgba(0,0,0,0.6);
      text-align: center;
    }
    .denied-code {
      font-size: 96px; font-weight: 800; letter-spacing: -4px;
      color: #dc3232; line-height: 1;
      text-shadow: 0 0 40px rgba(220,50,50,0.5);
    }
    .denied-title {
      font-size: 28px; font-weight: 700; letter-spacing: 4px;
      color: #f3fffb; margin: 12px 0 24px; text-transform: uppercase;
    }
    .denied-divider {
      width: 60px; height: 3px; background: #dc3232;
      margin: 0 auto 24px; border-radius: 2px;
    }
    .denied-msg {
      font-size: 15px; line-height: 1.7;
      color: rgba(239,255,250,0.75); margin-bottom: 20px;
    }
    .denied-ip {
      display: inline-block; font-family: monospace; font-size: 14px;
      color: #e05555; background: rgba(220,50,50,0.1);
      border: 1px solid rgba(220,50,50,0.25);
      border-radius: 6px; padding: 6px 14px;
    }
    .denied-footer {
      background: rgba(8,18,15,0.97);
      border-top: 1px solid rgba(137,255,224,0.1);
      padding: 16px 32px; text-align: center;
      font-size: 12px; color: rgba(239,255,250,0.3); letter-spacing: 1px;
    }
  </style>
</head>
<body>
  <div class="denied-topbar">
    <img src="./img/Official_USF_Bulls_Athletic_Logo.png" alt="USF Bulls">
    <span class="brand">USF <span>Bank</span></span>
    <span class="defense-badge">&#9632; SPECTER-AI Active Defense Engaged</span>
  </div>

  <div class="denied-main">
    <div class="denied-card">
      <div class="denied-code">403</div>
      <div class="denied-title">Access Denied</div>
      <div class="denied-divider"></div>
      <p class="denied-msg">
        Your IP address has been blocked by the<br>
        <strong style="color:#f3fffb">SPECTER-AI active defense system.</strong>
      </p>
      <div class="denied-ip">' . htmlspecialchars($_client_ip) . '</div>
    </div>
  </div>

  <div class="denied-footer">
    Team Aegis &bull; Specter-AI v1.0
  </div>
</body>
</html>';
            exit;
        }
    }
}

// ── Account lockout check ─────────────────────────────────────────────────
$_locked_file = '/data/locked_users.json';
if ($_SERVER['REQUEST_METHOD'] === 'POST'
    && isset($_POST['username'])
    && file_exists($_locked_file))
{
    $_locked_users = @json_decode(file_get_contents($_locked_file), true);
    if (is_array($_locked_users)) {
        $_post_username = trim($_POST['username'] ?? '');
        foreach ($_locked_users as $_entry) {
            if (isset($_entry['username']) && $_entry['username'] === $_post_username) {
                http_response_code(403);
                echo '<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Account Locked | USF Bank</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="./style.css">
  <style>
    body { display: block; overflow: auto; min-height: 100vh; }
    .denied-topbar {
      background: rgba(8,18,15,0.97);
      border-bottom: 1px solid rgba(137,255,224,0.18);
      padding: 0 32px; height: 56px;
      display: flex; align-items: center; gap: 12px;
    }
    .denied-topbar img { height: 32px; width: auto; }
    .denied-topbar .brand {
      font-size: 18px; font-weight: 800; color: #f3fffb;
    }
    .denied-topbar .brand span { color: #19e6bd; }
    .denied-topbar .defense-badge {
      margin-left: auto; font-size: 12px; font-weight: 700;
      color: #19e6bd; letter-spacing: 1px; text-transform: uppercase;
    }
    .denied-main {
      display: flex; align-items: center; justify-content: center;
      min-height: calc(100vh - 96px); padding: 40px 20px;
    }
    .denied-card {
      width: min(520px, 94vw);
      padding: 48px 40px;
      border-radius: 16px;
      background: rgba(13,25,21,0.94);
      border: 1px solid rgba(220,50,50,0.4);
      box-shadow: 0 0 60px rgba(220,50,50,0.15), 0 30px 90px rgba(0,0,0,0.6);
      text-align: center;
    }
    .denied-icon { font-size: 64px; margin-bottom: 16px; }
    .denied-title {
      font-size: 28px; font-weight: 700; letter-spacing: 2px;
      color: #f3fffb; margin-bottom: 12px; text-transform: uppercase;
    }
    .denied-divider {
      width: 60px; height: 3px; background: #dc3232;
      margin: 0 auto 24px; border-radius: 2px;
    }
    .denied-msg {
      font-size: 15px; line-height: 1.7;
      color: rgba(239,255,250,0.75); margin-bottom: 20px;
    }
    .denied-user {
      display: inline-block; font-family: monospace; font-size: 14px;
      color: #f0b040; background: rgba(240,176,64,0.1);
      border: 1px solid rgba(240,176,64,0.25);
      border-radius: 6px; padding: 6px 14px;
    }
    .denied-footer {
      background: rgba(8,18,15,0.97);
      border-top: 1px solid rgba(137,255,224,0.1);
      padding: 16px 32px; text-align: center;
      font-size: 12px; color: rgba(239,255,250,0.3); letter-spacing: 1px;
    }
  </style>
</head>
<body>
  <div class="denied-topbar">
    <img src="./img/Official_USF_Bulls_Athletic_Logo.png" alt="USF Bulls">
    <span class="brand">USF <span>Bank</span></span>
    <span class="defense-badge">&#9632; SPECTER-AI Account Protection Active</span>
  </div>

  <div class="denied-main">
    <div class="denied-card">
      <div class="denied-icon">&#128274;</div>
      <div class="denied-title">Account Locked</div>
      <div class="denied-divider"></div>
      <p class="denied-msg">
        This account has been locked by the SOC.<br>
        <strong style="color:#f3fffb">Contact administrator to restore access.</strong>
      </p>
      <div class="denied-user">' . htmlspecialchars($_post_username) . '</div>
    </div>
  </div>

  <div class="denied-footer">
    Team Aegis &bull; Specter-AI v1.0
  </div>
</body>
</html>';
                exit;
            }
        }
    }
}
