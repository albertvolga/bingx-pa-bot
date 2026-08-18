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
            target_price REAL, -- Может быть NULL для алертов по паттернам
            condition TEXT,    -- 'cross_above', 'cross_below', 'cross'
            alert_type TEXT DEFAULT 'PRICE', -- 'PRICE', 'PATTERN', 'TIMER'
            is_recurring BOOLEAN DEFAULT 0, -- 0 - одноразовый, 1 - многоразовый
            triggered_count INTEGER DEFAULT 0, -- Счетчик срабатываний для многоразовых
            note TEXT DEFAULT 'Алерт',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Проверка и добавление новых колонок (для обновления существующих БД)
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [col["name"] for col in cursor.fetchall()]
    
    if "note" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN note TEXT DEFAULT 'Алерт'")
    if "condition" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN condition TEXT")
    if "alert_type" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN alert_type TEXT DEFAULT 'PRICE'")
    if "is_recurring" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN is_recurring BOOLEAN DEFAULT 0")
    if "triggered_count" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN triggered_count INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

def add_alert(
    chat_id: int, 
    symbol: str, 
    target_price: float = None, 
    note: str = "Алерт", 
    condition: str = None, # 'cross_above', 'cross_below', 'cross'
    alert_type: str = "PRICE", # 'PRICE', 'PATTERN', 'TIMER'
    is_recurring: bool = False
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alerts (chat_id, symbol, target_price, note, condition, alert_type, is_recurring) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (chat_id, symbol.upper(), target_price, note, condition, alert_type, int(is_recurring))
    )
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id

def get_all_alerts(chat_id: int = None):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row # Убедимся, что возвращаются dict-like объекты
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

def clear_all_alerts(chat_id: int): # Убрал chat_id=None, так как для пользователя всегда есть chat_id
    """Удаление всех алертов для конкретного чата."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def update_alert_triggered_status(alert_id: int, increment_count: bool = True):
    """Обновляет статус алерта после срабатывания (увеличивает счетчик, если многоразовый)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if increment_count:
        cursor.execute("UPDATE alerts SET triggered_count = triggered_count + 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def set_alert_recurring(alert_id: int, is_recurring: bool):
    """Устанавливает алерт как многоразовый."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE alerts SET is_recurring = ? WHERE id = ?", (int(is_recurring), alert_id))
    conn.commit()
    conn.close()

# Инициализируем БД при импорте
# init_db() # Убираем, так как init_db() будет вызываться в main.py

def get_connection(): # Добавлена вспомогательная функция для main.py check_price_alerts
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
