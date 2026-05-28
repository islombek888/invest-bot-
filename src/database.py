import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import threading
from datetime import datetime, timedelta
from src.config import config

class DatabaseService:
    def __init__(self):
        self.db_path = config.DB_PATH
        self.lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.executescript("""
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
            """)
            conn.commit()
            conn.close()

    # User helper methods
    def get_user(self, user_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def create_user(self, id, username, first_name, referred_by=None):
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (id, username, first_name, balance, referred_by, created_at)
                VALUES (?, ?, ?, COALESCE((SELECT balance FROM users WHERE id = ?), 0.0), ?, COALESCE((SELECT created_at FROM users WHERE id = ?), ?))
            """, (id, username, first_name, id, referred_by, id, now))
            conn.commit()
            conn.close()
        return self.get_user(id)

    def update_balance(self, user_id, amount):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))
            conn.commit()
            conn.close()

    def set_balance(self, user_id, amount):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET balance = ? WHERE id = ?', (amount, user_id))
            conn.commit()
            conn.close()

    def get_referral_count(self, user_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE referred_by = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
        return row['count'] if row else 0

    # Deposit helper methods
    def create_deposit(self, user_id, amount, photo_file_id):
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO deposits (user_id, amount, photo_file_id, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
            """, (user_id, amount, photo_file_id, now, now))
            deposit_id = cursor.lastrowid
            conn.commit()
            cursor.execute('SELECT * FROM deposits WHERE id = ?', (deposit_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def get_deposit(self, deposit_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM deposits WHERE id = ?', (deposit_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def update_deposit_status(self, deposit_id, status):
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE deposits SET status = ?, updated_at = ? WHERE id = ?', (status, now, deposit_id))
            conn.commit()
            conn.close()

    # Withdrawal helper methods
    def create_withdrawal(self, user_id, amount, card_number):
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO withdrawals (user_id, amount, card_number, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
            """, (user_id, amount, card_number, now, now))
            withdrawal_id = cursor.lastrowid
            conn.commit()
            cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def get_withdrawal(self, withdrawal_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def update_withdrawal_status(self, withdrawal_id, status):
        now = datetime.now().isoformat()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE withdrawals SET status = ?, updated_at = ? WHERE id = ?', (status, now, withdrawal_id))
            conn.commit()
            conn.close()

    # Investment helper methods
    def create_investment(self, user_id, amount, duration_days, profit_percentage=25.0):
        now = datetime.now()
        end_date = now + timedelta(days=duration_days)
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO investments (user_id, amount, profit_percentage, duration_days, start_date, end_date, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
            """, (user_id, amount, profit_percentage, duration_days, now.isoformat(), end_date.isoformat(), now.isoformat()))
            investment_id = cursor.lastrowid
            conn.commit()
            cursor.execute('SELECT * FROM investments WHERE id = ?', (investment_id,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

    def get_active_investments(self):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM investments WHERE status = 'active'")
            rows = cursor.fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def get_user_investments(self, user_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
            rows = cursor.fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def complete_investment(self, investment_id):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE investments SET status = 'completed' WHERE id = ?", (investment_id,))
            conn.commit()
            conn.close()

    # Settings
    def get_setting(self, key, default_value):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            conn.close()
        return row['value'] if row else default_value

    def set_setting(self, key, value):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
            conn.commit()
            conn.close()

    # Statistics helper method
    def get_stats(self):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as count FROM users')
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT SUM(amount) as sum FROM deposits WHERE status = 'approved'")
            total_deposits = cursor.fetchone()['sum'] or 0
            
            cursor.execute("SELECT SUM(amount) as sum FROM withdrawals WHERE status = 'approved'")
            total_withdrawals = cursor.fetchone()['sum'] or 0
            
            cursor.execute("SELECT COUNT(*) as count, SUM(amount) as sum FROM investments WHERE status = 'active'")
            active_inv_row = cursor.fetchone()
            active_investments_count = active_inv_row['count']
            active_investments_sum = active_inv_row['sum'] or 0
            
            conn.close()
            
        return {
            'totalUsers': total_users,
            'totalDeposits': total_deposits,
            'totalWithdrawals': total_withdrawals,
            'activeInvestmentsCount': active_investments_count,
            'activeInvestmentsSum': active_investments_sum
        }

    def get_all_user_ids(self):
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users')
            rows = cursor.fetchall()
            conn.close()
        return [r['id'] for r in rows]

    def get_user_by_username(self, username):
        clean = username.replace('@', '').strip()
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (clean,))
            row = cursor.fetchone()
            conn.close()
        return dict(row) if row else None

db_service = DatabaseService()
