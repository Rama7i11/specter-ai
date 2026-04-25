<?php
// db.php — MySQL connection using env vars injected by Docker Compose
$db_host = getenv('MYSQL_HOST') ?: 'mysql';
$db_user = getenv('MYSQL_USER') ?: 'bankuser';
$db_pass = getenv('MYSQL_PASSWORD') ?: 'bankpass';
$db_name = getenv('MYSQL_DATABASE') ?: 'bankdb';

$conn = new mysqli($db_host, $db_user, $db_pass, $db_name);

if ($conn->connect_error) {
    http_response_code(503);
    die(json_encode(['error' => 'Database unavailable']));
}
$conn->set_charset('utf8mb4');
