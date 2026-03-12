# database.py
# Handles all persistent storage using SQLite.
# aiosqlite is async — it won't block the bot while reading/writing.

import aiosqlite

DB_PATH = "debate_bot.db"


async def init_db():
    """Create tables if they don't exist. Called once on bot startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT    DEFAULT '',
                elo       INTEGER DEFAULT 1000,
                debates   INTEGER DEFAULT 0,
                wins      INTEGER DEFAULT 0,
                losses    INTEGER DEFAULT 0,
                ties      INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def get_or_create_user(user_id: int, username: str = "") -> dict:
    """Fetch a user row, creating it with default Elo 1000 if new."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, username, elo, debates, wins, losses, ties "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username),
            )
            await db.commit()
            return {
                "user_id": user_id, "username": username,
                "elo": 1000, "debates": 0, "wins": 0, "losses": 0, "ties": 0,
            }
        return {
            "user_id": row[0], "username": row[1], "elo": row[2],
            "debates": row[3], "wins": row[4], "losses": row[5], "ties": row[6],
        }


async def update_after_debate(user_id: int, new_elo: int, result: str):
    """
    Update Elo and record count after a debate.
    result must be 'win', 'loss', or 'tie'.
    """
    col = {"win": "wins", "loss": "losses", "tie": "ties"}[result]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET elo = ?, debates = debates + 1, "
            f"{col} = {col} + 1 WHERE user_id = ?",
            (new_elo, user_id),
        )
        await db.commit()


async def get_leaderboard(limit: int = 10) -> list[tuple]:
    """Return top users sorted by Elo descending."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username, elo, wins, losses, ties, debates "
            "FROM users ORDER BY elo DESC LIMIT ?",
            (limit,),
        )
        return await cursor.fetchall()


async def get_user_rank(user_id: int) -> int:
    """Return the rank (position) of a user on the leaderboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE elo > "
            "(SELECT elo FROM users WHERE user_id = ?)",
            (user_id,),
        )
        row = await cursor.fetchone()
        return (row[0] + 1) if row else 0