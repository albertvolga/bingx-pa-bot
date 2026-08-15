import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alerts.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Создаем таблицу, если ее не существует
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            tf TEXT NOT NULL DEFAULT '1h',
            pattern TEXT NOT NULL,
            is_repeating INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Проверяем и добавляем отсутствующие колонки для старых баз
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'tf' not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN tf TEXT NOT NULL DEFAULT '1h'")
    if 'is_repeating' not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN is_repeating INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

def add_alert(chat_id: int, symbol: str, tf: str, pattern: str, is_repeating: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (chat_id, symbol, tf, pattern, is_repeating)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, symbol.upper(), tf.lower(), pattern.upper(), 1 if is_repeating else 0))
    conn.commit()
    conn.close()

def get_all_alerts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, chat_id, symbol, tf, pattern, is_repeating FROM alerts")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_alerts(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, tf, pattern, is_repeating FROM alerts WHERE chat_id = ?", (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_alert(alert_id: int, chat_id: int = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("DELETE FROM alerts WHERE id = ? AND chat_id = ?", (alert_id, chat_id))
    else:
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def clear_all_alerts(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

init_db()
