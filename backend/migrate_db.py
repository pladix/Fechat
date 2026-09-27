import asyncio
import aiosqlite
from pathlib import Path

async def migrate():
    db_path = Path(__file__).resolve().parent.parent / "fechat.db"
    if db_path.exists():
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(messages);")
            columns = [row[1] for row in await cursor.fetchall()]

            if "status" not in columns:
                print("Adicionando coluna 'status' na tabela messages...")
                await db.execute("ALTER TABLE messages ADD COLUMN status VARCHAR(20) DEFAULT 'sent';")
            if "read_at" not in columns:
                print("Adicionando coluna 'read_at' na tabela messages...")
                await db.execute("ALTER TABLE messages ADD COLUMN read_at DATETIME;")

            await db.commit()
            print("Migração concluída com sucesso!")

if __name__ == "__main__":
    asyncio.run(migrate())
