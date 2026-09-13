import sqlite3

DB_NAME = "tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            article TEXT NOT NULL,
            target_price REAL,
            last_price REAL,
            UNIQUE(user_id, article)
        )
    """)
    conn.commit()
    conn.close()

def add_tracked(user_id: int, article: str, target_price: float = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO tracked (user_id, article, target_price) VALUES (?, ?, ?)",
        (user_id, article, target_price)
    )
    conn.commit()
    conn.close()

def get_all_tracked():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, article, target_price, last_price FROM tracked")
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_last_price(record_id: int, price: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE tracked SET last_price = ? WHERE id = ?", (price, record_id))
    conn.commit()
    conn.close()
