import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from app.config import settings

def migrate_blocked_users():
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blocked_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blocker_id INTEGER NOT NULL,
        blocked_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (blocker_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (blocked_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_blocked_users_blocker ON blocked_users (blocker_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_blocked_users_blocked ON blocked_users (blocked_id);")

    conn.commit()
    conn.close()
    print("✅ Tabela blocked_users verificada e sincronizada com sucesso!")

if __name__ == "__main__":
    migrate_blocked_users()
