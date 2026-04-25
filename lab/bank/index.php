<?php
require_once __DIR__ . '/check_blocked.php';
session_start();
if (isset($_SESSION['user_id'])) {
    header('Location: dashboard.php');
    exit;
}

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    require 'db.php';

    $username = $_POST['username'] ?? '';
    $password = $_POST['password'] ?? '';

    // !! INTENTIONALLY VULNERABLE — SQL INJECTION — DEMO ONLY !!
    // This concatenates user input directly into the query.
    // Payloads like:  admin' OR '1'='1' --
    // will bypass authentication completely.
    $query = "SELECT * FROM users WHERE username = '$username' AND password = '$password'";
    $result = $conn->query($query);

    if ($result && $result->num_rows > 0) {
        $user = $result->fetch_assoc();
        $_SESSION['user_id']        = $user['id'];
        $_SESSION['username']       = $user['username'];
        $_SESSION['full_name']      = $user['full_name'];
        $_SESSION['balance']        = $user['balance'];
        $_SESSION['account_number'] = $user['account_number'];
        header('Location: dashboard.php');
        exit;
    } else {
        $error = 'Invalid credentials. Please try again.';
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Meridian National Bank — Secure Login</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0a0e1a;
      color: #c8d6e5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    .header-bar {
      position: fixed; top: 0; left: 0; right: 0;
      background: #0d1526;
      border-bottom: 2px solid #c9a84c;
      padding: 12px 32px;
      display: flex; align-items: center; gap: 14px;
    }
    .header-bar .logo { font-size: 22px; font-weight: 700; color: #c9a84c; letter-spacing: 1px; }
    .header-bar .tagline { font-size: 12px; color: #7a8ba0; margin-top: 2px; }
    .card {
      background: #0d1526;
      border: 1px solid #1e3050;
      border-top: 3px solid #c9a84c;
      border-radius: 4px;
      padding: 40px 44px;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .card h2 {
      font-size: 18px;
      font-weight: 600;
      color: #e8edf2;
      margin-bottom: 6px;
    }
    .card .subtitle { font-size: 13px; color: #5a7090; margin-bottom: 28px; }
    label { display: block; font-size: 12px; color: #8a9bb0; margin-bottom: 6px; letter-spacing: 0.5px; text-transform: uppercase; }
    input[type=text], input[type=password] {
      width: 100%;
      background: #060c18;
      border: 1px solid #1e3050;
      border-radius: 3px;
      color: #c8d6e5;
      font-size: 14px;
      padding: 10px 14px;
      margin-bottom: 20px;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus { border-color: #c9a84c; }
    .btn {
      width: 100%;
      background: #c9a84c;
      color: #0a0e1a;
      border: none;
      border-radius: 3px;
      font-size: 14px;
      font-weight: 700;
      padding: 12px;
      cursor: pointer;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      transition: background 0.2s;
    }
    .btn:hover { background: #e0c060; }
    .error {
      background: rgba(220, 50, 50, 0.12);
      border: 1px solid #dc3232;
      border-radius: 3px;
      color: #f08080;
      font-size: 13px;
      padding: 10px 14px;
      margin-bottom: 20px;
    }
    .footer {
      position: fixed; bottom: 0; left: 0; right: 0;
      background: #0d1526;
      border-top: 1px solid #1a2a40;
      padding: 10px 32px;
      font-size: 11px;
      color: #3a4e60;
      display: flex; justify-content: space-between;
    }
    .lock-icon { color: #c9a84c; margin-right: 6px; }
  </style>
</head>
<body>
  <div class="header-bar">
    <div>
      <div class="logo">&#9632; MERIDIAN NATIONAL BANK</div>
      <div class="tagline">Trusted Financial Services Since 1987</div>
    </div>
  </div>

  <div class="card">
    <h2>Online Banking Portal</h2>
    <p class="subtitle">Sign in to access your accounts securely.</p>

    <?php if ($error): ?>
      <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <form method="POST" action="index.php" autocomplete="off">
      <label for="username">Customer ID / Username</label>
      <input type="text" id="username" name="username" placeholder="Enter your username" required>

      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Enter your password" required>

      <button type="submit" class="btn">&#9654; Sign In Securely</button>
    </form>
  </div>

  <div class="footer">
    <span><span class="lock-icon">&#128274;</span>256-bit SSL Encrypted Connection</span>
    <span>&#169; 2024 Meridian National Bank. All rights reserved.</span>
    <span>FDIC Insured | Member SIPC</span>
  </div>
</body>
</html>
