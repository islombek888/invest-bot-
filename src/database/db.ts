import Database from 'better-sqlite3';
import { config } from '../config';

const db = new Database(config.dbPath);

// Initialize tables
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance REAL DEFAULT 0,
    referred_by INTEGER,
    created_at TEXT
  );

  CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    photo_file_id TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    card_number TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    profit_percentage REAL DEFAULT 25.0,
    duration_days INTEGER,
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );

  CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
  );
`);

export interface User {
  id: number;
  username: string | null;
  first_name: string;
  balance: number;
  referred_by: number | null;
  created_at: string;
}

export interface Deposit {
  id: number;
  user_id: number;
  amount: number;
  photo_file_id: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}

export interface Withdrawal {
  id: number;
  user_id: number;
  amount: number;
  card_number: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}

export interface Investment {
  id: number;
  user_id: number;
  amount: number;
  profit_percentage: number;
  duration_days: number;
  start_date: string;
  end_date: string;
  status: 'active' | 'completed';
  created_at: string;
}

// User helper methods
export const dbService = {
  // User
  getUser(id: number): User | null {
    const row = db.prepare('SELECT * FROM users WHERE id = ?').get(id);
    return row ? (row as User) : null;
  },

  createUser(id: number, username: string | null, firstName: string, referredBy?: number): User {
    const now = new Date().toISOString();
    db.prepare(`
      INSERT OR REPLACE INTO users (id, username, first_name, balance, referred_by, created_at)
      VALUES (?, ?, ?, COALESCE((SELECT balance FROM users WHERE id = ?), 0), ?, COALESCE((SELECT created_at FROM users WHERE id = ?), ?))
    `).run(id, username, firstName, id, referredBy || null, id, now);
    
    return this.getUser(id)!;
  },

  updateBalance(id: number, amount: number): void {
    db.prepare('UPDATE users SET balance = balance + ? WHERE id = ?').run(amount, id);
  },

  setBalance(id: number, amount: number): void {
    db.prepare('UPDATE users SET balance = ? WHERE id = ?').run(amount, id);
  },

  getReferralCount(id: number): number {
    const row = db.prepare('SELECT COUNT(*) as count FROM users WHERE referred_by = ?').get(id) as { count: number };
    return row.count;
  },

  // Deposit
  createDeposit(userId: number, amount: number, photoFileId: string): Deposit {
    const now = new Date().toISOString();
    const result = db.prepare(`
      INSERT INTO deposits (user_id, amount, photo_file_id, status, created_at, updated_at)
      VALUES (?, ?, ?, 'pending', ?, ?)
    `).run(userId, amount, photoFileId, now, now);
    
    return db.prepare('SELECT * FROM deposits WHERE id = ?').get(result.lastInsertRowid) as Deposit;
  },

  getDeposit(id: number): Deposit | null {
    const row = db.prepare('SELECT * FROM deposits WHERE id = ?').get(id);
    return row ? (row as Deposit) : null;
  },

  updateDepositStatus(id: number, status: 'approved' | 'rejected'): void {
    const now = new Date().toISOString();
    db.prepare('UPDATE deposits SET status = ?, updated_at = ? WHERE id = ?').run(status, now, id);
  },

  // Withdrawal
  createWithdrawal(userId: number, amount: number, cardNumber: string): Withdrawal {
    const now = new Date().toISOString();
    const result = db.prepare(`
      INSERT INTO withdrawals (user_id, amount, card_number, status, created_at, updated_at)
      VALUES (?, ?, ?, 'pending', ?, ?)
    `).run(userId, amount, cardNumber, now, now);
    
    return db.prepare('SELECT * FROM withdrawals WHERE id = ?').get(result.lastInsertRowid) as Withdrawal;
  },

  getWithdrawal(id: number): Withdrawal | null {
    const row = db.prepare('SELECT * FROM withdrawals WHERE id = ?').get(id);
    return row ? (row as Withdrawal) : null;
  },

  updateWithdrawalStatus(id: number, status: 'approved' | 'rejected'): void {
    const now = new Date().toISOString();
    db.prepare('UPDATE withdrawals SET status = ?, updated_at = ? WHERE id = ?').run(status, now, id);
  },

  // Investment
  createInvestment(userId: number, amount: number, durationDays: number, profitPercentage: number = 25.0): Investment {
    const now = new Date();
    const endDate = new Date(now.getTime() + durationDays * 24 * 60 * 60 * 1000);
    
    const result = db.prepare(`
      INSERT INTO investments (user_id, amount, profit_percentage, duration_days, start_date, end_date, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
    `).run(userId, amount, profitPercentage, durationDays, now.toISOString(), endDate.toISOString(), now.toISOString());
    
    return db.prepare('SELECT * FROM investments WHERE id = ?').get(result.lastInsertRowid) as Investment;
  },

  getActiveInvestments(): Investment[] {
    return db.prepare("SELECT * FROM investments WHERE status = 'active'").all() as Investment[];
  },

  getUserInvestments(userId: number): Investment[] {
    return db.prepare('SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC').all(userId) as Investment[];
  },

  completeInvestment(id: number): void {
    db.prepare("UPDATE investments SET status = 'completed' WHERE id = ?").run(id);
  },

  // Settings (Admin card and stats)
  getSetting(key: string, defaultValue: string): string {
    const row = db.prepare('SELECT value FROM settings WHERE key = ?').get(key) as { value: string } | undefined;
    return row ? row.value : defaultValue;
  },

  setSetting(key: string, value: string): void {
    db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run(key, value);
  },

  // Statistics
  getStats(): {
    totalUsers: number;
    totalDeposits: number;
    totalWithdrawals: number;
    activeInvestmentsCount: number;
    activeInvestmentsSum: number;
  } {
    const totalUsers = (db.prepare('SELECT COUNT(*) as count FROM users').get() as { count: number }).count;
    const totalDeposits = (db.prepare("SELECT SUM(amount) as sum FROM deposits WHERE status = 'approved'").get() as { sum: number | null }).sum || 0;
    const totalWithdrawals = (db.prepare("SELECT SUM(amount) as sum FROM withdrawals WHERE status = 'approved'").get() as { sum: number | null }).sum || 0;
    
    const activeInvRow = db.prepare("SELECT COUNT(*) as count, SUM(amount) as sum FROM investments WHERE status = 'active'").get() as { count: number; sum: number | null };
    
    return {
      totalUsers,
      totalDeposits,
      totalWithdrawals,
      activeInvestmentsCount: activeInvRow.count,
      activeInvestmentsSum: activeInvRow.sum || 0,
    };
  },

  getAllUserIds(): number[] {
    const rows = db.prepare('SELECT id FROM users').all() as { id: number }[];
    return rows.map(r => r.id);
  },

  getUserByUsername(username: string): User | null {
    const clean = username.replace('@', '').trim();
    const row = db.prepare('SELECT * FROM users WHERE username = ?').get(clean);
    return row ? (row as User) : null;
  }
};
