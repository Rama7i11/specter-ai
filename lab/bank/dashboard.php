<?php
require_once __DIR__ . '/check_blocked.php';
session_start();
if (!isset($_SESSION['user_id'])) {
    header('Location: index.php');
    exit;
}
require 'db.php';

$uid      = (int)$_SESSION['user_id'];
$username = $_SESSION['username'];
$name     = $_SESSION['full_name'];
$balance  = number_format((float)$_SESSION['balance'], 2);
$acct_no  = $_SESSION['account_number'];

// Recent transactions for this user
$txn_result = $conn->query(
    "SELECT description, amount, type, created_at FROM transactions
     WHERE user_id = $uid ORDER BY created_at DESC LIMIT 20"
);

// Admin dump: show all users (intentional — demonstrates data exposure)
$is_admin  = ($username === 'admin');
$all_users = null;
if ($is_admin) {
    $all_users = $conn->query("SELECT id, username, password, full_name, email, balance, account_number FROM users");
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>USF Bank — Account Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="./style.css">
  <style>
    body { margin: 0; overflow: auto; background: #07100d; display: block; }

    .topbar {
      position: sticky; top: 0; z-index: 10;
      background: rgba(8, 18, 15, 0.96);
      border-bottom: 1px solid rgba(137, 255, 224, 0.18);
      padding: 0 32px;
      display: flex; align-items: center; justify-content: space-between;
      height: 56px;
      backdrop-filter: blur(12px);
    }
    .topbar-logo {
      display: flex; align-items: center; gap: 10px;
      font-size: 18px; font-weight: 800; color: #f3fffb; text-decoration: none;
    }
    .topbar-logo img { height: 32px; width: auto; }
    .topbar-logo span { color: #19e6bd; }
    .topbar-user { font-size: 13px; color: rgba(239,255,250,0.7); }
    .topbar-user strong { color: #f3fffb; }
    .topbar-user a {
      color: #19e6bd; text-decoration: none;
      margin-left: 16px; font-size: 13px;
    }
    .topbar-user a:hover { text-decoration: underline; }

    .credit { color: #19e6bd; }
    .debit  { color: #e05555; }

    .admin-panel {
      margin-top: 24px; padding: 26px;
      border-radius: 14px;
      background: rgba(13, 25, 21, 0.94);
      border: 1px solid rgba(220, 50, 50, 0.3);
    }
    .admin-panel h2 {
      font-size: 20px; font-weight: 500; color: #e05555; margin-bottom: 12px;
    }
    .badge {
      display: inline-block; background: #dc3232; color: #fff;
      font-size: 10px; font-weight: 700; padding: 2px 8px;
      border-radius: 4px; text-transform: uppercase;
      letter-spacing: 0.5px; margin-left: 8px; vertical-align: middle;
    }
  </style>
</head>
<body>

  <div class="topbar">
    <div class="topbar-logo">
      <img src="./img/Official_USF_Bulls_Athletic_Logo.png" alt="USF Bulls">
      USF <span>Bank</span>
    </div>
    <div class="topbar-user">
      Welcome, <strong><?= htmlspecialchars($name ?: $username) ?></strong>
      <a href="logout.php">Sign Out</a>
    </div>
  </div>

  <div id="dashboard-page">
    <div class="dashboard-container">

      <div class="welcome-section">
        <h1 id="welcome">Hello, <span><?= htmlspecialchars($name ?: $username) ?></span></h1>
        <p class="subtext">
          Account <?= htmlspecialchars($acct_no) ?> &nbsp;&bull;&nbsp; Checking Account
        </p>
      </div>

      <div class="balance-card">
        <h2>Available Balance</h2>
        <div class="balance-amount">$<?= $balance ?></div>
      </div>

      <div class="actions-section">
        <button class="action-btn">Transfer Funds</button>
        <button class="action-btn">Pay Bills</button>
        <button class="action-btn">View Statements</button>
        <button class="action-btn">Open New Account</button>
      </div>

      <div class="transactions-section">
        <h2>Recent Transactions</h2>
        <table class="transactions-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Type</th>
              <th style="text-align:right">Amount</th>
            </tr>
          </thead>
          <tbody>
            <?php if ($txn_result && $txn_result->num_rows > 0): ?>
              <?php while ($row = $txn_result->fetch_assoc()): ?>
                <tr>
                  <td><?= htmlspecialchars($row['created_at']) ?></td>
                  <td><?= htmlspecialchars($row['description']) ?></td>
                  <td class="<?= $row['type'] ?>"><?= strtoupper($row['type']) ?></td>
                  <td class="<?= $row['type'] ?>" style="text-align:right; font-family:monospace">
                    <?= $row['type'] === 'debit' ? '-' : '+' ?>$<?= number_format((float)$row['amount'], 2) ?>
                  </td>
                </tr>
              <?php endwhile; ?>
            <?php else: ?>
              <tr>
                <td colspan="4" style="color:rgba(239,255,250,0.3); text-align:center; padding:24px">
                  No transactions found.
                </td>
              </tr>
            <?php endif; ?>
          </tbody>
        </table>
      </div>

      <?php if ($is_admin && $all_users): ?>
      <div class="admin-panel">
        <h2>User Administration <span class="badge">Sensitive</span></h2>
        <p style="font-size:13px; color:rgba(224,85,85,0.8); margin-bottom:16px">
          All registered accounts &mdash; admin access only.
        </p>
        <table class="transactions-table">
          <thead>
            <tr>
              <th>ID</th><th>Username</th><th>Password</th>
              <th>Full Name</th><th>Email</th><th>Balance</th><th>Account #</th>
            </tr>
          </thead>
          <tbody>
            <?php while ($u = $all_users->fetch_assoc()): ?>
              <tr>
                <td><?= $u['id'] ?></td>
                <td><?= htmlspecialchars($u['username']) ?></td>
                <td style="font-family:monospace; color:#e05555"><?= htmlspecialchars($u['password']) ?></td>
                <td><?= htmlspecialchars($u['full_name']) ?></td>
                <td><?= htmlspecialchars($u['email']) ?></td>
                <td>$<?= number_format((float)$u['balance'], 2) ?></td>
                <td style="font-family:monospace"><?= htmlspecialchars($u['account_number']) ?></td>
              </tr>
            <?php endwhile; ?>
          </tbody>
        </table>
      </div>
      <?php endif; ?>

    </div>
  </div>

  <script src="./script.js"></script>
</body>
</html>
