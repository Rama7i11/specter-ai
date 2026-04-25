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
$is_admin   = ($username === 'admin');
$all_users  = null;
if ($is_admin) {
    $all_users = $conn->query("SELECT id, username, password, full_name, email, balance, account_number FROM users");
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meridian National Bank — Account Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0e1a; color: #c8d6e5; }
    .topbar {
      background: #0d1526; border-bottom: 2px solid #c9a84c;
      padding: 0 32px; display: flex; align-items: center; justify-content: space-between; height: 56px;
    }
    .topbar .logo { font-size: 18px; font-weight: 700; color: #c9a84c; letter-spacing: 1px; }
    .topbar .user { font-size: 13px; color: #8a9bb0; }
    .topbar .user strong { color: #c8d6e5; }
    .topbar a { color: #c9a84c; font-size: 13px; text-decoration: none; margin-left: 20px; }
    .topbar a:hover { text-decoration: underline; }

    .main { max-width: 1100px; margin: 32px auto; padding: 0 24px; }

    .account-card {
      background: #0d1526; border: 1px solid #1e3050; border-top: 3px solid #c9a84c;
      border-radius: 4px; padding: 28px 32px; margin-bottom: 28px;
      display: flex; justify-content: space-between; align-items: center;
    }
    .account-card .acct-label { font-size: 11px; color: #5a7090; text-transform: uppercase; letter-spacing: 0.5px; }
    .account-card .acct-name { font-size: 20px; font-weight: 600; color: #e8edf2; margin: 4px 0; }
    .account-card .acct-num { font-size: 13px; color: #7a8ba0; font-family: monospace; }
    .account-card .balance-label { font-size: 11px; color: #5a7090; text-transform: uppercase; letter-spacing: 0.5px; text-align: right; }
    .account-card .balance { font-size: 32px; font-weight: 700; color: #c9a84c; text-align: right; }

    h3 { font-size: 14px; color: #8a9bb0; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 14px; }

    table { width: 100%; border-collapse: collapse; background: #0d1526; border-radius: 4px; overflow: hidden; }
    th { background: #060c18; color: #5a7090; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; padding: 12px 16px; text-align: left; border-bottom: 1px solid #1e3050; }
    td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #111d30; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #0f1a2e; }
    .credit { color: #4caf82; }
    .debit  { color: #e05555; }

    .admin-panel {
      margin-top: 40px; background: #0d1526; border: 1px solid #8b1a1a;
      border-top: 3px solid #dc3232; border-radius: 4px; padding: 24px 28px;
    }
    .admin-panel h3 { color: #dc3232; }
    .badge { display: inline-block; background: #dc3232; color: #fff; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.5px; margin-left: 8px; vertical-align: middle; }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="logo">&#9632; MERIDIAN NATIONAL BANK</div>
    <div class="user">
      Welcome, <strong><?= htmlspecialchars($name ?: $username) ?></strong>
      <a href="logout.php">Sign Out</a>
    </div>
  </div>

  <div class="main">
    <div class="account-card">
      <div>
        <div class="acct-label">Checking Account</div>
        <div class="acct-name"><?= htmlspecialchars($name ?: $username) ?></div>
        <div class="acct-num"><?= htmlspecialchars($acct_no) ?></div>
      </div>
      <div>
        <div class="balance-label">Available Balance</div>
        <div class="balance">$<?= $balance ?></div>
      </div>
    </div>

    <h3>Recent Transactions</h3>
    <table>
      <thead>
        <tr><th>Date</th><th>Description</th><th>Type</th><th style="text-align:right">Amount</th></tr>
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
          <tr><td colspan="4" style="color:#3a4e60; text-align:center; padding:24px">No transactions found.</td></tr>
        <?php endif; ?>
      </tbody>
    </table>

    <?php if ($is_admin && $all_users): ?>
    <div class="admin-panel">
      <h3>User Administration <span class="badge">Sensitive</span></h3>
      <p style="font-size:12px; color:#8b1a1a; margin-bottom:16px">All registered accounts — admin access only.</p>
      <table>
        <thead>
          <tr><th>ID</th><th>Username</th><th>Password</th><th>Full Name</th><th>Email</th><th>Balance</th><th>Account #</th></tr>
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
</body>
</html>
