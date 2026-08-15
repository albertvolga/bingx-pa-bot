import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alerts.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            target_price REAL NOT NULL,
            note TEXT DEFAULT 'Алерт',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [col["name"] for col in cursor.fetchall()]
    if "note" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN note TEXT DEFAULT 'Алерт'")
        conn.commit()

    conn.close()

def add_alert(chat_id: int, symbol: str, target_price: float, note: str = "Алерт") -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (chat_id, symbol, target_price, note) VALUES (?, ?, ?, ?)",
        (chat_id, symbol.upper(), target_price, note)
    )
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id

def get_all_alerts(chat_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("SELECT * FROM alerts WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
    else:
        cursor.execute("SELECT * FROM alerts ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_alert(alert_id: int, chat_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("DELETE FROM alerts WHERE id = ? AND chat_id = ?", (alert_id, chat_id))
    else:
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def clear_all_alerts(chat_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("DELETE FROM alerts WHERE chat_id = ?", (chat_id,))
    else:
        cursor.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()

def clear_user_alerts(chat_id: int):
    clear_all_alerts(chat_id)

init_db()
