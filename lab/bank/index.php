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
  <title>USF Bank — Secure Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="./style.css">
  <style>
    .error-msg {
      background: rgba(220, 50, 50, 0.12);
      border: 1px solid rgba(220, 50, 50, 0.4);
      border-radius: 8px;
      color: #f08080;
      font-size: 13px;
      padding: 10px 14px;
      margin-bottom: 16px;
    }
  </style>
</head>
<body>
  <div class="page-shell">

    <div class="hero-panel">
      <div class="navbar">
        <div class="logo">
          <img class="img" src="./img/Official_USF_Bulls_Athletic_Logo.png" alt="USF Bulls">
          USF <span>Bank</span>
        </div>
      </div>

      <div class="hero-content">
        <h1>Banking built<br>for <span>Bull</span><br>Nation.</h1>
        <p>Access your accounts, manage transactions, and stay in control of your finances — securely, 24/7.</p>
      </div>
    </div>

    <div class="login-card">
      <h2>Welcome back.</h2>
      <p class="subtitle">Sign in to your USF Bank account to continue.</p>

      <?php if ($error): ?>
        <div class="error-msg"><?= htmlspecialchars($error) ?></div>
      <?php endif; ?>

      <form method="POST" action="index.php" autocomplete="off">
        <div class="form-group">
          <label for="username">Username</label>
          <input type="text" id="username" name="username" placeholder="Enter your username" required>
        </div>

        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" placeholder="Enter your password" required>
        </div>

        <div class="checkbox-row">
          <input type="checkbox" id="remember">
          <label for="remember" style="margin-bottom:0; font-size:14px; color:rgba(237,255,250,0.72)">
            Remember me on this device
          </label>
        </div>

        <button type="submit" class="login-btn">Sign In</button>
      </form>

      <div class="security-note">
        <strong>Security Notice:</strong> USF Bank will never ask for your password
        by email or phone. Always verify you are on the official portal before
        entering credentials.
      </div>
    </div>

  </div>
  <script src="./script.js"></script>
</body>
</html>
