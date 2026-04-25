-- Meridian National Bank — demo schema
-- Seeded by /demo/seed endpoint; this init only creates tables + one default admin.

CREATE TABLE IF NOT EXISTS users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    password       VARCHAR(100) NOT NULL,
    full_name      VARCHAR(100),
    email          VARCHAR(100),
    balance        DECIMAL(12, 2) DEFAULT 0.00,
    account_number VARCHAR(20),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT          NOT NULL,
    description VARCHAR(200) NOT NULL,
    amount      DECIMAL(12, 2) NOT NULL,
    type        ENUM('credit', 'debit') NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Default admin account so app works before /demo/seed is called
INSERT IGNORE INTO users (username, password, full_name, email, balance, account_number)
VALUES ('admin', 'admin123', 'System Administrator', 'admin@meridianbank.com', 250000.00, 'MNB-0000-0001');
