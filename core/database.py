import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bot.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                symbol TEXT,
                target_price REAL,
                alert_type TEXT,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                trigger_time TIMESTAMP,
                message TEXT
            )
        ''')
        conn.commit()

def add_alert(symbol: str, target_price: float, alert_type: str = "CROSS", comment: str = "", chat_id: int = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alerts (chat_id, symbol, target_price, alert_type, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, symbol, target_price, alert_type, comment))
        conn.commit()

def get_all_alerts(chat_id: int = None):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if chat_id:
            cursor.execute('SELECT * FROM alerts WHERE chat_id = ? ORDER BY id ASC', (chat_id,))
        else:
            cursor.execute('SELECT * FROM alerts ORDER BY id ASC')
        return cursor.fetchall()

def delete_alert(alert_id: int, chat_id: int = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if chat_id:
            cursor.execute('DELETE FROM alerts WHERE id = ? AND chat_id = ?', (alert_id, chat_id))
        else:
            cursor.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
        conn.commit()

def clear_all_alerts(chat_id: int = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        if chat_id:
            cursor.execute('DELETE FROM alerts WHERE chat_id = ?', (chat_id,))
        else:
            cursor.execute('DELETE FROM alerts')
        conn.commit()

def add_timer(chat_id: int, trigger_time: datetime, message: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO timers (chat_id, trigger_time, message) VALUES (?, ?, ?)',
                       (chat_id, trigger_time.isoformat(), message))
        conn.commit()

def get_pending_timers():
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM timers')
        return cursor.fetchall()

def delete_timer(timer_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM timers WHERE id = ?', (timer_id,))
        conn.commit()
