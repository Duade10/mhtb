import asyncio
import aiosqlite

DB_PATH = 'sessions.db'


async def create_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_sessions (
                chat_id INTEGER,
                message_id INTEGER,
                resume_url TEXT,
                awaiting_custom INTEGER,
                timestamp REAL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        await db.commit()


async def save_session(chat_id: int, message_id: int, resume_url: str, timestamp: float, awaiting_custom: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO pending_sessions
            (chat_id, message_id, resume_url, awaiting_custom, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, message_id, resume_url, int(awaiting_custom), timestamp),
        )
        await db.commit()


async def get_session(chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT resume_url, awaiting_custom FROM pending_sessions WHERE chat_id=? AND message_id=?",
            (chat_id, message_id),
        )
        row = await cursor.fetchone()
    if row:
        return {"resume_url": row[0], "awaiting_custom": bool(row[1])}
    return None


async def get_pending_custom(chat_id: int):
    """Return the most recent pending custom session for a chat."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT message_id, resume_url
            FROM pending_sessions
            WHERE chat_id=? AND awaiting_custom=1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (chat_id,),
        )
        row = await cursor.fetchone()
    if row:
        return {"message_id": row[0], "resume_url": row[1]}
    return None


async def update_session_state(chat_id: int, message_id: int, *, awaiting_custom: bool | None = None, timestamp: float | None = None):
    fields = []
    values: list = []
    if awaiting_custom is not None:
        fields.append("awaiting_custom=?")
        values.append(int(awaiting_custom))
    if timestamp is not None:
        fields.append("timestamp=?")
        values.append(timestamp)
    if not fields:
        return
    values.extend([chat_id, message_id])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE pending_sessions SET {', '.join(fields)} WHERE chat_id=? AND message_id=?",
            values,
        )
        await db.commit()


async def delete_session(chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_sessions WHERE chat_id=? AND message_id=?",
            (chat_id, message_id),
        )
        await db.commit()


async def purge_expired(expiry_seconds: int = 300):
    cutoff = asyncio.get_running_loop().time() - expiry_seconds
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT chat_id, message_id, resume_url FROM pending_sessions WHERE timestamp < ?",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        await db.execute("DELETE FROM pending_sessions WHERE timestamp < ?", (cutoff,))
        await db.commit()
    return rows
